import os
import sys
import json
import urllib.request
import urllib.parse

def load_config(config_path="config.json"):
    if not os.path.exists(config_path):
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[!] 警告: 載入 {config_path} 失敗: {e}")
        return {}

def get_webhook_url(config):
    # 優先讀取 discord_link.txt
    txt_path = "discord_link.txt"
    if os.path.exists(txt_path):
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                url = f.read().strip()
                if url:
                    print(f"[+] 從 {txt_path} 讀取到 Discord Webhook URL")
                    return url
        except Exception as e:
            print(f"[!] 讀取 {txt_path} 失敗: {e}")
            
    # 次之讀取 config.json
    url = config.get("discord_webhook_url")
    if url:
        print("[+] 從 config.json 讀取到 Discord Webhook URL")
        return url
        
    print("[!] 錯誤: 找不到任何 Discord Webhook URL (檢查 discord_link.txt 或 config.json)")
    return None

def get_keywords(config):
    # 優先讀取 filter_by_keyword.txt
    txt_path = "filter_by_keyword.txt"
    if os.path.exists(txt_path):
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    keywords = [k.strip().lower() for k in content.split(",") if k.strip()]
                    print(f"[+] 從 {txt_path} 讀取到關鍵字: {keywords}")
                    return keywords
        except Exception as e:
            print(f"[!] 讀取 {txt_path} 失敗: {e}")
            
    # 次之讀取 config.json
    kws = config.get("keywords")
    if kws:
        keywords = [str(k).strip().lower() for k in kws if str(k).strip()]
        print(f"[+] 從 config.json 讀取到關鍵字: {keywords}")
        return keywords
        
    print("[!] 警告: 未找到任何過濾關鍵字，將發送所有貼文！")
    return []

def send_discord_webhook(webhook_url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    )
    try:
        with urllib.request.urlopen(req) as response:
            # Discord webhook returns 204 on success (or 200)
            return response.status in (200, 204)
    except Exception as e:
        print(f"[!] 發送至 Discord Webhook 失敗: {e}")
        return False

def main():
    print("==================================================")
    print("[*] 啟動過濾與 Discord 通知系統...")
    
    config = load_config()
    
    webhook_url = get_webhook_url(config)
    if not webhook_url:
        print("[!] 錯誤: 缺少 Discord Webhook URL，程式中止。")
        sys.exit(1)
        
    keywords = get_keywords(config)
    
    # 決定貼文輸入 JSON 檔與快取檔案路徑
    output_file = config.get("output_file", "fb_posts_output.csv")
    json_path = os.path.splitext(output_file)[0] + ".json"
    cache_path = config.get("sent_cache_file", "sent_posts_cache.json")
    
    if not os.path.exists(json_path):
        print(f"[!] 錯誤: 找不到貼文 JSON 檔案 {json_path}，請先執行爬蟲或轉換工具。")
        sys.exit(1)
        
    # 載入快取
    sent_posts = []
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                sent_posts = json.load(f)
                if not isinstance(sent_posts, list):
                    sent_posts = []
            print(f"[+] 已載入 {len(sent_posts)} 筆已發送的貼文快取")
        except Exception as e:
            print(f"[!] 警告: 載入快取檔案失敗，初始化為空快取: {e}")
            sent_posts = []
    else:
        print("[*] 找不到快取檔案，將建立新的快取紀錄")
        
    # 讀取待處理貼文
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            posts = json.load(f)
    except Exception as e:
        print(f"[!] 錯誤: 載入貼文 JSON 失敗: {e}")
        sys.exit(1)
        
    print(f"[*] 讀取到 {len(posts)} 筆貼文，開始進行關鍵字篩選...")
    
    match_count = 0
    sent_count = 0
    
    for idx, post in enumerate(posts):
        url = post.get("url", "").strip()
        publisher = post.get("publisher", "").strip() or "未知發布者"
        content = post.get("content", "").strip()
        
        # 防重複機制：已發送過就跳過
        if url in sent_posts:
            continue
            
        # 內文轉換為小寫進行比較
        content_lower = content.lower()
        
        # 進行關鍵字匹配
        matched_kws = []
        if keywords:
            for kw in keywords:
                if kw in content_lower:
                    matched_kws.append(kw)
        else:
            # 若無關鍵字，預設為全部匹配
            matched_kws = ["無設定過濾關鍵字（全發送）"]
            
        if matched_kws:
            match_count += 1
            print(f"[+] 貼文 {idx+1} 匹配成功！發布者: {publisher} | 關鍵字: {matched_kws} | 網址: {url}")
            
            # 格式化內文（防長度溢出）
            content_desc = content
            if len(content_desc) > 3000:
                content_desc = content_desc[:3000] + "\n...(內文過長已截斷)..."
                
            # 組織 Discord Embed
            payload = {
                "embeds": [
                    {
                        "title": "🔍 發現關鍵字匹配貼文",
                        "description": f"**【貼文內文】**\n{content_desc}",
                        "url": url,
                        "color": 15844367, # 金色
                        "fields": [
                            {
                                "name": "👤 發布者",
                                "value": publisher,
                                "inline": True
                            },
                            {
                                "name": "🏷️ 匹配關鍵字",
                                "value": ", ".join(matched_kws),
                                "inline": True
                            },
                            {
                                "name": "🔗 貼文連結",
                                "value": url,
                                "inline": False
                            }
                        ],
                        "footer": {
                            "text": "球鞋打劫計劃 - 自動監控系統"
                        }
                    }
                ]
            }
            
            # 發送 Webhook
            success = send_discord_webhook(webhook_url, payload)
            if success:
                print(f"    [+] Discord 訊息發送成功！")
                sent_posts.append(url)
                sent_count += 1
                
                # 每次發送成功後即時更新快取存檔，防止程式中斷時快取遺失
                try:
                    with open(cache_path, "w", encoding="utf-8") as f:
                        json.dump(sent_posts, f, indent=2, ensure_ascii=False)
                except Exception as e:
                    print(f"    [!] 儲存快取檔案失敗: {e}")
            else:
                print(f"    [!] Discord 訊息發送失敗。")
                
    print("==================================================")
    print(f"[*] 執行結果摘要：")
    print(f"    - 掃描貼文總數: {len(posts)}")
    print(f"    - 新匹配貼文數: {match_count}")
    print(f"    - 成功通知數: {sent_count}")
    print(f"    - 目前已發送快取紀錄總數: {len(sent_posts)}")
    print("==================================================")

if __name__ == "__main__":
    main()
