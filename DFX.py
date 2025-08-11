import os
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ============ Chrome / chromedriver (로컬 고정) ============
DRIVER_PATH = os.path.join(os.getcwd(), "chromedriver")
if not os.path.exists(DRIVER_PATH):
    raise FileNotFoundError(f"chromedriver not found at: {DRIVER_PATH}  (repo 루트에 두세요)")

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1920,1080")

# setup-chrome 스텝이 넘겨준 CHROME_BIN을 사용 (워크플로우에서 env로 전달됨)
chrome_bin = os.environ.get("CHROME_BIN")
if chrome_bin:
    options.binary_location = chrome_bin

# ★ PATH 무시하고, 로컬 드라이버만 사용
driver = webdriver.Chrome(service=Service(DRIVER_PATH), options=options)
wait = WebDriverWait(driver, 12)


# ============ Google Sheets ============
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)

SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "1tAHVNClKju6lzQm_PYhN7A1m5Hm0QRmejd_TdbWT_tw")
SOURCE_SHEET = os.environ.get("SOURCE_SHEET", "시트원본")

spreadsheet = client.open_by_key(SPREADSHEET_ID)
sheet_for_url = spreadsheet.worksheet(SOURCE_SHEET)


def scrape_one(query_name: str):
    url = f"https://dundam.xyz/search?server=adven&name={query_name}"
    driver.get(url)
    try:
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.scon")))
    except Exception:
        pass

    cards = driver.find_elements(By.CSS_SELECTOR, "div.scon")
    rows = []
    for card in cards:
        # 캐릭터명
        try:
            name = card.find_element(By.CSS_SELECTOR, ".seh_name > .name").text.split("\n")[0].strip()
        except Exception:
            name = ""

        # 랭킹딜량
        ranking_damage = ""
        try:
            stat_a = card.find_element(By.CSS_SELECTOR, "ul.stat_a")
            for statc in stat_a.find_elements(By.CSS_SELECTOR, "div.statc"):
                tl = statc.find_element(By.CSS_SELECTOR, "span.tl").text.strip()
                val = statc.find_element(By.CSS_SELECTOR, "span.val").text.strip()
                if "랭킹" in tl:
                    ranking_damage = val
                    break
        except Exception:
            pass

        # 버프점수
        buff_score = ""
        try:
            stat_b = card.find_element(By.CSS_SELECTOR, "ul.stat_b")
            scores = {}
            for statc in stat_b.find_elements(By.CSS_SELECTOR, "div.statc"):
                tl = statc.find_element(By.CSS_SELECTOR, "span.tl").text.strip()
                val = statc.find_element(By.CSS_SELECTOR, "span.val").text.strip()
                scores[tl] = val
            buff_score = scores.get("버프점수") or scores.get("4인") or ""
        except Exception:
            pass

        rows.append([name, ranking_damage, buff_score])

    return rows


# ============ 메인 루프 ============
row = 6  # A6부터 시작, 4칸 간격
while True:
    cell_addr = f"A{row}"
    value = sheet_for_url.acell(cell_addr).value
    if not value:
        break

    query_name = value.strip()
    data = scrape_one(query_name)

    try:
        ws = spreadsheet.worksheet(query_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=query_name, rows="200", cols="20")

    ws.clear()
    ws.append_row(["캐릭터명", "랭킹딜량", "버프점수"])
    if data:
        ws.append_rows(data)

    print(f"{query_name} 업로드 완료! ({len(data)}건)")
    row += 4

try:
    driver.quit()
except Exception:
    pass

print("모든 작업 완료!")
