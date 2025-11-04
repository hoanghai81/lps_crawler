#!/usr/bin/env python3
# Crawler EPG cho Redbull TV — Xuất redbulltv.xml (XMLTV)

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

API_URL = "https://www.redbull.com/bigcontent/services/rb2/global/en-INT/channel/EPG"

def log(msg=""):
    print(msg, flush=True)

def fetch_epg():
    try:
        today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
        params = {
            "startDate": today,
            "endDate": today
        }
        r = requests.get(API_URL, params=params, timeout=30, headers={
            "User-Agent": "Mozilla/5.0"
        })
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log(f"[!] API ERROR: {e}")
        return None

def ensure_dir(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def main():
    log("=== RUNNING CRAWLER (REDBULL TV) ===")

    data = fetch_epg()
    if not data or "channel" not in data:
        log("❌ Không có dữ liệu!")
        return

    programmes = data.get("programs", [])
    log(f"✅ {len(programmes)} programmes fetched")

    ensure_dir(OUTPUT_FILE)

    root = ET.Element("tv", {"generator-info-name": "redbulltv-crawler"})

    # Channel metadata
    ch = ET.SubElement(root, "channel", id=CHANNEL_ID)
    dn = ET.SubElement(ch, "display-name")
    dn.text = CHANNEL_NAME

    # Parse and write programmes
    for p in programmes:
        try:
            start = datetime.fromtimestamp(p["start"]/1000, tz=TIMEZONE)
            stop = datetime.fromtimestamp(p["end"]/1000, tz=TIMEZONE)

            start_fmt = start.strftime("%Y%m%d%H%M%S %z")
            stop_fmt = stop.strftime("%Y%m%d%H%M%S %z")

            node = ET.SubElement(root, "programme", {
                "start": start_fmt,
                "stop": stop_fmt,
                "channel": CHANNEL_ID
            })

            t = ET.SubElement(node, "title")
            t.text = p.get("title", "")

            desc = ET.SubElement(node, "desc")
            desc.text = p.get("synopsis", "")
        except:
            traceback.print_exc()
            continue

    ET.ElementTree(root).write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
    log(f"✅ Xuất thành công {OUTPUT_FILE}")
    log("=== DONE ===")

if __name__ == "__main__":
    main()
