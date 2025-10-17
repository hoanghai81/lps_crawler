import time
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import xml.etree.ElementTree as ET

# Cấu hình
URL = "https://brt.vn/truyen-hinh"
CHANNEL_ID = "brthtv"
CHANNEL_NAME = "BRT HTV"
OUTPUT = "brthtv.xml"
VN_TZ = timezone(timedelta(hours=7))

print("=== RUNNING CRAWLER (BRT HTV) ===")
print(f"Đang tải dữ liệu từ {URL} ...")

# Thiết lập trình duyệt headless
options = Options()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=options)
driver.get(URL)
time.sleep(5)  # chờ trang load JS

html = driver.page_source
driver.quit()

soup = BeautifulSoup(html, "html.parser")

# Tìm bảng chương trình
table = soup.find("table")
if not table:
    print("❌ Không tìm thấy bảng chương trình!")
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(f'<tv source-info-name="brt.vn" generator-info-name="lps_crawler">\n')
        f.write(f'  <channel id="{CHANNEL_ID}">\n')
        f.write(f'    <display-name>{CHANNEL_NAME}</display-name>\n')
        f.write(f'  </channel>\n</tv>')
    print(f"✅ Đã tạo file {OUTPUT}")
    print("=== DONE ===")
    exit()

rows = table.find_all("tr")
programmes = []
today = datetime.now(VN_TZ).date()

for row in rows:
    cols = row.find_all("td")
    if len(cols) >= 2:
        time_text = cols[0].get_text(strip=True)
        title = cols[1].get_text(strip=True)
        try:
            start = datetime.strptime(time_text, "%H:%M").replace(
                year=today.year, month=today.month, day=today.day, tzinfo=VN_TZ
            )
            programmes.append((start, title))
        except Exception:
            continue

if not programmes:
    print("❌ Không có chương trình nào để xuất.")
else:
    print(f"✅ Tổng cộng: {len(programmes)} chương trình")

# Xuất XMLTV
tv = ET.Element("tv", {"source-info-name": "brt.vn", "generator-info-name": "lps_crawler"})
channel = ET.SubElement(tv, "channel", {"id": CHANNEL_ID})
ET.SubElement(channel, "display-name").text = CHANNEL_NAME

for i, (start, title) in enumerate(programmes):
    prog = ET.SubElement(
        tv, "programme",
        {
            "start": start.strftime("%Y%m%d%H%M%S %z"),
            "channel": CHANNEL_ID,
        },
    )
    ET.SubElement(prog, "title", {"lang": "vi"}).text = title

tree = ET.ElementTree(tv)
tree.write(OUTPUT, encoding="utf-8", xml_declaration=True)

print(f"✅ Đã tạo file {OUTPUT}")
print("=== DONE ===")
