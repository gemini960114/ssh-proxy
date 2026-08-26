# ssh-proxy Installation and Usage Guide (Windows / macOS)

This guide is designed for beginners and students, covering everything from installing **uv** from scratch, cloning and configuring **ssh-proxy**, to connecting via **Terminal**, **VS Code Remote-SSH**, or **Antigravity**.

---

## 📖 Table of Contents

1. [Project Overview & Architecture](#1-project-overview--architecture)
2. [Windows Installation & Setup Step-by-Step](#2-windows-installation--setup-step-by-step)
3. [macOS Installation & Setup Step-by-Step](#3-macos-installation--setup-step-by-step)
4. [SSH Config Setup (Terminal, VS Code & Antigravity Integration)](#4-ssh-config-setup-terminal-vs-code--antigravity-integration)
5. [Classroom Quick Cheat Sheet](#5-classroom-quick-cheat-sheet)
6. [CLI Usage & Advanced Options](#6-cli-usage--advanced-options)
7. [Troubleshooting & FAQ](#7-troubleshooting--faq)
8. [Packaging as Standalone Binary (Windows .exe / macOS Binary)](#8-packaging-as-standalone-binary-windows-exe--macos-binary)

---

## 1. Project Overview & Architecture

### Why do you need ssh-proxy?
On many High-Performance Computing (HPC) clusters (such as NCHC Nano4 / Nano5) or enterprise servers, every new SSH connection requires you to enter:
1. Username
2. Password
3. **One-Time Password / 2FA Code (OTP / MFA)**

This means opening a new terminal tab, transferring files, or attaching VS Code / Antigravity Remote-SSH will repeatedly prompt you for an OTP, which can be very tedious.

### How it works
`ssh-proxy` is a lightweight local SSH proxy server:
- **First Connection**: You perform password and OTP authentication once inside a dedicated terminal window. The proxy maintains the underlying authenticated SSH session.
- **Subsequent Connections**: It opens a local proxy listener at `127.0.0.1:2222`. Your terminal, VS Code, or Antigravity connect directly to this port **without requiring an OTP again**.

```text
Your Local Client (Terminal / Antigravity / VS Code)
          │
          │ (No OTP needed, connects to local proxy)
          ▼
    127.0.0.1:2222   <─── ssh-proxy (Running in background window)
          │
          │ (OTP-authenticated session, auto Keep-Alive)
          ▼
    nano4.nchc.org.tw:22
```

---

## 2. Windows Installation & Setup Step-by-Step

> 💡 **Recommended (No Python/uv needed)**: Download **`ssh-proxy-windows-x64.exe`** directly from [GitHub Releases](https://github.com/gemini960114/ssh-proxy/releases/latest). Once your SSH config is set, simply double-click it to run! Follow below if you prefer running from source.

### Step 1: Open PowerShell

- Type `PowerShell` in the Windows Search bar and launch it.
- Using standard user privileges is recommended (Administrator is not required).

### Step 2: Install uv
Run the official installer script in PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

> **Note**: After installation completes, **close and reopen your PowerShell window**, then verify the installation:
> ```powershell
> uv --version
> ```
> Seeing `uv 0.x.x` indicates a successful installation.

### Step 3: Check Git and OpenSSH Client
Run the following in PowerShell:
```powershell
git --version
ssh -V
```
- If `git` is not found, install it from [Git for Windows](https://git-scm.com/download/win).
- Windows 10/11 includes an OpenSSH Client by default. If missing, enable it under **Settings** → **System** → **Optional features** → **OpenSSH Client**.

### Step 4: Clone the Repository (git clone)
Cloning to your user home directory is recommended:
```powershell
cd $env:USERPROFILE
git clone https://github.com/gemini960114/ssh-proxy.git
cd ssh-proxy
```

### Step 5: Sync Environment & Dependencies (uv sync)
The repository includes `pyproject.toml` and `uv.lock`. Simply run:
```powershell
uv sync
```
`uv` will automatically download and install Python (3.12+) and required dependencies (AsyncSSH, Rich, etc.). You do not need to manually manage virtual environments.

Verify Python version inside the environment:
```powershell
uv run python --version
```

### Step 6: Start ssh-proxy
Connect to your remote host (e.g., `nano4`):
```powershell
uv run ssh-proxy nano4
# Or run using the script directly:
uv run ssh_proxy.py nano4
```
- By default, it creates a local proxy server on `127.0.0.1:2222`.
- **On First Connection**: OpenSSH host key fingerprints will be displayed. Type `yes` to confirm and save the host key.
- Enter your Password and OTP / 2FA code when prompted.
- Once authenticated, **keep this PowerShell window open**.

### Step 7: Open a Second PowerShell to Test Connection
Launch a new PowerShell window and run:
```powershell
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p 2222 127.0.0.1
```
If you log in successfully without being asked for an OTP, the proxy is working!

---

## 3. macOS Installation & Setup Step-by-Step

### Step 1: Open Terminal
- Press `Command + Space` to open Spotlight search, type `Terminal`, and press Enter.

### Step 2: Install uv
Run the official installer script in Terminal:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

> **Note**: After installation completes, restart your Terminal or run `source $HOME/.cargo/env` (or `.zshrc`), then verify:
> ```bash
> uv --version
> ```
> Seeing `uv 0.x.x` indicates a successful installation.

### Step 3: Check Git
Run in Terminal:
```bash
git --version
```
- If prompted to install Command Line Tools, run `xcode-select --install`.

### Step 4: Clone the Repository (git clone)
```bash
cd ~
git clone https://github.com/gemini960114/ssh-proxy.git
cd ssh-proxy
```

### Step 5: Sync Environment & Dependencies (uv sync)
```bash
uv sync
```
Verify Python version:
```bash
uv run python --version
```

### Step 6: Start ssh-proxy
Start proxy connection for `nano4` (default port 2222):
```bash
uv run ssh-proxy nano4
# Or
uv run ssh_proxy.py nano4
```
- Type `yes` on first connection to trust the host key, then enter your password and OTP.
- Once connected, **keep this Terminal window running in the background**.

### Step 7: Open a Second Terminal to Test Connection
Open a new Terminal tab or window, and run:
```bash
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p 2222 127.0.0.1
```
Logging in successfully confirms the proxy setup.

---

## 4. SSH Config Setup (Terminal, VS Code & Antigravity Integration)

To avoid typing lengthy connection parameters every time, configure an SSH Config alias.

### Config File Location
- **Windows**: `C:\Users\<YourUsername>\.ssh\config`
- **macOS**: `~/.ssh/config`

(Create the `.ssh` directory or `config` file if it does not exist.)

### Config Content
Edit the `config` file and paste the following, replacing `YOUR_USERNAME` with your actual remote login username:

```sshconfig
# 1. Original Remote Host (used by ssh-proxy to read target connection settings)
Host nano4
  HostName nano4.nchc.org.tw
  User YOUR_USERNAME
  PubkeyAuthentication no
  KbdInteractiveAuthentication yes
  PreferredAuthentications keyboard-interactive,password
  ServerAliveInterval 30
  ServerAliveCountMax 3
  IPQoS none

# 2. Local Proxy Alias (used by Terminal, VS Code, and Antigravity)
Host nano4-proxy
  HostName 127.0.0.1
  Port 2222
  User YOUR_USERNAME
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
  LogLevel ERROR
  ServerAliveInterval 30
  ServerAliveCountMax 3

# 3. For Nano5 (Port 2223)
Host nano5-proxy
  HostName 127.0.0.1
  Port 2223
  User YOUR_USERNAME
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
  LogLevel ERROR
  ServerAliveInterval 30
  ServerAliveCountMax 3
```

### How to Use After Setup
1. **Standard Terminal Connection**:
   While `ssh-proxy` is running, simply execute:
   ```bash
   ssh nano4-proxy
   ```
2. **VS Code / Antigravity Remote-SSH**:
   - Click the bottom-left Remote-SSH icon (or press `Ctrl+Shift+P` / `Cmd+Shift+P` and search `Remote-SSH: Connect to Host...`).
   - Select **`nano4-proxy`** (Make sure to select `-proxy`, not the original `nano4`).
   - You can now open remote folders and debug without OTP prompts!

---

## 5. Classroom Quick Cheat Sheet

For slides or quick references:

### 🪟 Windows Quick Reference
```powershell
# 1. Install uv
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 2. Reopen PowerShell & verify
uv --version

# 3. Clone repository & install environment
git clone https://github.com/gemini960114/ssh-proxy.git
cd ssh-proxy
uv sync

# 4. Start Proxy (Keep window open)
uv run ssh-proxy nano4

# 5. Open a new window & connect
ssh nano4-proxy
```

### 🍎 macOS Quick Reference
```bash
# 1. Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Reopen Terminal & verify
uv --version

# 3. Clone repository & install environment
git clone https://github.com/gemini960114/ssh-proxy.git
cd ssh-proxy
uv sync

# 4. Start Proxy (Keep window open)
uv run ssh-proxy nano4

# 5. Open a new window & connect
ssh nano4-proxy
```

---

## 6. CLI Usage & Advanced Options

`ssh-proxy` provides several customizable command-line options:

```text
Usage: uv run ssh-proxy [HOST] [OPTIONS]
```

### Common Examples:
- **Custom Local Port (e.g. Nano5 on Port 2223)**:
  ```bash
  uv run ssh-proxy nano5 -l 2223
  ```
- **Custom Session Lifetime & Idle Timeout (default: max 8h, idle 60m)**:
  ```bash
  uv run ssh-proxy nano4 --max-lifetime 12h --idle-timeout 30m
  ```
- **Disable Automatic Timeout (Set to 0)**:
  ```bash
  uv run ssh-proxy nano4 --max-lifetime 0 --idle-timeout 0
  ```
- **Custom known-hosts file**:
  ```bash
  # Windows
  uv run ssh-proxy nano4 --known-hosts "$env:USERPROFILE\.ssh\nchc_known_hosts"
  # macOS
  uv run ssh-proxy nano4 --known-hosts "$HOME/.ssh/nchc_known_hosts"
  ```

---

## 7. Troubleshooting & FAQ

### Q1: Terminal or VS Code shows `WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED`
- **Cause**: The remote server's SSH Host Key changed or the system was reinstalled.
- **Solution**: `ssh-proxy` stops the connection automatically to protect credentials. Verify the SHA-256 fingerprint with your system administrator before updating `~/.ssh/known_hosts`.

### Q2: VS Code / Antigravity Remote-SSH connection freezes or fails
- **Check 1**: Ensure the Proxy window is still running in the background.
- **Check 2**: Ensure you are connecting to **`nano4-proxy`**, not `nano4`.
- **Check 3**: Close stale VS Code Remote windows, restart the Proxy, and reconnect.

### Q3: Windows PowerShell test script fails with `bash: $'\r': command not found`
- **Cause**: PowerShell pipeline may convert line endings to Windows CRLF (`\r\n`).
- **Fix**: Run test stdin relay in PowerShell using UTF-8 `\n`:
  ```powershell
  $script = "echo OK`nhostname`nwhoami`n"
  [IO.File]::WriteAllText("$env:TEMP\ssh-proxy-test.sh", $script, [Text.UTF8Encoding]::new($false))
  cmd /c type "%TEMP%\ssh-proxy-test.sh" | ssh -T nano4-proxy bash -s
  ```

### Q4: Warning `warning: VIRTUAL_ENV=... does not match` appears
- **Cause**: Another Python virtual environment is active in your current terminal session.
- **Fix**: This warning does not affect execution. Run `deactivate` or open a fresh terminal window to suppress it.

### Q5: Proxy automatically closes after running for a while
- **Cause**: This is a default security mechanism (closes after 8 hours max lifetime or 60 minutes of idle time).
- **Fix**: Re-run `uv run ssh-proxy nano4` with OTP, or add `--max-lifetime 12h` when starting.

---

## 8. Packaging as Standalone Binary (Windows .exe / macOS Binary)

To distribute `ssh-proxy` to users who do not have Python or `uv` installed, package it into a standalone single executable using PyInstaller:

### Build Command

```bash
uv run pyinstaller --onefile --name ssh-proxy --clean ssh_proxy.py
```

### Execution

- **Windows** (generated in `dist/ssh-proxy.exe`):
  ```powershell
  .\dist\ssh-proxy.exe nano4
  ```
- **macOS / Linux** (generated in `dist/ssh-proxy`):
  ```bash
  chmod +x dist/ssh-proxy
  ./dist/ssh-proxy nano4
  ```

> **macOS Notes**:
> 1. The binary architecture (Apple Silicon `arm64` vs Intel `x86_64`) matches the Mac architecture where the build is executed.
> 2. If downloaded from the internet, clear Apple quarantine attributes if prompted: `xattr -d com.apple.quarantine dist/ssh-proxy`.

---

## 📄 License
This project is licensed under the [MIT License](LICENSE).

