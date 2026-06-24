import os
import sys
import json
import csv
import time
import re
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

def load_config(config_path="config.json"):
    print(f"[*] 載入設定檔: {config_path}")
    if not os.path.exists(config_path):
        print(f"[!] 錯誤: 找不到設定檔 {config_path}，請確認檔案路徑是否正確。")
        sys.exit(1)
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[!] 錯誤: 解析設定檔失敗: {e}")
        sys.exit(1)

def check_and_parse_cookies(cookie_file_path):
    print(f"[*] 正在檢查 Cookie 檔案: {cookie_file_path}")
    if not os.path.exists(cookie_file_path):
        print(f"[!] 錯誤: 找不到 Cookie 檔案 {cookie_file_path}")
        sys.exit(1)
        
    try:
        with open(cookie_file_path, "r", encoding="utf-8") as f:
            cookies = json.load(f)
    except Exception as e:
        print(f"[!] 錯誤: 解析 JSON Cookie 失敗: {e}")
        sys.exit(1)
        
    if not isinstance(cookies, list):
        print("[!] 錯誤: Cookie 檔案格式錯誤，應為 JSON 陣列 (List)。")
        sys.exit(1)
        
    has_c_user = False
    has_xs = False
    for c in cookies:
        if not isinstance(c, dict):
            print("[!] 錯誤: Cookie 項目格式不符，必須為鍵值對 (Dictionary)。")
            sys.exit(1)
        name = c.get("name")
        if name == "c_user":
            has_c_user = True
            print(f"[+] 發現 c_user (Facebook 使用者 ID): {c.get('value')}")
        elif name == "xs":
            has_xs = True
            
    if not has_c_user or not has_xs:
        print("[!] 警告: 未在 Cookie 中發現 Facebook 的核心 Session 欄位 (c_user 或 xs)。這可能會導致無法登入！")
    else:
        print("[+] Cookie 基本結構檢查成功。")
        
    return cookies

def format_cookies_for_playwright(raw_cookies):
    playwright_cookies = []
    for c in raw_cookies:
        if "name" not in c or "value" not in c:
            continue
            
        cookie = {
            "name": str(c["name"]),
            "value": str(c["value"]),
            "domain": str(c.get("domain", ".facebook.com")),
            "path": str(c.get("path", "/")),
        }
        
        if "secure" in c:
            cookie["secure"] = bool(c["secure"])
        if "httpOnly" in c:
            cookie["httpOnly"] = bool(c["httpOnly"])
        if "expirationDate" in c:
            cookie["expires"] = float(c["expirationDate"])
            
        if "sameSite" in c and c["sameSite"] is not None:
            ss = str(c["sameSite"]).lower()
            if ss == "no_restriction":
                cookie["sameSite"] = "None"
            elif ss == "lax":
                cookie["sameSite"] = "Lax"
            elif ss == "strict":
                cookie["sameSite"] = "Strict"
            elif ss in ["none", "lax", "strict"]:
                cookie["sameSite"] = ss.capitalize()
                
        playwright_cookies.append(cookie)
    return playwright_cookies

def clean_fb_url(url):
    if not url:
        return ""
    parsed = urlparse(url)
    # 檢查是否為社團貼文網址
    if "/groups/" in parsed.path and ("/posts/" in parsed.path or "/permalink/" in parsed.path or "/multi_permalinks/" in parsed.path):
        return f"https://www.facebook.com{parsed.path}"
    return url

def scrape_group_posts(page, group_url, target_count=10):
    # 從社團網址中擷取社團 ID (例如 702305363575920)
    group_id_match = re.search(r'/groups/([^/?]+)', group_url)
    group_id = group_id_match.group(1) if group_id_match else ""
    
    print(f"\n[*] 正在開啟社團網址: {group_url}")
    try:
        page.goto(group_url, wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        print(f"[!] 無法載入網址 {group_url}: {e}")
        return []

    print("[*] 等待頁面貼文載入中...")
    page.wait_for_timeout(3000)  # 等待 JS 渲染

    # 階段一：滾動頁面收集貼文連結與發布者
    collected_posts = []
    seen_ids = set()
    no_change_count = 0
    max_scrolls = 40
    scroll_count = 0

    print("[*] 正在滾動社團首頁並收集貼文連結...")
    while len(collected_posts) < target_count and scroll_count < max_scrolls:
        current_collected_size = len(collected_posts)
        
        # 尋找所有的 H2 標題 (發布者姓名在 H2 內)
        h2_elements = page.locator("h2").all()
        
        for h2 in h2_elements:
            if len(collected_posts) >= target_count:
                break
                
            try:
                text = h2.inner_text().strip()
                if not text:
                    continue
                    
                # 排除非姓名之一般標題
                is_generic = any(w in text for w in ["貼文", "通知", "關於", "影音", "訊息", "撰寫", "搜尋", "相片", "活動", "成員", "檔案", "設定"])
                if is_generic or len(text) < 2:
                    continue
                    
                # 確認此 H2 內有使用者個人檔案連結 (含 /user/ 或 profile.php)
                has_user_link = h2.locator("a[href*='/user/'], a[href*='profile.php']").count() > 0
                if not has_user_link:
                    continue
                    
                # 清理發布者姓名
                publisher = text.split('\n')[0].split('·')[0].strip()
                
                # 使用 JS 向上回溯祖先元素，直到找到含有貼文 ID 的連結 (如 /posts/, /permalink/ 或 set=pcb.)
                res = h2.evaluate(r"""node => {
                    let p = node.parentElement;
                    let post_id = "";
                    let depth = 0;
                    
                    while (p && depth < 15) {
                        // 防錯邊界機制：若此父層包含多個 H2，表示已跨越貼文邊界進入 feed 層，立即中止回溯
                        let h2s = p.querySelectorAll('h2');
                        if (h2s.length > 1) {
                            break;
                        }
                        
                        let links = p.querySelectorAll('a');
                        for (let link of links) {
                            let href = link.href;
                            let m = href.match(/\/posts\/(\d+)/);
                            if (m) { post_id = m[1]; break; }
                            m = href.match(/\/permalink\/(\d+)/);
                            if (m) { post_id = m[1]; break; }
                            m = href.match(/set=pcb\.(\d+)/);
                            if (m) { post_id = m[1]; break; }
                        }
                        if (post_id) {
                            return { post_id, depth };
                        }
                        p = p.parentElement;
                        depth++;
                    }
                    return null;
                }""")
                
                if not res:
                    continue
                    
                post_id = res["post_id"]
                
                if post_id in seen_ids:
                    continue
                    
                # 取得該貼文的完整貼文連結
                post_url = f"https://www.facebook.com/groups/{group_id}/posts/{post_id}/"
                
                seen_ids.add(post_id)
                collected_posts.append({
                    "id": post_id,
                    "url": post_url,
                    "publisher": publisher
                })
                print(f"[+] 收集到貼文連結 {len(collected_posts)}: 發布者: {publisher} | 連結: {post_url}")
                
            except Exception:
                continue

        # 如果此輪滾動沒有收集到新連結，且我們已經收集到了一些連結，才累加計數器
        if len(collected_posts) == current_collected_size:
            if len(collected_posts) > 0:
                no_change_count += 1
        else:
            no_change_count = 0

        # 若連續 5 次滾動都沒有新增貼文連結，可能已經到底或載入受阻，提早結束
        if no_change_count >= 5:
            print("[*] 頁面似乎沒有新貼文連結載入，停止此社團滾動。")
            break

        # 滾動頁面載入更多
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        scroll_count += 1
        page.wait_for_timeout(2000)  # 等待載入

    print(f"[+] 連結收集完成，共收集到 {len(collected_posts)} 篇貼文連結。")

    # 階段二：逐一載入貼文頁面抓取完整內文
    scraped_posts = []
    print(f"\n[*] 階段二：開始逐一進入 {len(collected_posts)} 個貼文頁面抓取完整內容...")
    
    for idx, post in enumerate(collected_posts):
        post_url = post["url"]
        publisher = post["publisher"]
        post_id = post["id"]
        
        print(f"[*] 正在抓取貼文 {idx+1}/{len(collected_posts)}: {post_url} (發布者: {publisher})")
        try:
            page.goto(post_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(4000)  # 等待 JS 渲染
            
            # 嘗試點擊「顯示更多」/「查看更多」以展開極長貼文
            see_more_btn = page.locator('div[role="button"]:has-text("顯示更多"), div[role="button"]:has-text("查看更多"), span[role="button"]:has-text("顯示更多"), span[role="button"]:has-text("查看更多")')
            if see_more_btn.count() > 0 and see_more_btn.first.is_visible():
                try:
                    see_more_btn.first.click(timeout=1500)
                    page.wait_for_timeout(500)
                except Exception:
                    pass

            # 使用 JS 結合 H2 區段與 post_id 進行多層級精準內文提取
            content = page.evaluate("""({ publisher, post_id }) => {
                // Tier 1: 尋找標題含有發布者姓名的 H2 區段（例如 "廖偉証的貼文" 或 "Kuo Chen Tung 的貼文"）
                let h2s = Array.from(document.querySelectorAll('h2'));
                let targetH2 = h2s.find(h2 => h2.innerText && h2.innerText.includes(publisher));
                if (targetH2) {
                    let p = targetH2.parentElement;
                    let depth = 0;
                    while (p && depth < 20) {
                        let msg = p.querySelector('div[data-ad-rendering-role="story_message"], div[data-ad-comet-preview="message"], div[data-ad-preview="message"]');
                        if (msg) {
                            return msg.innerText;
                        }
                        p = p.parentElement;
                        depth++;
                    }
                }
                
                // Tier 2: 尋找含有該貼文 ID 連結的區塊，並限制回溯邊界以避免跨出貼文卡片
                let aElements = Array.from(document.querySelectorAll('a'));
                let matchingAnchors = aElements.filter(a => a.href && a.href.includes(post_id));
                for (let a of matchingAnchors) {
                    let p = a.parentElement;
                    let depth = 0;
                    while (p && depth < 20) {
                        let childH2s = p.querySelectorAll('h2');
                        if (childH2s.length > 1) {
                            break;
                        }
                        let msg = p.querySelector('div[data-ad-rendering-role="story_message"], div[data-ad-comet-preview="message"], div[data-ad-preview="message"]');
                        if (msg) {
                            return msg.innerText;
                        }
                        p = p.parentElement;
                        depth++;
                    }
                }
                
                // Tier 3: 最終 Fallback，抓取頁面中第一個匹配的 story message
                let firstMsg = document.querySelector('div[data-ad-rendering-role="story_message"], div[data-ad-comet-preview="message"], div[data-ad-preview="message"]');
                if (firstMsg) {
                    return firstMsg.innerText;
                }
                return "";
            }""", {"publisher": publisher, "post_id": post_id})
            
            content = content.strip() if content else ""
            
            scraped_posts.append({
                "url": post_url,
                "publisher": publisher,
                "content": content
            })
            print(f"[+] 成功抓取完整內文: 發布者: {publisher} | 字數: {len(content)}")
            
        except Exception as e:
            print(f"[!] 抓取貼文 {post_url} 失敗: {e}")
            # 為防程式中止，仍將已收集的資料加入（內文為空或錯誤）
            scraped_posts.append({
                "url": post_url,
                "publisher": publisher,
                "content": f"[抓取錯誤: {e}]"
            })
            continue

    print(f"[+] 此社團抓取完成，共抓取到 {len(scraped_posts)} 篇完整貼文。")
    return scraped_posts


def main():
    config = load_config()
    cookie_file = config.get("cookie_file", "facebook_cookie.json")
    headless = config.get("headless", False)
    group_urls = config.get("group_urls", [])
    output_file = config.get("output_file", "fb_posts_output.csv")
    
    if not group_urls:
        print("[!] 錯誤: 設定檔中沒有設定任何社團網址。")
        sys.exit(1)
        
    raw_cookies = check_and_parse_cookies(cookie_file)
    playwright_cookies = format_cookies_for_playwright(raw_cookies)
    
    all_results = []
    
    with sync_playwright() as p:
        print(f"[*] 正在啟動瀏覽器 (Headless: {headless})...")
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-notifications", "--mute-audio"]
        )
        
        # 使用自訂 User-Agent，並設定 viewport 大小
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        
        # 注入 Cookie
        print("[*] 正在注入 Cookie 登入 Facebook...")
        context.add_cookies(playwright_cookies)
        
        page = context.new_page()
        
        # 前往 Facebook 首頁進行登入驗證
        print("[*] 正在驗證登入狀態...")
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        
        # 檢查是否成功登入：
        # 如果頁面中包含登入表單（如 email 欄位），或網址包含 login，表示 Cookie 無效
        is_login_page = "login" in page.url or page.locator("input#email").count() > 0 or page.locator("input[name='email']").count() > 0
        if is_login_page:
            print("[!] 錯誤: Cookie 已失效或無效，Facebook 仍顯示登入畫面。")
            print("[!] 請重新從您的瀏覽器中匯出有效的 Cookie 檔案，並覆蓋 facebook_cookie.json。")
            browser.close()
            sys.exit(1)
            
        print("[+] 登入驗證成功！已進入 Facebook。")
        
        # 開始巡迴抓取每個社團
        for url in group_urls:
            posts = scrape_group_posts(page, url, target_count=10)
            all_results.extend(posts)
            
        browser.close()

    # 輸出成 CSV 檔案
    if all_results:
        print(f"\n[*] 正在輸出所有貼文至 {output_file}...")
        try:
            with open(output_file, "w", encoding="utf-8-sig", newline="") as csvfile:
                fieldnames = ["發布者", "貼文連結", "內文"]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for post in all_results:
                    writer.writerow({
                        "發布者": post["publisher"],
                        "貼文連結": post["url"],
                        "內文": post["content"]
                    })
            print(f"[+] 成功！已成功匯出 {len(all_results)} 篇貼文至 CSV。")
        except Exception as e:
            print(f"[!] 輸出 CSV 檔案失敗: {e}")

        # 同時輸出 JSON 檔案
        json_output_file = os.path.splitext(output_file)[0] + ".json"
        print(f"[*] 正在輸出所有貼文至 {json_output_file}...")
        try:
            json_posts = []
            for post in all_results:
                json_posts.append({
                    "publisher": post["publisher"],
                    "url": post["url"],
                    "content": post["content"]
                })
            with open(json_output_file, "w", encoding="utf-8") as jsonfile:
                json.dump(json_posts, jsonfile, indent=2, ensure_ascii=False)
            print(f"[+] 成功！已成功匯出 {len(all_results)} 篇貼文至 JSON。")
        except Exception as e:
            print(f"[!] 輸出 JSON 檔案失敗: {e}")
    else:
        print("[!] 警告: 未抓取到任何貼文，未建立輸出檔案。")

if __name__ == "__main__":
    main()
