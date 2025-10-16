import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import xml.sax.saxutils as sax

CHANNEL_ID = "cartoonito"
CHANNEL_NAME = "CARTOONITO"
BASE_URL = "https://info.msky.vn/vn/Boomerang.html?date={}"
TZ_OFFSET = "+0700"

def fetch_day(date_str):
    """Lấy lịch phát sóng trong ngày từ HTML"""
    url = BASE_URL.format(date_str)
    print(f"Fetching: {url}")
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.select("table tr")[1:]  # bỏ header

    programmes = []
    for row in rows:
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cols) < 2:
            continue

        time_str = cols[0].strip()
        vi_title = cols[1].strip()
        en_title = cols[2].strip() if len(cols) >= 3 else vi_title
        desc = cols[3].strip() if len(cols) >= 4 else ""

        # Bỏ qua dòng không có giờ phát sóng
        if not time_str or ":" not in time_str:
            continue

        try:
            start_dt = datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M")
        except ValueError:
            print(f"⚠️ Lỗi định dạng thời gian: {date_str} {time_str}")
            continue

        # Mặc định 30 phút nếu không có cột thời lượng
        stop_dt = start_dt + timedelta(minutes=30)

        # Nếu giờ kết thúc nhỏ hơn giờ bắt đầu => qua nửa đêm
        if stop_dt < start_dt:
            stop_dt += timedelta(days=1)

        programmes.append({
            "start": start_dt.strftime("%Y%m%d%H%M%S ") + TZ_OFFSET,
            "stop": stop_dt.strftime("%Y%m%d%H%M%S ") + TZ_OFFSET,
            "title_vi": vi_title,
            "title_en": en_title,
            "desc": desc,
        })

    print(f"✅ {date_str}: {len(programmes)} chương trình")
    return programmes


def create_xmltv(programmes, output_file="boomerang.xml"):
    """Tạo file XMLTV hợp chuẩn"""
    tv = ET.Element("tv", {
        "source-info-name": "msky.vn",
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
        ET.SubElement(p, "title", {"lang": "vi"}).text = sax.escape(prog["title_vi"])
        ET.SubElement(p, "title", {"lang": "en"}).text = sax.escape(prog["title_en"])

        if prog["desc"]:
            ET.SubElement(p, "desc", {"lang": "vi"}).text = sax.escape(prog["desc"])

    ET.ElementTree(tv).write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"📦 Xuất thành công {output_file} ({len(programmes)} programmes)")


if __name__ == "__main__":
    today = datetime.now()
    tomorrow = today + timedelta(days=1)
    date_list = [
        today.strftime("%d/%m/%Y"),
        tomorrow.strftime("%d/%m/%Y")
    ]

    all_programmes = []
    for d in date_list:
        try:
            all_programmes.extend(fetch_day(d))
        except Exception as e:
            print(f"⚠️ Lỗi crawl {d}: {e}")

    create_xmltv(all_programmes)
    
