import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz

# --- Cấu hình cơ bản ---
CHANNEL_ID = "brthtv"
CHANNEL_NAME = "BRT HTV"
SOURCE_URL = "https://brt.vn/truyen-hinh"
OUTPUT_FILE = "brthtv.xml"

def fetch_programs():
    try:
        response = requests.get(SOURCE_URL, timeout=20)
        response.encoding = "utf-8"
    except Exception as e:
        print(f"❌ Lỗi tải trang: {e}")
        return []

    soup = BeautifulSoup(response.text, "lxml")

    # Tìm bảng chương trình trong thẻ <tbody>
    tbody = soup.find("tbody")
    if not tbody:
        print("❌ Không tìm thấy bảng chương trình!")
        return []

    rows = tbody.find_all("tr")
    if not rows:
        print("❌ Không tìm thấy hàng chương trình!")
        return []

    # Lấy ngày hiện tại (theo giờ Hà Nội)
    tz = pytz.timezone("Asia/Ho_Chi_Minh")
    today = datetime.now(tz).strftime("%Y%m%d")

    programs = []
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 2:
            continue

        time_text = cols[0].get_text(strip=True)
        title = cols[1].get_text(strip=True)

        # Định dạng thời gian
        try:
            start_time = datetime.strptime(time_text, "%H:%M")
        except:
            continue

        start_dt = tz.localize(datetime.now().replace(hour=start_time.hour, minute=start_time.minute, second=0, microsecond=0))
        start_str = start_dt.strftime("%Y%m%d%H%M%S %z")

        programs.append({
            "start": start_str,
            "title": title
        })

    return programs

def build_xml(programs):
    xml = []
    xml.append('<?xml version="1.0" encoding="UTF-8"?>')
    xml.append('<tv source-info-name="brt.vn" generator-info-name="lps_crawler">')
    xml.append(f'  <channel id="{CHANNEL_ID}">')
    xml.append(f'    <display-name>{CHANNEL_NAME}</display-name>')
    xml.append("  </channel>")

    for p in programs:
        xml.append(f'  <programme start="{p["start"]}" channel="{CHANNEL_ID}">')
        xml.append(f'    <title lang="vi">{p["title"]}</title>')
        xml.append("  </programme>")

    xml.append("</tv>")
    return "\n".join(xml)

def main():
    print(f"Đang lấy dữ liệu từ {SOURCE_URL} ...")
    programs = fetch_programs()

    if not programs:
        print("❌ Không có chương trình nào để xuất.")
        xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<tv source-info-name="brt.vn" generator-info-name="lps_crawler">\n  <channel id="{CHANNEL_ID}">\n    <display-name>{CHANNEL_NAME}</display-name>\n  </channel>\n</tv>'
    else:
        print(f"✅ Đã lấy {len(programs)} chương trình.")
        xml = build_xml(programs)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(xml)

    print(f"✅ Đã tạo file {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
