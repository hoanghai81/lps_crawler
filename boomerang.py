# boomerang.py (fixed: normalize early-hours assigned to previous day)
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET
import xml.sax.saxutils as sax

# ========== CONFIG ==========
CHANNEL_ID = "boomerang"
CHANNEL_NAME = "CARTOONITO"
BASE_URL = "https://info.msky.vn/vn/Boomerang.html?date={date}"  # date in dd/mm/YYYY
OUTPUT_FILE = "boomerang.xml"
VN_TZ = timezone(timedelta(hours=7))
# ============================


def fetch_html_for_date(date_str):
    """Tải HTML của trang cho date_str định dạng dd/mm/YYYY"""
    url = BASE_URL.format(date=date_str)
    print(f"Fetching: {url}")
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def parse_table_rows(html, base_date):
    """
    Parse bảng EPG -> trả về list item dạng dict:
      { 'start_dt': datetime(tz=VN_TZ), 'title_vi': str, 'title_en': str_or_empty }
    Sử dụng chiến lược last_dt để xử lý rollover qua ngày tiếp theo.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        print("⚠️ Không tìm thấy bảng EPG")
        return []

    rows = table.find_all("tr")
    items = []

    last_dt = None

    # bỏ header nếu có
    for tr in rows[1:]:
        tds = tr.find_all("td")
        if not tds or len(tds) < 2:
            continue

        time_str = tds[0].get_text(strip=True)
        title_vi = tds[1].get_text(strip=True) if len(tds) > 1 else ""
        title_en = tds[2].get_text(strip=True) if len(tds) > 2 else ""

        # chuẩn hóa time_str
        if not time_str or ":" not in time_str:
            # bỏ nếu không có giờ
            continue

        # đảm bảo giờ dạng HH:MM
        parts = time_str.split(":")
        hh = parts[0].zfill(2)
        mm = parts[1].zfill(2)
        time_norm = f"{hh}:{mm}"

        # tạo datetime tạm dựa trên base_date
        try:
            start_dt = datetime.strptime(f"{base_date.strftime('%d/%m/%Y')} {time_norm}", "%d/%m/%Y %H:%M")
            start_dt = start_dt.replace(tzinfo=VN_TZ)
        except Exception as e:
            print(f"⚠️ Bỏ qua dòng thời gian không parse được: '{time_str}' ({e})")
            continue

        # Nếu đã có last_dt và start_dt <= last_dt => chương trình đã sang ngày tiếp theo
        if last_dt is not None:
            while start_dt <= last_dt:
                start_dt += timedelta(days=1)

        # append item (stop tính sau)
        items.append({
            "start_dt": start_dt,
            "title_vi": title_vi,
            "title_en": title_en,
            "duration_min": None  # có thể gán nếu có cột thời lượng
        })

        last_dt = start_dt

    return items


def compute_stops(items):
    """
    Từ danh sách items (có start_dt), tính stop_dt:
    - nếu có duration_min thì dùng
    - ngược lại stop = start của chương trình tiếp theo
    - chương trình cuối mặc định 30 phút
    """
    for i, it in enumerate(items):
        start = it["start_dt"]
        dur = it.get("duration_min")
        if dur and isinstance(dur, int) and dur > 0:
            stop = start + timedelta(minutes=dur)
        else:
            if i + 1 < len(items):
                stop = items[i + 1]["start_dt"]
                # nếu stop <= start (không hợp lệ) thì cộng 1 ngày để an toàn
                if stop <= start:
                    stop += timedelta(days=1)
            else:
                stop = start + timedelta(minutes=30)
        it["stop_dt"] = stop
    return items


def normalize_early_hours_to_base_date(items, base_date):
    """
    Một số site liệt kê 00:00-03:xx ở phần đầu của bảng và chúng có thể bị gán lùi về ngày trước.
    Nếu mục có start_dt.date() < base_date và giờ < 4 (00..03), ta +1 ngày để đưa về base_date.
    Điều này giữ các chương trình 00:00..03:59 thuộc ngày hiện tại.
    """
    adjusted = 0
    for it in items:
        sd = it["start_dt"]
        if sd.date() < base_date and sd.hour < 4:
            # shift forward until date == base_date (tránh shift quá)
            while sd.date() < base_date:
                sd = sd + timedelta(days=1)
            # adjust stop_dt tương ứng (nếu stop_dt <= old start => cộng cùng số ngày)
            delta_days = (sd.date() - it["start_dt"].date()).days
            it["start_dt"] = sd
            if "stop_dt" in it and it["stop_dt"] is not None:
                it["stop_dt"] = it["stop_dt"] + timedelta(days=delta_days)
            adjusted += 1
    if adjusted:
        print(f"🔧 Đã điều chỉnh {adjusted} mục early-hours sang ngày {base_date.isoformat()}")
    return items


def filter_only_today(items, base_date):
    """
    Lọc chỉ giữ chương trình có start thuộc ngày base_date (giờ VN).
    base_date: datetime.date (VN)
    """
    start_day = datetime.combine(base_date, datetime.min.time()).replace(tzinfo=VN_TZ)
    end_day = start_day + timedelta(days=1)
    filtered = [it for it in items if start_day <= it["start_dt"] < end_day]
    return filtered


def build_xml(items, output_file=OUTPUT_FILE):
    tv = ET.Element("tv", {
        "source-info-name": "msky.vn",
        "generator-info-name": "lps_crawler"
    })

    ch = ET.SubElement(tv, "channel", {"id": CHANNEL_ID})
    ET.SubElement(ch, "display-name").text = CHANNEL_NAME
    ET.SubElement(ch, "url").text = "https://info.msky.vn/vn/Boomerang.html"

    for it in items:
        start_s = it["start_dt"].strftime("%Y%m%d%H%M%S ") + "+0700"
        stop_s = it["stop_dt"].strftime("%Y%m%d%H%M%S ") + "+0700"
        prog = ET.SubElement(tv, "programme", {
            "start": start_s,
            "stop": stop_s,
            "channel": CHANNEL_ID
        })
        ET.SubElement(prog, "title", {"lang": "vi"}).text = sax.escape(it["title_vi"] or "")
        if it.get("title_en"):
            ET.SubElement(prog, "title", {"lang": "en"}).text = sax.escape(it["title_en"])

    tree = ET.ElementTree(tv)
    try:
        ET.indent(tree, space="  ", level=0)
    except Exception:
        pass
    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"✅ Xuất thành công {output_file} ({len(items)} programmes)")


def main():
    now_vn = datetime.now(VN_TZ)
    base_date = now_vn.date()
    date_str = base_date.strftime("%d/%m/%Y")

    html = fetch_html_for_date(date_str)
    items = parse_table_rows(html, base_date)
    if not items:
        # fallback: nếu không parse được, vẫn tạo file rỗng / header
        print("⚠️ Không có item nào từ parse_table_rows()")
        build_xml([], OUTPUT_FILE)
        return

    items = compute_stops(items)

    # --- CHỖ SỬA: normalize early hours (00:00-03:59) nếu bị gán về ngày trước
    items = normalize_early_hours_to_base_date(items, base_date)

    # Lọc chỉ giữ chương trình start thuộc ngày hiện tại (VN)
    filtered = filter_only_today(items, base_date)

    # Debug prints (in danh sách start để anh kiểm tra)
    print("=== Program starts (all parsed) ===")
    for it in items[:200]:
        print(it["start_dt"].strftime("%Y-%m-%d %H:%M:%S %z"), "-", it["title_vi"])

    print("=== Program starts (filtered = today) ===")
    for it in filtered[:200]:
        print(it["start_dt"].strftime("%Y-%m-%d %H:%M:%S %z"), "-", it["title_vi"])

    build_xml(filtered, OUTPUT_FILE)


if __name__ == "__main__":
    print("=== RUNNING CRAWLER ===")
    try:
        main()
    except Exception as e:
        print("⚠️ Lỗi:", e)
    print("=== DONE ===")
