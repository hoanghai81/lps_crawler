import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET
import xml.sax.saxutils as sax

CHANNEL_ID = "brthtv"
CHANNEL_NAME = "BRT HTV"
OUTPUT_FILE = "brthtv.xml"
VN_TZ = timezone(timedelta(hours=7))

def fetch_html():
    url = "https://brt.vn/truyen-hinh"
    print(f"Fetching: {url}")
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text

def parse_html(html):
    """Parse lịch chương trình từ HTML, trả về list các chương trình (start_dt, stop_dt, title)"""
    soup = BeautifulSoup(html, "html.parser")
    items = []
    # tìm bảng hoặc danh sách chứa lịch
    table = soup.find("table")
    if table:
        rows = table.find_all("tr")
        for row in rows[1:]:
            cols = row.find_all("td")
            if len(cols) >= 2:
                time_str = cols[0].get_text(strip=True)
                title = cols[1].get_text(strip=True)
                try:
                    base = datetime.now(VN_TZ).date()
                    dt = datetime.strptime(time_str, "%H:%M")
                    start_dt = datetime.combine(base, dt.time(), VN_TZ)
                except Exception as e:
                    print("⚠️ Time parse error:", time_str, e)
                    continue
                items.append({"start_dt": start_dt, "title": title})
    else:
        print("⚠️ Không tìm thấy bảng lịch")

    # Tính stop
    for i in range(len(items)):
        if i + 1 < len(items):
            items[i]["stop_dt"] = items[i+1]["start_dt"]
        else:
            items[i]["stop_dt"] = items[i]["start_dt"] + timedelta(minutes=30)
    return items

def build_xml(progs):
    tv = ET.Element("tv", {
        "source-info-name": "brt.vn",
        "generator-info-name": "lps_crawler"
    })
    ch = ET.SubElement(tv, "channel", {"id": CHANNEL_ID})
    ET.SubElement(ch, "display-name").text = CHANNEL_NAME

    for p in progs:
        ET.SubElement(tv, "programme", {
            "start": p["start_dt"].strftime("%Y%m%d%H%M%S +0700"),
            "stop": p["stop_dt"].strftime("%Y%m%d%H%M%S +0700"),
            "channel": CHANNEL_ID
        }).text = sax.escape(p["title"])

    tree = ET.ElementTree(tv)
    tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
    print(f"✅ Xuất thành công {OUTPUT_FILE} ({len(progs)} chương trình)")

if __name__ == "__main__":
    html = fetch_html()
    progs = parse_html(html)
    build_xml(progs)
