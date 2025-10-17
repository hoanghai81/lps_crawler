from playwright.sync_api import sync_playwright
from lxml import etree, html as lh
import datetime, time

print("=== RUNNING CRAWLER (BRT HTV) ===")

URL = "https://brt.vn/truyen-hinh"

def fetch_brt_schedule():
    html_content = ""
    for attempt in range(3):
        print(f"Đang tải dữ liệu (lần {attempt+1}/3) từ {URL} ...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_default_navigation_timeout(90000)
                page.goto(URL, wait_until="networkidle")
                time.sleep(5)  # chờ JS render
                html_content = page.content()
                browser.close()
                if html_content:
                    print("✅ Tải thành công!")
                    break
        except Exception as e:
            print(f"⚠️ Lỗi khi tải (lần {attempt+1}): {e}")
            time.sleep(5)
    return html_content

def parse_schedule(html):
    doc = lh.fromstring(html)
    schedule = []

    # Cấu trúc phổ biến trên trang BRT hiện tại
    items = doc.xpath('//div[contains(@class,"epg-item") or contains(@class,"epg_row")]')
    if not items:
        print("⚠️ Không tìm thấy div.epg-item hoặc .epg_row, thử cấu trúc fallback ...")
        items = doc.xpath('//div[contains(@class,"schedule-item")]')

    for item in items:
        time_txt = item.xpath('.//div[contains(@class,"time") or contains(@class,"epg-time")]/text()')
        title_txt = item.xpath('.//div[contains(@class,"title") or contains(@class,"epg-title")]/text()')
        if time_txt and title_txt:
            time_str = time_txt[0].strip()
            title_str = title_txt[0].strip()
            if time_str and title_str:
                schedule.append((time_str, title_str))
    return schedule

def export_xml(schedule):
    tv = etree.Element("tv", attrib={
        "source-info-name": "brt.vn",
        "generator-info-name": "lps_crawler"
    })

    channel = etree.SubElement(tv, "channel", id="brthtv")
    etree.SubElement(channel, "display-name").text = "BRT HTV"

    today_str = datetime.datetime.now().strftime("%Y%m%d")
    for time_txt, title in schedule:
        clean_time = time_txt.replace(":", "").zfill(4)
        start_time = f"{today_str}{clean_time}00 +0700"
        programme = etree.SubElement(tv, "programme", attrib={
            "start": start_time,
            "channel": "brthtv"
        })
        etree.SubElement(programme, "title", lang="vi").text = title

    tree = etree.ElementTree(tv)
    tree.write("brthtv.xml", encoding="utf-8", xml_declaration=True, pretty_print=True)
    print(f"✅ Xuất thành công brthtv.xml ({len(schedule)} chương trình)")

if __name__ == "__main__":
    html = fetch_brt_schedule()
    if not html:
        print("❌ Không lấy được nội dung trang sau 3 lần thử.")
    else:
        schedule = parse_schedule(html)
        if schedule:
            export_xml(schedule)
        else:
            print("❌ Không tìm thấy chương trình trong bảng HTML.")
