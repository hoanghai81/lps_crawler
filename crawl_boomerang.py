#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
import xml.sax.saxutils as sax
import sys

BASE_URL = "https://info.msky.vn/vn/Boomerang.html"
CHANNEL_XMLTV_ID = "Boomerang.msky"
DISPLAY_NAME = "Boomerang"
TZ_OFFSET = "+0700"

def fetch(url):
    resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return resp.text

def parse_date_str(s):
    """Chuyển 'dd/mm/yyyy' -> datetime.date"""
    return datetime.strptime(s, "%d/%m/%Y").date()

def extract_date(soup):
    text = soup.get_text(" ")
    m = re.search(r'(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})', text)
    if m:
        return parse_date_str(f"{m.group(1)}/{m.group(2)}/{m.group(3)}")
    return datetime.utcnow().date()

def parse_schedule(html):
    soup = BeautifulSoup(html, "html.parser")
    date = extract_date(soup)
    table = soup.find("table")
    if not table:
        return [], date

    items = []
    for tr in table.find_all("tr"):
        tds = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(tds) < 2:
            continue
        time_str = tds[0]
        title_vn = tds[1]
        title_orig = tds[2] if len(tds) >= 3 else ""
        duration = ""
        if len(tds) >= 4 and re.match(r'^\d+:\d{2}$', tds[3]):
            duration = tds[3]
        if re.match(r'^\d{1,2}:\d{2}$', time_str):
            items.append({
                "time": time_str,
                "title_vn": title_vn,
                "title_orig": title_orig,
                "duration": duration,
                "date": date
            })
    return items, date

def parse_duration(s):
    if not s:
        return 30
    m = re.match(r'(\d+):(\d{2})', s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    try:
        return int(s)
    except:
        return 30

def fmt_dt(dt):
    return dt.strftime("%Y%m%d%H%M%S") + " " + TZ_OFFSET

def build_xml(all_items):
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<tv source-info-name="msky" generator-info-name="lps_crawler">')
    lines.append(f'  <channel id="{sax.escape(CHANNEL_XMLTV_ID)}"><display-name>{sax.escape(DISPLAY_NAME)}</display-name></channel>')

    for it in all_items:
        hh, mm = map(int, it["time"].split(":"))
        start = datetime.combine(it["date"], datetime.min.time()) + timedelta(hours=hh, minutes=mm)
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
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    dates = [today, tomorrow]
    all_items = []

    for d in dates:
        date_str = d.strftime("%d/%m/%Y")
        url = f"{BASE_URL}?date={date_str}"
        print(f"Fetching schedule for {date_str}...", file=sys.stderr)
        html = fetch(url)
        items, date = parse_schedule(html)
        if items:
            all_items.extend(items)
        else:
            print(f"No items found for {date_str}", file=sys.stderr)

    if not all_items:
        print("No schedule items parsed", file=sys.stderr)
        sys.exit(1)

    xml = build_xml(all_items)
    print(xml)

if __name__ == "__main__":
    main()
    
