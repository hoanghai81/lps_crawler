#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
import xml.sax.saxutils as sax
import sys

URL = "https://info.msky.vn/vn/Boomerang.html"
CHANNEL_XMLTV_ID = "Boomerang.msky"
DISPLAY_NAME = "Boomerang"
TZ_OFFSET = "+0700"

def fetch(url):
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.text

def extract_date(text):
    m = re.search(r'(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})', text)
    if m:
        d, m_, y = m.group(1), m.group(2), m.group(3)
        return datetime.strptime(f"{d}/{m_}/{y}", "%d/%m/%Y").date()
    return datetime.utcnow().date()

def parse_schedule(html):
    soup = BeautifulSoup(html, "html.parser")
    full = soup.get_text("\n")
    idx = full.find("Thời gian Tên chương trình")
    if idx < 0:
        return []
    end = full.find("Tin NÓNG", idx)
    if end < 0:
        end = len(full)
    block = full[idx:end]
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    items = []
    i = 0
    while i < len(lines):
        if re.match(r'^\d{1,2}:\d{2}$', lines[i]):
            time = lines[i]
            title_vn = lines[i+1] if i+1 < len(lines) else ""
            title_orig = lines[i+2] if i+2 < len(lines) else ""
            duration = ""
            # try a few next lines for duration
            for j in range(i+3, min(i+6, len(lines))):
                if re.match(r'^\d{1,2}:\d{2}$', lines[j]):
                    duration = lines[j]
                    break
            items.append({
                "time": time,
                "title_vn": title_vn,
                "title_orig": title_orig,
                "duration": duration
            })
        i += 1
    return items

def parse_duration(s):
    if not s:
        return 30
    s = s.strip()
    m = re.match(r'(\d+):(\d{2})', s)
    if not m:
        try:
            return int(s)
        except:
            return 30
    return int(m.group(1)) * 60 + int(m.group(2))

def fmt_dt(dt):
    return dt.strftime("%Y%m%d%H%M%S") + " " + TZ_OFFSET

def build_xml(items, date):
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<tv source-info-name="msky" generator-info-name="lps_crawler">')
    lines.append(f'  <channel id="{sax.escape(CHANNEL_XMLTV_ID)}"><display-name>{sax.escape(DISPLAY_NAME)}</display-name></channel>')
    for it in items:
        hh, mm = map(int, it["time"].split(":"))
        start = datetime.combine(date, datetime.min.time()) + timedelta(hours=hh, minutes=mm)
        dur = parse_duration(it.get("duration", ""))
        stop = start + timedelta(minutes=dur)
        lines.append(f'  <programme start="{fmt_dt(start)}" stop="{fmt_dt(stop)}" channel="{sax.escape(CHANNEL_XMLTV_ID)}">')
        lines.append(f'    <title lang="vi">{sax.escape(it.get("title_vn",""))}</title>')
        if it.get("title_orig"):
            lines.append(f'    <title lang="en">{sax.escape(it.get("title_orig",""))}</title>')
        lines.append('  </programme>')
    lines.append('</tv>')
    return "\n".join(lines)

def main():
    try:
        html = fetch(URL)
    except Exception as e:
        print(f"Error fetching URL: {e}", file=sys.stderr)
        sys.exit(1)
    dt = extract_date(html)
    items = parse_schedule(html)
    if not items:
        print("No schedule items parsed", file=sys.stderr)
        sys.exit(1)
    xml = build_xml(items, dt)
    print(xml)

if __name__ == "__main__":
    main()
  
