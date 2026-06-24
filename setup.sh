#!/bin/bash
# 讓腳本在出錯時立即停止執行
set -e

echo "[*] =================================================="
echo "[*] 開始安裝「球鞋打劫計劃」伺服器環境..."
echo "[*] =================================================="

# 1. 更新系統並安裝 python3-pip 與 python3-venv
echo "[*] 步驟 1: 更新系統並安裝 python3-pip, python3-venv..."
sudo apt update
sudo apt install python3-pip python3-venv -y

# 2. 建立 venv 虛擬環境
echo "[*] 步驟 2: 建立 Python 虛擬環境 (venv)..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "[+] 虛擬環境 venv 建立成功！"
else
    echo "[*] 虛擬環境 venv 已存在，跳過建立。"
fi

# 3. 升級 pip 並根據 requirements.txt 安裝套件
echo "[*] 步驟 3: 安裝 Python 依賴套件 (requirements.txt)..."
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# 4. 安裝 Playwright 瀏覽器及其系統相依套件
echo "[*] 步驟 4: 安裝 Playwright 瀏覽器核心與系統依賴..."
# 針對較新的 Ubuntu 26.04 ARM64 系統，強制覆蓋為相容的 ubuntu24.04-arm64 版本以利下載
export PLAYWRIGHT_HOST_PLATFORM_OVERRIDE="ubuntu24.04-arm64"
./venv/bin/playwright install chromium
sudo -E ./venv/bin/playwright install-deps

echo ""
echo "[*] =================================================="
echo "[+] 環境配置完成！"
echo "[+] 您現在可以直接執行：./run_pipeline.sh 測試程式。"
echo "[*] =================================================="
