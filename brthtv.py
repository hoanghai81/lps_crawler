import requests
from lxml import html, etree
from datetime import datetime, timedelta, timezone

print("=== RUNNING CRAWLER (BRT HTV) ===")

URL = "https://brt.vn/truyen-hinh"
JINA_PROXY = "https://r.jina.ai/" + URL  # dùng Jina AI proxy thay Browserless

try:
    print(f"Đang tải dữ liệu qua Jina AI proxy: {URL}")
    res = requests.get(JINA_PROXY, timeout=30)
    res.raise_for_status()
    page = res.text
except Exception as e:
    print(f"❌ Lỗi khi tải trang: {e}")
    page = ""

if not page.strip():
    print("❌ Không nhận được nội dung HTML.")
else:
    tree = html.fromstring(page)
    rows = tree.xpath('//div[contains(@class,"schedule")]//tr | //tr[contains(@class,"row") or .//td]')
    programmes = []

    for row in rows:
        time_text = "".join(row.xpath('.//time/text() | .//td[1]//text()')).strip()
        title = "".join(row.xpath('.//a/text() | .//td[2]//text()')).strip()
        if not time_text or not title:
            continue
        try:
            start_dt = datetime.strptime(time_text, "%H:%M").replace(
                year=datetime.now().year,
                month=datetime.now().month,
                day=datetime.now().day,
                tzinfo=timezone(timedelta(hours=7))
            )
        except:
            continue
        programmes.append((start_dt, title))

    print(f"✅ Tổng cộng: {len(programmes)} chương trình")

    tv = etree.Element("tv", source_info_name="brt.vn", generator_info_name="lps_crawler")
    channel = etree.SubElement(tv, "channel", id="brthtv")
    etree.SubElement(channel, "display-name").text = "BRT HTV"

    for i, (start, title) in enumerate(programmes):
        start_str = start.strftime("%Y%m%d%H%M%S +0700")
        stop_str = (programmes[i+1][0].strftime("%Y%m%d%H%M%S +0700") if i+1 < len(programmes)
                    else (start + timedelta(minutes=30)).strftime("%Y%m%d%H%M%S +0700"))
        prog = etree.SubElement(tv, "programme", start=start_str, stop=stop_str, channel="brthtv")
        etree.SubElement(prog, "title", lang="vi").text = title

    with open("brthtv.xml", "wb") as f:
        f.write(etree.tostring(tv, pretty_print=True, encoding="utf-8", xml_declaration=True))

    print("✅ Xuất thành công brthtv.xml")

print("=== DONE ===")
