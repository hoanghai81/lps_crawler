#!/usr/bin/env python3
import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pytz
import traceback

CHANNEL_ID = "redbulltv"
CHANNEL_NAME = "Redbull TV"
OUTPUT_FILE = "docs/redbulltv.xml"

TIMEZONE = pytz.timezone("Asia/Ho_Chi_Minh")
API_URL = "https://www.redbull.com/int-en/epg.json"

def log(msg=""):
    print(msg, flush=True)

def ensure_dir(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def main():
    log("=== RUNNING CRAWLER (REDBULL TV) ===")

    try:
        r = requests.get(API_URL, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log(f"[!] API ERROR: {e}")
        return

    if "schedule" not in data:
        log("❌ No 'schedule' in response!")
        return

    schedule = data["schedule"]

    today = datetime.now(TIMEZONE).date()
    programmes = []

    for item in schedule:
        try:
            start = datetime.fromisoformat(item["start_time"].replace("Z", "+00:00")).astimezone(TIMEZONE)
            stop  = datetime.fromisoformat(item["end_time"].replace("Z", "+00:00")).astimezone(TIMEZONE)
        except:
            continue

        # Filter đúng ngày hôm nay theo giờ VN
        if start.date() != today:
            continue

        programmes.append({
            "start": start,
            "stop": stop,
            "title": item.get("title", "").strip(),
            "desc": item.get("short_description", "").strip()
        })

    log(f"✅ Found {len(programmes)} programmes for today")

    ensure_dir(OUTPUT_FILE)

    root = ET.Element("tv", {"generator-info-name": "redbulltv-crawler"})

    ch = ET.SubElement(root, "channel", id=CHANNEL_ID)
    dn = ET.SubElement(ch, "display-name")
    dn.text = CHANNEL_NAME

    for p in programmes:
        start_fmt = p["start"].strftime("%Y%m%d%H%M%S %z")
        stop_fmt = p["stop"].strftime("%Y%m%d%H%M%S %z")
        node = ET.SubElement(root, "programme", {
            "start": start_fmt,
            "stop": stop_fmt,
            "channel": CHANNEL_ID
        })
        t = ET.SubElement(node, "title")
        t.text = p["title"] or ""
        if p["desc"]:
            d = ET.SubElement(node, "desc")
            d.text = p["desc"]

    ET.ElementTree(root).write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)

    log(f"✅ Xuất thành công {OUTPUT_FILE}")
    log("=== DONE ===")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
