import requests
from bs4 import BeautifulSoup
from datetime import datetime
import xml.etree.ElementTree as ET

# =====================
# CONFIG
# =====================
URL = "https://angiangtv.vn/lich-phat-song/?ngay=2025-10-18&kenh=TV2"
CHANNEL_ID = "atv3"
CHANNEL_NAME = "An Giang 3"
OUTPUT_FILE = "atv3kg2.xml"
# =====================

print("=== RUNNING CRAWLER (AN GIANG 3) ===")
print(f"Đang lấy dữ liệu từ {URL} ...")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}
try:
    response = requests.get(URL, headers=headers, timeout=20)
    response.raise_for_status()
except Exception as e:
    print("❌ Lỗi khi tải trang:", e)
    exit()

soup = BeautifulSoup(response.text, "html.parser")

# Tìm bảng lịch
rows = soup.select("div.table div.tbl-row")

programs = []
for row in rows:
    time_tag = row.select_one(".time")
    prog_tag = row.select_one(".program")
    if time_tag and prog_tag:
        start = time_tag.get_text(strip=True)
        title = prog_tag.get_text(strip=True)
        programs.append((start, title))

print(f"✅ Tổng cộng: {len(programs)} chương trình")

# ====== GHI RA XML ======
tv = ET.Element("tv")
channel = ET.SubElement(tv, "channel", id=CHANNEL_ID)
ET.SubElement(channel, "display-name").text = CHANNEL_NAME

for t, title in programs:
    start_dt = datetime.strptime(f"2025-10-18 {t}", "%Y-%m-%d %H:%M")
    start_str = start_dt.strftime("%Y%m%d%H%M%S +0700")
    prog = ET.SubElement(tv, "programme", start=start_str, channel=CHANNEL_ID)
    ET.SubElement(prog, "title", lang="vi").text = title

ET.ElementTree(tv).write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
print(f"✅ Xuất thành công {OUTPUT_FILE}")
print("=== DONE ===")
