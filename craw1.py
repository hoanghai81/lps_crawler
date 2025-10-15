#!/usr/bin/env python3
# craw1.py
"""
Crawler that:
- Reads kenh.txt (each line: "id | url | name" or just URL)
- For each channel URL, normalizes the ngay= parameter at runtime to Hanoi date(s)
- Fetches pages and parses programmes
- Produces a single epg1.xml in XMLTV format containing programmes for multiple days
- Saves debug_<channel>.html, channels_processed.txt, programmes_count.txt
- Prints a preview of epg1.xml for CI logs

Behavior:
- Uses timezone Asia/Ho_Chi_Minh for date calculation and XML times (+0700)
- By default fetches two days: today (offset 0) and tomorrow (offset 1)
- You can override days using env var EPG_DAY_OFFSETS (comma-separated offsets, e.g., "0,1" or "0")
"""

import os
import re
import sys
import time
import traceback
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date, timedelta
from dateutil import parser as dateparser
import pytz
import xml.etree.ElementTree as ET

# Config
KENH_TXT = "kenh.txt"
OUTPUT = "epg1.xml"
TIMEZONE = "Asia/Ho_Chi_Minh"
DEFAULT_DURATION_MIN = 30
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36")

tz = pytz.timezone(TIMEZONE)


def today_in_hanoi():
    tz_local = pytz.timezone(TIMEZONE)
    return datetime.now(tz_local).date()


def parse_offsets_env():
    v = os.environ.get("EPG_DAY_OFFSETS", "0,1")
    parts = [p.strip() for p in v.split(",") if p.strip() != ""]
    offsets = []
    for p in parts:
        try:
            offsets.append(int(p))
        except Exception:
            continue
    if not offsets:
        offsets = [0, 1]
    return sorted(set(offsets))


def load_channels_from_kenh_txt(path):
    if not os.path.exists(path):
        print(f"[ERROR] {path} not found", file=sys.stderr)
        return []
    chans = []
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            if "|" in ln:
                parts = [p.strip() for p in ln.split("|")]
                if len(parts) >= 2:
                    cid = parts[0]
                    url = parts[1]
                    name = parts[2] if len(parts) >= 3 else cid
                    chans.append({"id": cid, "url": url, "name": name})
                    continue
            if ln.startswith("http"):
                host = re.sub(r'https?://(www\.)?', '', ln).split("/")[0]
                cid = host.replace(".", "_")
                chans.append({"id": cid, "url": ln, "name": cid})
            else:
                print(f"[WARN] Skipping invalid line in {path}: {ln}", file=sys.stderr)
    return chans


def normalize_date_in_url(url, offset_days=0):
    """
    Replace or add ngay=YYYY-MM-DD in url according to offset_days (Hanoi date)
    """
    d = today_in_hanoi() + timedelta(days=offset_days)
    ds = d.strftime("%Y-%m-%d")
    if re.search(r"ngay=[0-9]{4}-[0-9]{2}-[0-9]{2}", url):
        return re.sub(r"(ngay=)[0-9]{4}-[0-9]{2}-[0-9]{2}", r"\1" + ds, url)
    if "?" in url:
        return url + "&ngay=" + ds if "ngay=" not in url else url
    return url + "?ngay=" + ds


def fetch(url):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8"
    }
    try:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        time.sleep(0.3)
        return r.content
    except Exception as e:
        print(f"[ERROR] fetch error {url}: {e}", file=sys.stderr)
        return b""


def parse_time_from_text(base_date, txt):
    txt = (txt or "").strip()
    txt = txt.replace("h", ":").replace(".", ":")
    m = re.search(r'(\d{1,2}:\d{2})', txt)
    if not m:
        try:
            t = dateparser.parse(txt).time()
            return datetime.combine(base_date, t)
        except Exception:
            return None
    try:
        t = dateparser.parse(m.group(1)).time()
        return datetime.combine(base_date, t)
    except Exception:
        return None


def parse_angiang_html(html, base_date):
    """
    Specialized parser for angiangtv.vn pages.
    Heuristics:
    - Find rows/blocks containing time token.
    - Try to extract title from sibling cells, specific class names, or text after time token.
    """
    soup = BeautifulSoup(html, "lxml")
    items = []

    # 1) Try table rows first
    for row in soup.select("tr"):
        txt = row.get_text(" ", strip=True)
        m = re.search(r'(\d{1,2}[:h\.]\d{2})', txt)
        if not m:
            continue
        time_token = m.group(1).replace("h", ":").replace(".", ":")
        title = ""
        # Try td siblings (common pattern: time in one td, title in another)
        tds = row.find_all("td")
        if tds:
            for td in tds:
                ttxt = td.get_text(" ", strip=True)
                if not re.search(r'\d{1,2}[:h\.]\d{2}', ttxt):
                    if len(ttxt) > 0:
                        title = ttxt
                        break
        if not title:
            cand = row.select_one(".tieu-de, .title, .chuongtrinh, .program, .name, .ten-chuong-trinh, .tv-title")
            if cand:
                title = cand.get_text(" ", strip=True)
        if not title:
            tail = re.split(re.escape(m.group(1)), txt, maxsplit=1)
            if len(tail) > 1:
                title = tail[1].strip()
        if not title:
            nxt = row.find_next_sibling()
            if nxt:
                title = nxt.get_text(" ", strip=True)
        start_dt = parse_time_from_text(base_date, time_token)
        if start_dt:
            items.append({"start": start_dt, "title": title or "Unknown", "desc": ""})

    # 2) If none found in rows, scan li/div blocks
    if not items:
        for node in soup.select("li, div"):
            txt = node.get_text(" ", strip=True)
            m = re.search(r'(\d{1,2}[:h\.]\d{2})', txt)
            if not m:
                continue
            time_token = m.group(1).replace("h", ":").replace(".", ":")
            title = ""
            cand = node.select_one(".tieu-de, .title, .chuongtrinh, .program, .name, .ten-chuong-trinh, .tv-title")
            if cand:
                title = cand.get_text(" ", strip=True)
            if not title:
                tail = re.split(re.escape(m.group(1)), txt, maxsplit=1)
                if len(tail) > 1:
                    title = tail[1].strip()
            if not title:
                nxt = node.find_next_sibling()
                if nxt:
                    title = nxt.get_text(" ", strip=True)
            start_dt = parse_time_from_text(base_date, time_token)
            if start_dt:
                items.append({"start": start_dt, "title": title or "Unknown", "desc": ""})

    # sort + infer stop times
    items = sorted(items, key=lambda x: x['start'])
    for i in range(len(items) - 1):
        items[i]['stop'] = items[i + 1]['start']
    if items and 'stop' not in items[-1]:
        items[-1]['stop'] = items[-1]['start'] + timedelta(minutes=DEFAULT_DURATION_MIN)
    return items

###

def parse_antv_html(html, base_date):
    """
    Robust ANTV parser with contact/ad filtering.
    - Locates schedule container by heading or by subtree with many time tokens.
    - Selects candidate nodes with exactly 1 time token and not too large.
    - Filters out nodes that look like contact/ hotline/ email/ ads.
    - Deduplicates by (time, title).
    - Returns items with start/title/desc and inferred stop times.
    """
    soup = BeautifulSoup(html, "lxml")

    # helper to count time tokens
    def count_time_tokens(node):
        txt = node.get_text(" ", strip=True)
        return len(re.findall(r'\b\d{1,2}[:h\.]\d{2}\b', txt))

    # 1) find schedule heading
    schedule_heading = None
    for h_tag in soup.select("h1,h2,h3,h4,h5"):
        if "LỊCH PHÁT SÓNG" in h_tag.get_text(" ", strip=True).upper():
            schedule_heading = h_tag
            break

    # 2) choose container by ascending ancestors with many time tokens
    container = None
    if schedule_heading:
        best = (None, 0)
        node = schedule_heading
        for _ in range(5):
            if not node:
                break
            cnt = count_time_tokens(node)
            if cnt > best[1]:
                best = (node, cnt)
            node = node.parent
        if best[0] and best[1] >= 3:
            parent = best[0]
            # pick child of parent that contains time tokens
            candidates = []
            for child in parent.find_all(recursive=False):
                c = count_time_tokens(child)
                if c >= 1:
                    candidates.append((child, c))
            if candidates:
                container = sorted(candidates, key=lambda x: -x[1])[0][0]
            else:
                container = best[0]

    # fallback selectors
    if not container:
        container = soup.select_one(".lich-phat-song, .tv-schedule, .schedule, .box-list, .list-news")
    if not container:
        container = soup.select_one("main, #main, .content, .page-content") or soup

    # 3) collect candidates but stricter: prefer elements with 1 time token and small size
    raw_candidates = []
    for sel in ["li", "article", ".item", ".post-item", "div"]:
        for node in container.select(sel):
            txt = node.get_text(" ", strip=True)
            if not txt:
                continue
            time_count = len(re.findall(r'\b\d{1,2}[:h\.]\d{2}\b', txt))
            if time_count == 0:
                continue
            # skip very long blocks or many-lines blocks (likely sidebar/aggregates)
            lines = [ln for ln in txt.splitlines() if ln.strip()]
            if len(lines) > 8 or len(txt) > 400:
                continue
            # avoid nodes with too many time tokens (aggregates)
            if time_count > 3:
                continue
            raw_candidates.append((node, time_count))

    # preserve order, dedupe identical text blocks
    seen_texts = set()
    ordered_nodes = []
    for node, _ in raw_candidates:
        key = node.get_text(" ", strip=True)
        if key not in seen_texts:
            seen_texts.add(key)
            ordered_nodes.append(node)

    # 4) filters for contact/ads: regexes to detect phone/email/hotline/website/advert
    phone_re = re.compile(r'\b0\d{8,}\b')            # long phone numbers starting with 0 (>=9 digits)
    intl_phone_re = re.compile(r'\+\d{6,}')          # +country numbers
    email_re = re.compile(r'[\w\.-]+@[\w\.-]+')
    hotline_kw = re.compile(r'\b(hotline|hot-line|số điện thoại|điện thoại| hotline )\b', re.I)
    contact_kw = re.compile(r'\b(email|gmail|yahoo|facebook|zalo|web|www\.|http[:\/]{2})\b', re.I)
    ads_kw = re.compile(r'\b(quảng cáo|advertis|đặt quảng cáo|quảng cáo|sponsor)\b', re.I)

    items = []
    seen_programs = set()

    for node in ordered_nodes:
        txt = node.get_text("\n", strip=True)
        # skip blocks that clearly look like contact or ads
        if phone_re.search(txt) or intl_phone_re.search(txt) or email_re.search(txt) or hotline_kw.search(txt) or contact_kw.search(txt) or ads_kw.search(txt):
            continue

        # find first time token
        m = re.search(r'(\d{1,2}[:h\.]\d{2})', txt)
        if not m:
            continue
        time_token_raw = m.group(1)
        time_token = time_token_raw.replace("h", ":").replace(".", ":")

        # split into lines to get title/desc
        lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
        idx = None
        for i, ln in enumerate(lines):
            if re.search(re.escape(time_token_raw), ln):
                idx = i
                break

        title = ""
        desc = ""
        if idx is None:
            cleaned = re.sub(re.escape(time_token_raw), "", txt).strip()
            title = cleaned.split("\n")[0].strip()
        else:
            if idx + 1 < len(lines):
                title = lines[idx + 1]
                if idx + 2 < len(lines):
                    desc = " ".join(lines[idx + 2: idx + 4])
            else:
                # time and title on same line
                line_after = re.sub(re.escape(time_token_raw), "", lines[idx]).strip()
                title = line_after if line_after else "Unknown"

        # normalize title and filter trivial titles
        title_norm = re.sub(r'\b\d{1,2}[:h\.]\d{2}\b', '', title)
        title_norm = " ".join(title_norm.split()).strip()
        if not title_norm or len(title_norm) < 2:
            continue
        # avoid titles that are pure contact-like short strings
        if phone_re.search(title_norm) or email_re.search(title_norm) or hotline_kw.search(title_norm) or contact_kw.search(title_norm):
            continue

        dedupe_key = (time_token, title_norm.lower())
        if dedupe_key in seen_programs:
            continue
        seen_programs.add(dedupe_key)

        start_dt = parse_time_from_text(base_date, time_token)
        if not start_dt:
            continue

        items.append({"start": start_dt, "title": title_norm, "desc": " ".join(desc.split()) if desc else ""})

    # 5) sort + infer stop times (ensure monotonic stops)
    items = sorted(items, key=lambda x: x['start'])
    for i in range(len(items) - 1):
        if items[i + 1]['start'] <= items[i]['start']:
            items[i]['stop'] = items[i]['start'] + timedelta(minutes=DEFAULT_DURATION_MIN)
        else:
            items[i]['stop'] = items[i + 1]['start']
    if items and 'stop' not in items[-1]:
        items[-1]['stop'] = items[-1]['start'] + timedelta(minutes=DEFAULT_DURATION_MIN)

    return items
      

def crawl_generic(html, url):
    soup = BeautifulSoup(html, "lxml")
    m = re.search(r"ngay=([0-9\-]+)", url)
    try:
        base_date = dateparser.parse(m.group(1)).date() if m else today_in_hanoi()
    except Exception:
        base_date = today_in_hanoi()

    items = []
    selectors = [
        ".lich-item", ".lich-row", ".schedule-item", ".schedule .item",
        ".list-group-item", ".program-row", "ul.schedule li", "div.programme",
        "table tr", ".tg", ".time", ".thoigian"
    ]
    for sel in selectors:
        found = False
        for node in soup.select(sel):
            text = node.get_text(" ", strip=True)
            mtime = re.search(r'(\d{1,2}[:h\.]\d{2})', text)
            if not mtime:
                continue
            raw_time = mtime.group(1)
            time_text = raw_time.replace("h", ":").replace(".", ":")
            title = re.sub(re.escape(raw_time), "", text).strip()
            if not title:
                tn = node.select_one(".title, .tieu-de, .name")
                if tn:
                    title = tn.get_text(" ", strip=True)
            start_dt = parse_time_from_text(base_date, time_text)
            if start_dt:
                items.append({"start": start_dt, "title": title or "Unknown", "desc": ""})
                found = True
        if found:
            break

    if not items:
        for node in soup.find_all(text=re.compile(r'\d{1,2}[:h\.]\d{2}')):
            raw_time = node.strip()
            time_text = raw_time.replace("h", ":").replace(".", ":")
            parent = node.parent
            title = re.sub(re.escape(raw_time), "", parent.get_text(" ", strip=True)).strip()
            if not title:
                sib = parent.find_next_sibling()
                if sib:
                    title = sib.get_text(" ", strip=True)
            if not title:
                cand = node.find_next(string=lambda s: s and len(s.strip()) > 2 and not re.search(r'\d{1,2}[:h\.]\d{2}', s))
                if cand:
                    title = cand.strip()
            start_dt = parse_time_from_text(base_date, time_text)
            if start_dt:
                items.append({"start": start_dt, "title": title or "Unknown", "desc": ""})

    items = sorted(items, key=lambda x: x['start'])
    for i in range(len(items) - 1):
        items[i]['stop'] = items[i + 1]['start']
    if items and 'stop' not in items[-1]:
        items[-1]['stop'] = items[-1]['start'] + timedelta(minutes=DEFAULT_DURATION_MIN)

    return items


def build_xmltv(channels_programmes, outpath=OUTPUT):
    tv = ET.Element("tv", {"generator-info-name": "lps_crawler_v1"})
    for ch in channels_programmes:
        ch_el = ET.SubElement(tv, "channel", id=ch['id'])
        dn = ET.SubElement(ch_el, "display-name")
        dn.text = ch.get("name", ch['id'])
    total = 0
    for ch in channels_programmes:
        for p in ch.get("programmes", []):
            start = p['start']
            stop = p.get('stop') or (p['start'] + timedelta(minutes=DEFAULT_DURATION_MIN))
            if start.tzinfo is None:
                start = tz.localize(start)
            if stop.tzinfo is None:
                stop = tz.localize(stop)
            prog = ET.SubElement(tv, "programme", {
                "start": start.strftime("%Y%m%d%H%M%S %z"),
                "stop": stop.strftime("%Y%m%d%H%M%S %z"),
                "channel": ch['id']
            })
            t = ET.SubElement(prog, "title", {"lang": "vi"})
            t.text = p.get("title", "Unknown")
            if p.get("desc"):
                d = ET.SubElement(prog, "desc", {"lang": "vi"})
                d.text = p.get("desc", "")
            total += 1
    try:
        import xml.dom.minidom
        raw = ET.tostring(tv, encoding="utf-8")
        pretty = xml.dom.minidom.parseString(raw).toprettyxml(indent="  ", encoding="utf-8")
        with open(outpath, "wb") as f:
            f.write(pretty)
    except Exception as e:
        print(f"[ERROR] Failed to write pretty XML: {e}", file=sys.stderr)
        minimal = '<?xml version="1.0" encoding="UTF-8"?><tv generator-info-name="lps_crawler_v1"></tv>'
        with open(outpath, "wb") as f:
            f.write(minimal.encode("utf-8"))
    return total


def main():
    try:
        offsets = parse_offsets_env()  # e.g., [0,1]
        chans = load_channels_from_kenh_txt(KENH_TXT)
        if not chans:
            print("[ERROR] No channels to process - kenh.txt missing or empty", file=sys.stderr)
            with open(OUTPUT, "wb") as f:
                f.write(b'<?xml version="1.0" encoding="UTF-8"?><tv generator-info-name="lps_crawler_v1"></tv>')
            with open("channels_processed.txt", "w", encoding="utf-8") as f:
                f.write("")
            with open("programmes_count.txt", "w", encoding="utf-8") as f:
                f.write("0")
            sys.exit(0)

        processed = []
        channels_programmes = []

        # For each channel, for each requested offset, fetch and parse programmes for that base_date
        for ch in chans:
            cid = ch.get("id")
            orig_url = ch.get("url")
            name = ch.get("name", cid)
            all_items = []
            print(f"[INFO] Processing channel {cid} ({name}) for offsets: {offsets}")
            for off in offsets:
                effective_url = normalize_date_in_url(orig_url, offset_days=off)
                print(f"[INFO] Crawling {cid} offset={off} -> {effective_url}")
                try:
                    html = fetch(effective_url)
                    if html:
                        debug_name = f"debug_{cid}_d{off}.html"
                        try:
                            with open(debug_name, "wb") as fh:
                                fh.write(html)
                            print(f"[DEBUG] Saved debug HTML -> {debug_name}")
                        except Exception as e:
                            print(f"[WARN] Could not save debug HTML {debug_name}: {e}", file=sys.stderr)
                    else:
                        print(f"[WARN] No HTML fetched for {effective_url}", file=sys.stderr)

                    m = re.search(r"ngay=([0-9\-]+)", effective_url)
                    try:
                        base_date = dateparser.parse(m.group(1)).date() if m else today_in_hanoi()
                    except Exception:
                        base_date = today_in_hanoi()

                    if "angiangtv.vn" in effective_url:
                        items = parse_angiang_html(html, base_date)
                    else:
                        items = crawl_generic(html, effective_url)

                    # ensure items are for the correct base_date (parser uses base_date already)
                    all_items.extend(items)
                except Exception as e:
                    print(f"[ERROR] Exception while crawling {effective_url}: {e}", file=sys.stderr)
                    traceback.print_exc()
                time.sleep(0.2)

            # sort and ensure stops consistent across combined day items
            all_items = sorted(all_items, key=lambda x: x['start'])
            for i in range(len(all_items) - 1):
                all_items[i]['stop'] = all_items[i + 1]['start']
            if all_items and 'stop' not in all_items[-1]:
                all_items[-1]['stop'] = all_items[-1]['start'] + timedelta(minutes=DEFAULT_DURATION_MIN)

            channels_programmes.append({"id": cid, "name": name, "programmes": all_items})
            processed.append(cid)

        total_programmes = 0
        try:
            total_programmes = build_xmltv(channels_programmes, outpath=OUTPUT)
            print(f"[INFO] Wrote {OUTPUT}, total_programmes={total_programmes}")
            print("==== epg1.xml preview ====")
            try:
                with open(OUTPUT, "r", encoding="utf-8") as fh:
                    for i, line in enumerate(fh):
                        if i < 200:
                            print(line.rstrip())
                        else:
                            break
            except Exception as e:
                print(f"[WARN] Could not read {OUTPUT} for preview: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[ERROR] build_xmltv failed: {e}", file=sys.stderr)
            traceback.print_exc()
            with open(OUTPUT, "wb") as f:
                f.write(b'<?xml version="1.0" encoding="UTF-8"?><tv generator-info-name="lps_crawler_v1"></tv>')
            total_programmes = 0

        # write stats files
        try:
            with open("channels_processed.txt", "w", encoding="utf-8") as f:
                for p in processed:
                    f.write(p + "\n")
            with open("programmes_count.txt", "w", encoding="utf-8") as f:
                f.write(str(total_programmes))
        except Exception as e:
            print(f"[WARN] Could not write stats files: {e}", file=sys.stderr)

        print(f"[DONE] channels={len(processed)} programmes={total_programmes}")
        sys.exit(0)
    except Exception as e:
        print(f"[FATAL] Unexpected error: {e}", file=sys.stderr)
        traceback.print_exc()
        try:
            with open(OUTPUT, "wb") as f:
                f.write(b'<?xml version="1.0" encoding="UTF-8"?><tv generator-info-name="lps_crawler_v1"></tv>')
            with open("channels_processed.txt", "w", encoding="utf-8") as f:
                f.write("")
            with open("programmes_count.txt", "w", encoding="utf-8") as f:
                f.write("0")
        except:
            pass
        sys.exit(0)


if __name__ == "__main__":
    main()
      
