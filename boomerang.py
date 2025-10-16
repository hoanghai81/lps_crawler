#!/usr/bin/env python3
"""
Generate boomerang.xml (XMLTV) for CARTOONITO (channel id: cartoonito)
Source: https://info.msky.vn/vn/Boomerang.html

Behavior:
- Fetches the source page and looks for a markdown-style table or lines with
  time | title | original_title | duration.
- Builds XMLTV with timezone +0700 and writes boomerang.xml in current dir.
- Handles midnight rollover: times that decrease are considered next day.
- Default duration: 30 minutes if not parseable.
"""

import re
import sys
from datetime import datetime, date, time, timedelta
import requests
from bs4 import BeautifulSoup
from dateutil import tz, parser as dateparser
import html
import xml.etree.ElementTree as ET

SOURCE_URL = "https://info.msky.vn/vn/Boomerang.html"
CHANNEL_ID = "cartoonito"
CHANNEL_NAME = "CARTOONITO"
OUTPUT_FILE = "boomerang.xml"
DEFAULT_DURATION_MIN = 30
TZ_STR = "+0700"

def fetch_page(url):
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.text

def extract_table_text(html_text):
    """
    Try to extract a markdown-style table or plain text schedule from page.
    Returns list of rows as lists of cells.
    """
    soup = BeautifulSoup(html_text, "lxml")
    # Prefer any <pre> or <table> or main content
    # 1) raw text blocks
    candidates = []
    for tag in soup.find_all(["pre", "code"]):
        txt = tag.get_text("\n", strip=True)
        if "|" in txt:
            candidates.append(txt)
    # 2) markdown-like in page content
    main = soup.get_text("\n", strip=True)
    if "|" in main:
        candidates.append(main)

    if not candidates:
        return []

    # pick the largest candidate containing 'Thời gian' or many '|' separators
    best = max(candidates, key=lambda t: (t.count("\n"), t.count("|")))
    lines = [ln.strip() for ln in best.splitlines() if ln.strip()]

    # keep only lines that look like table rows (contain pipes) or look like "HH:MM"
    table_lines = [ln for ln in lines if "|" in ln or re.search(r'^\d{1,2}[:.]\d{2}\b', ln)]
    rows = []
    for ln in table_lines:
        # split by pipe but avoid splitting URLs
        parts = [p.strip() for p in re.split(r'\s*\|\s*', ln) if p.strip()]
        if len(parts) >= 2:
            rows.append(parts)
    return rows

def parse_rows_to_programs(rows, base_date):
    """
    Input: rows = list of cell lists. Expected columns include a HH:MM cell and a title and duration.
    Return list of dicts: {start: datetime, stop: datetime, title: str, desc: str}
    """
    progs = []
    last_start = None
    current_day = base_date
    for cells in rows:
        # find time token in any cell
        time_token = None
        for c in cells[:2]:
            m = re.search(r'(\d{1,2}[:.]\d{2})', c)
            if m:
                time_token = m.group(1).replace(".", ":")
                break
        if not time_token:
            continue

        # title heuristics: prefer second column, else first non-time cell
        title = ""
        desc = ""
        if len(cells) >= 2:
            # sometimes table is: time | title | original | duration
            title = cells[1]
            if len(cells) >= 4:
                desc = cells[2]
                dur_cell = cells[3]
            elif len(cells) == 3:
                # guess whether third cell is duration or original title
                if re.search(r'\d+[:.]?\d*', cells[2]):
                    dur_cell = cells[2]
                else:
                    desc = cells[2]
                    dur_cell = ""
            else:
                dur_cell = ""
        else:
            # fallback: split line by spaces after time
            rest = re.sub(re.escape(time_token), "", " ".join(cells)).strip()
            parts = rest.split("  ")
            title = parts[0] if parts else rest
            dur_cell = ""

        title = re.sub(r'\s+', ' ', title).strip()
        desc = re.sub(r'\s+', ' ', desc).strip()

        # parse start datetime
        hh, mm = (int(x) for x in time_token.split(":"))
        start_dt = datetime.combine(current_day, time(hh, mm))
        # detect rollover: if last_start exists and this start <= last_start, advance day
        if last_start and start_dt <= last_start:
            start_dt = start_dt + timedelta(days=1)
            current_day = start_dt.date()

        # parse duration from dur_cell or fallback to DEFAULT_DURATION_MIN
        duration_min = None
        if 'dur_cell' in locals() and dur_cell:
            # common formats: "1:00", "0:30", "30", "1:00 "
            dm = re.search(r'(\d{1,2})[:.](\d{2})', dur_cell)
            if dm:
                duration_min = int(dm.group(1)) * 60 + int(dm.group(2))
            else:
                dn = re.search(r'(\d+)\s*ph', dur_cell, re.I) or re.search(r'(\d+)', dur_cell)
                if dn:
                    duration_min = int(dn.group(1))
        if not duration_min:
            duration_min = DEFAULT_DURATION_MIN

        stop_dt = start_dt + timedelta(minutes=duration_min)

        progs.append({
            "start": start_dt,
            "stop": stop_dt,
            "title": title,
            "desc": desc
        })
        last_start = start_dt

    return progs

def build_xmltv(programs, generated_date=None):
    tv = ET.Element("tv")
    tv.set("generator-info-name", "boomerang.py")
    tv.set("source-info-url", SOURCE_URL)

    # channel
    ch = ET.SubElement(tv, "channel", id=CHANNEL_ID)
    dn = ET.SubElement(ch, "display-name")
    dn.text = CHANNEL_NAME

    # programmes
    for p in programs:
        # format: YYYYMMDDHHMMSS +0700
        start_str = p["start"].strftime("%Y%m%d%H%M%S") + " " + TZ_STR
        stop_str = p["stop"].strftime("%Y%m%d%H%M%S") + " " + TZ_STR
        prog = ET.SubElement(tv, "programme", start=start_str, stop=stop_str, channel=CHANNEL_ID)
        title = ET.SubElement(prog, "title", lang="vi")
        title.text = p["title"]
        if p.get("desc"):
            desc = ET.SubElement(prog, "desc", lang="vi")
            desc.text = p["desc"]
        # source tag
        src = ET.SubElement(prog, "credits")
        provider = ET.SubElement(src, "presenter")
        provider.text = "Source: " + SOURCE_URL

    # pretty print
    return ET.tostring(tv, encoding="utf-8", method="xml")

def main():
    # base date = today in Hanoi
    hanoi = tz.gettz("Asia/Ho_Chi_Minh")
    today_hanoi = datetime.now(tz=hanoi).date()

    try:
        html_text = fetch_page(SOURCE_URL)
    except Exception as e:
        print("Failed to fetch source:", e, file=sys.stderr)
        sys.exit(2)

    rows = extract_table_text(html_text)
    if not rows:
        print("No schedule table found on source page", file=sys.stderr)
        sys.exit(3)

    programs = parse_rows_to_programs(rows, today_hanoi)
    if not programs:
        print("No programs parsed", file=sys.stderr)
        sys.exit(4)

    xml_bytes = build_xmltv(programs)
    with open(OUTPUT_FILE, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(xml_bytes)

    print(f"Wrote {OUTPUT_FILE} with {len(programs)} programmes")

if __name__ == "__main__":
    main()
  
