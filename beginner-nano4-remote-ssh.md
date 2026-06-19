# Beginner Guide: Connect to nano4 with Remote-SSH

This guide is for students who are connecting to `nano4` directly for the first time.

In this beginner setup, every new SSH / Remote-SSH connection may ask for:

1. Username
2. Password
3. OTP / MFA verification

This is normal. After this direct connection works, students can later use `ssh-proxy` to avoid repeated OTP prompts.

## Step 1: Check SSH Is Available

Open PowerShell and run:

```powershell
ssh -V
```

If `ssh` is not found, install OpenSSH Client from Windows:

```text
Settings -> System -> Optional features -> Add an optional feature -> OpenSSH Client
```

## Step 2: Open SSH Config

Open PowerShell and run:

```powershell
mkdir $env:USERPROFILE\.ssh -Force
notepad $env:USERPROFILE\.ssh\config
```

This opens your SSH config file:

```text
C:\Users\<your-windows-username>\.ssh\config
```

## Step 3: Add nano4 Config

Paste the following block into the config file.

Replace `YOUR_USERNAME` with your computing-host username.

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
```

Example:

```sshconfig
Host nano4
  HostName nano4.nchc.org.tw
  User c00xxxxx

  PubkeyAuthentication no
  IdentitiesOnly yes

  KbdInteractiveAuthentication yes
  PreferredAuthentications keyboard-interactive,password

  IPQoS none
  MACs hmac-sha2-512,hmac-sha2-256-etm@openssh.com,hmac-sha2-256

  ServerAliveInterval 30
  ServerAliveCountMax 3
```

Save the file and close Notepad.

## Step 4: Test SSH in PowerShell

Run:

```powershell
ssh nano4
```

You should see the remote login flow. Complete the password and OTP / MFA prompts.

If login succeeds, you are now inside the remote host.

To leave the remote host:

```bash
exit
```

## Step 5: Connect with Antigravity or VS Code Remote-SSH

Open Antigravity or VS Code Remote-SSH.

Choose:

```text
nano4
```

The IDE will use the same SSH config. It may ask for password and OTP again. This is expected for the direct beginner setup.

## Common Issues

### `ssh: Could not resolve hostname nano4`

Your SSH config was not saved correctly, or it was saved to the wrong path.

Check that this file exists:

```text
C:\Users\<your-windows-username>\.ssh\config
```

### Password or OTP does not appear

Make sure the config includes:

```sshconfig
PubkeyAuthentication no
KbdInteractiveAuthentication yes
PreferredAuthentications keyboard-interactive,password
```

### Remote-SSH keeps asking for OTP

This is normal for the direct `nano4` setup. Each new SSH connection may require password and OTP.

To reduce repeated OTP prompts, use the advanced `ssh-proxy` setup later.

## Beginner vs Advanced Setup

Beginner setup:

```text
Antigravity / VS Code -> nano4 -> password + OTP every new connection
```

Advanced setup:

```text
Antigravity / VS Code -> nano4-proxy -> ssh-proxy -> nano4
```

Use the beginner setup first to confirm the account, password, OTP, and SSH config are correct. Then move to `ssh-proxy` when repeated OTP prompts become inconvenient.
