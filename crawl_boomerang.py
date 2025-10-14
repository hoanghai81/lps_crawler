import requests
import datetime
import xml.etree.ElementTree as ET

# Kênh cần crawl
CHANNEL_ID = "boomerang"
CHANNEL_NAME = "Boomerang"
CHANNEL_LOGO = "https://info.msky.vn/images/logo/Boomerang.png"

# Hàm lấy dữ liệu EPG từ API JSON
def fetch_epg(date_str):
    url = f"https://info.msky.vn/ajax/getepg.php?channel=Boomerang&date={date_str}"
    print(f"Fetching: {url}")
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json() if resp.text.strip() else []

# Hàm tạo XMLTV
def build_xmltv(programs_today, programs_tomorrow):
    tv = ET.Element("tv")
    channel = ET.SubElement(tv, "channel", id=CHANNEL_ID)
    ET.SubElement(channel, "display-name").text = CHANNEL_NAME
    ET.SubElement(channel, "icon", src=CHANNEL_LOGO)

    def add_programs(progs):
        for p in progs:
            start_time = p["time_start"]
            stop_time = p["time_end"]

            # Chuẩn hóa ngày giờ dạng XMLTV
            today = datetime.datetime.strptime(p["date"], "%d/%m/%Y").date()
            s_h, s_m = map(int, start_time.split(":"))
            e_h, e_m = map(int, stop_time.split(":"))

            start_dt = datetime.datetime.combine(today, datetime.time(s_h, s_m))
            end_dt = datetime.datetime.combine(today, datetime.time(e_h, e_m))

            start_fmt = start_dt.strftime("%Y%m%d%H%M%S +0700")
            end_fmt = end_dt.strftime("%Y%m%d%H%M%S +0700")

            programme = ET.SubElement(tv, "programme", {
                "start": start_fmt,
                "stop": end_fmt,
                "channel": CHANNEL_ID
            })

            ET.SubElement(programme, "title").text = p.get("title", "").strip()
            desc_text = p.get("desc", "").strip() or p.get("description", "")
            if desc_text:
                ET.SubElement(programme, "desc").text = desc_text

    add_programs(programs_today)
    add_programs(programs_tomorrow)

    tree = ET.ElementTree(tv)
    tree.write("boomerang.xml", encoding="utf-8", xml_declaration=True)
    print("✅ Xuất thành công boomerang.xml")

# === Main ===
today = datetime.date.today()
tomorrow = today + datetime.timedelta(days=1)

today_str = today.strftime("%d/%m/%Y")
tomorrow_str = tomorrow.strftime("%d/%m/%Y")

programs_today = fetch_epg(today_str)
programs_tomorrow = fetch_epg(tomorrow_str)

count_today = len(programs_today)
count_tomorrow = len(programs_tomorrow)

build_xmltv(programs_today, programs_tomorrow)

print(f"Hôm nay: {count_today} chương trình")
print(f"Ngày mai: {count_tomorrow} chương trình")
print("=== DONE ===")
            
