from playwright.sync_api import sync_playwright
from lxml import etree, html as lh
import datetime, time

print("=== RUNNING CRAWLER (BRT HTV) ===")

URL = "https://brt.vn/truyen-hinh"

def fetch_brt_schedule():
    """Tải HTML bằng Chromium (render JS, retry 3 lần nếu lỗi)"""
    html_content = ""
    for attempt in range(3):
        print(f"Đang tải dữ liệu (lần {attempt+1}/3) từ {URL} ...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_default_navigation_timeout(90000)  # 90 giây
                page.goto(URL, wait_until="networkidle")
                time.sleep(5)  # chờ thêm JS render
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
    """Phân tích HTML để lấy lịch phát sóng"""
    doc = lh.fromstring(html)
    schedule = []
    rows = doc.xpath('//table//tr')
    for row in rows:
        cols = [c.strip() for c in row.xpath('.//td//text()') if c.strip()]
        if len(cols) >= 2:
            schedule.append((cols[0], cols[1]))
    return schedule

def export_xml(schedule):
    """Xuất ra file XMLTV chuẩn"""
    tv = etree.Element("tv", attrib={
        "source-info-name": "brt.vn",
        "generator-info-name": "lps_crawler"
    })

    channel = etree.SubElement(tv, "channel", id="brthtv")
    etree.SubElement(channel, "display-name").text = "BRT HTV"

    today_str = datetime.datetime.now().strftime("%Y%m%d")
    for time_txt, title in schedule:
        start_time = f"{today_str}{time_txt.replace(':','')}00 +0700"
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
