#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Crawler for Unbeaten (Sports)
- Source: https://www.tvpassport.com/tv-listings/stations/unbeaten/37456
- Produces unbeaten.xml (XMLTV)
- Convert schedule to Asia/Ho_Chi_Minh timezone
"""

import sys
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

CHANNEL_ID = "unbeaten"
CHANNEL_NAME = "Unbeaten"
BASE_URL = "https://www.tvpassport.com/tv-listings/stations/unbeaten/37456"
OUT_FILE = "unbeaten.xml"

TZ_US = ZoneInfo("America/New_York")  # TVPassport timezone
TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")  # Output timezone

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; lps_crawler/1.0; +https://github.com/hoanghai81/lps_crawler)"
}


def fetch_html():
    resp = requests.get(BASE_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("li.listing")
    programmes = []

    today = datetime.now(TZ_VN).date()

    for item in rows:
        time_el = item.select_one(".listingTime")
        title_el = item.select_one(".listingTitle")

        if not time_el or not title_el:
            continue

        t = time_el.get_text(strip=True)
        title = title_el.get_text(" ", strip=True)

        try:
            dt_us = datetime.strptime(t, "%I:%M %p").replace(tzinfo=TZ_US)
        except:
            continue

        dt_vn = dt_us.astimezone(TZ_VN).replace(year=today.year, month=today.month, day=today.day)

        if dt_vn.hour < 6:
            dt_vn += timedelta(days=1)

        programmes.append((dt_vn, title))

    programmes.sort(key=lambda x: x[0])
    return programmes


def build_xml(programmes):
    tv = ET.Element("tv", {
        "generator-info-name": "unbeaten-epg",
        "source-info-name": "tvpassport.com"
    })
    ch = ET.SubElement(tv, "channel", {"id": CHANNEL_ID})
    ET.SubElement(ch, "display-name").text = CHANNEL_NAME

    for i, (start_dt, title) in enumerate(programmes):
        if i + 1 < len(programmes):
            stop_dt = programmes[i + 1][0]
        else:
            stop_dt = start_dt.replace(hour=23, minute=59)

        start_str = start_dt.strftime("%Y%m%d%H%M%S") + " +0700"
        stop_str = stop_dt.strftime("%Y%m%d%H%M%S") + " +0700"

        p = ET.SubElement(tv, "programme", {
            "start": start_str,
            "stop": stop_str,
            "channel": CHANNEL_ID
        })

        ET.SubElement(p, "title", {"lang": "en"}).text = title

    return b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(tv, encoding="utf-8")


def main():
    print("=== RUNNING CRAWLER (UNBEATEN) ===")
    try:
        html = fetch_html()
    except Exception as e:
        print("❌ Error fetching page:", e)
        sys.exit(1)

    programmes = parse(html)

    xml_bytes = build_xml(programmes)
    with open(OUT_FILE, "wb") as f:
        f.write(xml_bytes)

    print(f"✅ {len(programmes)} programmes exported -> {OUT_FILE}")
    print("=== DONE ===")


if __name__ == "__main__":
    main()
