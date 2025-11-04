#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

CHANNEL_ID = "unbeaten"
CHANNEL_NAME = "Unbeaten"
STATION_ID = "37456"
OUT_FILE = "unbeaten.xml"

TZ_US = ZoneInfo("America/New_York")
TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")

API_URL = f"https://www.tvpassport.com/api/stations/{STATION_ID}/listings?date="
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.tvpassport.com/",
}


def fetch_json(date):
    url = API_URL + date
    print("📡 API:", url)
    resp = requests.get(url, headers=HEADERS, timeout=30)

    if resp.status_code == 404:
        print("⚠️ Data not ready for", date)
        return None

    resp.raise_for_status()
    return resp.json()


def build_xml(programmes):
    tv = ET.Element("tv")
    ch = ET.SubElement(tv, "channel", {"id": CHANNEL_ID})
    ET.SubElement(ch, "display-name").text = CHANNEL_NAME

    for prog in programmes:
        start_str = prog["start"].strftime("%Y%m%d%H%M%S") + " +0700"
        stop_str = prog["stop"].strftime("%Y%m%d%H%M%S") + " +0700"

        p = ET.SubElement(tv, "programme", {
            "start": start_str,
            "stop": stop_str,
            "channel": CHANNEL_ID
        })
        ET.SubElement(p, "title", {"lang": "en"}).text = prog["title"]
        if prog.get("desc"):
            ET.SubElement(p, "desc", {"lang": "en"}).text = prog["desc"]

    return b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(tv, encoding="utf-8")


def main():
    today_us = datetime.now(TZ_US).date()
    date_str = today_us.strftime("%Y-%m-%d")

    json_data = fetch_json(date_str)

    # Retry fallback: lùi thêm 1 ngày nếu chưa có
    if not json_data:
        fallback_date = today_us - timedelta(days=1)
        date_str = fallback_date.strftime("%Y-%m-%d")
        print("🔁 Try fallback:", date_str)
        json_data = fetch_json(date_str)

    if not json_data:
        print("❌ No data available -> export 0 programmes")
        with open(OUT_FILE, "wb") as f:
            f.write(build_xml([]))
        return

    programmes = []
    for item in json_data:
        title = item.get("title", "Unknown")
        desc = item.get("description")

        start = datetime.fromisoformat(item["startTime"]).replace(tzinfo=TZ_US)
        end = datetime.fromisoformat(item["endTime"]).replace(tzinfo=TZ_US)

        programmes.append({
            "title": title,
            "desc": desc,
            "start": start.astimezone(TZ_VN),
            "stop": end.astimezone(TZ_VN)
        })

    xml_bytes = build_xml(programmes)
    with open(OUT_FILE, "wb") as f:
        f.write(xml_bytes)

    print(f"✅ {len(programmes)} shows exported -> {OUT_FILE}")


if __name__ == "__main__":
    main()
