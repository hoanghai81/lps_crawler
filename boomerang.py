import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

# Giờ Việt Nam (UTC+7)
VN_TZ = timezone(timedelta(hours=7))

def fetch_epg(date_str):
    """
    Lấy EPG từ info.msky.vn cho ngày cụ thể (dd/mm/yyyy)
    """
    url = f"https://info.msky.vn/vn/Boomerang.html?date={date_str}"
    print(f"Fetching: {url}")
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    return resp.text

def parse_html_to_programs(html, base_date):
    """
    Parse HTML -> danh sách chương trình [(start_dt, stop_dt, title, desc)]
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"class": "tableEPG"})
    programs = []

    if not table:
        print("⚠️ Không tìm thấy bảng EPG")
        return programs

    rows = table.find_all("tr")
    for row in rows[1:]:  # bỏ header
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cols) < 2:
            continue

        time_str, title = cols[0], cols[1]
        desc = cols[2] if len(cols) > 2 else ""

        # Thời gian bắt đầu: HH:MM
        try:
            start_time = datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            continue

        start_dt = datetime.combine(base_date, start_time, VN_TZ)
        programs.append((start_dt, title, desc))

    # Tính giờ kết thúc (stop) bằng giờ bắt đầu kế tiếp
    result = []
    for i, (start_dt, title, desc) in enumerate(programs):
        if i < len(programs) - 1:
            stop_dt = programs[i + 1][0]
        else:
            stop_dt = start_dt + timedelta(minutes=30)  # chương trình cuối mặc định 30 phút
        result.append((start_dt, stop_dt, title, desc))

    return result


def generate_xmltv(programs, output_file="boomerang.xml"):
    tv = ET.Element("tv", attrib={"generator-info-name": "msky_crawler"})

    # Channel info
    ch = ET.SubElement(tv, "channel", id="cartoonito")
    ET.SubElement(ch, "display-name").text = "CARTOONITO"
    ET.SubElement(ch, "url").text = "https://info.msky.vn/vn/Boomerang.html"

    for start_dt, stop_dt, title, desc in programs:
        prog = ET.SubElement(
            tv,
            "programme",
            {
                "start": start_dt.strftime("%Y%m%d%H%M%S +0700"),
                "stop": stop_dt.strftime("%Y%m%d%H%M%S +0700"),
                "channel": "cartoonito",
            },
        )
        ET.SubElement(prog, "title", lang="vi").text = title
        ET.SubElement(prog, "desc", lang="vi").text = desc

    tree = ET.ElementTree(tv)
    ET.indent(tree, space="  ", level=0)
    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"✅ Xuất thành công {output_file} ({len(programs)} programmes)")


if __name__ == "__main__":
    print("=== RUNNING CRAWLER ===")
    today = datetime.now(VN_TZ).date()
    date_str = today.strftime("%d/%m/%Y")

    try:
        html = fetch_epg(date_str)
        programs = parse_html_to_programs(html, today)
        print(f"✅ Tổng cộng: {len(programs)} chương trình")
        generate_xmltv(programs)
    except Exception as e:
        print(f"⚠️ Lỗi: {e}")

    print("=== DONE ===")
