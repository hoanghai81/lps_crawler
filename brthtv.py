# brthtv.py
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz
import re
import xml.sax.saxutils as sax

URL = "https://brt.vn/truyen-hinh"
CHANNEL_ID = "brthtv"
CHANNEL_NAME = "BRT HTV"
OUTPUT = "brthtv.xml"
VN = pytz.timezone("Asia/Ho_Chi_Minh")

time_re = re.compile(r'^\s*(\d{1,2}:\d{2})\s*$')

def render_page_html(url, wait_ms=3000):
    """Render page with Playwright and return HTML content."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = browser.new_context()
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        # small extra wait for dynamic inserts
        page.wait_for_timeout(wait_ms)
        content = page.content()
        browser.close()
        return content

def extract_schedule_from_html(html):
    """
    Robust extractor:
    - Find elements whose text matches a time pattern (HH:MM)
    - For each, try to find the program title in same row / sibling / nearby element
    Returns list of tuples: (time_str 'HH:MM', title)
    """
    soup = BeautifulSoup(html, "html.parser")
    schedule = []

    # strategy 1: look for <td> with time in table rows
    for td in soup.find_all(['td','span','div','p','li']):
        txt = td.get_text(strip=True)
        if not txt:
            continue
        m = time_re.match(txt)
        if m:
            time_txt = m.group(1)
            title = None

            # Try to find title in same table row (<tr>)
            tr = td.find_parent('tr')
            if tr:
                # find other <td> in this tr that are not the time
                for other in tr.find_all('td'):
                    ot = other.get_text(strip=True)
                    if ot and not time_re.match(ot):
                        title = ot
                        break

            # If not found, try siblings in DOM (next elements)
            if not title:
                # search next siblings/elements for a non-time text
                # use next_elements generator
                for nxt in td.next_elements:
                    if getattr(nxt, "string", None):
                        s = nxt.get_text(strip=True) if hasattr(nxt, "get_text") else str(nxt).strip()
                    else:
                        try:
                            s = str(nxt).strip()
                        except:
                            s = ""
                    if not s:
                        continue
                    if time_re.match(s):
                        # hit another time — stop searching for this one
                        break
                    # ignore tiny separators
                    if len(s) >= 2:
                        title = s
                        break

            # If still not found, try parent container text minus time text
            if not title:
                parent = td.find_parent()
                if parent:
                    full = parent.get_text(" ", strip=True)
                    # remove the time part
                    full_minus_time = re.sub(re.escape(time_txt), "", full).strip()
                    if full_minus_time:
                        title = full_minus_time

            if title:
                schedule.append((time_txt, title))

    # Deduplicate preserving order (some times may be found multiple times)
    seen = set()
    dedup = []
    for t, ttl in schedule:
        key = (t, ttl)
        if key in seen:
            continue
        seen.add(key)
        dedup.append((t, ttl))

    return dedup

def build_xmltv(schedule):
    """
    schedule: list of (time_str, title) sorted by appearance
    Only for today's date (VN time).
    """
    tz = VN
    today = datetime.now(tz).date()
    programmes = []

    # build datetime objects
    for time_str, title in schedule:
        # normalize time strings like "7:00" -> "07:00"
        hhmm = time_str.strip()
        if ':' in hhmm:
            parts = hhmm.split(':')
            hh = parts[0].zfill(2)
            mm = parts[1].zfill(2)
            hhmm = f"{hh}:{mm}"
        try:
            dt = datetime.strptime(hhmm, "%H:%M")
        except ValueError:
            continue
        start_dt = datetime(year=today.year, month=today.month, day=today.day,
                            hour=dt.hour, minute=dt.minute)
        start_dt = tz.localize(start_dt)
        programmes.append({"start": start_dt, "title": title})

    # if no programmes return empty xml
    if not programmes:
        root = '<?xml version="1.0" encoding="UTF-8"?>\n'
        root += f'<tv source-info-name="brt.vn" generator-info-name="lps_crawler">\n'
        root += f'  <channel id="{CHANNEL_ID}"><display-name>{CHANNEL_NAME}</display-name></channel>\n</tv>\n'
        return root

    # compute stop times: next start or +30m default
    for i in range(len(programmes)):
        start = programmes[i]["start"]
        if i + 1 < len(programmes):
            stop = programmes[i + 1]["start"]
            # if next start <= start (rare) add a day to next start
            if stop <= start:
                stop = stop + timedelta(days=1)
        else:
            stop = start + timedelta(minutes=30)
        programmes[i]["stop"] = stop

    # ensure chronological order
    programmes.sort(key=lambda x: x["start"])

    # build xml
    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append(f'<tv source-info-name="brt.vn" generator-info-name="lps_crawler">')
    lines.append(f'  <channel id="{CHANNEL_ID}">')
    lines.append(f'    <display-name>{CHANNEL_NAME}</display-name>')
    lines.append(f'  </channel>')

    for p in programmes:
        start_s = p["start"].strftime("%Y%m%d%H%M%S %z")
        stop_s = p["stop"].strftime("%Y%m%d%H%M%S %z")
        title_escaped = sax.escape(p["title"])
        lines.append(f'  <programme start="{start_s}" stop="{stop_s}" channel="{CHANNEL_ID}">')
        lines.append(f'    <title lang="vi">{title_escaped}</title>')
        lines.append(f'  </programme>')

    lines.append('</tv>')
    return "\n".join(lines)

def main():
    print("=== RUNNING PLAYWRIGHT CRAWLER (BRT HTV) ===")
    try:
        html = render_page_html(URL, wait_ms=3000)
    except Exception as e:
        print("❌ Render error:", e)
        html = ""

    if not html:
        print("❌ Không nhận được HTML đã render.")
        xml = build_xmltv([]) if False else '<?xml version="1.0" encoding="UTF-8"?><tv source-info-name="brt.vn" generator-info-name="lps_crawler"><channel id="brthtv"><display-name>BRT HTV</display-name></channel></tv>'
        with open(OUTPUT, "w", encoding="utf-8") as f:
            f.write(xml)
        print(f"✅ Đã tạo file {OUTPUT}")
        return

    schedule = extract_schedule_from_html(html)
    print(f"✅ Phát hiện {len(schedule)} mục (time,title) raw.")
    for i, (t, ttl) in enumerate(schedule[:50]):
        print(f"{i+1:02d}. {t}  - {ttl}")

    xml = build_xmltv(schedule)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"✅ Xuất file {OUTPUT} (chứa {xml.count('<programme') } programmes)")
    print("=== DONE ===")

if __name__ == "__main__":
    main()
