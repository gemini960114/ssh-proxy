# ssh-proxy 繁體中文安裝與使用教學 (Windows / macOS)

本教學專為初學者與學員設計，整合從零安裝 **uv**、下載並設定 **ssh-proxy**，到搭配 **Terminal**、**VS Code Remote-SSH** 或 **Antigravity** 連線的完整流程。

---

## 📖 目錄

1. [專案介紹與運作原理](#1-專案介紹與運作原理)
2. [Windows 完整安裝與操作步驟](#2-windows-完整安裝與操作步驟)
3. [macOS 完整安裝與操作步驟](#3-macos-完整安裝與操作步驟)
4. [SSH Config 設定（終端機與 VS Code / Antigravity 整合）](#4-ssh-config-設定終端機與-vs-code--antigravity-整合)
5. [課堂初學者極簡速查表 (Cheat Sheet)](#5-課堂初學者極簡速查表-cheat-sheet)
6. [常用指令與進階參數](#6-常用指令與進階參數)
7. [常見問題與故障排除 (Troubleshooting)](#7-常見問題與故障排除-troubleshooting)
8. [打包為免安裝獨立執行檔 (Windows .exe / macOS Binary)](#8-打包為免安裝獨立執行檔-windows-exe--macos-binary)

---

## 1. 專案介紹與運作原理

### 為什麼需要 ssh-proxy？
在許多高效能運算中心（例如 NCHC 國網中心 Nano4、Nano5）或企業主機上，每次建立 SSH 連線時都需要輸入：
1. 使用者名稱（Username）
2. 密碼（Password）
3. **動態驗證碼（OTP / MFA 2FA）**

這導致每開一個新的終端機分頁、傳輸檔案、或使用 VS Code / Antigravity Remote-SSH 時，都要手動輸入一次 OTP，非常繁瑣。

### 運作架構
`ssh-proxy` 是一個輕量級的本地 SSH Proxy：
- **第一次連線**：在專用的終端視窗中完成密碼與 OTP 驗證，並保持底層 SSH 連線。
- **後續連線**：在本機開啟 `127.0.0.1:2222` 本地 Proxy，您的終端機、VS Code 或 Antigravity 直接連線至該 Port，**免再重複輸入 OTP**。

```text
您的本機用戶端 (Terminal / Antigravity / VS Code)
          │
          │ (免輸入 OTP，連線至本機 Proxy)
          ▼
    127.0.0.1:2222   <─── ssh-proxy (常駐中)
          │
          │ (已通過 OTP 驗證的遠端連線，自動 Keep-Alive)
          ▼
    nano4.nchc.org.tw:22
```

---

## 2. Windows 完整安裝與操作步驟

> 💡 **最推薦（免安裝 Python/uv）**：直接至 [GitHub Releases](https://github.com/gemini960114/ssh-proxy/releases/latest) 下載 **`ssh-proxy-windows-x64.exe`**，設定好 SSH Config 後雙擊即可執行！若想透過原始碼執行，請依照以下步驟安裝。

### 步驟 1：開啟 PowerShell

- 在 Windows 搜尋列輸入 `PowerShell` 並開啟。
- 建議使用**一般使用者權限**即可，不需要 Administrator。

### 步驟 2：安裝 uv
在 PowerShell 中執行官方安裝腳本：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

> **提示**：安裝完成後，請**關閉 PowerShell 視窗並重新開啟**，接著檢查版本：
> ```powershell
> uv --version
> ```
> 若顯示 `uv 0.x.x` 即代表安裝成功。

### 步驟 3：確認 Git 與 OpenSSH Client
在 PowerShell 執行：
```powershell
git --version
ssh -V
```
- 若提示找不到 `git`，請先至 [Git for Windows](https://git-scm.com/download/win) 安裝。
- Windows 10/11 通常已內建 OpenSSH Client；若無，可至「設定」→「系統」→「選用功能」新增「OpenSSH 用戶端」。

### 步驟 4：下載專案 (git clone)
建議下載至家目錄下：
```powershell
cd $env:USERPROFILE
git clone https://github.com/gemini960114/ssh-proxy.git
cd ssh-proxy
```

### 步驟 5：建立環境與自動安裝套件 (uv sync)
專案已配置 `pyproject.toml` 與 `uv.lock`，直接執行：
```powershell
uv sync
```
`uv` 會自動下載並安裝符合需求的 Python（需 3.12+）以及相關相依套件（AsyncSSH、Rich 等），無需手動管理虛擬環境。

可檢查環境的 Python 版本：
```powershell
uv run python --version
```

### 步驟 6：啟動 ssh-proxy
連線至遠端主機（例如 `nano4`）：
```powershell
uv run ssh-proxy nano4
# 或使用腳本方式執行
uv run ssh_proxy.py nano4
```
- 預設會在本機建立 `127.0.0.1:2222` 的 Proxy。
- **第一次連線**：會顯示遠端 SSH Host Key 指紋，請輸入完整的 `yes` 確認。
- 接著依照提示輸入密碼與 OTP 驗證碼。
- 驗證成功後，**請保持此 PowerShell 視窗開啟**（不要關閉）。

### 步驟 7：開啟第二個 PowerShell 測試連線
另外開啟一個新的 PowerShell 視窗，執行：
```powershell
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p 2222 127.0.0.1
```
成功登入即代表 Proxy 運作正常！

---

## 3. macOS 完整安裝與操作步驟

### 步驟 1：開啟 Terminal
- 按快捷鍵 `Command + Space` 叫出 Spotlight 搜尋，輸入 `Terminal`（終端機）並按 Enter。

### 步驟 2：安裝 uv
在 Terminal 中執行官方安裝腳本：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

> **提示**：安裝完成後，請依提示重啟 Terminal 或執行 `source $HOME/.cargo/env`（或 `.zshrc`），並檢查版本：
> ```bash
> uv --version
> ```
> 若顯示 `uv 0.x.x` 即代表安裝成功。

### 步驟 3：確認 Git
在 Terminal 執行：
```bash
git --version
```
- 若系統提示需要安裝 Command Line Tools，請執行 `xcode-select --install` 完成安裝。

### 步驟 4：下載專案 (git clone)
```bash
cd ~
git clone https://github.com/gemini960114/ssh-proxy.git
cd ssh-proxy
```

### 步驟 5：建立環境與自動安裝套件 (uv sync)
```bash
uv sync
```
可確認 Python 版本：
```bash
uv run python --version
```

### 步驟 6：啟動 ssh-proxy
啟動 Nano4 連線（預設 Port 2222）：
```bash
uv run ssh-proxy nano4
# 或
uv run ssh_proxy.py nano4
```
- 首次連線輸入 `yes` 信任主機指紋，接著輸入密碼與 OTP。
- 啟動成功後，**保持此 Terminal 視窗於背景執行**。

### 步驟 7：開啟第二個 Terminal 測試連線
開啟另一個新的 Terminal 分頁或視窗，執行：
```bash
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p 2222 127.0.0.1
```
若順利登入遠端主機，即代表 Proxy 建置成功。

---

## 4. SSH Config 設定（終端機與 VS Code / Antigravity 整合）

為了避免每次都要輸入長長的連線參數，建議設定 SSH Config 別名。

### 設定檔位置
- **Windows**: `C:\Users\<使用者名稱>\.ssh\config`
- **macOS**: `~/.ssh/config`

（如果 `.ssh` 資料夾或 `config` 檔案不存在，可自行建立）

### 設定內容
請編輯 `config` 檔案，將下列內容貼上，並將 `YOUR_USERNAME` 替換為您的遠端登入帳號：

```sshconfig
# 1. 原始遠端主機（給 ssh-proxy 讀取主機資訊使用）
Host nano4
  HostName nano4.nchc.org.tw
  User YOUR_USERNAME
  PubkeyAuthentication no
  KbdInteractiveAuthentication yes
  PreferredAuthentications keyboard-interactive,password
  ServerAliveInterval 30
  ServerAliveCountMax 3
  IPQoS none

# 2. 本地 Proxy 別名（給終端機、VS Code、Antigravity 使用）
Host nano4-proxy
  HostName 127.0.0.1
  Port 2222
  User YOUR_USERNAME
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
  LogLevel ERROR
  ServerAliveInterval 30
  ServerAliveCountMax 3

# 3. 若有使用 Nano5（Port 2223）
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

### 設定後的使用方式
1. **一般終端機連線**：
   在 Proxy 啟動狀態下，只要輸入以下簡短指令即可連線：
   ```bash
   ssh nano4-proxy
   ```
2. **VS Code / Antigravity Remote-SSH**：
   - 點擊左下角 Remote-SSH 按鈕（或 `Ctrl+Shift+P` / `Cmd+Shift+P` 搜尋 `Remote-SSH: Connect to Host...`）。
   - 選擇 **`nano4-proxy`**（注意：請選 `-proxy` 別名，不要選原始的 `nano4`）。
   - 即可直接開啟遠端工作區進行開發與偵錯！

---

## 5. 課堂初學者極簡速查表 (Cheat Sheet)

針對教學投影片或快速操作，可直接參考以下極簡版：

### 🪟 Windows 速查
```powershell
# 1. 安裝 uv
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 2. 重新開啟 PowerShell 並確認
uv --version

# 3. 下載專案並安裝環境
git clone https://github.com/gemini960114/ssh-proxy.git
cd ssh-proxy
uv sync

# 4. 啟動 Proxy (保持視窗開啟)
uv run ssh-proxy nano4

# 5. 另開視窗連線使用
ssh nano4-proxy
```

### 🍎 macOS 速查
```bash
# 1. 安裝 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 重新開啟 Terminal 並確認
uv --version

# 3. 下載專案並安裝環境
git clone https://github.com/gemini960114/ssh-proxy.git
cd ssh-proxy
uv sync

# 4. 啟動 Proxy (保持視窗開啟)
uv run ssh-proxy nano4

# 5. 另開視窗連線使用
ssh nano4-proxy
```

---

## 6. 常用指令與進階參數

`ssh-proxy` 提供多種客製化選項：

```text
使用方式: uv run ssh-proxy [主機名稱] [參數]
```

### 常用範例：
- **指定自訂本地 Port（例如 Nano5 使用 2223）**：
  ```bash
  uv run ssh-proxy nano5 -l 2223
  ```
- **指定自訂 known-hosts 檔案**：
  ```bash
  # Windows
  uv run ssh-proxy nano4 --known-hosts "$env:USERPROFILE\.ssh\nchc_known_hosts"
  # macOS
  uv run ssh-proxy nano4 --known-hosts "$HOME/.ssh/nchc_known_hosts"
  ```

### 逾時參數說明

Proxy 有兩個彼此獨立的自動停止計時器：

| 參數 | 預設值 | 計時方式 |
|---|---:|---|
| `--idle-timeout` | `60m` | 只有在**沒有任何本機 SSH client 連線**時才累計。只要終端機或 Remote-SSH 仍連著，就不會觸發；最後一個 client 中斷時會重新開始計時。 |
| `--max-lifetime` | `8h` | 從 Proxy 啟動後持續累計，即使有 client 正在使用，達到上限仍會停止。 |

上游 SSH 每 30 秒送出的 Keep-Alive 是用來避免網路閒置斷線，**不算本機 client 活動**，因此不會重設上述計時器。

下載版 Windows EXE 範例：

```powershell
# 將無 client 的閒置時間延長為 4 小時；總存活時間仍是預設 8 小時。
.\ssh-proxy-windows-x64.exe nano4 --idle-timeout 4h

# 將兩個限制都延長為一天。
.\ssh-proxy-windows-x64.exe nano4 --idle-timeout 1d --max-lifetime 1d

# 完全停用兩個自動停止計時器。
.\ssh-proxy-windows-x64.exe nano4 --idle-timeout 0 --max-lifetime 0
```

從原始碼執行時，參數完全相同：

```powershell
uv run ssh-proxy nano4 --idle-timeout 2h --max-lifetime 12h
```

---

## 7. 常見問題與故障排除 (Troubleshooting)

### Q1: 終端機或 VS Code 顯示 `WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED`
- **原因**：遠端伺服器的 SSH Host Key 發生變動，或重新安裝過系統。
- **處理方式**：`ssh-proxy` 會主動停止連線以保護安全。請先向伺服器管理員確認 SHA-256 指紋是否正確，確認無誤後再更新 `~/.ssh/known_hosts`。

### Q2: VS Code / Antigravity Remote-SSH 連線卡住或失敗
- **檢查重點 1**：確認 Proxy 視窗沒有被關閉。
- **檢查重點 2**：確認 Remote-SSH 連線的是 **`nano4-proxy`** 而非原始的 `nano4`。
- **檢查重點 3**：關閉所有失效的 VS Code Remote 視窗後，重啟 Proxy 再重新連線。

### Q3: Windows PowerShell 測試指令出現 `bash: $'\r': command not found`
- **原因**：PowerShell Pipeline 傳遞文字時可能自動轉為 Windows CRLF 換行符號。
- **解法**：在 Windows 測試 stdin relay 時，請使用：
  ```powershell
  $script = "echo OK`nhostname`nwhoami`n"
  [IO.File]::WriteAllText("$env:TEMP\ssh-proxy-test.sh", $script, [Text.UTF8Encoding]::new($false))
  cmd /c type "%TEMP%\ssh-proxy-test.sh" | ssh -T nano4-proxy bash -s
  ```

### Q4: 出現 `warning: VIRTUAL_ENV=... does not match` 警告
- **原因**：目前終端機環境中已經啟用了其他的 Python 虛擬環境。
- **解法**：此警告通常不影響執行；若想消除，可執行 `deactivate` 退出其他虛擬環境，或重新開啟一個乾淨的終端機。

### Q5: Proxy 運作一段時間後自動停止
- **`Idle timeout reached...`**：連續 60 分鐘沒有本機終端機或 Remote-SSH client 連線。使用 `--idle-timeout 2h` 可延長為 2 小時。
- **`Maximum lifetime reached...`**：Proxy 已達預設 8 小時總存活時間。使用 `--max-lifetime 12h` 可延長為 12 小時。
- **`Remote SSH connection closed.`**：上游 SSH 已中斷，與上述兩個計時器不同。

若是雙擊 EXE 啟動，程式結束時視窗也會一起關閉。建議從 PowerShell 啟動，才能看到最後的停止原因：

```powershell
.\ssh-proxy-windows-x64.exe nano4 --idle-timeout 2h --max-lifetime 12h
```

---

## 8. 打包為免安裝獨立執行檔 (Windows .exe / macOS Binary)

若要分發給沒有安裝 Python 或 uv 的同學/使用者，可以使用 PyInstaller 打包成單一獨立執行檔：

### 打包指令

```bash
uv run pyinstaller --onefile --name ssh-proxy --clean ssh_proxy.py
```

### 執行方式

- **Windows**（生成於 `dist/ssh-proxy.exe`）：
  ```powershell
  .\dist\ssh-proxy.exe nano4
  ```
- **macOS / Linux**（生成於 `dist/ssh-proxy`）：
  ```bash
  chmod +x dist/ssh-proxy
  ./dist/ssh-proxy nano4
  ```

> **macOS 注意事項**：
> 1. 打包時產生的架構（Apple Silicon `arm64` 或 Intel `x86_64`）取決於編譯所在的 Mac。
> 2. 若從網路下載執行檔後出現安全性提示，可執行 `xattr -d com.apple.quarantine dist/ssh-proxy` 移除隔離標籤。

---

## 📄 授權條款 (License)
本專案採用 [MIT License](LICENSE) 授權。
