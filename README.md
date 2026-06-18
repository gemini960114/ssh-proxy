# ssh-proxy

A lightweight SSH OTP Local Proxy written in Python (asyncssh + rich).

Authenticate with OTP/2FA **once**, then connect as many times as you want — no repeated prompts for terminals, VS Code Remote-SSH, Git, or SFTP.

---

## How It Works

```
Your SSH Client (VS Code / terminal)
          │  no OTP needed
          ▼
    localhost:2222   ← ssh-proxy (this tool)
          │  OTP authenticated once, connection kept alive
          ▼
    nano5.nchc.org.tw:22
```

1. `ssh_proxy.py` connects to the remote host using keyboard-interactive (OTP/2FA).
2. After you complete the OTP challenge, a **local SSH server** starts on `localhost:2222` (or any port you choose).
3. All subsequent connections to `localhost:2222` are **bridged** through the already-authenticated remote connection — no OTP required.

---

## Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

---

## Installation

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/ssh-proxy.git
cd ssh-proxy

# Install dependencies with uv
uv sync
```

---

## Usage

### Basic

```bash
# Connect to nano5.nchc.org.tw, proxy on local port 2223
uv run ssh_proxy.py nano5.nchc.org.tw -l 2223

# Or use an alias defined in ~/.ssh/config
uv run ssh_proxy.py nano5 -l 2223
```

### Options

```
usage: ssh_proxy.py [-h] [-p PORT] [-l LOCAL_PORT] [host]

positional arguments:
  host              SSH Host alias or hostname (default: nano4)

options:
  -p, --port        Remote SSH port (default: 22)
  -l, --local-port  Local proxy port (default: 2222)
```

### Connect After Proxy Is Running

```bash
# Terminal / any SSH client
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p 2223 localhost
```

### Optional: Add to ~/.ssh/config for short alias

```
Host nano5-proxy
  HostName localhost
  Port 2223
  User YOUR_USERNAME
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
```

Then simply:
```bash
ssh nano5-proxy
```

---

## Supported Hosts

Works with **any SSH server** that uses keyboard-interactive / OTP authentication, including:

- `nano4.nchc.org.tw`
- `nano5.nchc.org.tw`
- `f1-ilgn*.nchc.org.tw`
- Any other MFA-protected SSH server

---

## License

MIT
