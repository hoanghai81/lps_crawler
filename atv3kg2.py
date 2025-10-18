import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

print("=== RUNNING CRAWLER (AN GIANG 3) ===")

# ---- CẤU HÌNH ----
tz = pytz.timezone("Asia/Ho_Chi_Minh")
today = datetime.now(tz)
date_str = today.strftime("%Y-%m-%d")
url = f"https://angiangtv.vn/lich-phat-song/?ngay={date_str}&kenh=TV2"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/117.0.0.0 Safari/537.36",
    "Referer": "https://angiangtv.vn/",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

print(f"Đang lấy dữ liệu từ {url} ...")

# ---- TẢI NỘI DUNG ----
try:
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
except Exception as e:
    print(f"❌ Lỗi khi tải trang: {e}")
    print("=== DONE ===")
    exit()

soup = BeautifulSoup(resp.text, "html.parser")

# ---- PHÂN TÍCH HTML ----
programs = []
rows = soup.select("table tbody tr")
if not rows:
    rows = soup.select("tbody tr")  # fallback nếu cấu trúc khác

for row in rows:
    cols = row.find_all("td")
    if len(cols) >= 2:
        time_str = cols[0].get_text(strip=True)
        title = cols[1].get_text(strip=True)
        if time_str and title:
            programs.append({"time": time_str, "title": title})

print(f"✅ Tổng cộng: {len(programs)} chương trình")

# ---- XUẤT XMLTV ----
tv = Element("tv", {
    "source-info-name": "angiangtv.vn",
    "generator-info-name": "lps_crawler"
})

channel = SubElement(tv, "channel", {"id": "atv3kg2"})
SubElement(channel, "display-name").text = "AN GIANG 3"

for i, p in enumerate(programs):
    try:
        # giờ bắt đầu
        start_time = datetime.strptime(p["time"], "%H:%M").replace(
            year=today.year, month=today.month, day=today.day
        )
        # giờ kết thúc = kế tiếp hoặc +30p
        if i + 1 < len(programs):
            next_time = datetime.strptime(programs[i + 1]["time"], "%H:%M").replace(
                year=today.year, month=today.month, day=today.day
            )
        else:
            next_time = start_time + timedelta(minutes=30)

        start_str = start_time.strftime("%Y%m%d%H%M%S +0700")
        stop_str = next_time.strftime("%Y%m%d%H%M%S +0700")

        prog = SubElement(tv, "programme", {
            "start": start_str,
            "stop": stop_str,
            "channel": "atv3kg2"
        })
        SubElement(prog, "title").text = p["title"]

    except Exception as e:
        print(f"⚠️ Lỗi khi parse {p}: {e}")

xml_str = minidom.parseString(tostring(tv, "utf-8")).toprettyxml(indent="  ")

with open("atv3kg2.xml", "w", encoding="utf-8") as f:
    f.write(xml_str)

print("✅ Xuất thành công atv3kg2.xml")
print("=== DONE ===")
