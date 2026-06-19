# ssh-proxy Student Tutorial

This tutorial helps students connect to an OTP-protected computing host through `ssh-proxy`.

The goal is simple: complete SSH password + OTP authentication once, then reuse the local proxy for additional SSH sessions, Antigravity, VS Code Remote-SSH, and port forwarding.

## What Problem Are We Solving?

On many computing hosts, each SSH connection requires:

1. Username
2. Password
3. OTP / MFA verification

Even when opening a second terminal or Remote-SSH window in the same working environment, users often need to repeat the same full login process.

`ssh-proxy` solves this by keeping one authenticated SSH connection alive. After that, students connect to a local proxy host such as `nano4-proxy` without repeating OTP.

## Step 1: Install uv on Windows

Open PowerShell and run:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Close PowerShell, open a new PowerShell window, and verify:

```powershell
uv --version
```

Reference: https://docs.astral.sh/uv/getting-started/installation/

## Step 2: Check SSH Is Available

In PowerShell, run:

```powershell
ssh -V
```

Windows 10 and Windows 11 usually include OpenSSH Client. If `ssh` is not found, install OpenSSH Client from:

```text
Settings -> System -> Optional features -> Add an optional feature -> OpenSSH Client
```

## Step 3: Download ssh-proxy

In PowerShell:

```powershell
cd $env:USERPROFILE
git clone https://github.com/gemini960114/ssh-proxy.git
cd ssh-proxy
uv sync
```

## Step 4: Configure SSH

Open your SSH config file:

```powershell
notepad $env:USERPROFILE\.ssh\config
```

If the file or `.ssh` folder does not exist, create it:

```powershell
mkdir $env:USERPROFILE\.ssh -Force
notepad $env:USERPROFILE\.ssh\config
```

Paste the following config and replace `YOUR_USERNAME` with your own computing-host username.

```sshconfig
Host nano4
  HostName nano4.nchc.org.tw
  User YOUR_USERNAME
  PubkeyAuthentication no
  IdentitiesOnly yes
  KbdInteractiveAuthentication yes
  PreferredAuthentications keyboard-interactive,password
  IPQoS none
  MACs hmac-sha2-512,hmac-sha2-256-etm@openssh.com,hmac-sha2-256
  ServerAliveInterval 30
  ServerAliveCountMax 3

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
```

Important:

- `nano4` is the real remote host and still requires OTP.
- `nano4-proxy` is the local proxy host. Use this in Antigravity or VS Code Remote-SSH.
- The proxy port in SSH config must match the port used when starting `ssh-proxy`. The example uses port `2222`.

## Step 5: Start ssh-proxy

Open the first PowerShell window:

```powershell
cd $env:USERPROFILE\ssh-proxy
uv run ssh-proxy nano4
```

Complete the login prompts:

1. Choose the OTP method.
2. Enter your password if prompted.
3. Approve the OTP / PUSH / MFA challenge.

After login succeeds, keep this PowerShell window open. It is running the local SSH proxy.

## Step 6: Test the Proxy

Open a second PowerShell window:

```powershell
ssh nano4-proxy
```

If the proxy is working, you should enter the remote host without repeating OTP.

Exit the remote shell:

```bash
exit
```

## Step 7: Verify Remote-SSH Compatibility

In PowerShell:

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

This confirms that `bash -s` stdin relay works. Antigravity and VS Code Remote-SSH need this behavior when installing or starting their remote server.

## Step 8: Use Antigravity or VS Code Remote-SSH

In Antigravity or VS Code Remote-SSH, choose:

```text
nano4-proxy
```

Do not choose `nano4` unless you want to connect directly and repeat OTP.

When Antigravity / VS Code connects successfully, the proxy window may show logs like:

```text
-> tcp forward: 127.0.0.1:xxxxx -> 127.0.0.1:yyyyy
```

This is normal. Remote-SSH uses SSH port forwarding to communicate with the remote server.

## Troubleshooting

### `uv` says `VIRTUAL_ENV=... does not match`

This usually means another Python virtual environment is active. It is often harmless. To avoid the warning, open a clean PowerShell window and run the command again.

### `ssh nano4-proxy` cannot connect

Check these points:

1. The first PowerShell window is still running `uv run ssh-proxy nano4`.
2. `nano4-proxy` uses `Port 2222`.
3. The proxy was started with the default port `2222`, or with `-l 2222`.

### PowerShell test shows `bash: $'\r': command not found`

This is caused by Windows CRLF line endings in PowerShell pipelines. Use the tutorial's `cmd /c type` command when testing `bash -s`.

### Antigravity or VS Code Remote-SSH hangs

Restart the proxy and reconnect:

```powershell
# In the proxy window, press Ctrl+C first.
cd $env:USERPROFILE\ssh-proxy
uv run ssh-proxy nano4
```

Then close the stale Remote-SSH window and connect again to `nano4-proxy`.

## Teaching Summary

`ssh-proxy` does not bypass OTP. It performs the required OTP authentication once, keeps that SSH connection alive, and exposes a local SSH proxy. Students then connect to `nano4-proxy` for repeated terminal sessions, Antigravity, VS Code Remote-SSH, and port forwarding without re-entering password and OTP each time.
