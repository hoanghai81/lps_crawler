import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

# ==============================
# Cấu hình
# ==============================
CHANNEL_ID = "cartoonito"
CHANNEL_NAME = "CARTOONITO"
BASE_URL = "https://info.msky.vn/vn/Boomerang.html?date={}"
TZ_OFFSET = "+0700"  # múi giờ Hà Nội

# ==============================
# Hàm crawl dữ liệu từng ngày
# ==============================
def fetch_day(date_str):
    """Truy xuất HTML và parse thành danh sách chương trình"""
    url = BASE_URL.format(date_str)
    print(f"Fetching: {url}")
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.select("table tr")[1:]  # bỏ hàng tiêu đề

    programmes = []
    for row in rows:
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cols) < 3:
            continue
        time_str, vi_title, en_title = cols[:3]
        start_dt = datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M")
        stop_dt = start_dt + timedelta(minutes=30)  # mặc định 30 phút nếu không rõ
        programmes.append({
            "start": start_dt.strftime("%Y%m%d%H%M%S ") + TZ_OFFSET,
            "stop": stop_dt.strftime("%Y%m%d%H%M%S ") + TZ_OFFSET,
            "title_vi": vi_title,
            "title_en": en_title or vi_title,
        })
    return programmes

# ==============================
# Hàm tạo file XMLTV
# ==============================
def create_xmltv(programmes, output_file="boomerang.xml"):
    tv = ET.Element("tv", {
        "source-info-name": "msky",
        "generator-info-name": "lps_crawler"
    })

    channel = ET.SubElement(tv, "channel", {"id": CHANNEL_ID})
    ET.SubElement(channel, "display-name").text = CHANNEL_NAME

    for prog in programmes:
        p = ET.SubElement(tv, "programme", {
            "start": prog["start"],
            "stop": prog["stop"],
            "channel": CHANNEL_ID
        })
        ET.SubElement(p, "title", {"lang": "vi"}).text = prog["title_vi"]
        ET.SubElement(p, "title", {"lang": "en"}).text = prog["title_en"]

    ET.ElementTree(tv).write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"✅ Xuất thành công {output_file} ({len(programmes)} programmes)")

# ==============================
# Main
# ==============================
if __name__ == "__main__":
    today = datetime.now().strftime("%d/%m/%Y")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")

    programmes = []
    for d in [today, tomorrow]:
        try:
            programmes.extend(fetch_day(d))
        except Exception as e:
            print(f"⚠️ Lỗi khi crawl {d}: {e}")

    create_xmltv(programmes)
    
