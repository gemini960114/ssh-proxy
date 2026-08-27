"""
SSH OTP Proxy
使用 asyncssh process_factory API 建立本地代理，讓後續連線免密碼/免 OTP。
"""
import asyncio
import getpass
import os
import sys
import time
import traceback
from pathlib import Path

import asyncssh
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

CONSOLE = Console()


# ──────────────────────────────────────────────────
# Step 1: 互動式 2FA 客戶端（連到 NCHC 時使用）
# ──────────────────────────────────────────────────
class OTPSSHClient(asyncssh.SSHClient):
    def kbdint_auth_requested(self):
        return ''

    def kbdint_challenge_received(self, name, instructions, lang, prompts):
        responses = []
        if name:
            print(f"\n{name}")
        if instructions:
            print(instructions)
        for prompt, echo in prompts:
            if echo:
                responses.append(input(prompt.strip() + " "))
            else:
                responses.append(getpass.getpass(prompt.strip() + " "))
        return responses


class HostKeyVerificationError(Exception):
    """遠端 SSH host key 無法安全驗證。"""


def ensure_known_hosts_file(path: Path) -> None:
    """建立 OpenSSH known_hosts 檔案（若尚不存在）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)

    # POSIX 上限制為目前使用者可讀寫。Windows 權限仍由使用者目錄 ACL 管理。
    if os.name != 'nt':
        path.chmod(0o600)


def known_host_pattern(host: str, port: int) -> str:
    """回傳 OpenSSH known_hosts 使用的 host pattern。"""
    return host if port == 22 else f'[{host}]:{port}'


def append_known_host(path: Path, host: str, port: int,
                      key: asyncssh.SSHKey) -> None:
    """將使用者確認過的 host key 寫入 known_hosts。"""
    entry = (
        f'{known_host_pattern(host, port)} '
        f'{key.export_public_key().decode("ascii").strip()}\n'
    ).encode('ascii')

    needs_newline = False
    if path.stat().st_size:
        with path.open('rb') as existing:
            existing.seek(-1, os.SEEK_END)
            needs_newline = existing.read(1) not in {b'\n', b'\r'}

    with path.open('ab') as known_hosts:
        if needs_newline:
            known_hosts.write(b'\n')
        known_hosts.write(entry)
        known_hosts.flush()
        os.fsync(known_hosts.fileno())


def matching_known_host_keys(path: Path, host: str, port: int):
    """取得 known_hosts 中已記錄於指定 hostname 的 host identities。"""
    known_hosts = asyncssh.read_known_hosts(str(path))
    # 第二個參數必須是實際 IP 或空字串，不能重複傳入 DNS hostname。
    # 正式連線仍由 AsyncSSH 同時依實際解析到的位址執行完整驗證。
    return known_hosts.match(host, '', port)


def format_fingerprints(keys) -> str:
    """格式化一組 SSH keys 的 SHA-256 fingerprints。"""
    return '\n'.join(
        f'  {key.get_algorithm()}: {key.get_fingerprint()}'
        for key in keys
    )


async def connect_remote(remote_host: str, remote_port: int, remote_user: str,
                         known_hosts_path: Path):
    """嚴格驗證遠端 host key，未知主機則在登入前執行 TOFU 確認。"""
    ensure_known_hosts_file(known_hosts_path)

    connect_options = {
        'port': remote_port,
        'username': remote_user,
        'client_factory': OTPSSHClient,
        'known_hosts': str(known_hosts_path),
        'config': None,
        'preferred_auth': ['keyboard-interactive'],
        'client_keys': [],
        # Keep the OTP-authenticated upstream session active even when no
        # application data is flowing. This is configured here because
        # config=None intentionally prevents AsyncSSH from reading
        # ServerAliveInterval/ServerAliveCountMax from ~/.ssh/config.
        'keepalive_interval': 30,
        'keepalive_count_max': 3,
    }

    try:
        return await asyncssh.connect(remote_host, **connect_options)
    except asyncssh.HostKeyNotVerifiable as original_error:
        # 只執行 SSH key exchange，不進行使用者驗證，也不會送出密碼或 OTP。
        presented_key = await asyncssh.get_server_host_key(
            remote_host,
            port=remote_port,
            config=None,
        )

        if presented_key is None:
            raise HostKeyVerificationError(
                'Remote server did not present a verifiable SSH host key.'
            ) from original_error

        matches = matching_known_host_keys(
            known_hosts_path, remote_host, remote_port
        )
        recorded_identities = [
            key
            for group in matches[:5]
            for key in group
            if hasattr(key, 'get_fingerprint')
        ]

        if recorded_identities:
            recorded = format_fingerprints(recorded_identities)
            raise HostKeyVerificationError(
                f'REMOTE HOST IDENTIFICATION HAS CHANGED for '
                f'{remote_host}:{remote_port}.\n'
                f'Received: {presented_key.get_algorithm()}: '
                f'{presented_key.get_fingerprint()}\n'
                f'Recorded identities:\n{recorded}\n'
                f'Check with the server administrator before editing '
                f'{known_hosts_path}.'
            ) from original_error

        CONSOLE.print(Panel(
            f"[bold yellow]First connection to "
            f"{remote_host}:{remote_port}[/bold yellow]\n\n"
            f"Host key algorithm: [cyan]"
            f"{presented_key.get_algorithm()}[/cyan]\n"
            f"SHA-256 fingerprint: [bold cyan]"
            f"{presented_key.get_fingerprint()}[/bold cyan]\n\n"
            "Verify this fingerprint through a trusted source, such as the "
            "server administrator, before accepting it.",
            title="Unknown SSH Host",
            border_style="yellow",
        ))

        try:
            answer = input(
                f"Trust this host key and save it to {known_hosts_path}? "
                "Type yes to continue: "
            )
        except EOFError as exc:
            raise HostKeyVerificationError(
                'Cannot confirm an unknown host key without interactive input.'
            ) from exc

        if answer.strip().lower() != 'yes':
            raise HostKeyVerificationError(
                'Host key was not accepted. No credentials were sent.'
            )

        append_known_host(
            known_hosts_path, remote_host, remote_port, presented_key
        )
        CONSOLE.print(
            f"[green][OK] Saved the verified host key to "
            f"{known_hosts_path}[/green]"
        )

        # 重新連線並透過剛保存的 key 做正式驗證，避免確認與登入間被替換。
        return await asyncssh.connect(remote_host, **connect_options)


class ProxyActivity:
    """追蹤本機 SSH clients，供 idle timeout 判斷使用。"""

    def __init__(self):
        self.active_clients = 0
        self.idle_since = time.monotonic()

    def client_connected(self):
        self.active_clients += 1

    def client_disconnected(self):
        self.active_clients = max(0, self.active_clients - 1)
        if self.active_clients == 0:
            self.idle_since = time.monotonic()

    def idle_seconds(self) -> float:
        if self.active_clients:
            return 0
        return time.monotonic() - self.idle_since


# ──────────────────────────────────────────────────
# Step 2: 本地 SSH 伺服器（免驗證）
# ──────────────────────────────────────────────────
class NoAuthServer(asyncssh.SSHServer):
    """接受任何本地連線，無需密碼或金鑰"""

    def __init__(self, remote_conn: asyncssh.SSHClientConnection,
                 activity: ProxyActivity):
        self._remote_conn = remote_conn
        self._activity = activity
        self._peer = 'unknown'

    def connection_made(self, conn: asyncssh.SSHServerConnection):
        peer = conn.get_extra_info('peername')
        if peer:
            self._peer = f'{peer[0]}:{peer[1]}'
        self._activity.client_connected()
        CONSOLE.print(
            f"[dim cyan]-> local client connected: {self._peer}[/dim cyan]"
        )

    def connection_lost(self, exc):
        self._activity.client_disconnected()
        if exc:
            CONSOLE.print(
                f"[yellow]-> local client disconnected: {self._peer} "
                f"({exc})[/yellow]"
            )
        else:
            CONSOLE.print(
                f"[dim cyan]-> local client disconnected: "
                f"{self._peer}[/dim cyan]"
            )

    def begin_auth(self, username):
        # 回傳 False = 直接允許，跳過所有驗證
        return False

    def password_auth_supported(self):
        return False

    def public_key_auth_supported(self):
        return False

    def connection_requested(self, dest_host, dest_port, orig_host, orig_port):
        """把 -L/-D direct-tcpip forwarding 轉送到已驗證的遠端 SSH 連線"""
        CONSOLE.print(
            f"[dim cyan]-> tcp forward: "
            f"client={self._peer}  "
            f"{orig_host}:{orig_port} -> {dest_host}:{dest_port}[/dim cyan]"
        )
        return self._remote_conn


# ──────────────────────────────────────────────────
# Step 3: 每個 session 的處理函式
# ──────────────────────────────────────────────────
async def copy_stream(src, dst, label="", write_eof=True):
    """把 src 的資料逐筆複製到 dst"""
    try:
        while True:
            data = await src.read(65536)
            if not data:
                break
            dst.write(data)
            drain = getattr(dst, "drain", None)
            if drain:
                await drain()
    except asyncssh.BreakReceived:
        pass
    except (BrokenPipeError, asyncssh.ChannelOpenError):
        # The opposite side may legitimately close first, for example when a
        # remote command exits before consuming all client stdin.
        pass
    except Exception as e:
        sys.stderr.write(f"[copy {label}] {type(e).__name__}: {e}\n")
    finally:
        if write_eof:
            try:
                dst.write_eof()
            except Exception:
                pass


async def handle_session(remote_conn: asyncssh.SSHClientConnection,
                          process: asyncssh.SSHServerProcess):
    """
    process_factory 呼叫的 async handler。
    在 remote_conn 上開一個遠端 process，雙向橋接 stdin/stdout。
    """
    try:
        kwargs: dict = {}

        # PTY / Terminal
        if process.term_type:
            kwargs['term_type'] = process.term_type
            ts = process.term_size
            if ts:
                kwargs['term_size'] = (ts[0], ts[1])  # width, height

        # exec / subsystem / interactive shell
        if process.subsystem:
            kwargs['subsystem'] = process.subsystem
        elif process.command:
            kwargs['command'] = process.command
        # else: interactive shell（不需傳 command）

        CONSOLE.print(
            f"[dim cyan]-> new session: "
            f"shell={'shell' if not process.command and not process.subsystem else ''}"
            f"{process.command or ''}{process.subsystem or ''}"
            f"  tty={bool(process.term_type)}[/dim cyan]"
        )

        async with remote_conn.create_process(encoding=None, **kwargs) as remote_proc:
            stdin_task = asyncio.create_task(
                copy_stream(process.stdin, remote_proc.stdin, "local->remote stdin")
            )
            stdout_task = asyncio.create_task(
                copy_stream(
                    remote_proc.stdout, process.stdout,
                    "remote->local stdout", write_eof=False
                )
            )
            stderr_task = asyncio.create_task(
                copy_stream(
                    remote_proc.stderr, process.stderr,
                    "remote->local stderr", write_eof=False
                )
            )

            await remote_proc.wait()

            # stdout/stderr should naturally hit EOF after the remote process exits.
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)

            # If the remote command exited before consuming all stdin, stop the
            # Stop local-to-remote copying after the remote lifecycle completes.
            if not stdin_task.done():
                stdin_task.cancel()
            await asyncio.gather(stdin_task, return_exceptions=True)

            process.exit(remote_proc.exit_status or 0)

    except Exception as e:
        sys.stderr.write(f"[PROXY ERROR] {type(e).__name__}: {e}\n")
        traceback.print_exc(file=sys.stderr)
        try:
            process.stderr.write(f"Proxy error: {e}\n")
            process.exit(1)
        except Exception:
            pass


# ──────────────────────────────────────────────────
# Step 4: 解析 ~/.ssh/config
# ──────────────────────────────────────────────────
def parse_ssh_config(alias: str) -> tuple[str, str]:
    """從 ~/.ssh/config 取得 HostName 與 User"""
    hostname = alias
    user = getpass.getuser()

    config_path = os.path.expanduser("~/.ssh/config")
    if not os.path.exists(config_path):
        return hostname, user

    try:
        with open(config_path, 'r', encoding='utf-8', errors='ignore') as f:
            in_block = False
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if line.lower().startswith('host '):
                    tokens = line.split()
                    in_block = alias in tokens[1:]
                elif in_block:
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        k = parts[0].lower()
                        v = parts[1].strip().strip('"\'')
                        if k == 'hostname':
                            hostname = v
                        elif k == 'user':
                            user = v
    except Exception:
        pass

    return hostname, user


# ──────────────────────────────────────────────────
# Step 5: 主流程
# ──────────────────────────────────────────────────
async def wait_for_shutdown(remote_conn: asyncssh.SSHClientConnection,
                            activity: ProxyActivity, max_lifetime: int,
                            idle_timeout: int) -> str:
    """等待遠端斷線、最大存活時間或無本機 client 的 idle timeout。"""
    started_at = time.monotonic()
    remote_closed = asyncio.create_task(remote_conn.wait_closed())

    try:
        while True:
            if remote_closed.done():
                return 'Remote SSH connection closed.'

            now = time.monotonic()
            if max_lifetime and now - started_at >= max_lifetime:
                return f'Maximum lifetime reached ({format_duration(max_lifetime)}).'

            if idle_timeout and activity.active_clients == 0 and \
                    activity.idle_seconds() >= idle_timeout:
                return (
                    'Idle timeout reached with no local SSH clients '
                    f'({format_duration(idle_timeout)}).'
                )

            deadlines = [5.0]
            if max_lifetime:
                deadlines.append(max_lifetime - (now - started_at))
            if idle_timeout and activity.active_clients == 0:
                deadlines.append(idle_timeout - activity.idle_seconds())

            await asyncio.wait(
                {remote_closed},
                timeout=max(0.1, min(deadlines)),
            )
    finally:
        if not remote_closed.done():
            remote_closed.cancel()
            await asyncio.gather(remote_closed, return_exceptions=True)


def parse_duration(value: str) -> int:
    """解析 30s、15m、8h、1d；0 表示停用。"""
    normalized = value.strip().lower()
    if normalized in {'0', 'off', 'none'}:
        return 0

    units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
    if len(normalized) < 2 or normalized[-1] not in units:
        raise ValueError('Use a duration such as 30s, 60m, 8h, 1d, or 0.')

    try:
        amount = int(normalized[:-1])
    except ValueError as exc:
        raise ValueError(
            'Use a duration such as 30s, 60m, 8h, 1d, or 0.'
        ) from exc

    if amount < 0:
        raise ValueError('Duration cannot be negative.')

    return amount * units[normalized[-1]]


def argparse_duration(value: str) -> int:
    """argparse-compatible duration parser。"""
    import argparse

    try:
        return parse_duration(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def format_duration(seconds: int) -> str:
    """將秒數格式化為適合 CLI 顯示的時間。"""
    if seconds == 0:
        return 'disabled'

    for unit, size in (('d', 86400), ('h', 3600), ('m', 60)):
        if seconds % size == 0:
            return f'{seconds // size}{unit}'

    return f'{seconds}s'


async def start_proxy(host: str, remote_port: int, local_port: int,
                      known_hosts_path: Path, max_lifetime: int,
                      idle_timeout: int):
    remote_host, remote_user = parse_ssh_config(host)

    CONSOLE.print(Panel(
        f"Connecting to [bold cyan]{remote_user}@{remote_host}:{remote_port}[/bold cyan]...\n"
        "Please complete the 2FA challenge when prompted below.",
        title="SSH OTP Proxy",
        border_style="cyan"
    ))

    # 連到遠端（需要 2FA）
    try:
        remote_conn = await connect_remote(
            remote_host,
            remote_port,
            remote_user,
            known_hosts_path,
        )
    except HostKeyVerificationError as e:
        CONSOLE.print(
            f"[bold red][ERROR] Host Key Verification Failed[/bold red]\n{e}"
        )
        return
    except Exception as e:
        CONSOLE.print(f"[bold red][ERROR] Connection Error: {e}[/bold red]")
        return

    CONSOLE.print(
        "[bold green][OK] Successfully connected to remote host![/bold green]"
    )

    # 本地 SSH 伺服器 host key
    server_key = asyncssh.generate_private_key('ssh-ed25519')
    activity = ProxyActivity()

    # 用 closure 綁定 remote_conn 到 process handler
    async def session_handler(process: asyncssh.SSHServerProcess):
        await handle_session(remote_conn, process)

    server = await asyncssh.create_server(
        lambda: NoAuthServer(remote_conn, activity),
        '127.0.0.1', local_port,
        server_host_keys=[server_key],
        process_factory=session_handler,
        encoding=None,
    )

    txt = Text()
    txt.append("[OK] Local proxy is running!\n\n", style="bold green")
    txt.append("Connect without password or OTP:\n", style="white")
    txt.append(
        f"  ssh -o StrictHostKeyChecking=no"
        f" -o UserKnownHostsFile=/dev/null"
        f" -p {local_port} 127.0.0.1\n\n",
        style="bold yellow"
    )
    txt.append(
        f"Remote known_hosts: {known_hosts_path}\n"
        f"Maximum lifetime: {format_duration(max_lifetime)}\n"
        f"Idle timeout: {format_duration(idle_timeout)} "
        "(only while no local SSH clients are connected)\n\n",
        style="dim",
    )
    txt.append("Or use the alias (already added to your config):\n", style="white")
    txt.append("  ssh nano4-proxy\n\n", style="bold yellow")
    txt.append("Press Ctrl+C to stop the proxy.", style="dim")
    CONSOLE.print(Panel(txt, title="Proxy Server Status", border_style="green"))

    try:
        shutdown_reason = await wait_for_shutdown(
            remote_conn,
            activity,
            max_lifetime,
            idle_timeout,
        )
        CONSOLE.print(f"[yellow]{shutdown_reason} Stopping proxy.[/yellow]")
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        server.close()
        await server.wait_closed()
        remote_conn.close()
        await remote_conn.wait_closed()
        CONSOLE.print("[yellow]Proxy stopped.[/yellow]")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="SSH OTP Local Proxy")
    parser.add_argument("host", nargs="?", default="nano4",
                        help="SSH Host alias or hostname")
    parser.add_argument("-p", "--port", type=int, default=22,
                        help="Remote SSH port (default: 22)")
    parser.add_argument("-l", "--local-port", type=int, default=2222,
                        help="Local proxy port (default: 2222)")
    parser.add_argument(
        "--known-hosts",
        type=Path,
        default=Path("~/.ssh/known_hosts").expanduser(),
        help="Remote host key database (default: ~/.ssh/known_hosts)",
    )
    parser.add_argument(
        "--max-lifetime",
        type=argparse_duration,
        default=parse_duration("8h"),
        metavar="DURATION",
        help="Stop after this time, e.g. 8h; 0 disables (default: 8h)",
    )
    parser.add_argument(
        "--idle-timeout",
        type=argparse_duration,
        default=parse_duration("60m"),
        metavar="DURATION",
        help=(
            "Stop after this time with no local SSH clients, e.g. 60m; "
            "0 disables (default: 60m)"
        ),
    )
    args = parser.parse_args()

    try:
        asyncio.run(start_proxy(
            args.host,
            args.port,
            args.local_port,
            args.known_hosts.expanduser(),
            args.max_lifetime,
            args.idle_timeout,
        ))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
