#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
boomerang.py (debuggable)
- Tìm và parse bảng markdown (pipe) từ SOURCE_URL
- Ghi boomerang.xml và boomerang_debug.txt để kiểm tra nếu parser không thấy gì
- Cải tiến tìm marker: nhiều biến thể có/không dấu, unescape HTML trước khi tìm
"""

from datetime import datetime, time as dtime, timedelta
import re
import sys
import html as html_mod
import xml.etree.ElementTree as ET

import requests
from dateutil import tz

SOURCE_URL = "https://info.msky.vn/vn/Boomerang.html"
CHANNEL_ID = "cartoonito"
CHANNEL_NAME = "CARTOONITO"
OUTPUT_FILE = "boomerang.xml"
DEBUG_FILE = "boomerang_debug.txt"
DEFAULT_DURATION_MIN = 30
TZ_OFFSET = "+0700"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; boomerang-bot/1.0)"}

TIME_RE = re.compile(r'\b([01]?\d|2[0-3])[:.][0-5]\d\b')
DUR_HHMM_RE = re.compile(r'(\d{1,2})[:.](\d{2})')
DUR_MIN_RE = re.compile(r'(\d{1,3})\s*(?:ph|phút|min)?', re.I)
PIPE_SPLIT_RE = re.compile(r'\s*\|\s*')


def fetch_html(url, timeout=20):
    r = requests.get(url, timeout=timeout, headers=HEADERS)
    r.raise_for_status()
    return r.text


def xmltv_timestamp(dt):
    return dt.strftime("%Y%m%d%H%M%S") + " " + TZ_OFFSET


def write_xml(programs):
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
    xml_bytes = ET.tostring(tv, encoding="utf-8", method="xml")
    with open(OUTPUT_FILE, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(xml_bytes)


def find_table_block_candidates(html_raw):
    """
    Return list of candidate blocks (each a list of lines containing '|' ).
    Tries several strategies:
      - find marker with '| Thời gian' or variants
      - find 'Thời gian' (with/without diacritics) and take surrounding lines
      - fallback: search contiguous runs of pipe-lines
    """
    candidates = []

    # unescape html entities to make pipes visible if encoded
    html_unesc = html_mod.unescape(html_raw)

    # 1) markers with pipe
    markers = ['| Thời gian', '|Thời gian', '| Time', '| Thoi gian', '|Thoi gian', '| Th\u1EDDi gian']
    for m in markers:
        idx = html_unesc.find(m)
        if idx != -1:
            start = max(0, html_unesc.rfind('\n', 0, idx) - 2000)
            end = min(len(html_unesc), idx + 40000)
            block = html_unesc[start:end]
            rows = [ln.strip() for ln in block.splitlines() if '|' in ln]
            if len(rows) >= 3 and any(TIME_RE.search(r) for r in rows):
                candidates.append(rows)
                # prefer earliest successful marker
                break

    # 2) marker without pipe: just 'Thời gian' or 'Thoi gian' (no surrounding pipe)
    if not candidates:
        for m in ['Thời gian', 'Thoi gian', 'Thoi', 'Thoi gian'.strip()]:
            idx = html_unesc.find(m)
            if idx != -1:
                start = max(0, html_unesc.rfind('\n', 0, idx) - 3000)
                end = min(len(html_unesc), idx + 50000)
                block = html_unesc[start:end]
                rows = [ln.strip() for ln in block.splitlines() if '|' in ln]
                if len(rows) >= 3 and any(TIME_RE.search(r) for r in rows):
                    candidates.append(rows)
                    break

    # 3) fallback: find long contiguous pipe blocks anywhere
    if not candidates:
        lines = html_unesc.splitlines()
        best = []
        best_len = 0
        i = 0
        while i < len(lines):
            if '|' in lines[i]:
                j = i
                block = []
                while j < len(lines) and '|' in lines[j]:
                    block.append(lines[j].strip())
                    j += 1
                if len(block) >= 3 and any(TIME_RE.search(r) for r in block):
                    if len(block) > best_len:
                        best_len = len(block)
                        best = block
                i = j
            else:
                i += 1
        if best:
            candidates.append(best)

    return candidates, html_unesc


def parse_table_rows(rows, base_date):
    """
    rows: list of pipe-line strings
    returns programs list
    """
    cleaned = []
    for ln in rows:
        if re.match(r'^\s*\|\s*-{1,}\s*(\|\s*-{1,}\s*)+', ln):
            continue
        cleaned.append(ln.strip())

    programs = []
    seen = set()
    last_start = None
    current_day = base_date

    for ln in cleaned:
        parts = [p.strip() for p in PIPE_SPLIT_RE.split(ln)]
        parts = [p for p in parts if p != '']
        if not parts:
            continue
        # find time token
        time_token = None
        time_idx = None
        for i, c in enumerate(parts[:4]):
            m = TIME_RE.search(c)
            if m:
                time_token = m.group(0).replace('.', ':')
                time_idx = i
                break
        if not time_token:
            m = TIME_RE.search(ln)
            if m:
                time_token = m.group(0).replace('.', ':')
        if not time_token:
            continue

        title = ""
        desc = ""
        dur_cell = ""
        if time_idx is not None and len(parts) > time_idx + 1:
            title = parts[time_idx + 1]
            if len(parts) >= time_idx + 4:
                dur_candidate = parts[-1]
                if DUR_HHMM_RE.search(dur_candidate) or DUR_MIN_RE.search(dur_candidate):
                    dur_cell = dur_candidate
                    if len(parts) > time_idx + 2:
                        desc = " ".join(parts[time_idx + 2:-1])
                else:
                    desc = " ".join(parts[time_idx + 2:])
            elif len(parts) == time_idx + 2:
                pass
            else:
                desc = " ".join(parts[time_idx + 2:])
        else:
            if len(parts) >= 2:
                title = parts[1]
                if len(parts) > 2:
                    desc = " ".join(parts[2:])
            else:
                title = " ".join(parts)

        title = re.sub(r'https?://\S+', '', title).strip()
        desc = re.sub(r'https?://\S+', '', desc).strip()
        if title.lower().startswith('thời gian') or title.lower().startswith('tên chương trình'):
            continue

        try:
            hh, mm = (int(x) for x in time_token.split(':'))
        except Exception:
            continue
        start_dt = datetime.combine(current_day, dtime(hh, mm))
        if last_start and start_dt <= last_start:
            start_dt = start_dt + timedelta(days=1)
            current_day = start_dt.date()

        duration_min = None
        if dur_cell:
            m = DUR_HHMM_RE.search(dur_cell)
            if m:
                duration_min = int(m.group(1)) * 60 + int(m.group(2))
            else:
                m2 = DUR_MIN_RE.search(dur_cell)
                if m2:
                    duration_min = int(m2.group(1))
        if duration_min is None:
            # try find in title/desc/ln
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

        key = (start_dt.isoformat(), re.sub(r'\s+', ' ', title).lower())
        if key in seen:
            last_start = start_dt
            continue
        seen.add(key)

        programs.append({"start": start_dt, "stop": stop_dt, "title": title, "desc": desc})
        last_start = start_dt

    programs = sorted(programs, key=lambda x: x["start"])
    for i in range(len(programs) - 1):
        if programs[i + 1]["start"] > programs[i]["start"]:
            programs[i]["stop"] = programs[i + 1]["start"]
    return programs


def fallback_scan_for_time_tokens(html_unesc, base_date):
    # simple fallback scanning lines with '|' and a time token
    alt_lines = [ln for ln in html_unesc.splitlines() if '|' in ln and TIME_RE.search(ln)]
    if alt_lines:
        return parse_table_rows(alt_lines, base_date)
    # final fallback: scan the whole unescaped text for lines with time token
    lines = [ln.strip() for ln in html_unesc.splitlines() if TIME_RE.search(ln)]
    programs = []
    seen = set()
    last_start = None
    current_day = base_date
    for ln in lines:
        m = TIME_RE.search(ln)
        if not m: continue
        time_token = m.group(0).replace('.', ':')
        # title: rest of line after time
        rest = ln[m.end():].strip()
        title = re.sub(r'https?://\S+', '', rest).strip()
        if not title:
            title = ln[:m.start()].strip()
        try:
            hh, mm = (int(x) for x in time_token.split(':'))
        except Exception:
            continue
        start_dt = datetime.combine(current_day, dtime(hh, mm))
        if last_start and start_dt <= last_start:
            start_dt = start_dt + timedelta(days=1)
            current_day = start_dt.date()
        stop_dt = start_dt + timedelta(minutes=DEFAULT_DURATION_MIN)
        key = (start_dt.isoformat(), re.sub(r'\s+', ' ', title).lower())
        if key in seen:
            last_start = start_dt
            continue
        seen.add(key)
        programs.append({"start": start_dt, "stop": stop_dt, "title": title, "desc": ""})
        last_start = start_dt
    return programs


def main():
    htz = tz.gettz("Asia/Ho_Chi_Minh")
    base_date = datetime.now(tz=htz).date()

    try:
        html_raw = fetch_html(SOURCE_URL)
    except Exception as e:
        # write minimal xml and debug
        write_xml([])
        with open(DEBUG_FILE, "w", encoding="utf-8") as df:
            df.write("FETCH FAILED: " + str(e) + "\n")
        print("Fetch failed:", e, file=sys.stderr)
        sys.exit(0)

    # try to find table blocks
    candidates, html_unesc = find_table_block_candidates(html_raw)

    debug_lines = []
    debug_lines.append(f"Candidates found: {len(candidates)}")
    programs = []

    if candidates:
        # take the first candidate
        rows = candidates[0]
        debug_lines.append(f"Candidate rows count: {len(rows)}")
        debug_lines.append("First 10 rows preview:")
        for r in rows[:10]:
            debug_lines.append(r)
        programs = parse_table_rows(rows, base_date)
        debug_lines.append(f"Programs parsed from candidate: {len(programs)}")
    else:
        debug_lines.append("No table candidate found, will fallback.")
        programs = fallback_scan_for_time_tokens(html_unesc, base_date)
        debug_lines.append(f"Programs parsed from fallback: {len(programs)}")

    # write debug file with some context
    with open(DEBUG_FILE, "w", encoding="utf-8") as df:
        df.write("SOURCE_URL: " + SOURCE_URL + "\n\n")
        df.write("\n".join(debug_lines) + "\n\n")
        df.write("== Parsed programs (first 50) ==\n")
        for p in programs[:50]:
            df.write(f"{p['start'].isoformat()} -> {p['stop'].isoformat()} | {p['title']}\n")
        df.write("\n\n== Extracted HTML snippet (first 20000 chars of unescaped) ==\n")
        df.write(html_unesc[:20000])

    # write xml
    write_xml(programs)
    print(f"Wrote {OUTPUT_FILE} with {len(programs)} programmes (source: {SOURCE_URL})")
    print("Debug written to", DEBUG_FILE)


if __name__ == "__main__":
    main()
