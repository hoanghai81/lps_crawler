#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Crawler for An Giang TV (ATV3 / KG2) — produce atv3kg2.xml (XMLTV)
- fetches https://angiangtv.vn/lich-phat-song/?ngay=YYYY-MM-DD&kenh=TV2
- parses rows .tbl-row -> .time and .program
- builds <programme start=... stop=... channel="atv3kg2">...
"""
import sys
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

# Config
CHANNEL_ID = "atv3kg2"
CHANNEL_NAME = "An Giang 3"
BASE_URL = "https://angiangtv.vn/lich-phat-song/"
OUT_FILE = "atv3kg2.xml"
TZ = ZoneInfo("Asia/Ho_Chi_Minh")  # +07:00

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; lps_crawler/1.0; +https://github.com/hoanghai81/lps_crawler)"
}

def fetch_html_for(date_obj: date):
    params = {"ngay": date_obj.strftime("%Y-%m-%d"), "kenh": "TV2"}
    resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text

def parse_rows(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    rows = soup.select("div.tbl-row")
    items = []
    for r in rows:
        t_el = r.select_one(".time")
        p_el = r.select_one(".program")
        if not t_el or not p_el:
            continue
        time_text = t_el.get_text(strip=True)
        prog_text = p_el.get_text(" ", strip=True)
        items.append((time_text, prog_text))
    return items

def make_dt_for(today: date, hhmm_str: str):
    s = hhmm_str.strip()
    parts = s.split(":")
    if len(parts) != 2:
        raise ValueError("Unknown time format: %r" % s)
    hh = int(parts[0])
    mm = int(parts[1])
    return datetime.combine(today, time(hour=hh, minute=mm)).replace(tzinfo=TZ)

def build_xml(programmes, for_date: date):
    tv = ET.Element("tv", {
        "generator-info-name": "lps_crawler",
        "source-info-name": "angiangtv.vn"
    })

    ch = ET.SubElement(tv, "channel", {"id": CHANNEL_ID})
    dn = ET.SubElement(ch, "display-name")
    dn.text = CHANNEL_NAME

    for i, (dt_start, title) in enumerate(programmes):
        if i + 1 < len(programmes):
            dt_stop = programmes[i + 1][0]
        else:
            next_day = (for_date + timedelta(days=1))
            dt_stop = datetime.combine(next_day, time(0, 0)).replace(tzinfo=TZ)

        start_str = dt_start.strftime("%Y%m%d%H%M%S") + " +0700"
        stop_str = dt_stop.strftime("%Y%m%d%H%M%S") + " +0700"
        p = ET.SubElement(tv, "programme", {
            "start": start_str,
            "stop": stop_str,
            "channel": CHANNEL_ID
        })
        t = ET.SubElement(p, "title", {"lang": "vi"})
        t.text = title

    xml_str = ET.tostring(tv, encoding="utf-8")
    return b"<?xml version=\"1.0\" encoding=\"utf-8\"?>\n" + xml_str

def main():
    # ✅ fix timezone issue: always use Vietnam time, not UTC
    today = datetime.now(TZ).date()

    try:
        print(f"=== RUNNING CRAWLER (AN GIANG 3) ===")
        print(f"Đang lấy dữ liệu từ {BASE_URL}?ngay={today.strftime('%Y-%m-%d')}&kenh=TV2 ...")
        html = fetch_html_for(today)
    except Exception as e:
        print("❌ Lỗi khi tải trang:", e)
        sys.exit(1)

    rows = parse_rows(html)
    if not rows:
        print("❌ Không tìm thấy bảng chương trình!")
        root = ET.Element("tv", {
            "generator-info-name": "lps_crawler",
            "source-info-name": "angiangtv.vn"
        })
        ch = ET.SubElement(root, "channel", {"id": CHANNEL_ID})
        ET.SubElement(ch, "display-name").text = CHANNEL_NAME
        out = b"<?xml version=\"1.0\" encoding=\"utf-8\"?>\n" + ET.tostring(root, encoding="utf-8")
        with open(OUT_FILE, "wb") as f:
            f.write(out)
        print(f"✅ Đã tạo file {OUT_FILE}")
        return

    prog_list = []
    for time_text, title in rows:
        try:
            dt = make_dt_for(today, time_text)
        except Exception as e:
            print("⚠️ Bỏ chương trình do format time không đúng:", time_text, title)
            continue
        prog_list.append((dt, title))

    prog_list.sort(key=lambda x: x[0])

    xml_bytes = build_xml(prog_list, today)
    with open(OUT_FILE, "wb") as f:
        f.write(xml_bytes)

    print(f"✅ Tổng cộng: {len(prog_list)} chương trình")
    print(f"✅ Xuất thành công {OUT_FILE}")

if __name__ == "__main__":
    main()
