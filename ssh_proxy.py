"""
SSH OTP Proxy
使用 asyncssh process_factory API 建立本地代理，讓後續連線免密碼/免 OTP。
"""
import asyncio
import getpass
import os
import sys
import traceback
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


# ──────────────────────────────────────────────────
# Step 2: 本地 SSH 伺服器（免驗證）
# ──────────────────────────────────────────────────
class NoAuthServer(asyncssh.SSHServer):
    """接受任何本地連線，無需密碼或金鑰"""

    def begin_auth(self, username):
        # 回傳 False = 直接允許，跳過所有驗證
        return False

    def password_auth_supported(self):
        return False

    def public_key_auth_supported(self):
        return False


# ──────────────────────────────────────────────────
# Step 3: 每個 session 的處理函式
# ──────────────────────────────────────────────────
async def copy_stream(src, dst, label=""):
    """把 src 的資料逐筆複製到 dst"""
    try:
        while True:
            data = await src.read(65536)
            if not data:
                break
            dst.write(data)
    except asyncssh.BreakReceived:
        pass
    except Exception as e:
        sys.stderr.write(f"[copy {label}] {type(e).__name__}: {e}\n")
    finally:
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
            f"[dim cyan]→ new session: "
            f"shell={'shell' if not process.command and not process.subsystem else ''}"
            f"{process.command or ''}{process.subsystem or ''}"
            f"  tty={bool(process.term_type)}[/dim cyan]"
        )

        async with remote_conn.create_process(encoding=None, **kwargs) as remote_proc:
            # 雙向橋接
            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(
                        copy_stream(process.stdin, remote_proc.stdin, "local→remote")
                    ),
                    asyncio.create_task(
                        copy_stream(remote_proc.stdout, process.stdout, "remote→local")
                    ),
                ],
                return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            rc = remote_proc.exit_status
            process.exit(rc if rc is not None else 0)

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
async def start_proxy(host: str, remote_port: int, local_port: int):
    remote_host, remote_user = parse_ssh_config(host)

    CONSOLE.print(Panel(
        f"Connecting to [bold cyan]{remote_user}@{remote_host}:{remote_port}[/bold cyan]...\n"
        "Please complete the 2FA challenge when prompted below.",
        title="SSH OTP Proxy",
        border_style="cyan"
    ))

    # 連到遠端（需要 2FA）
    try:
        remote_conn = await asyncssh.connect(
            remote_host,
            port=remote_port,
            username=remote_user,
            client_factory=OTPSSHClient,
            known_hosts=None,
            config=None,
            preferred_auth=['keyboard-interactive'],
            client_keys=[],
        )
    except Exception as e:
        CONSOLE.print(f"[bold red]❌ Connection Error: {e}[/bold red]")
        return

    CONSOLE.print("[bold green]✔ Successfully connected to remote host![/bold green]")

    # 本地 SSH 伺服器 host key
    server_key = asyncssh.generate_private_key('ssh-ed25519')

    # 用 closure 綁定 remote_conn 到 process handler
    async def session_handler(process: asyncssh.SSHServerProcess):
        await handle_session(remote_conn, process)

    server = await asyncssh.create_server(
        NoAuthServer,
        '127.0.0.1', local_port,
        server_host_keys=[server_key],
        process_factory=session_handler,
        encoding=None,
    )

    txt = Text()
    txt.append("✔ Local proxy is running!\n\n", style="bold green")
    txt.append("Connect without password or OTP:\n", style="white")
    txt.append(
        f"  ssh -o StrictHostKeyChecking=no"
        f" -o UserKnownHostsFile=/dev/null -p {local_port} localhost\n\n",
        style="bold yellow"
    )
    txt.append("Or use the alias (already added to your config):\n", style="white")
    txt.append("  ssh nano4-proxy\n\n", style="bold yellow")
    txt.append("Press Ctrl+C to stop the proxy.", style="dim")
    CONSOLE.print(Panel(txt, title="Proxy Server Status", border_style="green"))

    try:
        while True:
            await asyncio.sleep(5)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        server.close()
        await server.wait_closed()
        remote_conn.close()
        CONSOLE.print("[yellow]Proxy stopped.[/yellow]")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SSH OTP Local Proxy")
    parser.add_argument("host", nargs="?", default="nano4",
                        help="SSH Host alias or hostname")
    parser.add_argument("-p", "--port", type=int, default=22,
                        help="Remote SSH port (default: 22)")
    parser.add_argument("-l", "--local-port", type=int, default=2222,
                        help="Local proxy port (default: 2222)")
    args = parser.parse_args()

    try:
        asyncio.run(start_proxy(args.host, args.port, args.local_port))
    except KeyboardInterrupt:
        pass
