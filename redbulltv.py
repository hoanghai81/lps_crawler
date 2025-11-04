#!/usr/bin/env python3
import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import pytz
import traceback

CHANNEL_ID = "redbulltv"
CHANNEL_NAME = "Red Bull TV"
OUTPUT_FILE = "docs/redbulltv.xml"
TIMEZONE = pytz.timezone("Asia/Ho_Chi_Minh")

API_URL = "https://www.redbull.com/int-en/epg.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json",
    "Referer": "https://www.redbull.com/"
}

def log(msg):
    print(msg, flush=True)

def ensure_dir(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def main():
    log("=== RUNNING CRAWLER (REDBULL TV) ===")

    try:
        r = requests.get(API_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        txt = r.text.strip()
        if not txt.startswith("{"):
            raise ValueError("Response is not JSON")
        data = r.json()
    except Exception as e:
        log(f"[!] API ERROR: {e}")
        return

    if "items" not in data:
        log("❌ No 'items' in response!")
        return

    schedules = data.get("items", [])
    if not schedules:
        log("❌ Empty schedule list")
        return

    today = datetime.now(TIMEZONE).date()
    programmes = []

    for item in schedules:
        try:
            start_utc = datetime.fromisoformat(item["start"].replace("Z", "+00:00"))
            stop_utc  = datetime.fromisoformat(item["end"].replace("Z", "+00:00"))
            start = start_utc.astimezone(TIMEZONE)
            stop = stop_utc.astimezone(TIMEZONE)
        except:
            continue

        if start.date() != today:
            continue

        programmes.append({
            "start": start,
            "stop": stop,
            "title": item.get("title", "").strip(),
            "desc": item.get("description", "").strip()
        })

    log(f"✅ {len(programmes)} programmes found")

    ensure_dir(OUTPUT_FILE)
    root = ET.Element("tv", {"generator-info-name": "rbtv-epg"})

    ch = ET.SubElement(root, "channel", id=CHANNEL_ID)
    dn = ET.SubElement(ch, "display-name")
    dn.text = CHANNEL_NAME

    for p in programmes:
        p_el = ET.SubElement(
            root, "programme",
            start=p["start"].strftime("%Y%m%d%H%M%S %z"),
            stop=p["stop"].strftime("%Y%m%d%H%M%S %z"),
            channel=CHANNEL_ID
        )
        t = ET.SubElement(p_el, "title")
        t.text = p["title"]
        if p["desc"]:
            d = ET.SubElement(p_el, "desc")
            d.text = p["desc"]

    ET.ElementTree(root).write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)

    log(f"✅ Xuất thành công {OUTPUT_FILE}")
    log("=== DONE ===")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
