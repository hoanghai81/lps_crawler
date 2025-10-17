import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz

def fetch_brt_schedule():
    url = "https://brt.vn/truyen-hinh"
    response = requests.get(url, timeout=10)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, 'html.parser')

    tbody = soup.find('tbody')
    if not tbody:
        print("❌ Không tìm thấy bảng chương trình!")
        return []

    schedule = []
    rows = tbody.find_all('tr')
    for row in rows:
        cols = row.find_all('td')
        if len(cols) >= 2:
            time_str = cols[0].get_text(strip=True)
            title = cols[1].get_text(strip=True)
            if time_str and title:
                schedule.append((time_str, title))

    return schedule

def generate_epg(schedule):
    if not schedule:
        return '<tv source-info-name="brt.vn" generator-info-name="lps_crawler">\n<channel id="brthtv">\n<display-name>BRT HTV</display-name>\n</channel>\n</tv>'

    vn_tz = pytz.timezone("Asia/Ho_Chi_Minh")
    today = datetime.now(vn_tz)
    date_str = today.strftime("%Y%m%d")

    epg = [
        '<tv source-info-name="brt.vn" generator-info-name="lps_crawler">',
        '  <channel id="brthtv">',
        '    <display-name>BRT HTV</display-name>',
        '  </channel>'
    ]

    for i, (time_str, title) in enumerate(schedule):
        try:
            start_time = datetime.strptime(f"{date_str} {time_str}", "%Y%m%d %H:%M")
        except ValueError:
            continue

        start = vn_tz.localize(start_time)
        if i + 1 < len(schedule):
            next_time_str = schedule[i + 1][0]
            try:
                end_time = datetime.strptime(f"{date_str} {next_time_str}", "%Y%m%d %H:%M")
                end = vn_tz.localize(end_time)
            except ValueError:
                end = start + timedelta(minutes=30)
        else:
            end = start + timedelta(minutes=30)

        start_fmt = start.strftime("%Y%m%d%H%M%S %z")
        end_fmt = end.strftime("%Y%m%d%H%M%S %z")

        epg.append(f'  <programme start="{start_fmt}" stop="{end_fmt}" channel="brthtv">')
        epg.append(f'    <title lang="vi">{title}</title>')
        epg.append('  </programme>')

    epg.append('</tv>')
    return '\n'.join(epg)

def save_epg(epg_data, filename="brthtv.xml"):
    with open(filename, "w", encoding="utf-8") as f:
        f.write(epg_data)
    print(f"✅ Đã tạo xong file {filename}")

if __name__ == "__main__":
    schedule = fetch_brt_schedule()
    epg = generate_epg(schedule)
    save_epg(epg)
