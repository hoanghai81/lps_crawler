import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone

def fetch_epg():
    today = datetime.now(timezone(timedelta(hours=7)))
    date_str = today.strftime("%Y-%m-%d")
    url = f"https://angiangtv.vn/lich-phat-song/?ngay={date_str}&kenh=TV2"
    print("=== RUNNING CRAWLER (AN GIANG 3) ===")
    print(f"Đang lấy dữ liệu từ {url} ...")

    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ Lỗi khi tải trang: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Các khung giờ nằm trong div.col-2, còn tên chương trình trong div.col-10
    times = [t.get_text(strip=True) for t in soup.select(".col-2")]
    titles = [t.get_text(strip=True) for t in soup.select(".col-10")]

    if not times or not titles or len(times) != len(titles):
        print("❌ Không tìm thấy dữ liệu chương trình hợp lệ!")
        return []

    programmes = []
    for i in range(len(times)):
        try:
            start = datetime.strptime(f"{date_str} {times[i]}", "%Y-%m-%d %H:%M")
            programmes.append({
                "start": start,
                "title": titles[i]
            })
        except Exception:
            continue

    print(f"✅ Tổng cộng: {len(programmes)} chương trình")
    return programmes


def export_xmltv(programmes):
    channel_id = "atv3kg2"
    display_name = "AN GIANG 3"

    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<tv source-info-name="angiangtv.vn" generator-info-name="lps_crawler">'
    ]
    xml.append(f'  <channel id="{channel_id}">')
    xml.append(f'    <display-name>{display_name}</display-name>')
    xml.append("  </channel>")

    for i, p in enumerate(programmes):
        start = p["start"].strftime("%Y%m%d%H%M%S +0700")
        end = (
            programmes[i + 1]["start"].strftime("%Y%m%d%H%M%S +0700")
            if i + 1 < len(programmes)
            else (p["start"] + timedelta(hours=1)).strftime("%Y%m%d%H%M%S +0700")
        )
        xml.append(f'  <programme start="{start}" stop="{end}" channel="{channel_id}">')
        xml.append(f'    <title lang="vi">{p["title"]}</title>')
        xml.append("  </programme>")

    xml.append("</tv>")

    with open("atv3kg2.xml", "w", encoding="utf-8") as f:
        f.write("\n".join(xml))

    print(f"✅ Xuất thành công atv3kg2.xml ({len(programmes)} programmes)")


if __name__ == "__main__":
    epg = fetch_epg()
    if epg:
        export_xmltv(epg)
    print("=== DONE ===")
