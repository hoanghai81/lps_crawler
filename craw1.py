#!/usr/bin/env python3
# craw1.py
"""
craw1.py
- Đọc list kênh từ kenh.txt (mỗi dòng: "id | url | name" hoặc chỉ URL)
- Crawl từng URL, trích giờ + tiêu đề bằng heuristics
- Sinh epg1.xml (xmltv) ở thư mục gốc
- Ghi channels_processed.txt và programmes_count.txt để workflow báo cáo
"""

import os
import re
import sys
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date, timedelta
from dateutil import parser as dateparser
import pytz
import xml.etree.ElementTree as ET

# Config
KENH_TXT = "kenh.txt"
OUTPUT = "epg1.xml"
TIMEZONE = "Asia/Ho_Chi_Minh"
DEFAULT_DURATION_MIN = 30
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36")

tz = pytz.timezone(TIMEZONE)

def load_channels_from_kenh_txt(path):
    if not os.path.exists(path):
        print(f"{path} not found", file=sys.stderr)
        return []
    chans = []
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            if "|" in ln:
                parts = [p.strip() for p in ln.split("|")]
                if len(parts) >= 2:
                    cid = parts[0]
                    url = parts[1]
                    name = parts[2] if len(parts) >= 3 else cid
                    chans.append({"id": cid, "url": url, "name": name})
                    continue
            if ln.startswith("http"):
                host = re.sub(r'https?://(www\.)?','', ln).split("/")[0]
                cid = host.replace(".", "_")
                chans.append({"id": cid, "url": ln, "name": cid})
            else:
                print(f"Skipping invalid line in {path}: {ln}", file=sys.stderr)
    return chans

def fetch(url):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8"
    }
    try:
        r = requests.get(url, headers=headers, timeout=25)
        r.raise_for_status()
        time.sleep(0.4)
        return r.content
    except Exception as e:
        print(f"fetch error {url}: {e}", file=sys.stderr)
        return b""

def parse_time_from_text(base_date, txt):
    txt = txt.strip()
    txt = txt.replace("h", ":").replace(".", ":")
    m = re.search(r'(\d{1,2}:\d{2})', txt)
    if not m:
        try:
            t = dateparser.parse(txt).time()
            return datetime.combine(base_date, t)
        except:
            return None
    try:
        t = dateparser.parse(m.group(1)).time()
        return datetime.combine(base_date, t)
    except:
        return None

def crawl_generic(url):
    html = fetch(url)
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")

    m = re.search(r"ngay=([0-9\-]+)", url)
    try:
        base_date = dateparser.parse(m.group(1)).date() if m else date.today()
    except:
        base_date = date.today()

    items = []
    selectors = [
        ".lich-item", ".lich-row", ".schedule-item", ".schedule .item",
        ".list-group-item", ".program-row", "ul.schedule li", "div.programme",
        "table tr", ".tg", ".time", ".thoigian"
    ]
    for sel in selectors:
        found = False
        for node in soup.select(sel):
            text = node.get_text(" ", strip=True)
            mtime = re.search(r'(\d{1,2}[:h\.]\d{2})', text)
            if not mtime:
                continue
            raw_time = mtime.group(1)
            time_text = raw_time.replace("h", ":").replace(".", ":")
            title = re.sub(re.escape(raw_time), "", text).strip()
            if not title:
                tn = node.select_one(".title, .tieu-de, .name")
                if tn:
                    title = tn.get_text(" ", strip=True)
            start_dt = parse_time_from_text(base_date, time_text)
            if start_dt:
                items.append({"start": start_dt, "title": title or "Unknown", "desc": ""})
                found = True
        if found:
            break

    if not items:
        for node in soup.find_all(text=re.compile(r'\d{1,2}[:h\.]\d{2}')):
            raw_time = node.strip()
            time_text = raw_time.replace("h", ":").replace(".", ":")
            parent = node.parent
            title = re.sub(re.escape(raw_time), "", parent.get_text(" ", strip=True)).strip()
            if not title:
                sib = parent.find_next_sibling()
                if sib:
                    title = sib.get_text(" ", strip=True)
            if not title:
                cand = node.find_next(string=lambda s: s and len(s.strip())>2 and not re.search(r'\d{1,2}[:h\.]\d{2}', s))
                if cand:
                    title = cand.strip()
            start_dt = parse_time_from_text(base_date, time_text)
            if start_dt:
                items.append({"start": start_dt, "title": title or "Unknown", "desc": ""})

    items = sorted(items, key=lambda x: x['start'])
    for i in range(len(items)-1):
        items[i]['stop'] = items[i+1]['start']
    if items and 'stop' not in items[-1]:
        items[-1]['stop'] = items[-1]['start'] + timedelta(minutes=DEFAULT_DURATION_MIN)

    return items

def build_xmltv(channels_programmes, outpath=OUTPUT):
    tv = ET.Element("tv", {"generator-info-name":"lps_crawler_v1"})
    for ch in channels_programmes:
        ch_el = ET.SubElement(tv, "channel", id=ch['id'])
        dn = ET.SubElement(ch_el, "display-name")
        dn.text = ch.get("name", ch['id'])
    total = 0
    for ch in channels_programmes:
        for p in ch.get("programmes", []):
            start = p['start']; stop = p.get('stop') or (p['start'] + timedelta(minutes=DEFAULT_DURATION_MIN))
            if start.tzinfo is None:
                start = tz.localize(start)
            if stop.tzinfo is None:
                stop = tz.localize(stop)
            prog = ET.SubElement(tv, "programme", {
                "start": start.strftime("%Y%m%d%H%M%S %z"),
                "stop": stop.strftime("%Y%m%d%H%M%S %z"),
                "channel": ch['id']
            })
            t = ET.SubElement(prog, "title", {"lang":"vi"})
            t.text = p.get("title", "Unknown")
            if p.get("desc"):
                d = ET.SubElement(prog, "desc", {"lang":"vi"})
                d.text = p.get("desc","")
            total += 1
    import xml.dom.minidom
    raw = ET.tostring(tv, encoding="utf-8")
    pretty = xml.dom.minidom.parseString(raw).toprettyxml(indent="  ", encoding="utf-8")
    with open(outpath, "wb") as f:
        f.write(pretty)
    return total

def main():
    chans = load_channels_from_kenh_txt(KENH_TXT)
    if not chans:
        print("No channels to process", file=sys.stderr)
        sys.exit(1)

    processed = []
    channels_programmes = []

    for ch in chans:
        cid = ch.get("id")
        url = ch.get("url")
        name = ch.get("name", cid)
        print(f"Crawling {cid} -> {url}")
        try:
            items = crawl_generic(url)
            # save debug HTML for angiang if present to help later debugging
            if "angiangtv.vn" in url:
                html = fetch(url)
                if html:
                    with open("angiang_debug.html", "wb") as fh:
                        fh.write(html)
        except Exception as e:
            print(f"Error crawling {url}: {e}", file=sys.stderr)
            items = []
        channels_programmes.append({"id": cid, "name": name, "programmes": items})
        processed.append(cid)
        time.sleep(0.3)

    total_programmes = build_xmltv(channels_programmes, outpath=OUTPUT)

    with open("channels_processed.txt", "w", encoding="utf-8") as f:
        for p in processed:
            f.write(p + "\n")
    with open("programmes_count.txt", "w", encoding="utf-8") as f:
        f.write(str(total_programmes))

    print(f"Done. channels={len(processed)} programmes={total_programmes}")
    sys.exit(0)

if __name__ == "__main__":
    main()
      
