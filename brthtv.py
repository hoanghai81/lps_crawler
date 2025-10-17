import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz

def fetch_brt_html():
    url = "https://brt.vn/truyen-hinh"
    print(f"Đang tải dữ liệu từ {url} ...")
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'android', 'mobile': True})
    res = scraper.get(url, timeout=30)
    res.raise_for_status()
    return res.text

def parse_programs(html):
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if not table:
        print("❌ Không tìm thấy bảng chương trình!")
        return []

    programs = []
    rows = table.find_all("tr")
    tz = pytz.timezone("Asia/Ho_Chi_Minh")
    today = datetime.now(tz).date()

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 2:
            continue

        time_text = cols[0].get_text(strip=True)
        title = cols[1].get_text(" ", strip=True)

        try:
            start_dt = tz.localize(datetime.strptime(f"{today} {time_text}", "%Y-%m-%d %H:%M"))
        except Exception:
            continue

        programs.append({
            "start": start_dt,
            "title": title
        })

    print(f"✅ Tìm thấy {len(programs)} chương trình.")
    return programs

def write_xml(programs):
    tz = pytz.timezone("Asia/Ho_Chi_Minh")
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<tv source-info-name="brt.vn" generator-info-name="lps_crawler">',
        '  <channel id="brthtv">',
        '    <display-name>BRT HTV</display-name>',
        '  </channel>'
    ]

    for i, p in enumerate(programs):
        start_str = p["start"].strftime("%Y%m%d%H%M%S +0700")
        end_time = (programs[i + 1]["start"] if i + 1 < len(programs) else p["start"] + timedelta(minutes=30))
        end_str = end_time.strftime("%Y%m%d%H%M%S +0700")
        title = p["title"].replace("&", "&amp;")

        xml.append(f'  <programme start="{start_str}" stop="{end_str}" channel="brthtv">')
        xml.append(f'    <title lang="vi">{title}</title>')
        xml.append('  </programme>')

    xml.append('</tv>')

    with open("brthtv.xml", "w", encoding="utf-8") as f:
        f.write("\n".join(xml))

    print("✅ Đã tạo file brthtv.xml")

if __name__ == "__main__":
    print("=== RUNNING CRAWLER (BRT HTV) ===")
    try:
        html = fetch_brt_html()
        programs = parse_programs(html)
        if programs:
            write_xml(programs)
        else:
            print("❌ Không có chương trình nào để xuất.")
    except Exception as e:
        print(f"❌ Lỗi: {e}")
    print("=== DONE ===")
