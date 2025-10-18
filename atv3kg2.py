import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

async def fetch_html(url):
    print(f"Đang tải dữ liệu (render JS) từ {url} ...")
    for attempt in range(3):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, timeout=90000, wait_until="networkidle")
                html = await page.content()
                await browser.close()
                print(f"✅ Tải thành công (lần {attempt+1})")
                return html
        except Exception as e:
            print(f"⚠️ Lỗi lần {attempt+1}: {e}")
            await asyncio.sleep(3)
    print("❌ Không thể tải trang sau 3 lần thử.")
    return None


def parse_programs(html):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        print("❌ Không tìm thấy bảng chương trình!")
        return []

    rows = table.find_all("tr")
    programmes = []
    for row in rows:
        cols = row.find_all("td")
        if len(cols) >= 2:
            time_str = cols[0].get_text(strip=True)
            title = cols[1].get_text(strip=True)
            if not time_str or not title:
                continue
            try:
                start_dt = datetime.strptime(time_str, "%H:%M")
                today = datetime.now(timezone(timedelta(hours=7)))
                start = today.replace(hour=start_dt.hour, minute=start_dt.minute, second=0, microsecond=0)
                programmes.append({
                    "start": start,
                    "title": title
                })
            except:
                continue
    return programmes


def export_xml(programmes, output_file):
    tv = ET.Element("tv", {
        "source-info-name": "angiangtv.vn",
        "generator-info-name": "lps_crawler"
    })

    channel = ET.SubElement(tv, "channel", {"id": "atv3kg2"})
    ET.SubElement(channel, "display-name").text = "AN GIANG 3"

    for p in programmes:
        prog = ET.SubElement(tv, "programme", {
            "start": p["start"].strftime("%Y%m%d%H%M%S +0700"),
            "channel": "atv3kg2"
        })
        ET.SubElement(prog, "title", {"lang": "vi"}).text = p["title"]

    tree = ET.ElementTree(tv)
    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"✅ Xuất thành công {output_file} ({len(programmes)} programmes)")


async def main():
    print("=== RUNNING CRAWLER (AN GIANG 3) ===")
    today = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d")
    url = f"https://angiangtv.vn/lich-phat-song/?ngay={today}&kenh=TV2"

    html = await fetch_html(url)
    if not html:
        print("❌ Không nhận được nội dung HTML.")
        print("=== DONE ===")
        return

    programmes = parse_programs(html)
    print(f"✅ Tổng cộng: {len(programmes)} chương trình")
    export_xml(programmes, "atv3kg2.xml")
    print("=== DONE ===")


if __name__ == "__main__":
    asyncio.run(main())
