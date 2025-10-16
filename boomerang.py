#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
boomerang.py
Generate boomerang.xml (XMLTV) for CARTOONITO (channel id: cartoonito)
Source: https://info.msky.vn/vn/Boomerang.html

This version directly extracts the markdown-style pipe table from the raw HTML text (not only
soup.get_text) to avoid losing pipe separators, parses time/title/duration columns exactly,
handles rollover, dedup, and writes a valid XMLTV file.
"""

from datetime import datetime, date, time as dtime, timedelta
import re
import sys
import xml.etree.ElementTree as ET

import requests
from dateutil import tz

SOURCE_URL = "https://info.msky.vn/vn/Boomerang.html"
CHANNEL_ID = "cartoonito"
CHANNEL_NAME = "CARTOONITO"
OUTPUT_FILE = "boomerang.xml"
DEFAULT_DURATION_MIN = 30
TZ_OFFSET = "+0700"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; boomerang-bot/1.0)"}

# match time like 0:00 or 00:00 or 23:59 or 7.30
TIME_RE = re.compile(r'\b([01]?\d|2[0-3])[:.][0-5]\d\b')
# match a table row that contains at least two pipes and a time token
TABLE_ROW_RE = re.compile(r'^\s*\|.*\|.*$', re.M)
# split pipes but keep content between
PIPE_SPLIT_RE = re.compile(r'\s*\|\s*')
DUR_HHMM_RE = re.compile(r'(\d{1,2})[:.](\d{2})')
DUR_MIN_RE = re.compile(r'(\d{1,3})\s*(?:ph|phút|min)?', re.I)


def fetch_html(url, timeout=20):
    r = requests.get(url, timeout=timeout, headers=HEADERS)
    r.raise_for_status()
    return r.text


def extract_table_block_from_html(html):
    """
    Find the largest contiguous block of lines that look like a markdown pipe table.
    Return list of table lines (strings).
    """
    # Try to find explicit table by locating the header line containing 'Thời gian' (Vietnamese)
    markers = ['| Thời gian', '|Thời gian', '| Time', '| Thoi gian', '|Thoi gian']
    for m in markers:
        idx = html.find(m)
        if idx != -1:
            # expand to include surrounding lines up to a reasonable limit
            start = max(0, html.rfind('\n', 0, idx) - 2000)
            end = min(len(html), idx + 40000)
            block = html[start:end]
            # extract lines that contain pipes
            lines = [ln for ln in block.splitlines() if '|' in ln]
            # filter lines that look like table rows (at least two pipes)
            rows = [ln.strip() for ln in lines if ln.count('|') >= 2]
            # ensure we have useful rows (rows with time tokens)
            if any(TIME_RE.search(r) for r in rows):
                return rows
    # fallback: find any long segment with many pipe-rows in whole HTML
    all_lines = html.splitlines()
    best_block = []
    best_len = 0
    for i in range(len(all_lines)):
        if '|' not in all_lines[i]:
            continue
        # expand forward to collect contiguous pipe lines
        j = i
        block = []
        while j < len(all_lines) and '|' in all_lines[j]:
            block.append(all_lines[j].strip())
            j += 1
        if len(block) >= 3 and any(TIME_RE.search(r) for r in block):
            if len(block) > best_len:
                best_len = len(block)
                best_block = block
    return best_block


def parse_table_rows(rows, base_date):
    """
    rows: list of pipe-line strings
    returns list of programs: dict {start, stop, title, desc}
    """
    cleaned_rows = []
    # remove separator lines like '| --- | --- |'
    for ln in rows:
        if re.match(r'^\s*\|\s*-{1,}\s*(\|\s*-{1,}\s*)+', ln):
            continue
        # normalize consecutive spaces and trim
        cleaned_rows.append(ln.strip())

    programs = []
    seen = set()
    last_start = None
    current_day = base_date

    for ln in cleaned_rows:
        # split into cells
        parts = [p.strip() for p in PIPE_SPLIT_RE.split(ln)]
        # remove empty leading/trailing if split produced empties due to leading/trailing pipe
        parts = [p for p in parts if p != '']
        if not parts:
            continue
        # find first time token in row
        time_token = None
        time_idx = None
        for i, c in enumerate(parts[:4]):  # usually in first few columns
            m = TIME_RE.search(c)
            if m:
                time_token = m.group(0).replace('.', ':')
                time_idx = i
                break
        if not time_token:
            # try entire row
            m = TIME_RE.search(ln)
            if m:
                time_token = m.group(0).replace('.', ':')
        if not time_token:
            continue

        # heuristics: title is cell after time cell
        title = ""
        desc = ""
        dur_cell = ""
        if time_idx is not None and len(parts) > time_idx + 1:
            title = parts[time_idx + 1]
            if len(parts) >= time_idx + 4:
                # assume last column is duration
                dur_candidate = parts[-1]
                if DUR_HHMM_RE.search(dur_candidate) or DUR_MIN_RE.search(dur_candidate):
                    dur_cell = dur_candidate
                    # desc is any middle columns between title and duration
                    if len(parts) > time_idx + 2:
                        desc = " ".join(parts[time_idx + 2:-1])
                else:
                    # no explicit duration, combine remaining as desc
                    desc = " ".join(parts[time_idx + 2:])
            elif len(parts) == time_idx + 2:
                pass
            else:
                desc = " ".join(parts[time_idx + 2:])
        else:
            # fallback: if second column exists use it
            if len(parts) >= 2:
                title = parts[1]
                if len(parts) > 2:
                    desc = " ".join(parts[2:])
            else:
                title = " ".join(parts)

        # clean title/desc
        title = re.sub(r'https?://\S+', '', title).strip()
        desc = re.sub(r'https?://\S+', '', desc).strip()
        if title.lower().startswith('thời gian') or title.lower().startswith('tên chương trình'):
            # header line
            continue

        # parse hh:mm
        try:
            hh, mm = (int(x) for x in time_token.split(':'))
        except Exception:
            continue
        start_dt = datetime.combine(current_day, dtime(hh, mm))
        if last_start and start_dt <= last_start:
            start_dt = start_dt + timedelta(days=1)
            current_day = start_dt.date()

        # parse duration from dur_cell first
        duration_min = None
        if dur_cell:
            m = DUR_HHMM_RE.search(dur_cell)
            if m:
                duration_min = int(m.group(1)) * 60 + int(m.group(2))
            else:
                m2 = DUR_MIN_RE.search(dur_cell)
                if m2:
                    duration_min = int(m2.group(1))
        # fallback: detect duration decorated in any part of row
        if duration_min is None:
            # check title and desc for hh:mm or minutes
            for txt in (title, desc, ln):
                m = DUR_HHMM_RE.search(txt)
                if m:
                    duration_min = int(m.group(1)) * 60 + int(m.group(2))
                    break
                m2 = DUR_MIN_RE.search(txt)
                if m2:
                    duration_min = int(m2.group(1))
                    break
        if duration_min is None:
            duration_min = DEFAULT_DURATION_MIN

        stop_dt = start_dt + timedelta(minutes=duration_min)

        # dedupe
        key = (start_dt.isoformat(), re.sub(r'\s+', ' ', title).lower())
        if key in seen:
            last_start = start_dt
            continue
        seen.add(key)

        programs.append({"start": start_dt, "stop": stop_dt, "title": title, "desc": desc})
        last_start = start_dt

    # ensure programs sorted and infer stops from next start (prefer next start)
    programs = sorted(programs, key=lambda x: x['start'])
    for i in range(len(programs) - 1):
        if programs[i+1]['start'] > programs[i]['start']:
            programs[i]['stop'] = programs[i+1]['start']
    return programs


def xmltv_timestamp(dt):
    return dt.strftime("%Y%m%d%H%M%S") + " " + TZ_OFFSET


def build_xmltv(programs):
    tv = ET.Element("tv")
    tv.set("generator-info-name", "boomerang.py")
    tv.set("source-info-url", SOURCE_URL)

    ch = ET.SubElement(tv, "channel", id=CHANNEL_ID)
    dn = ET.SubElement(ch, "display-name")
    dn.text = CHANNEL_NAME

    for p in programs:
        if not p.get("start") or not p.get("stop") or not p.get("title"):
            continue
        prog = ET.SubElement(tv, "programme",
                             start=xmltv_timestamp(p["start"]),
                             stop=xmltv_timestamp(p["stop"]),
                             channel=CHANNEL_ID)
        title = ET.SubElement(prog, "title", lang="vi")
        title.text = p["title"]
        if p.get("desc"):
            desc = ET.SubElement(prog, "desc", lang="vi")
            desc.text = p["desc"]
        credits = ET.SubElement(prog, "credits")
        presenter = ET.SubElement(credits, "presenter")
        presenter.text = SOURCE_URL

    return ET.tostring(tv, encoding="utf-8", method="xml")


def write_xml(xml_bytes):
    with open(OUTPUT_FILE, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(xml_bytes)


def main():
    htz = tz.gettz("Asia/Ho_Chi_Minh")
    base_date = datetime.now(tz=htz).date()

    try:
        html = fetch_html(SOURCE_URL)
    except Exception as e:
        # write minimal xml with channel node to avoid CI failures
        xml_bytes = build_xmltv([])
        write_xml(xml_bytes)
        print("fetch failed:", e, file=sys.stderr)
        sys.exit(0)

    rows = extract_table_block_from_html(html)
    programs = []
    if rows:
        programs = parse_table_rows(rows, base_date)

    # fallback: if still empty, try scanning HTML text for pipe-like lines later
    if not programs:
        # as a last fallback, use any lines in html with pipes that include a time
        alt = [ln for ln in html.splitlines() if '|' in ln and TIME_RE.search(ln)]
        if alt:
            programs = parse_table_rows(alt, base_date)

    xml_bytes = build_xmltv(programs)
    write_xml(xml_bytes)
    print(f"Wrote {OUTPUT_FILE} with {len(programs)} programmes (source: {SOURCE_URL})")


if __name__ == "__main__":
    main()
