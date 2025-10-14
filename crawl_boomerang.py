import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, date
import xml.etree.ElementTree as ET

BASE_URL = "https://info.msky.vn/vn/Boomerang.html?date={}"

def parse_date_str(s):
    """Chuyển 'dd/mm/yyyy' -> datetime.date"""
    return datetime.strptime(s, "%d/%m/%Y").date()

def fetch_schedule(date_str):
    """Tải và phân tích HTML theo ngày"""
    url = BASE_URL.format(date_str)
    print(f"Fetching: {url}")
    resp = requests.get(url)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.select("table tbody tr")

    programs = []
    for r in rows:
        cols = r.find_all("td")
        if len(cols) >= 2:
            time_str = cols[0].get_text(strip=True)
            title = cols[1].get_text(strip=True)
            # Bỏ qua dòng không có giờ hoặc tên
            if not time_str or not title:
                continue
            programs.append((time_str, title))
    return programs

def to_xmltv(programs_today, programs_tomorrow):
    """Tạo file XMLTV chuẩn"""
    tv = ET.Element("tv")

    ch = ET.SubElement(tv, "channel", id="boomerang.vn")
    ET.SubElement(ch, "display-name").text = "Boomerang"
    ET.SubElement(ch, "icon", src="https://upload.wikimedia.org/wikipedia/commons/3/3c/Boomerang_tv_logo.png")

    tz_offset = "+0700"
    all_programs = [("today", programs_today), ("tomorrow", programs_tomorrow)]

    for label, (date_str, programs) in all_programs:
        current_date = date_str  # ví dụ "14/10/2025"
        for i, (start_time, title) in enumerate(programs):
            if not start_time.strip():
                continue

            # Chuẩn hóa giờ (ví dụ "9:00" → "09:00")
            if len(start_time) == 4:
                start_time = "0" + start_time

            try:
                start_dt = datetime.strptime(f"{current_date} {start_time}", "%d/%m/%Y %H:%M")
            except ValueError:
                print(f"⚠️ Bỏ qua dòng lỗi: {current_date} {start_time}")
                continue

            if i + 1 < len(programs):
                next_time = programs[i + 1][0]
                if len(next_time) == 4:
                    next_time = "0" + next_time
                try:
                    stop_dt = datetime.strptime(f"{current_date} {next_time}", "%d/%m/%Y %H:%M")
                    if stop_dt <= start_dt:
                        stop_dt += timedelta(days=1)
                except ValueError:
                    stop_dt = start_dt + timedelta(hours=1)
            else:
                stop_dt = start_dt + timedelta(hours=1)

            prog = ET.SubElement(
                tv,
                "programme",
                start=start_dt.strftime("%Y%m%d%H%M%S ") + tz_offset,
                stop=stop_dt.strftime("%Y%m%d%H%M%S ") + tz_offset,
                channel="boomerang.vn"
            )
            ET.SubElement(prog, "title", lang="vi").text = title

    return tv


def main():
    today = date.today()
    tomorrow = today + timedelta(days=1)

    date_today_str = today.strftime("%d/%m/%Y")
    date_tomorrow_str = tomorrow.strftime("%d/%m/%Y")

    progs_today = fetch_schedule(date_today_str)
    progs_tomorrow = fetch_schedule(date_tomorrow_str)

    tv = to_xmltv((date_today_str, progs_today), (date_tomorrow_str, progs_tomorrow))
    tree = ET.ElementTree(tv)

    output_file = "boomerang.xml"
    tree.write(output_file, encoding="utf-8", xml_declaration=True)

    print(f"✅ Xuất thành công {output_file}")
    print(f"Hôm nay: {len(progs_today)} chương trình")
    print(f"Ngày mai: {len(progs_tomorrow)} chương trình")

    with open("counts.txt", "w", encoding="utf-8") as f:
        f.write(f"Today: {len(progs_today)}\n")
        f.write(f"Tomorrow: {len(progs_tomorrow)}\n")


if __name__ == "__main__":
    main()
    
