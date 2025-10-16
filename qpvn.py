import requests_html
from datetime import datetime, timedelta, timezone
from xml.etree.ElementTree import Element, SubElement, ElementTree

def fetch_qpvn():
    session = requests_html.HTMLSession()
    url = "https://qpvn.vn/tv.html"
    print(f"Fetching: {url}")
    r = session.get(url)
    r.html.render(timeout=30, sleep=3)
    items = r.html.find(".schedule-item, .list-schedule-item")

    programmes = []
    today = datetime.now(timezone(timedelta(hours=7)))
    date_str = today.strftime("%Y%m%d")

    for item in items:
        try:
            time_str = item.find(".time", first=True).text.strip()
            title_el = item.find(".title", first=True)
            title = title_el.text.strip() if title_el else "Chương trình"
            desc_el = item.find(".desc, .description", first=True)
            desc = desc_el.text.strip() if desc_el else ""

            start_dt = datetime.strptime(
                f"{today.strftime('%Y-%m-%d')} {time_str}", "%Y-%m-%d %H:%M"
            ).replace(tzinfo=timezone(timedelta(hours=7)))

            # tạm thời cộng 1h cho thời gian kết thúc
            stop_dt = start_dt + timedelta(hours=1)

            programmes.append({
                "start": start_dt.strftime("%Y%m%d%H%M%S %z"),
                "stop": stop_dt.strftime("%Y%m%d%H%M%S %z"),
                "title": title,
                "desc": desc
            })
        except Exception as e:
            print(f"⚠️ Parse error: {e}")
            continue

    return programmes


def export_xmltv(programmes, output_file="qpvn.xml"):
    tv = Element("tv")
    channel = SubElement(tv, "channel", id="qpvn1")
    SubElement(channel, "display-name").text = "QPVN"

    for p in programmes:
        prog = SubElement(
            tv, "programme", start=p["start"], stop=p["stop"], channel="qpvn1"
        )
        SubElement(prog, "title", lang="vi").text = p["title"]
        if p["desc"]:
            SubElement(prog, "desc", lang="vi").text = p["desc"]

    ElementTree(tv).write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"✅ Xuất thành công {output_file} ({len(programmes)} programmes)")


if __name__ == "__main__":
    programmes = fetch_qpvn()
    export_xmltv(programmes)
  
