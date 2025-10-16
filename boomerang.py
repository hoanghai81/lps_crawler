import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

# =====================
# CONFIG
# =====================
CHANNEL_ID = "boomerang"
CHANNEL_NAME = "Boomerang"
SOURCE_NAME = "msky.vn"
BASE_URL = "https://info.msky.vn/vn/Boomerang.html?date={date}"

# =====================
# GET CURRENT DATE (VN TIME)
# =====================
VN_TZ = timezone(timedelta(hours=7))
today_vn = datetime.now(VN_TZ)
today_str = today_vn.strftime("%d/%m/%Y")
today_xml = today_vn.strftime("%Y%m%d")

# =====================
# FETCH PAGE
# =====================
print("=== RUNNING CRAWLER ===")
print(f"Fetching: {BASE_URL.format(date=today_str)}")

res = requests.get(BASE_URL.format(date=today_str), timeout=30)
res.encoding = "utf-8"
soup = BeautifulSoup(res.text, "html.parser")

table = soup.find("table")
if not table:
    print("⚠️ Không tìm thấy bảng EPG")
    programmes = []
else:
    programmes = []
    rows = table.find_all("tr")[1:]  # Bỏ tiêu đề
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 3:
            continue

        time_str = cols[0].get_text(strip=True)
        title_vi = cols[1].get_text(strip=True)
        title_en = cols[2].get_text(strip=True) if len(cols) > 2 else ""

        try:
            start_dt = datetime.strptime(f"{today_str} {time_str}", "%d/%m/%Y %H:%M")
            # Gán timezone VN
            start_dt = start_dt.replace(tzinfo=VN_TZ)
            if start_dt.hour < 4:
                # Nếu giờ < 4 thì coi là sáng hôm sau
                start_dt += timedelta(days=1)
        except:
            continue

        stop_dt = start_dt + timedelta(minutes=30)
        programmes.append({
            "start": start_dt,
            "stop": stop_dt,
            "title_vi": title_vi,
            "title_en": title_en,
        })

# =====================
# FILTER ONLY TODAY (0h–23h59)
# =====================
start_day = today_vn.replace(hour=0, minute=0, second=0, microsecond=0)
end_day = start_day + timedelta(days=1)
filtered = [
    p for p in programmes
    if start_day <= p["start"] < end_day
]

# =====================
# BUILD XMLTV
# =====================
tv = ET.Element("tv", {
    "source-info-name": SOURCE_NAME,
    "generator-info-name": "lps_crawler"
})

chan = ET.SubElement(tv, "channel", {"id": CHANNEL_ID})
ET.SubElement(chan, "display-name").text = CHANNEL_NAME

for p in filtered:
    prog = ET.SubElement(tv, "programme", {
        "start": p["start"].strftime("%Y%m%d%H%M%S +0700"),
        "stop": p["stop"].strftime("%Y%m%d%H%M%S +0700"),
        "channel": CHANNEL_ID
    })
    ET.SubElement(prog, "title", {"lang": "vi"}).text = p["title_vi"]
    if p["title_en"]:
        ET.SubElement(prog, "title", {"lang": "en"}).text = p["title_en"]

tree = ET.ElementTree(tv)
tree.write(f"{CHANNEL_ID}.xml", encoding="utf-8", xml_declaration=True)

print(f"✅ Tổng cộng: {len(filtered)} chương trình")
print(f"✅ Xuất thành công {CHANNEL_ID}.xml")
print("=== DONE ===")
