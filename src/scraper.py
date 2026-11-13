import json
import time
import re
from playwright.sync_api import sync_playwright

def scrape_vegamovies():
    results = []
    
    with sync_playwright() as p:
        # हेडलेस ब्राउज़र लॉन्च करें (GitHub Actions के लिए ज़रूरी है)
        browser = p.chromium.launch(headless=True)
        
        # ब्राउज़र कॉन्टेक्स्ट सेट करें (Ads और बॉट ब्लॉकिंग से बचने के लिए)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        
        page = context.new_page()

        print("Level 1: मुख्य वेबसाइट पर जा रहे हैं...")
        try:
            page.goto("https://vegamovies.lease", timeout=60000)
            page.wait_for_selector(".poster-card", timeout=30000)
            time.sleep(2) # पेज लोड होने दें

            # सिर्फ पहले 2 पोस्ट्स के लिए
            post_cards = page.locator(".poster-card").all()[:2]

            for card in post_cards:
                post_data = {
                    "Title": "", "Image URL": "", 
                    "G-Direct Final Link": "", 
                    "V-Cloud Final Links": [], 
                    "Multi Final Links": []
                }

                try:
                    # Title और Image URL निकालें
                    post_data["Title"] = card.locator(".poster-title").inner_text().strip()
                    post_data["Image URL"] = card.locator(".poster-image img").get_attribute("src")
                    
                    # Post URL निकालें (पैरेंट <a> टैग से)
                    post_url = card.locator("xpath=..").get_attribute("href")
                    print(f"स्क्रैप कर रहे हैं: {post_data['Title']}")

                    print(f"  Level 2: पोस्ट पेज पर जा रहे हैं... ({post_url})")
                    page.goto(post_url, timeout=60000)
                    time.sleep(3)

                    # Post Page पर nexdrive लिंक ढूँढें
                    nexdrive_link = None
                    links = page.locator("a").all()
                    for link in links:
                        href = link.get_attribute("href")
                        if href and "nexdrive" in href:
                            nexdrive_link = href
                            break

                    if nexdrive_link:
                        print(f"  Level 3: Nexdrive पेज पर जा रहे हैं... ({nexdrive_link})")
                        page.goto(nexdrive_link, timeout=60000)
                        time.sleep(3) # लिंक लोड होने का इंतज़ार करें

                        # G-Direct लिंक हैंडल करें
                        try:
                            print("    G-Direct का लिंक निकाल रहे हैं...")
                            with page.context.expect_page(timeout=10000) as new_page_info:
                                page.locator("a:has-text('G-Direct'), a:has-text('GDIRECT'), a:has-text('G-Direct')").first.click()
                            new_tab = new_page_info.value
                            new_tab.wait_for_load_state()
                            post_data["G-Direct Final Link"] = new_tab.url
                            new_tab.close()
                        except Exception as e:
                            print(f"    G-Direct Error: {e}")

                        # V-Cloud लिंक हैंडल करें
                        try:
                            print("    V-Cloud के लिंक्स निकाल रहे हैं...")
                            with page.context.expect_page(timeout=10000) as new_page_info:
                                page.locator("a:has-text('V-Cloud'), a:has-text('VCloud')").first.click()
                            new_tab = new_page_info.value
                            new_tab.wait_for_load_state()
                            time.sleep(3)
                            
                            # V-Cloud पेज से सारे लिंक निकालें
                            v_links = []
                            anchors = new_tab.locator("a").all()
                            for a in anchors:
                                href = a.get_attribute("href")
                                if href and href.startswith("http") and "t.me" not in href and "telegram" not in href.lower():
                                    if href not in v_links:
                                        v_links.append(href)
                            post_data["V-Cloud Final Links"] = v_links[:5] # सिर्फ 5 लिंक तक
                            new_tab.close()
                        except Exception as e:
                            print(f"    V-Cloud Error: {e}")

                        # Multi लिंक हैंडल करें
                        try:
                            print("    Multi के लिंक्स निकाल रहे हैं...")
                            with page.context.expect_page(timeout=10000) as new_page_info:
                                page.locator("a:has-text('Multi')").first.click()
                            new_tab = new_page_info.value
                            new_tab.wait_for_load_state()
                            time.sleep(3)
                            
                            m_links = []
                            anchors = new_tab.locator("a").all()
                            for a in anchors:
                                href = a.get_attribute("href")
                                if href and href.startswith("http") and "t.me" not in href and "telegram" not in href.lower():
                                    if href not in m_links:
                                        m_links.append(href)
                            post_data["Multi Final Links"] = m_links[:5]
                            new_tab.close()
                        except Exception as e:
                            print(f"    Multi Error: {e}")

                    else:
                        print("  Nexdrive लिंक नहीं मिला।")
                        
                except Exception as e:
                    print(f"पोस्ट स्क्रैप करने में एरर: {e}")
                
                # डेटा को लिस्ट में जोड़ें
                results.append(post_data)
                
        except Exception as e:
            print(f"मुख्य पेज एरर: {e}")

        browser.close()
        
    # डेटा को JSON में सेव करें
    with open("api/latest.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)
    
    print("स्क्रैपिंग सफलतापूर्वक पूरी हुई!")

if __name__ == "__main__":
    scrape_vegamovies()
