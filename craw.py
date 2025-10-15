#!/usr/bin/env python3
# craw.py
import os
import re
import sys
import yaml
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date, time, timedelta
from dateutil import parser as dateparser
import pytz
import xml.etree.ElementTree as ET

# CONFIG
TIMEZONE = "Asia/Ho_Chi_Minh"
KENH_TXT = "kenh.txt"
YML = "crawl1.yml"
OUTPUT = "epg.xml"
DEFAULT_DURATION_MIN = 30

def load_from_kenh_txt(path):
    if not os.path.exists(path):
        return []
    channels = []
    content = open(path, "r", encoding="utf-8").read()
    # try to find lines like: id | url | name or "boomerang | https://..."
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # split by pipe
        if "|" in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 2:
                if len(parts) == 2:
                    # id | url
                    channels.append({"id": parts[0], "url": parts[1], "name": parts[0]})
                else:
                    channels.append({"id": parts[0], "url": parts[1], "name": parts[2]})
        else:
            # try detect plain url line
            if line.startswith("http"):
                # fallback id from hostname
                host = re.sub(r'https?://(www\.)?','', line).split("/")[0]
                channels.append({"id": host, "url": line, "name": host})
    return channels

def load_from_yaml(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("channels", [])

def fetch(url):
    headers = {"User-Agent": "epg-crawler/1.0"}
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    return r.content

def parse_time_text_angiang(base_date, txt):
    # common formats: "07:30", "7h30"
    txt = txt.strip()
    txt = txt.replace("h", ":")
    txt = txt.replace(".", ":")
    try:
        t = dateparser.parse(txt).time()
    except Exception:
        # try HH:MM
        m = re.search(r'(\d{1,2}:\d{2})', txt)
        if m:
            t = dateparser.parse(m.group(1)).time()
        else:
            return None
    return datetime.combine(base_date, t)

def crawl_angiang(url):
    # parse schedule items from angiangtv page
    bs = BeautifulSoup(fetch(url), "lxml")
    # try find date from URL param
    m = re.search(r"ngay=([0-9\-]+)", url)
    if m:
        try:
            base_date = dateparser.parse(m.group(1)).date()
        except:
            base_date = date.today()
    else:
        base_date = date.today()
    items = []
    # heuristics: look for elements that contain time like "07:30" and a nearby title
    for node in bs.find_all(text=re.compile(r"\d{1,2}[:h\.]\d{2}")):
        parent = node.parent
        time_text = node.strip()
        # find title near by: sibling or next element
        title = ""
        desc = ""
        # sibling
        sib = parent.find_next_sibling()
        if sib and sib.get_text(strip=True):
            title = sib.get_text(" ", strip=True)
        else:
            # try parent next
            nxt = parent.parent.find_next_sibling()
            if nxt:
                title = nxt.get_text(" ", strip=True)
        # fallback: use parent text minus time
        if not title:
            t = parent.get_text(" ", strip=True)
            title = re.sub(re.escape(time_text), "", t).strip()
        start_dt = parse_time_text_angiang(base_date, time_text)
        if start_dt:
            items.append({"start": start_dt, "title": title or "Unknown", "desc": desc})
    # if none found try table rows
    if not items:
        for tr in bs.select("table tr"):
            tds = tr.find_all("td")
            if len(tds) >= 2:
                time_text = tds[0].get_text(" ", strip=True)
                title = tds[1].get_text(" ", strip=True)
                start_dt = parse_time_text_angiang(base_date, time_text)
                if start_dt:
                    items.append({"start": start_dt, "title": title, "desc": ""})
    # sort and infer stops
    items = sorted(items, key=lambda x: x['start'])
    for i in range(len(items)-1):
        items[i]['stop'] = items[i+1]['start']
    if items:
        items[-1]['stop'] = items[-1]['start'] + timedelta(minutes=DEFAULT_DURATION_MIN)
    return items

def crawl_msky_boomerang(url):
    # specific parser for info.msky.vn Boomerang style
    bs = BeautifulSoup(fetch(url), "lxml")
    # try to find day's date on page or assume today
    base_date = date.today()
    items = []
    # Observed list items or schedule table: find elements with time pattern and title near
    for node in bs.find_all(text=re.compile(r"\d{1,2}[:\.]\d{2}")):
        time_text = node.strip()
        parent = node.parent
        # find next text which seems like title
        title = ""
        # check siblings and parent's siblings for title
        candidate = parent.find_next(string=lambda s: s and len(s.strip())>2 and not re.search(r'\d{1,2}[:\.]\d{2}', s))
        if candidate:
            title = candidate.strip()
        else:
            # fallback: parent text minus time
            txt = parent.get_text(" ", strip=True)
            title = re.sub(re.escape(time_text), "", txt).strip()
        try:
            t = dateparser.parse(time_text).time()
            start_dt = datetime.combine(base_date, t)
            items.append({"start": start_dt, "title": title or "Unknown", "desc": ""})
        except:
            continue
    # alternate: look for schedule rows with class names
    if not items:
        for row in bs.select(".tv-schedule-row, .schedule, .program-row, .item"):
            txt = row.get_text(" ", strip=True)
            m = re.search(r'(\d{1,2}[:\.]\d{2})', txt)
            if m:
                time_text = m.group(1)
                title = re.sub(re.escape(time_text), "", txt).strip()
                try:
                    t = dateparser.parse(time_text).time()
                    items.append({"start": datetime.combine(base_date, t), "title": title, "desc": ""})
                except:
                    continue
    items = sorted(items, key=lambda x: x['start'])
    for i in range(len(items)-1):
        items[i]['stop'] = items[i+1]['start']
    if items:
        items[-1]['stop'] = items[-1]['start'] + timedelta(minutes=DEFAULT_DURATION_MIN)
    return items

def build_xmltv(channels_programmes):
    tz = pytz.timezone(TIMEZONE)
    tv = ET.Element("tv", {"generator-info-name":"lps_crawler"})
    # create channel elements
    for ch in channels_programmes:
        ch_tag = ET.SubElement(tv, "channel", id=ch['id'])
        dn = ET.SubElement(ch_tag, "display-name")
        dn.text = ch.get("name", ch['id'])
    # programme elements
    for ch in channels_programmes:
        for p in ch.get("programmes", []):
            start = p['start']
            stop = p.get('stop') or (p['start'] + timedelta(minutes=DEFAULT_DURATION_MIN))
            # ensure timezone-aware
            if start.tzinfo is None:
                start = tz.localize(start)
            if stop.tzinfo is None:
                stop = tz.localize(stop)
            prog = ET.SubElement(tv, "programme", {
                "start": start.strftime("%Y%m%d%H%M%S %z"),
                "stop": stop.strftime("%Y%m%d%H%M%S %z"),
                "channel": ch['id']
            })
            t = ET.SubElement(prog, "title", {"lang":"vi"})
            t.text = p.get("title", "Unknown")
            if p.get("desc"):
                d = ET.SubElement(prog, "desc", {"lang":"vi"})
                d.text = p.get("desc","")
    # pretty print
    import xml.dom.minidom
    raw = ET.tostring(tv, encoding="utf-8")
    pretty = xml.dom.minidom.parseString(raw).toprettyxml(indent="  ", encoding="utf-8")
    with open(OUTPUT, "wb") as f:
        f.write(pretty)
    print(f"Wrote {OUTPUT} with {sum(len(ch.get('programmes',[])) for ch in channels_programmes)} programmes.")

def main():
    # load channels from kenh.txt first, else from crawl1.yml
    channels = load_from_kenh_txt(KENH_TXT)
    if not channels:
        channels = load_from_yaml(YML)
    if not channels:
        print("No channels found in kenh.txt or crawl1.yml", file=sys.stderr)
        sys.exit(1)
    channels_programmes = []
    for ch in channels:
        url = ch['url']
        ch_id = ch.get('id') or re.sub(r'https?://(www\.)?','', url).split("/")[0]
        name = ch.get('name') or ch_id
        print(f"Crawling {ch_id} -> {url}")
        try:
            if "angiangtv.vn" in url:
                programmes = crawl_angiang(url)
            elif "info.msky.vn" in url or "msky.vn" in url:
                programmes = crawl_msky_boomerang(url)
            else:
                # generic crawler: find time+title pairs
                bs = BeautifulSoup(fetch(url), "lxml")
                base_date = date.today()
                programmes = []
                for node in bs.find_all(text=re.compile(r"\d{1,2}[:\.]\d{2}")):
                    time_text = node.strip()
                    # title guess
                    title = ""
                    candidate = node.find_next(string=lambda s: s and len(s.strip())>2 and not re.search(r'\d{1,2}[:\.]\d{2}', s))
                    if candidate:
                        title = candidate.strip()
                    else:
                        title = node.parent.get_text(" ", strip=True)
                    try:
                        t = dateparser.parse(time_text).time()
                        programmes.append({"start": datetime.combine(base_date, t), "title": title, "desc": ""})
                    except:
                        continue
                programmes = sorted(programmes, key=lambda x: x['start'])
                for i in range(len(programmes)-1):
                    programmes[i]['stop'] = programmes[i+1]['start']
                if programmes:
                    programmes[-1]['stop'] = programmes[-1]['start'] + timedelta(minutes=DEFAULT_DURATION_MIN)
        except Exception as e:
            print(f"Error crawling {url}: {e}", file=sys.stderr)
            programmes = []
        channels_programmes.append({"id": ch_id, "name": name, "programmes": programmes})
    build_xmltv(channels_programmes)

if __name__ == "__main__":
    main()
