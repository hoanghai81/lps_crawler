import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import xml.sax.saxutils as sax

# ====================================
# CONFIG
# ====================================
BASE_URL = "https://info.msky.vn/vn/Boomerang.html?date="
CHANNEL_ID = "cartoonito"
CHANNEL_NAME = "CARTOONITO"
OUTPUT_FILE = "boomerang.xml"
TZ_OFFSET = "+0700"


# ====================================
# HÀM CRAWL
# ====================================
def fetch_day(date_str):
    """Crawl 1 ngày từ trang Boomerang (dạng dd/mm/YYYY)"""
    url = BASE_URL + date_str
    print(f"Fetching: {url}")
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    rows = soup.select("table tr")
    items = []
    for tr in rows:
        tds = tr.find_all("td")
        if len(tds) >= 2:
            time_str = tds[0].get_text(strip=True)
            title_vi = tds[1].get_text(strip=True)
            if not time_str or not title_vi:
                continue
            items.append({
                "date_str": date_str,
                "time_str": time_str,
                "title_vi": title_vi,
                "title_en": title_vi,   # fallback
                "duration_min": None
            })
    return items


# ====================================
# HÀM XUẤT XMLTV (đã FIX rollover)
# ====================================
def create_xmltv(program_items, output_file=OUTPUT_FILE):
    tv = ET.Element("tv", {"source-info-name": "msky.vn", "generator-info-name": "lps_crawler"})
    ch = ET.SubElement(tv, "channel", {"id": CHANNEL_ID})
    ET.SubElement(ch, "display-name").text = CHANNEL_NAME

    last_dt = None
    programmes = []

    for item in program_items:
        date_str = item.get("date_str")
        time_str = item.get("time_str")
        title_vi = item.get("title_vi", "").strip()
        title_en = item.get("title_en", "").strip() or title_vi
        duration_min = item.get("duration_min")

        if not date_str or not time_str:
            continue

        time_str = time_str.strip()
        # thêm số 0 phía trước nếu giờ chỉ có 1 chữ số
        if len(time_str.split(":")[0]) == 1:
            time_str = "0" + time_str

        try:
            start_dt = datetime.strptime(f"{date_str.strip()} {time_str}", "%d/%m/%Y %H:%M")
        except Exception as e:
            print(f"⚠️ Bỏ qua dòng lỗi: {date_str} {time_str} ({e})")
            continue

        # nếu giờ nhỏ hơn giờ trước đó → đã sang ngày mới
        if last_dt is not None:
            while start_dt <= last_dt:
                start_dt += timedelta(days=1)

        programmes.append({
            "start_dt": start_dt,
            "title_vi": title_vi,
            "title_en": title_en,
            "duration_min": duration_min
        })

        last_dt = start_dt

    # tính giờ kết thúc (stop)
    for i, p in enumerate(programmes):
        start_dt = p["start_dt"]
        duration = p.get("duration_min")

        if duration and isinstance(duration, int) and duration > 0:
            stop_dt = start_dt + timedelta(minutes=duration)
        else:
            if i + 1 < len(programmes):
                stop_dt = programmes[i + 1]["start_dt"]
                if stop_dt <= start_dt:
                    stop_dt += timedelta(days=1)
            else:
                stop_dt = start_dt + timedelta(minutes=30)

        if stop_dt <= start_dt:
            stop_dt = start_dt + timedelta(minutes=30)

        prog = ET.SubElement(tv, "programme", {
            "start": start_dt.strftime("%Y%m%d%H%M%S ") + TZ_OFFSET,
            "stop": stop_dt.strftime("%Y%m%d%H%M%S ") + TZ_OFFSET,
            "channel": CHANNEL_ID
        })
        ET.SubElement(prog, "title", {"lang": "vi"}).text = sax.escape(p["title_vi"])
        ET.SubElement(prog, "title", {"lang": "en"}).text = sax.escape(p["title_en"])

    ET.ElementTree(tv).write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"✅ Xuất thành công {output_file} ({len(programmes)} programmes)")


# ====================================
# MAIN
# ====================================
def main():
    today = datetime.now().strftime("%d/%m/%Y")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")

    all_items = []
    for d in [today, tomorrow]:
        try:
            items = fetch_day(d)
            all_items.extend(items)
        except Exception as e:
            print(f"⚠️ Lỗi khi crawl {d}: {e}")

    print(f"✅ Tổng cộng: {len(all_items)} chương trình")

    create_xmltv(all_items, OUTPUT_FILE)


if __name__ == "__main__":
    print("=== RUNNING CRAWLER ===")
    main()
    print("=== DONE ===")
