#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
boomerang.py
Generate boomerang.xml (XMLTV) for CARTOONITO (channel id: cartoonito)
Source: https://info.msky.vn/vn/Boomerang.html

Behavior:
- Fetches the source page and finds the best container with schedule by counting time tokens.
- Removes scripts/styles before parsing.
- Extracts time tokens (HH:MM) and nearest titles, handles midnight rollover.
- Deduplicates by (start_time, normalized_title).
- Always writes a valid XMLTV with channel node even if no programmes found.
- Timezone fixed to +0700.
"""

from datetime import datetime, date, time as dtime, timedelta
import re
import sys
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from dateutil import tz

SOURCE_URL = "https://info.msky.vn/vn/Boomerang.html"
CHANNEL_ID = "cartoonito"
CHANNEL_NAME = "CARTOONITO"
OUTPUT_FILE = "boomerang.xml"
DEFAULT_DURATION_MIN = 30
TZ_OFFSET = "+0700"  # for timestamps in XMLTV

# regex to find time tokens like 6:30, 06:30, 23:59, 6.30 (dot allowed)
TIME_RE = re.compile(r'\b([01]?\d|2[0-3])[:.][0-5]\d\b')

# text patterns to treat as noise
NOISE_PATTERNS = [
    re.compile(r'console\.log', re.I),
    re.compile(r'function\s*\(', re.I),
    re.compile(r'\$\(|jQuery', re.I),
    re.compile(r'http[:\/]{2}', re.I),
    re.compile(r'@[\w\.-]+', re.I),  # emails
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; boomerang-bot/1.0)"}


def fetch_html(url, timeout=20):
    resp = requests.get(url, timeout=timeout, headers=HEADERS)
    resp.raise_for_status()
    return resp.text


def clean_soup(soup):
    # remove scripts, styles, comments
    for tag in soup.find_all(["script", "style", "noscript", "iframe"]):
        tag.decompose()
    # remove comments
    for element in soup(text=lambda t: isinstance(t, (NavigableString,)) and isinstance(t, type(soup.new_string(''))) and t.strip().startswith("<!--")):
        try:
            element.extract()
        except Exception:
            pass
    return soup


def count_time_tokens(node):
    txt = node.get_text(" ", strip=True)
    return len(TIME_RE.findall(txt))


def choose_best_container(soup):
    # candidate selectors that often contain schedules
    selectors = [
        "main", "#main", ".content", ".page-content", ".schedule", ".lich-phat-song",
        ".lps", ".program-list", ".tv-schedule", ".box-list", "article"
    ]
    candidates = []
    # try explicit selectors first
    for sel in selectors:
        found = soup.select(sel)
        for f in found:
            cnt = count_time_tokens(f)
            if cnt:
                candidates.append((f, cnt))
    # fallback: search all divs with at least one time token, limit to reasonable count
    if not candidates:
        for div in soup.find_all(["div", "section", "article"], limit=200):
            cnt = count_time_tokens(div)
            if cnt:
                candidates.append((div, cnt))
    if not candidates:
        # final fallback: entire document
        return soup
    # choose candidate with maximum time tokens
    best = max(candidates, key=lambda x: x[1])[0]
    return best


def is_noise_text(s):
    if not s:
        return True
    low = s.lower()
    # short nonsense
    if len(low) < 2:
        return True
    for p in NOISE_PATTERNS:
        if p.search(low):
            return True
    # lines that look like pure digits or just punctuation
    if re.fullmatch(r'[\d\-\:\.\s\|]+', low):
        return True
    return False


def extract_time_nodes(container):
    """
    Return list of tuples (time_str, node) in document order from the container.
    node is the NavigableString that contains the time token.
    """
    matches = []
    for text in container.find_all(string=TIME_RE):
        # skip empty or noise-containing text
        parent = getattr(text, "parent", None)
        if parent and parent.name in ("script", "style", "noscript", "iframe"):
            continue
        t = TIME_RE.search(text)
        if t:
            matches.append((t.group(0).replace(".", ":"), text))
    return matches


def sibling_text(s):
    if isinstance(s, Tag):
        return s.get_text(" ", strip=True)
    return str(s).strip()


def clean_title(s):
    if not s:
        return ""
    s = re.sub(r'\s+', ' ', s).strip()
    # remove leading/trailing separators
    s = re.sub(r'^[\-\:\–\—\|]+\s*', '', s)
    s = re.sub(r'\s*[\-\:\–\—\|]+$', '', s)
    # remove code-like fragments
    for p in NOISE_PATTERNS:
        s = p.sub('', s)
    return s.strip()


def extract_title_near_node(node):
    """
    Given a NavigableString node containing a time token, attempt to find the program title:
    Strategy:
      1) If same text node contains additional text (after or before time), use it.
      2) Check direct siblings (next and previous).
      3) Check parent element child nodes after the time node.
      4) Search next elements in doc order up to a small limit.
    """
    text_str = str(node)
    m = TIME_RE.search(text_str)
    if m:
        after = text_str[m.end():].strip()
        if after and not TIME_RE.search(after) and not is_noise_text(after):
            return clean_title(after)
        before = text_str[:m.start()].strip()
        if before and not TIME_RE.search(before) and not is_noise_text(before):
            return clean_title(before)

    # siblings: prefer next sibling
    ns = node.next_sibling
    if ns:
        st = sibling_text(ns)
        if st and not TIME_RE.search(st) and not is_noise_text(st):
            return clean_title(st)

    ps = node.previous_sibling
    if ps:
        st = sibling_text(ps)
        if st and not TIME_RE.search(st) and not is_noise_text(st):
            return clean_title(st)

    # parent children after the node
    parent = getattr(node, "parent", None)
    if parent:
        found = False
        for child in parent.contents:
            if child is node or (isinstance(child, NavigableString) and child == node):
                found = True
                continue
            if found:
                ct = child.get_text(" ", strip=True) if isinstance(child, Tag) else str(child).strip()
                if ct and not TIME_RE.search(ct) and not is_noise_text(ct):
                    return clean_title(ct)

    # search next text nodes in document order (limited steps)
    nxt = node
    steps = 0
    while nxt and steps < 15:
        nxt = nxt.next_element
        if isinstance(nxt, NavigableString):
            s = str(nxt).strip()
            if s and not TIME_RE.search(s) and not is_noise_text(s):
                return clean_title(s)
        steps += 1

    return ""


def build_programs_from_time_nodes(time_nodes, base_date):
    """
    time_nodes: list of (time_str, node) in doc order
    base_date: date for the first day's schedules
    Returns: list of programs dicts with start, stop, title
    """
    programs = []
    last_start = None
    current_day = base_date
    seen = set()

    for time_str, node in time_nodes:
        title = extract_title_near_node(node)
        if not title:
            # try to find an emphasized tag in parent (b,strong,h*)
            p = getattr(node, "parent", None)
            if p:
                heading = p.find(["b", "strong", "h1", "h2", "h3", "h4", "h5"])
                if heading:
                    title = heading.get_text(" ", strip=True)
        if not title:
            # skip if no plausible title
            continue

        # skip noisy titles
        if is_noise_text(title):
            continue

        # parse time
        hh, mm = (int(x) for x in time_str.split(":"))
        start_dt = datetime.combine(current_day, dtime(hh, mm))
        if last_start and start_dt <= last_start:
            # rollover to next day
            start_dt = start_dt + timedelta(days=1)
            current_day = start_dt.date()

        # dedupe by (date, time, normalized title)
        key = (start_dt.isoformat(), re.sub(r'\s+', ' ', title).lower())
        if key in seen:
            last_start = start_dt
            continue
        seen.add(key)

        programs.append({"start": start_dt, "stop": start_dt + timedelta(minutes=DEFAULT_DURATION_MIN), "title": title})
        last_start = start_dt

    # infer stops from next start times
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

    # channel node
    ch = ET.SubElement(tv, "channel", id=CHANNEL_ID)
    dn = ET.SubElement(ch, "display-name")
    dn.text = CHANNEL_NAME

    # programmes
    for p in programs:
        prog = ET.SubElement(tv, "programme", start=xmltv_timestamp(p["start"]), stop=xmltv_timestamp(p["stop"]), channel=CHANNEL_ID)
        title = ET.SubElement(prog, "title", lang="vi")
        title.text = p["title"]
        # optional source info in credits
        credits = ET.SubElement(prog, "credits")
        presenter = ET.SubElement(credits, "presenter")
        presenter.text = "Source: " + SOURCE_URL

    # produce bytes
    return ET.tostring(tv, encoding="utf-8", method="xml")


def main():
    # base_date = today in Hanoi
    htz = tz.gettz("Asia/Ho_Chi_Minh")
    today_hanoi = datetime.now(tz=htz).date()

    try:
        html = fetch_html(SOURCE_URL)
    except Exception as e:
        print("Failed to fetch source:", e, file=sys.stderr)
        # write minimal xml with channel node and exit 0 so CI doesn't fail hard
        empty_xml = build_xmltv([])
        with open(OUTPUT_FILE, "wb") as f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write(empty_xml)
        sys.exit(0)

    soup = BeautifulSoup(html, "lxml")
    clean_soup(soup)

    container = choose_best_container(soup)

    # extract time nodes in container
    time_nodes = extract_time_nodes(container)
    if not time_nodes:
        # fallback: try whole page if container had none
        time_nodes = extract_time_nodes(soup)

    # ensure order is document order (they should be)
    programs = build_programs_from_time_nodes(time_nodes, today_hanoi)

    # write xmltv even if empty
    xml_bytes = build_xmltv(programs)
    with open(OUTPUT_FILE, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(xml_bytes)

    print(f"Wrote {OUTPUT_FILE} with {len(programs)} programmes (source: {SOURCE_URL})")


if __name__ == "__main__":
    main()
