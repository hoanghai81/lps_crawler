#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
boomerang.py
Generate boomerang.xml (XMLTV) for CARTOONITO (channel id: cartoonito)
Source: https://info.msky.vn/vn/Boomerang.html

Improvements in this version:
- Remove scripts/styles/pre/code/json-ld before parsing.
- Find best container by counting time tokens.
- Extract time tokens and nearest titles, with robust cleaning.
- Remove "Source: ..." and other noise from titles.
- Deduplicate by (start_iso, normalized_title).
- Infer stop times from next program; fallback default duration.
- Always write valid XMLTV with channel node even if no programmes found.
"""

from datetime import datetime, date, time as dtime, timedelta
import re
import sys
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup, NavigableString, Tag, Comment
from dateutil import tz

SOURCE_URL = "https://info.msky.vn/vn/Boomerang.html"
CHANNEL_ID = "cartoonito"
CHANNEL_NAME = "CARTOONITO"
OUTPUT_FILE = "boomerang.xml"
DEFAULT_DURATION_MIN = 30
TZ_OFFSET = "+0700"  # timezone for timestamps

# regex to find time tokens like 6:30, 06:30, 23:59, 6.30 (dot allowed)
TIME_RE = re.compile(r'\b([01]?\d|2[0-3])[:.][0-5]\d\b')

# noise patterns to avoid
NOISE_PATTERNS = [
    re.compile(r'console\.log', re.I),
    re.compile(r'function\s*\(', re.I),
    re.compile(r'\$\(|jQuery', re.I),
    re.compile(r'http[:\/]{2}', re.I),
    re.compile(r'@[\w\.-]+', re.I),  # emails
    re.compile(r'\bhotline\b', re.I),
    re.compile(r'\bemail\b', re.I),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; boomerang-bot/1.0)"}


def fetch_html(url, timeout=20):
    r = requests.get(url, timeout=timeout, headers=HEADERS)
    r.raise_for_status()
    return r.text


def remove_noise_tags(soup):
    # remove script/style/noscript/iframe/pre/code/json-ld and comments
    for tag in soup.find_all(["script", "style", "noscript", "iframe", "pre", "code"]):
        try:
            tag.decompose()
        except Exception:
            pass
    # remove JSON-LD blocks (application/ld+json)
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            tag.decompose()
        except Exception:
            pass
    # remove comments
    for c in soup.find_all(text=lambda t: isinstance(t, Comment)):
        try:
            c.extract()
        except Exception:
            pass
    return soup


def count_time_tokens(node):
    txt = node.get_text(" ", strip=True)
    return len(TIME_RE.findall(txt))


def choose_best_container(soup):
    selectors = [
        "main", "#main", ".content", ".page-content", ".schedule", ".lich-phat-song",
        ".lps", ".program-list", ".tv-schedule", ".box-list", "article", ".site-content"
    ]
    candidates = []
    for sel in selectors:
        for el in soup.select(sel):
            cnt = count_time_tokens(el)
            if cnt:
                candidates.append((el, cnt))
    if not candidates:
        # fallback: search reasonable nodes
        for el in soup.find_all(["div", "section", "article"], limit=300):
            cnt = count_time_tokens(el)
            if cnt:
                candidates.append((el, cnt))
    if not candidates:
        return soup
    best = max(candidates, key=lambda x: x[1])[0]
    return best


def is_noise_text(s):
    if not s or not s.strip():
        return True
    low = s.strip().lower()
    if len(low) < 2:
        return True
    for p in NOISE_PATTERNS:
        if p.search(low):
            return True
    # pure punctuation/digits
    if re.fullmatch(r'[\d\-\:\.\s\|,]+', low):
        return True
    return False


def extract_time_nodes(container):
    """
    Return list of (time_str, node) in document order where node is the NavigableString containing the token.
    """
    matches = []
    for text in container.find_all(string=TIME_RE):
        parent = getattr(text, "parent", None)
        if parent and parent.name in ("script", "style", "noscript", "iframe"):
            continue
        m = TIME_RE.search(text)
        if m:
            matches.append((m.group(0).replace(".", ":"), text))
    return matches


def sibling_text(x):
    if isinstance(x, Tag):
        return x.get_text(" ", strip=True)
    return str(x).strip()


def clean_title(s):
    if not s:
        return ""
    s = re.sub(r'\s+', ' ', s).strip()
    # remove leading/trailing separators
    s = re.sub(r'^[\-\:\–\—\|]+\s*', '', s)
    s = re.sub(r'\s*[\-\:\–\—\|]+$', '', s)
    # remove explicit Source: URL or similar
    s = re.sub(r'\bSource:\s*https?:\/\/\S+', '', s, flags=re.I)
    s = re.sub(r'https?:\/\/\S+', '', s, flags=re.I)
    # remove code-like or noise patterns
    for p in NOISE_PATTERNS:
        s = p.sub('', s)
    s = s.strip()
    return s


def extract_title_near_node(node):
    """
    For a text node containing a time token, try to extract a nearby title.
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

    # next sibling
    ns = node.next_sibling
    if ns:
        st = sibling_text(ns)
        if st and not TIME_RE.search(st) and not is_noise_text(st):
            return clean_title(st)

    # prev sibling
    ps = node.previous_sibling
    if ps:
        st = sibling_text(ps)
        if st and not TIME_RE.search(st) and not is_noise_text(st):
            return clean_title(st)

    # parent children after node
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

    # search forward in document order
    nxt = node
    steps = 0
    while nxt and steps < 20:
        nxt = nxt.next_element
        if isinstance(nxt, NavigableString):
            s = str(nxt).strip()
            if s and not TIME_RE.search(s) and not is_noise_text(s):
                return clean_title(s)
        steps += 1

    return ""


def build_programs_from_time_nodes(time_nodes, base_date):
    programs = []
    last_start = None
    current_day = base_date
    seen = set()
    for time_str, node in time_nodes:
        title = extract_title_near_node(node)
        if not title:
            p = getattr(node, "parent", None)
            if p:
                heading = p.find(["b", "strong", "h1", "h2", "h3", "h4", "h5"])
                if heading:
                    title = heading.get_text(" ", strip=True)
        title = clean_title(title)
        if not title or is_noise_text(title):
            continue
        try:
            hh, mm = (int(x) for x in time_str.split(":"))
        except Exception:
            continue
        start_dt = datetime.combine(current_day, dtime(hh, mm))
        if last_start and start_dt <= last_start:
            start_dt = start_dt + timedelta(days=1)
            current_day = start_dt.date()
        key = (start_dt.isoformat(), re.sub(r'\s+', ' ', title).lower())
        if key in seen:
            last_start = start_dt
            continue
        seen.add(key)
        programs.append({"start": start_dt, "stop": start_dt + timedelta(minutes=DEFAULT_DURATION_MIN), "title": title})
        last_start = start_dt

    # infer stops
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
        if not p.get("start") or not p.get("stop") or not p.get("title"):
            continue
        prog = ET.SubElement(tv, "programme", start=xmltv_timestamp(p["start"]), stop=xmltv_timestamp(p["stop"]), channel=CHANNEL_ID)
        title = ET.SubElement(prog, "title", lang="vi")
        title.text = p["title"]
        credits = ET.SubElement(prog, "credits")
        presenter = ET.SubElement(credits, "presenter")
        presenter.text = "Source: " + SOURCE_URL
    return ET.tostring(tv, encoding="utf-8", method="xml")


def write_xml_file(xml_bytes):
    with open(OUTPUT_FILE, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(xml_bytes)


def main():
    htz = tz.gettz("Asia/Ho_Chi_Minh")
    today_hanoi = datetime.now(tz=htz).date()

    try:
        html = fetch_html(SOURCE_URL)
    except Exception as e:
        # write minimal xml and exit 0 to avoid CI failing hard
        empty_xml = build_xmltv([])
        write_xml_file(empty_xml)
        print("Failed to fetch source:", e, file=sys.stderr)
        sys.exit(0)

    soup = BeautifulSoup(html, "lxml")
    remove_noise_tags(soup)
    container = choose_best_container(soup)

    # additional defensive removals on chosen container
    for bad in container.select(".debug, .json-ld, .hidden, .rawdump"):
        try:
            bad.decompose()
        except Exception:
            pass

    time_nodes = extract_time_nodes(container)
    if not time_nodes:
        time_nodes = extract_time_nodes(soup)

    programs = build_programs_from_time_nodes(time_nodes, today_hanoi)

    xml_bytes = build_xmltv(programs)
    write_xml_file(xml_bytes)

    print(f"Wrote {OUTPUT_FILE} with {len(programs)} programmes (source: {SOURCE_URL})")


if __name__ == "__main__":
    main()
