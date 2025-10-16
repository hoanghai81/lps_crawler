import datetime
from requests_html import HTMLSession
import xml.etree.ElementTree as ET

def crawl_qpvn():
    url = "https://qpvn.vn/tv.html"
    channel_id = "qpvn1"
    channel_name = "QPVN"

    print(f"Fetching: {url}")

    session = HTMLSession()
    r = session.get(url)

    try:
        # Render toàn bộ trang – cho phép JS load lịch
        r.html.render(timeout=60, sleep=10)
    except Exception as e:
        print(f"⚠️ Render error: {e}")

    # thử vài selector phổ biến trên trang này
    selectors = [
        ".schedule-item",         # giả định
        ".item-schedule",         # dự phòng
        ".tv-schedule-item",      # dự phòng khác
        "li",                     # fallback
    ]

    programmes = []
    for sel in selectors:
        items = r.html.find(sel)
        if len(items) > 2:
            print(f"✅ Dò được selector: {sel} ({len(items)} items)")
            for it in items:
                try:
                    time_text = it.find("span.time", first=True).text.strip()
                    title = it.find("span.title", first=True).text.strip()
                    desc_el = it.find("span.description", first=True)
                    desc = desc_el.text.strip() if desc_el else ""

                    today = datetime.date.today().strftime("%Y%m%d")
                    start_dt = datetime.datetime.strptime(
                        f"{today} {time_text}", "%Y%m%d %H:%M"
                    )
                    stop_dt = start_dt + datetime.timedelta(minutes=30)  # tạm thời 30 phút

                    programmes.append({
                        "start": start_dt.strftime("%Y%m%d%H%M%S") + " +0700",
                        "stop": stop_dt.strftime("%Y%m%d%H%M%S") + " +0700",
                        "title": title,
                        "desc": desc
                    })
                except Exception as e:
                    print("⚠️ Parse error:", e)
            break

    print(f"✅ Tổng cộng: {len(programmes)} chương trình")

    # Xuất XMLTV
    tv = ET.Element("tv")
    channel = ET.SubElement(tv, "channel", id=channel_id)
    ET.SubElement(channel, "display-name").text = channel_name

    for p in programmes:
        pr = ET.SubElement(tv, "programme", start=p["start"], stop=p["stop"], channel=channel_id)
        ET.SubElement(pr, "title").text = p["title"]
        ET.SubElement(pr, "desc").text = p["desc"]

    ET.ElementTree(tv).write("qpvn.xml", encoding="utf-8", xml_declaration=True)
    print("✅ Xuất thành công qpvn.xml")

if __name__ == "__main__":
    crawl_qpvn()
        
