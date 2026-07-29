# ssh-proxy

A lightweight SSH OTP local proxy written in Python with AsyncSSH and Rich.

Authenticate with OTP/2FA once, then connect as many times as you want without repeated prompts. It supports terminals, Antigravity / VS Code Remote-SSH, Git, SFTP, and SSH port forwarding.

## Quick Start

```powershell
# Step 1: Start the proxy. Enter OTP only once.
uv run ssh_proxy.py nano4          # nano4, local port 2222
uv run ssh_proxy.py nano5 -l 2223  # nano5, local port 2223

# Step 2: Connect freely. No OTP needed.
ssh -p 2222 127.0.0.1   # forwards to nano4.nchc.org.tw
ssh -p 2223 127.0.0.1   # forwards to nano5.nchc.org.tw

# Or use aliases from ssh_config.example.
ssh nano4-proxy
```

Keep the proxy terminal open. Press `Ctrl+C` to stop it.

## How It Works

```text
Your SSH client (terminal / Antigravity / VS Code)
          |
          | no OTP needed
          v
    127.0.0.1:2222   <- ssh-proxy
          |
          | OTP-authenticated SSH connection kept alive
          v
    nano4.nchc.org.tw:22
```

1. `ssh_proxy.py` connects to the remote host using keyboard-interactive auth for OTP/2FA.
2. Before any password or OTP is sent, the remote SSH host key is verified against `~/.ssh/known_hosts`.
3. After authentication succeeds, it starts a local SSH server on `127.0.0.1:2222` or the port you choose with `-l`.
4. Local SSH sessions are bridged through the authenticated remote connection.
5. Shell/exec stdin, stdout, stderr, and TCP forwarding (`-L`, `-D`, `ProxyJump`) are tunneled through the remote connection. TCP forwarding is required by Antigravity and VS Code Remote-SSH.

## Security Model

### Remote host verification

The proxy verifies that it is connecting to the expected remote SSH server:

- On the first connection, it displays the host-key algorithm and SHA-256 fingerprint before asking for a password or OTP.
- Verify this fingerprint with the server administrator or another trusted source.
- Type the full word `yes` to store the key in `~/.ssh/known_hosts`.
- Later connections must match the stored key.
- If a recorded host key changes, the proxy stops before asking for credentials. Do not remove the old entry until the server administrator confirms the change.

Use a separate known-hosts file when needed:

```powershell
uv run ssh-proxy nano4 --known-hosts "$env:USERPROFILE\.ssh\nchc_known_hosts"
```

### Local proxy

The local SSH server intentionally requires no password or OTP and listens only on IPv4 loopback (`127.0.0.1`). This mode is intended for a trusted, single-user computer. Other programs running on the same computer can use the authenticated proxy while it is running.

Safety limits are enabled by default:

- The proxy stops after 8 hours.
- It stops after 60 minutes with no local SSH clients connected.
- An active terminal or Remote-SSH connection prevents the idle timeout.
- The proxy stops if the remote SSH connection closes.

Override these limits when necessary:

```powershell
uv run ssh-proxy nano4 --max-lifetime 12h --idle-timeout 30m
uv run ssh-proxy nano4 --max-lifetime 0 --idle-timeout 0  # Disable both
```

## Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) recommended, or another Python package manager

## Installation

```powershell
git clone https://github.com/gemini960114/ssh-proxy.git
cd ssh-proxy
uv sync
```

Run as a script:

```powershell
uv run ssh_proxy.py nano4
```

Or run the packaged console command:

```powershell
uv run ssh-proxy nano4
```

## Usage

### Basic

```powershell
# Connect to nano5.nchc.org.tw, proxy on local port 2223.
uv run ssh_proxy.py nano5.nchc.org.tw -l 2223

# Or use an alias defined in ~/.ssh/config.
uv run ssh_proxy.py nano5 -l 2223

# Connect to nano4 on default local port 2222.
uv run ssh_proxy.py nano4
```

### Options

```text
usage: ssh_proxy.py [-h] [-p PORT] [-l LOCAL_PORT]
                    [--known-hosts KNOWN_HOSTS]
                    [--max-lifetime DURATION]
                    [--idle-timeout DURATION]
                    [host]

positional arguments:
  host              SSH host alias or hostname (default: nano4)

options:
  -p, --port        Remote SSH port (default: 22)
  -l, --local-port  Local proxy port (default: 2222)
  --known-hosts     Remote host key database (default: ~/.ssh/known_hosts)
  --max-lifetime    Stop after this time, e.g. 8h; 0 disables (default: 8h)
  --idle-timeout    Stop after this time with no local SSH clients;
                    0 disables (default: 60m)
```

### Connect After Proxy Is Running

```powershell
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p 2222 127.0.0.1
```

### SSH Config Aliases

Copy the relevant sections from [ssh_config.example](ssh_config.example) into `~/.ssh/config` or `C:\Users\<you>\.ssh\config`.

Start with the real remote host. Replace `YOUR_USERNAME` with your NCHC username:

```sshconfig
Host nano4
  HostName nano4.nchc.org.tw
  User YOUR_USERNAME

  # Go directly to the OTP / MFA authentication flow
  PubkeyAuthentication no
  KbdInteractiveAuthentication yes
  PreferredAuthentications keyboard-interactive,password

  # Keep the direct OpenSSH connection alive and detect failures
  ServerAliveInterval 30
  ServerAliveCountMax 3

  # Useful on networks which have IP QoS compatibility issues
  IPQoS none
```

`ssh-proxy` reads `HostName` and `User` from this block. The authentication, keepalive, and `IPQoS` options are used when connecting directly with `ssh nano4`; the proxy configures its own authentication behavior.

Add the local proxy alias used by terminal and Remote-SSH clients:

```sshconfig
Host nano4-proxy
  HostName 127.0.0.1
  Port 2222
  User YOUR_USERNAME

  # The local proxy creates a temporary host key on every start
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
  LogLevel ERROR

  # Detect when the local proxy has stopped responding
  ServerAliveInterval 30
  ServerAliveCountMax 3

Host nano5-proxy
  HostName 127.0.0.1
  Port 2223
  User YOUR_USERNAME

  # These two host-key settings must only be used for this local proxy alias
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
  LogLevel ERROR

  ServerAliveInterval 30
  ServerAliveCountMax 3
```

The proxy binds specifically to IPv4 loopback (`127.0.0.1`), so the alias uses that address instead of `localhost`. This avoids an unnecessary IPv6 `::1` connection attempt. The proxy port must match the port used when starting `ssh_proxy.py`. For example, `nano4-proxy` uses port `2222`, so start it with:

`StrictHostKeyChecking no` and `UserKnownHostsFile /dev/null` are necessary here because the local proxy currently creates a new temporary host key on every start. Keep these settings scoped to `nano4-proxy` and `nano5-proxy`; never add them to the real remote hosts.

```powershell
uv run ssh_proxy.py nano4 -l 2222
```

For Antigravity or VS Code Remote-SSH, choose the proxy host, such as `nano4-proxy`, not the direct host `nano4`.

### Verify Remote-SSH Compatibility

After the proxy is running, verify that `bash -s` stdin relay works:

```powershell
$script = "echo OK`nhostname`nwhoami`n"
[IO.File]::WriteAllText("$env:TEMP\ssh-proxy-test.sh", $script, [Text.UTF8Encoding]::new($false))
cmd /c type "%TEMP%\ssh-proxy-test.sh" | ssh -T nano4-proxy bash -s
```

Expected output:

```text
OK
<remote-hostname>
<your-remote-username>
```

Antigravity and VS Code Remote-SSH also need SSH port forwarding. When forwarding is used, the proxy log should show entries like:

```text
-> tcp forward: client=127.0.0.1:xxxxx 127.0.0.1:xxxxx -> 127.0.0.1:yyyyy
```

## Supported Hosts

Works with SSH servers that use keyboard-interactive / OTP authentication, including:

- `nano4.nchc.org.tw`
- `nano5.nchc.org.tw`
- `f1-ilgn*.nchc.org.tw`
- Other MFA-protected SSH servers

## Troubleshooting

### `bash: $'\r': command not found` in PowerShell tests

PowerShell pipelines can convert line endings to CRLF. Use `cmd /c type` as shown in the verification command above.

### Antigravity or VS Code Remote-SSH hangs

Make sure you restarted the proxy after updating `ssh_proxy.py`. Remote-SSH requires TCP forwarding (`ssh -D` / `ssh -L`), and older versions of this proxy only handled shell sessions.

Close stale Remote-SSH windows and reconnect to the proxy alias, for example `nano4-proxy`.

### `REMOTE HOST IDENTIFICATION HAS CHANGED`

The remote server presented a different SSH host key than the one stored in `~/.ssh/known_hosts`. The proxy stops before sending a password or OTP.

Do not delete the recorded key merely to bypass this warning. First verify the new SHA-256 fingerprint with the server administrator. A legitimate server reinstall or host-key rotation can cause this warning, but so can a network interception attempt.

### The proxy stopped after 8 hours or while idle

These are the default safety limits. Start it again and complete OTP, or choose different limits:

```powershell
uv run ssh-proxy nano4 --max-lifetime 12h --idle-timeout 2h
```

### `warning: VIRTUAL_ENV=... does not match`

This warning comes from `uv` when another virtual environment is active. It is usually harmless. To avoid it, deactivate the other environment or run from a clean PowerShell.

## License

MIT
