# ssh-proxy

A lightweight SSH OTP local proxy written in Python with AsyncSSH and Rich.

Authenticate with OTP/2FA once, then connect as many times as you want without repeated prompts. It supports terminals, Antigravity / VS Code Remote-SSH, Git, SFTP, and SSH port forwarding.

## Quick Start

```powershell
# Step 1: Start the proxy. Enter OTP only once.
uv run ssh_proxy.py nano4          # nano4, local port 2222
uv run ssh_proxy.py nano5 -l 2223  # nano5, local port 2223

# Step 2: Connect freely. No OTP needed.
ssh -p 2222 localhost   # forwards to nano4.nchc.org.tw
ssh -p 2223 localhost   # forwards to nano5.nchc.org.tw

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
    localhost:2222   <- ssh-proxy
          |
          | OTP-authenticated SSH connection kept alive
          v
    nano4.nchc.org.tw:22
```

1. `ssh_proxy.py` connects to the remote host using keyboard-interactive auth for OTP/2FA.
2. After authentication succeeds, it starts a local SSH server on `localhost:2222` or the port you choose with `-l`.
3. Local SSH sessions are bridged through the authenticated remote connection.
4. Shell/exec stdin, stdout, stderr, and TCP forwarding (`-L`, `-D`, `ProxyJump`) are tunneled through the remote connection. TCP forwarding is required by Antigravity and VS Code Remote-SSH.

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
usage: ssh_proxy.py [-h] [-p PORT] [-l LOCAL_PORT] [host]

positional arguments:
  host              SSH host alias or hostname (default: nano4)

options:
  -p, --port        Remote SSH port (default: 22)
  -l, --local-port  Local proxy port (default: 2222)
```

### Connect After Proxy Is Running

```powershell
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p 2222 localhost
```

### SSH Config Aliases

Copy the relevant sections from [ssh_config.example](ssh_config.example) into `~/.ssh/config` or `C:\Users\<you>\.ssh\config`.

```sshconfig
Host nano4-proxy
  HostName localhost
  Port 2222
  User YOUR_USERNAME
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
  LogLevel ERROR
  IPQoS none
  ServerAliveInterval 30
  ServerAliveCountMax 3

Host nano5-proxy
  HostName localhost
  Port 2223
  User YOUR_USERNAME
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
  LogLevel ERROR
  IPQoS none
  ServerAliveInterval 30
  ServerAliveCountMax 3
```

The proxy port must match the port used when starting `ssh_proxy.py`. For example, `nano4-proxy` uses port `2222`, so start it with:

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
-> tcp forward: 127.0.0.1:xxxxx -> 127.0.0.1:yyyyy
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

### `warning: VIRTUAL_ENV=... does not match`

This warning comes from `uv` when another virtual environment is active. It is usually harmless. To avoid it, deactivate the other environment or run from a clean PowerShell.

## License

MIT
