import requests
import pandas as pd
from datetime import datetime, timedelta, date
import xml.etree.ElementTree as ET

# ---- CONFIG ----
CHANNEL_ID = "Boomerang"
CHANNEL_NAME = "Boomerang"
TZ = "+0700"
BASE_URL = "https://info.msky.vn/vn/export.php?iCat=162&iName=Boomerang&date={}"

# ----------------

def fetch_excel(date_str):
    """Tải file Excel export theo ngày (dd/mm/yyyy)"""
    url = BASE_URL.format(date_str)
    print("Fetching:", url)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.content

def parse_excel(data):
    """Đọc Excel thành DataFrame"""
    df = pd.read_excel(data)
    df = df.dropna(subset=["Giờ", "Tên chương trình", "Thời lượng"])
    return df

def parse_duration(dur_str):
    """Chuyển '1:00' hoặc '0:25' thành số phút"""
    try:
        h, m = map(int, dur_str.split(":"))
        return h * 60 + m
    except Exception:
        return 30

def build_xmltv(df_list, days):
    """Ghép nhiều ngày thành XMLTV"""
    tv = ET.Element("tv", {"generator-info-name": "lps_crawler"})
    ch = ET.SubElement(tv, "channel", id=CHANNEL_ID)
    ET.SubElement(ch, "display-name").text = CHANNEL_NAME

    for df, day in zip(df_list, days):
        for _, row in df.iterrows():
            time_str = str(row["Giờ"]).strip()
            title = str(row["Tên chương trình"]).strip()
            duration_str = str(row["Thời lượng"]).strip()
            # Parse giờ bắt đầu
            try:
                hh, mm = map(int, time_str.split(":"))
            except:
                continue
            start_dt = datetime.combine(day, datetime.min.time()) + timedelta(hours=hh, minutes=mm)
            # Thêm duration
            dur = parse_duration(duration_str)
            stop_dt = start_dt + timedelta(minutes=dur)
            # Ghi XML
            prog = ET.SubElement(tv, "programme", {
                "start": start_dt.strftime("%Y%m%d%H%M%S ") + TZ,
                "stop": stop_dt.strftime("%Y%m%d%H%M%S ") + TZ,
                "channel": CHANNEL_ID
            })
            ET.SubElement(prog, "title", {"lang": "vi"}).text = title

    return tv

def main():
    today = date.today()
    tomorrow = today + timedelta(days=1)

    df_today = parse_excel(fetch_excel(today.strftime("%d/%m/%Y")))
    df_tomorrow = parse_excel(fetch_excel(tomorrow.strftime("%d/%m/%Y")))

    tv = build_xmltv([df_today, df_tomorrow], [today, tomorrow])
    ET.ElementTree(tv).write("boomerang.xml", encoding="utf-8", xml_declaration=True)

    print("✅ Xuất thành công boomerang.xml")
    print(f"Hôm nay: {len(df_today)} chương trình")
    print(f"Ngày mai: {len(df_tomorrow)} chương trình")

if __name__ == "__main__":
    main()
        
