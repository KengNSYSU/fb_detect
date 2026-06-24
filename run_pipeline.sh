#!/bin/bash
# 進入專案目錄
cd "/Users/keng/Desktop/球鞋打劫計劃"

echo "[*] =================================================="
echo "[*] 開始執行完整 Pipeline (時間: $(date))"
echo "[*] =================================================="

# 1. 執行爬蟲更新資料
echo "[*] 步驟 1: 執行 Facebook 爬蟲..."
./venv/bin/python fb_scraper.py
SCRAPER_STATUS=$?

if [ $SCRAPER_STATUS -ne 0 ]; then
    echo "[!] 警告: Facebook 爬蟲執行失敗，但仍將嘗試執行過濾與通知（使用現有資料）"
fi

# 2. 執行過濾與發送通知
echo "[*] 步驟 2: 執行貼文篩選與 Discord 通知..."
./venv/bin/python filter_and_notify.py
NOTIFY_STATUS=$?

echo "[*] Pipeline 執行結束 (狀態碼: Scraper=$SCRAPER_STATUS, Notify=$NOTIFY_STATUS)"
echo "[*] =================================================="
