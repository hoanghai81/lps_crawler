import requests
from bs4 import BeautifulSoup
from datetime import datetime, date, timedelta
import xml.etree.ElementTree as ET

CHANNEL_ID = "boomerang"
CHANNEL_NAME = "Boomerang"
CHANNEL_LOGO = "https://info.msky.vn/images/logo/Boomerang.png"

def fetch_html(date_str):
    url = f"https://info.msky.vn/vn/Boomerang.html?date={date_str}"
    print(f"Fetching: {url}")
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.text

def parse_schedule(html, current_date):
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select(".lichphatsong tbody tr")
    programs = []

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 2:
            continue
        time_str = cols[0].get_text(strip=True)
        title = cols[1].get_text(strip=True)
        desc = cols[1].get("title", "") or ""

        # Parse thời gian HH:MM
        try:
            t = datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            continue

        programs.append({
            "datetime": datetime.combine(current_date, t),
            "title": title,
            "desc": desc
        })

    return programs

def build_xmltv(progs_today, progs_tomorrow):
    tv = ET.Element("tv")
    channel = ET.SubElement(tv, "channel", id=CHANNEL_ID)
    ET.SubElement(channel, "display-name").text = CHANNEL_NAME
    ET.SubElement(channel, "icon", src=CHANNEL_LOGO)

    all_progs = progs_today + progs_tomorrow

    for i, p in enumerate(all_progs):
        start_dt = p["datetime"]
        if i + 1 < len(all_progs):
            end_dt = all_progs[i + 1]["datetime"]
        else:
            end_dt = start_dt + timedelta(hours=1)

        start_fmt = start_dt.strftime("%Y%m%d%H%M%S +0700")
        end_fmt = end_dt.strftime("%Y%m%d%H%M%S +0700")

        prog = ET.SubElement(tv, "programme", {
            "start": start_fmt,
            "stop": end_fmt,
            "channel": CHANNEL_ID
        })
        ET.SubElement(prog, "title").text = p["title"]
        if p["desc"]:
            ET.SubElement(prog, "desc").text = p["desc"]

    tree = ET.ElementTree(tv)
    tree.write("boomerang.xml", encoding="utf-8", xml_declaration=True)
    print("✅ Xuất thành công boomerang.xml")

def main():
    today = date.today()
    tomorrow = today + timedelta(days=1)

    dates = [today.strftime("%d/%m/%Y"), tomorrow.strftime("%d/%m/%Y")]
    all_progs_today, all_progs_tomorrow = [], []

    for idx, d in enumerate(dates):
        html = fetch_html(d)
        parsed = parse_schedule(html, today if idx == 0 else tomorrow)
        if idx == 0:
            all_progs_today = parsed
        else:
            all_progs_tomorrow = parsed

    build_xmltv(all_progs_today, all_progs_tomorrow)
    print(f"Hôm nay: {len(all_progs_today)} chương trình")
    print(f"Ngày mai: {len(all_progs_tomorrow)} chương trình")
    print("=== DONE ===")

if __name__ == "__main__":
    main()
        
