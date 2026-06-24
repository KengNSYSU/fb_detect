import csv
import json
import os

def main():
    csv_path = "fb_posts_output.csv"
    json_path = "fb_posts_output.json"
    
    if not os.path.exists(csv_path):
        print(f"[!] 錯誤: 找不到 CSV 檔案 {csv_path}")
        return
        
    print(f"[*] 正在將 {csv_path} 轉換為 {json_path}...")
    posts = []
    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                posts.append({
                    "publisher": row.get("發布者", "").strip(),
                    "url": row.get("貼文連結", "").strip(),
                    "content": row.get("內文", "").strip()
                })
        
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(posts, f, indent=2, ensure_ascii=False)
            
        print(f"[+] 轉換成功！共處理了 {len(posts)} 筆貼文，已寫入 {json_path}")
    except Exception as e:
        print(f"[!] 轉換失敗: {e}")

if __name__ == "__main__":
    main()
