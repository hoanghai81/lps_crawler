#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
boomerang.py
Generate boomerang.xml (XMLTV) for CARTOONITO (channel id: cartoonito)
Source: https://info.msky.vn/vn/Boomerang.html

This version:
- Preferentially parses a markdown-style table (pipes) found on the source page.
- Falls back to time-token scanning only if no table is found.
- Parses durations from table when available.
- Handles midnight rollover, deduplicates entries, and infers stop times.
- Always writes a valid XMLTV file with a channel node.
"""

from datetime import datetime, date, time as dtime, timedelta
import re
import sys
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup, Comment
from dateutil import tz

SOURCE_URL = "https://info.msky.vn/vn/Boomerang.html"
CHANNEL_ID = "cartoonito"
CHANNEL_NAME = "CARTOONITO"
OUTPUT_FILE = "boomerang.xml"
DEFAULT_DURATION_MIN = 30
TZ_OFFSET = "+0700"  # XMLTV timestamps timezone

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; boomerang-bot/1.0)"}

TIME_RE = re.compile(r'\b([01]?\d|2[0-3])[:.][0-5]\d\b')
DUR_HHMM_RE = re.compile(r'(\d{1,2})[:.](\d{2})')
DUR_MIN_RE = re.compile(r'(\d{1,3})\s*(?:ph|phút|min)?', re.I)


def fetch_html(url, timeout=20):
    r = requests.get(url, timeout=timeout, headers=HEADERS)
    r.raise_for_status()
    return r.text


def clean_soup(soup):
    for tag in soup.find_all(["script", "style", "noscript", "iframe", "pre", "code"]):
        try:
            tag.decompose()
        except Exception:
            pass
    for c in soup.find_all(string=lambda t: isinstance(t, Comment)):
        try:
            c.extract()
        except Exception:
            pass
    return soup


def find_markdown_table_text(soup):
    """
    Try to extract a block of text that contains a markdown-style pipe table.
    Return the block (string) or None.
    """
    full = soup.get_text("\n", strip=True)
    # common Vietnamese header could be '| Thời gian' or '|Thời gian'
    idx = None
    # search for '| Thời gian' or '|Thoi gian' patterns to be tolerant
    for marker in ['| Thời gian', '|Thời gian', '| Thoi gian', '|Thoi gian', '| Time', '|Thời gian|']:
        idx = full.find(marker)
        if idx != -1:
            break
    if idx == -1:
        # fallback: look for any line with at least 2 pipes and a time token
        lines = full.splitlines()
        candidates = []
        for i, ln in enumerate(lines):
            if ln.count('|') >= 2 and TIME_RE.search(ln):
                # take a block around this line
                start = max(0, i - 20)
                end = min(len(lines), i + 200)
                block = "\n".join(lines[start:end])
                candidates.append(block)
        if candidates:
            # choose longest
            return max(candidates, key=len)
        return None
    # take a reasonably large slice starting at idx
    block = full[idx: idx + 30000]
    return block


def parse_markdown_table(block_text, base_date):
    """
    Parse pipe-delimited lines into program rows.
    Returns list of dicts: {start: datetime, stop: datetime, title: str, desc: str}
    """
    lines = [ln.strip() for ln in block_text.splitlines() if ln.strip()]
    # keep only lines starting with '|' (table rows) or containing at least one pipe and a time
    table_lines = []
    for ln in lines:
        if ln.startswith('|') or ('|' in ln and TIME_RE.search(ln)):
            table_lines.append(ln)
    # remove separator lines like '| --- | --- |'
    rows = []
    for ln in table_lines:
        if re.match(r'^\|\s*-+', ln):
            continue
        # split by pipe and trim
        parts = [p.strip() for p in re.split(r'\s*\|\s*', ln) if p.strip()]
        if parts:
            rows.append(parts)
    if not rows:
        return []

    # determine column mapping heuristically
    # common patterns:
    # [Thời gian, Tên chương trình, Tên gốc, Thời lượng]
    # [Thời gian, Tên chương trình, Thời lượng]
    programs = []
    last_start = None
    current_day = base_date
    seen = set()

    for cells in rows:
        # find time cell: first cell that matches TIME_RE
        time_cell = None
        time_idx = None
        for i, c in enumerate(cells[:3]):  # usually in first 3 columns
            if TIME_RE.search(c):
                time_cell = TIME_RE.search(c).group(0).replace('.', ':')
                time_idx = i
                break
        if not time_cell:
            # try whole row
            joined = " ".join(cells)
            m = TIME_RE.search(joined)
            if m:
                time_cell = m.group(0).replace('.', ':')
            else:
                continue

        # heuristics for title and duration
        # prefer the column right after time column as title if exists
        title = ""
        desc = ""
        dur_cell = ""
        if time_idx is not None and len(cells) > time_idx + 1:
            title = cells[time_idx + 1]
            # remaining columns may include original title and duration
            if len(cells) >= time_idx + 3:
                # assume last column is duration if looks like duration
                possible_dur = cells[-1]
                if DUR_HHMM_RE.search(possible_dur) or DUR_MIN_RE.search(possible_dur):
                    dur_cell = possible_dur
                    # desc may be middle column(s)
                    if len(cells) - (time_idx + 2) >= 1:
                        desc = " ".join(cells[time_idx + 2:-1])
                else:
                    # no explicit duration, put extras into desc
                    desc = " ".join(cells[time_idx + 2:])
            elif len(cells) == time_idx + 2:
                # only time and title
                pass
        else:
            # fallback: take second cell as title if exists
            if len(cells) >= 2:
                title = cells[1]
            else:
                title = " ".join(cells)

        title = re.sub(r'https?://\S+', '', title).strip()
        desc = re.sub(r'https?://\S+', '', desc).strip()

        # parse start datetime
        try:
            hh, mm = (int(x) for x in time_cell.split(":"))
        except Exception:
            continue
        start_dt = datetime.combine(current_day, dtime(hh, mm))
        if last_start and start_dt <= last_start:
            # rollover to next day
            start_dt = start_dt + timedelta(days=1)
            current_day = start_dt.date()

        # parse duration if present
        duration_min = None
        dm = DUR_HHMM_RE.search(dur_cell)
        if dm:
            duration_min = int(dm.group(1)) * 60 + int(dm.group(2))
        else:
            dm2 = DUR_MIN_RE.search(dur_cell)
            if dm2:
                # if it's hhmm like '1:00' this is already caught; here it's plain minutes
                duration_min = int(dm2.group(1))

        # fallback: try to detect duration inside title like " (1:00)" or " - 30'"
        if duration_min is None:
            mtitle_dur = DUR_HHMM_RE.search(title) or DUR_MIN_RE.search(title)
            if mtitle_dur:
                if ':' in mtitle_dur.group(0) or '.' in mtitle_dur.group(0):
                    # hh:mm
                    a, b = DUR_HHMM_RE.search(title).groups()
                    duration_min = int(a) * 60 + int(b)
                else:
                    duration_min = int(mtitle_dur.group(1))

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

    # infer stop times from next program if desired (already computed from duration)
    programs = sorted(programs, key=lambda x: x["start"])
    for i in range(len(programs) - 1):
        if programs[i + 1]["start"] > programs[i]["start"]:
            programs[i]["stop"] = programs[i + 1]["start"]

    return programs


def fallback_time_token_parse(soup, base_date):
    """
    If no markdown table found, fallback to scanning for time tokens and nearest titles.
    """
    # remove heavy noise already done
    text_nodes = []
    for text in soup.find_all(string=TIME_RE):
        parent = getattr(text, "parent", None)
        if parent and parent.name in ("script", "style"):
            continue
        m = TIME_RE.search(text)
        if m:
            text_nodes.append((m.group(0).replace('.', ':'), text))

    programs = []
    last_start = None
    current_day = base_date
    seen = set()

    def sibling_text(node):
        try:
            nxt = node.next_sibling
            if nxt:
                return str(nxt).strip()
        except Exception:
            pass
        return ""

    for time_str, node in text_nodes:
        title = ""
        txt = str(node)
        m = TIME_RE.search(txt)
        if m:
            after = txt[m.end():].strip()
            before = txt[:m.start()].strip()
            if after and not TIME_RE.search(after):
                title = after
            elif before and not TIME_RE.search(before):
                title = before
        if not title:
            title = sibling_text(node) or ""
        title = re.sub(r'https?://\S+', '', title).strip()
        if not title:
            continue
        try:
            hh, mm = (int(x) for x in time_str.split(":"))
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

    programs = sorted(programs, key=lambda x: x["start"])
    for i in range(len(programs) - 1):
        if programs[i + 1]["start"] > programs[i]["start"]:
            programs[i]["stop"] = programs[i + 1]["start"]
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


def write_xml_file(xml_bytes):
    with open(OUTPUT_FILE, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(xml_bytes)


def main():
    # base date = today Hanoi
    htz = tz.gettz("Asia/Ho_Chi_Minh")
    today_hanoi = datetime.now(tz=htz).date()

    try:
        html = fetch_html(SOURCE_URL)
    except Exception as e:
        # write minimal xml and exit 0 to avoid CI failing hard
        xml_bytes = build_xmltv([])
        write_xml_file(xml_bytes)
        print("Failed to fetch source:", e, file=sys.stderr)
        sys.exit(0)

    soup = BeautifulSoup(html, "lxml")
    clean_soup(soup)

    # first try to parse markdown table block
    table_block = find_markdown_table_text(soup)
    programs = []
    if table_block:
        programs = parse_markdown_table(table_block, today_hanoi)

    if not programs:
        # fallback generic parse
        programs = fallback_time_token_parse(soup, today_hanoi)

    xml_bytes = build_xmltv(programs)
    write_xml_file(xml_bytes)
    print(f"Wrote {OUTPUT_FILE} with {len(programs)} programmes (source: {SOURCE_URL})")


if __name__ == "__main__":
    main()
        
