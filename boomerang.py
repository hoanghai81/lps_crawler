#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
boomerang.py
Generate boomerang.xml (XMLTV) for CARTOONITO
Source: https://info.msky.vn/vn/Boomerang.html

Strategy:
1) Try parse HTML <table> that contains header 'Thời gian' (most reliable for this site).
2) If not found, try markdown pipe table block extraction.
3) Fallback to time-token scanning.
"""
from datetime import datetime, date, time as dtime, timedelta
import re
import sys
import xml.etree.ElementTree as ET
import html as html_mod

import requests
from bs4 import BeautifulSoup, Comment
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


def clean_soup_remove_noise(soup):
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


def parse_html_table(soup, base_date):
    """
    Find table element whose header contains 'Thời gian' (vn) or 'Time' then parse rows.
    Returns list of programs.
    """
    tables = soup.find_all("table")
    programs = []
    seen = set()
    last_start = None
    current_day = base_date

    for tbl in tables:
        # check header cells text for 'Thời gian' or 'Thoi gian' or 'Time'
        header_text = " ".join([th.get_text(" ", strip=True).lower() for th in tbl.find_all(["th", "td"])][:6])
        if any(k in header_text for k in ("thời gian", "thoi gian", "time", "thoi")):
            # found candidate table; parse rows
            for tr in tbl.find_all("tr"):
                tds = tr.find_all("td")
                if not tds:
                    continue
                # extract text from cells
                cells = [td.get_text(" ", strip=True) for td in tds]
                # try to find time token in first few cells
                time_token = None
                time_idx = None
                for i, c in enumerate(cells[:4]):
                    m = TIME_RE.search(c)
                    if m:
                        time_token = m.group(0).replace(".", ":")
                        time_idx = i
                        break
                if not time_token:
                    continue
                # title heuristics: cell after time_idx
                title = ""
                desc = ""
                dur_cell = ""
                if time_idx is not None and len(cells) > time_idx + 1:
                    title = cells[time_idx + 1]
                    if len(cells) >= time_idx + 4:
                        candidate = cells[-1]
                        if DUR_HHMM_RE.search(candidate) or DUR_MIN_RE.search(candidate):
                            dur_cell = candidate
                            if len(cells) > time_idx + 2:
                                desc = " ".join(cells[time_idx + 2:-1])
                        else:
                            desc = " ".join(cells[time_idx + 2:])
                    elif len(cells) == time_idx + 2:
                        pass
                    else:
                        desc = " ".join(cells[time_idx + 2:])
                else:
                    # fallback: second cell
                    if len(cells) >= 2:
                        title = cells[1]
                        if len(cells) > 2:
                            desc = " ".join(cells[2:])
                    else:
                        title = " ".join(cells)

                title = re.sub(r'https?://\S+', '', title).strip()
                desc = re.sub(r'https?://\S+', '', desc).strip()
                if not title or title.lower().startswith("thời gian") or title.lower().startswith("tên chương trình"):
                    continue

                try:
                    hh, mm = (int(x) for x in time_token.split(":"))
                except Exception:
                    continue
                start_dt = datetime.combine(current_day, dtime(hh, mm))
                if last_start and start_dt <= last_start:
                    start_dt = start_dt + timedelta(days=1)
                    current_day = start_dt.date()

                # parse duration
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
                    # search in title/desc/row
                    for txt in (title, desc, " ".join(cells)):
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
            # after parsing one suitable table, stop (site uses single table)
            break
    # infer stops from next start
    programs = sorted(programs, key=lambda x: x["start"])
    for i in range(len(programs) - 1):
        if programs[i + 1]["start"] > programs[i]["start"]:
            programs[i]["stop"] = programs[i + 1]["start"]
    return programs


def extract_pipe_table_from_html(html_raw):
    # similar to previous implementation: find pipe blocks
    html_unesc = html_mod.unescape(html_raw)
    markers = ['| Thời gian', '|Thời gian', '| Time', '| Thoi gian', '|Thoi gian']
    for m in markers:
        idx = html_unesc.find(m)
        if idx != -1:
            start = max(0, html_unesc.rfind('\n', 0, idx) - 2000)
            end = min(len(html_unesc), idx + 40000)
            block = html_unesc[start:end]
            rows = [ln.strip() for ln in block.splitlines() if '|' in ln]
            if len(rows) >= 3 and any(TIME_RE.search(r) for r in rows):
                return rows
    # fallback contiguous pipe runs
    all_lines = html_unesc.splitlines()
    best = []
    best_len = 0
    i = 0
    while i < len(all_lines):
        if '|' in all_lines[i]:
            j = i
            block = []
            while j < len(all_lines) and '|' in all_lines[j]:
                block.append(all_lines[j].strip())
                j += 1
            if len(block) >= 3 and any(TIME_RE.search(r) for r in block):
                if len(block) > best_len:
                    best_len = len(block)
                    best = block
            i = j
        else:
            i += 1
    return best


def parse_pipe_rows(rows, base_date):
    # reuse parse logic from earlier for pipe rows
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
                candidate = parts[-1]
                if DUR_HHMM_RE.search(candidate) or DUR_MIN_RE.search(candidate):
                    dur_cell = candidate
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
        if title.lower().startswith("thời gian") or title.lower().startswith("tên chương trình"):
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


def fallback_time_scan_unescaped(html_unesc, base_date):
    lines = [ln.strip() for ln in html_unesc.splitlines() if TIME_RE.search(ln)]
    programs = []
    seen = set()
    last_start = None
    current_day = base_date
    for ln in lines:
        m = TIME_RE.search(ln)
        if not m:
            continue
        time_token = m.group(0).replace('.', ':')
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
    programs = sorted(programs, key=lambda x: x["start"])
    for i in range(len(programs) - 1):
        if programs[i + 1]["start"] > programs[i]["start"]:
            programs[i]["stop"] = programs[i + 1]["start"]
    return programs


def main():
    htz = tz.gettz("Asia/Ho_Chi_Minh")
    base_date = datetime.now(tz=htz).date()

    try:
        html_raw = fetch_html(SOURCE_URL)
    except Exception as e:
        write_xml([])
        with open(DEBUG_FILE, "w", encoding="utf-8") as df:
            df.write("FETCH FAILED: " + str(e) + "\n")
        print("Fetch failed:", e, file=sys.stderr)
        sys.exit(0)

    html_unesc = html_mod.unescape(html_raw)
    soup = BeautifulSoup(html_raw, "lxml")
    clean_soup_remove_noise(soup)

    # 1) try HTML table parse
    programs = parse_html_table(soup, base_date)

    # 2) if none found, try pipe table extraction from raw HTML
    if not programs:
        rows = extract_pipe_table_from_html(html_raw)
        if rows:
            programs = parse_pipe_rows(rows, base_date)

    # 3) fallback scanning unescaped text
    if not programs:
        programs = fallback_time_scan_unescaped(html_unesc, base_date)

    # write debug
    with open(DEBUG_FILE, "w", encoding="utf-8") as df:
        df.write("Programs parsed: " + str(len(programs)) + "\n\n")
        for p in programs[:200]:
            df.write(f"{p['start'].isoformat()} -> {p['stop'].isoformat()} | {p['title']}\n")
        df.write("\n\n=== HTML snippet (first 20000 chars unescaped) ===\n")
        df.write(html_unesc[:20000])

    write_xml(programs)
    print(f"Wrote {OUTPUT_FILE} with {len(programs)} programmes (source: {SOURCE_URL})")
    print("Debug written to", DEBUG_FILE)


if __name__ == "__main__":
    main()
        
