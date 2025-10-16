#!/usr/bin/env python3
"""
Robust boomerang.py
- Scrape schedule from SOURCE_URL by finding time tokens (HH:MM) in HTML then extracting nearby titles.
- Build XMLTV boomerang.xml for channel id "cartoonito", name "CARTOONITO".
- Handles midnight rollover.
- If no programs found, writes an empty but valid XMLTV with channel element.
"""

import re
import sys
from datetime import datetime, date, time, timedelta
import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from dateutil import tz
import xml.etree.ElementTree as ET

SOURCE_URL = "https://info.msky.vn/vn/Boomerang.html"
CHANNEL_ID = "cartoonito"
CHANNEL_NAME = "CARTOONITO"
OUTPUT_FILE = "boomerang.xml"
DEFAULT_DURATION_MIN = 30
TZ_OFFSET = "+0700"

TIME_RE = re.compile(r'\b([01]?\d|2[0-3])[:.][0-5]\d\b')

def fetch_page(url, timeout=20):
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.text

def find_time_nodes(soup):
    """
    Return list of (time_str, node) where node is the Tag or NavigableString containing that time text.
    """
    results = []
    # search text nodes
    for text in soup.find_all(string=TIME_RE):
        # ignore inside scripts/styles
        if isinstance(text, NavigableString):
            parent = text.parent
            # skip if inside script/style or hidden
            if parent.name in ("script", "style", "noscript"):
                continue
            t = TIME_RE.search(text)
            if t:
                results.append((t.group(0).replace(".", ":"), text))
    return results

def extract_title_from_node(node):
    """
    Attempt to find program title nearest to a time token node.
    Strategies:
    1) If same text node contains more than time (e.g., "06:30 Thời sự An Giang"), return rest.
    2) Check sibling nodes (next_sibling, previous_sibling).
    3) Check parent tag and its child text nodes excluding time token.
    4) As fallback, return the nearest text within parent's next element.
    """
    # 1) same node
    txt = str(node)
    m = TIME_RE.search(txt)
    if m:
        after = txt[m.end():].strip()
        if after:
            return clean_title(after)
        before = txt[:m.start()].strip()
        if before:
            return clean_title(before)

    # 2) siblings
    sib = node.next_sibling
    if sib:
        stext = sibling_text(sib)
        if stext and not TIME_RE.search(stext):
            return clean_title(stext)
    sib = node.previous_sibling
    if sib:
        stext = sibling_text(sib)
        if stext and not TIME_RE.search(stext):
            return clean_title(stext)

    # 3) parent children (look after the current node)
    parent = node.parent
    if parent:
        found = False
        for child in parent.contents:
            if found:
                ct = child.get_text(" ", strip=True) if isinstance(child, Tag) else str(child).strip()
                if ct and not TIME_RE.search(ct):
                    return clean_title(ct)
            else:
                if child is node or (isinstance(child, NavigableString) and child == node):
                    found = True

    # 4) nearest next element in document order
    nxt = node
    steps = 0
    while nxt and steps < 10:
        nxt = nxt.next_element
        if isinstance(nxt, NavigableString):
            s = str(nxt).strip()
            if s and not TIME_RE.search(s):
                return clean_title(s)
        steps += 1

    return ""

def sibling_text(s):
    if isinstance(s, Tag):
        return s.get_text(" ", strip=True)
    return str(s).strip()

def clean_title(s):
    s = re.sub(r'\s+', ' ', s).strip()
    # strip leading punctuation or separators
    s = re.sub(r'^[\-\:\–\—\|]+\s*', '', s)
    # remove trailing separators
    s = re.sub(r'\s*[\-\:\–\—\|]+$', '', s)
    return s

def build_program_list(time_nodes, base_date):
    """
    Convert list of (time_str, node) into ordered programs with start/stop/title.
    """
    items = []
    last_start = None
    current_day = base_date
    for time_str, node in time_nodes:
        title = extract_title_from_node(node)
        if not title:
            # try to get nearest heading or strong tag in parent
            p = node.parent
            if p:
                heading = p.find(['b','strong','h1','h2','h3','h4','h5'])
                if heading:
                    title = heading.get_text(" ", strip=True)
        if not title:
            # skip if no reasonable title
            continue

        hh, mm = (int(x) for x in time_str.split(":"))
        start_dt = datetime.combine(current_day, time(hh, mm))
        if last_start and start_dt <= last_start:
            start_dt = start_dt + timedelta(days=1)
            current_day = start_dt.date()

        # default duration
        stop_dt = start_dt + timedelta(minutes=DEFAULT_DURATION_MIN)

        items.append({"start": start_dt, "stop": stop_dt, "title": title})
        last_start = start_dt

    # infer stops by next start when possible
    items_sorted = sorted(items, key=lambda x: x['start'])
    for i in range(len(items_sorted)-1):
        items_sorted[i]['stop'] = items_sorted[i+1]['start']
    return items_sorted

def build_xmltv(programs):
    tv = ET.Element("tv")
    tv.set("generator-info-name", "boomerang.py")
    tv.set("source-info-url", SOURCE_URL)

    # channel node
    ch = ET.SubElement(tv, "channel", id=CHANNEL_ID)
    dn = ET.SubElement(ch, "display-name")
    dn.text = CHANNEL_NAME

    # programmes
    for p in programs:
        start_str = p["start"].strftime("%Y%m%d%H%M%S") + " " + TZ_OFFSET
        stop_str = p["stop"].strftime("%Y%m%d%H%M%S") + " " + TZ_OFFSET
        prog = ET.SubElement(tv, "programme", start=start_str, stop=stop_str, channel=CHANNEL_ID)
        title = ET.SubElement(prog, "title", lang="vi")
        title.text = p["title"]
    return ET.tostring(tv, encoding="utf-8", method="xml")

def main():
    # base date = today in Hanoi
    hanoi = tz.gettz("Asia/Ho_Chi_Minh")
    today_hanoi = datetime.now(tz=hanoi).date()

    try:
        html = fetch_page(SOURCE_URL)
    except Exception as e:
        print("Failed to fetch source:", e, file=sys.stderr)
        sys.exit(2)

    soup = BeautifulSoup(html, "lxml")

    # 1) first try to find explicit tables or pre blocks with pipes (legacy)
    rows_with_pipes = []
    for tag in soup.find_all(["pre", "code", "table"]):
        txt = tag.get_text("\n", strip=True)
        if "|" in txt or tag.name == "table":
            rows_with_pipes.append(txt)
    programs = []
    if rows_with_pipes:
        # attempt to parse time rows from best candidate
        best = max(rows_with_pipes, key=lambda t: (t.count("\n"), t.count("|")))
        # split lines, find lines containing times
        lines = [ln.strip() for ln in best.splitlines() if ln.strip()]
        time_lines = [ln for ln in lines if TIME_RE.search(ln)]
        time_nodes = []
        for ln in time_lines:
            m = TIME_RE.search(ln)
            if m:
                time_nodes.append((m.group(0).replace(".", ":"), ln))
        # Convert pseudo-nodes to Titles (ln string)
        last_start = None
        current_day = today_hanoi
        for time_str, ln in time_nodes:
            # title is rest of line after time
            title = re.sub(re.escape(time_str), "", ln, count=1).strip()
            if not title:
                continue
            hh, mm = (int(x) for x in time_str.split(":"))
            start_dt = datetime.combine(current_day, time(hh, mm))
            if last_start and start_dt <= last_start:
                start_dt = start_dt + timedelta(days=1)
                current_day = start_dt.date()
            stop_dt = start_dt + timedelta(minutes=DEFAULT_DURATION_MIN)
            programs.append({"start": start_dt, "stop": stop_dt, "title": clean_title(title)})
            last_start = start_dt

    # 2) fallback: generic search for time tokens in page and extract nearby titles
    if not programs:
        time_nodes = find_time_nodes(soup)
        # keep order of appearance
        programs = build_program_list(time_nodes, today_hanoi)

    # Write XMLTV (even if empty program list, include channel node)
    xml_bytes = build_xmltv(programs)
    with open(OUTPUT_FILE, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(xml_bytes)

    print(f"Wrote {OUTPUT_FILE} with {len(programs)} programmes (source: {SOURCE_URL})")

if __name__ == "__main__":
    main()
      
