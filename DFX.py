# -*- coding: utf-8 -*-
import os
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ===== 설정 =====
QUERY_NAME = "재윤단"  # 검색할 이름
SHEET_NAME = "재윤단"  # 업로드할 시트명
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "1tAHVNClKju6lzQm_PYhN7A1m5Hm0QRmejd_TdbWT_tw")
DRIVER_PATH = os.path.join(os.getcwd(), "chromedriver")

# ===== Chrome 설정 =====
options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1920,1080")
options.add_argument("--lang=ko-KR")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)

chrome_bin = os.environ.get("CHROME_BIN")
if chrome_bin:
    options.binary_location = chrome_bin

driver = webdriver.Chrome(service=Service(DRIVER_PATH), options=options)
wait = WebDriverWait(driver, 6)

try:
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"}
    )
except Exception:
    pass

# ===== Google Sheets 인증 =====
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key(SPREADSHEET_ID)

# ===== 크롤링 =====
def scrape_one(name):
    url = f"https://dundam.xyz/search?server=adven&name={name}"
    driver.get(url)
    try:
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.scon")))
    except:
        print(f"[WARN] '{name}' 결과 없음 또는 로딩 실패")
        return []

    cards = driver.find_elements(By.CSS_SELECTOR, "div.scon")
    rows = []
    for card in cards:
        # 캐릭터명
        try:
            nm = card.find_element(By.CSS_SELECTOR, ".seh_name > .name").text.split("\n")[0].strip()
        except:
            nm = ""
        # 랭킹딜량
        rk = ""
        try:
            stat_a = card.find_element(By.CSS_SELECTOR, "ul.stat_a")
            for sc in stat_a.find_elements(By.CSS_SELECTOR, "div.statc"):
                tl = sc.find_element(By.CSS_SELECTOR, "span.tl").text.strip()
                val = sc.find_element(By.CSS_SELECTOR, "span.val").text.strip()
                if "랭킹" in tl:
                    rk = val
                    break
        except:
            pass
        # 버프점수
        bf = ""
        try:
            stat_b = card.find_element(By.CSS_SELECTOR, "ul.stat_b")
            m = {}
            for sc in stat_b.find_elements(By.CSS_SELECTOR, "div.statc"):
                tl = sc.find_element(By.CSS_SELECTOR, "span.tl").text.strip()
                val = sc.find_element(By.CSS_SELECTOR, "span.val").text.strip()
                m[tl] = val
            bf = m.get("버프점수") or m.get("4인") or ""
        except:
            pass
        rows.append([nm, rk, bf])
    return rows

# ===== 시트 업로드 =====
def upload_to_sheet(sheet_name, data):
    sheet_name = re.sub(r'[:\\/\?\*\[\]]', "_", (sheet_name or "").strip())[:100] or "EMPTY_NAME"
    try:
        ws = spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=sheet_name, rows="200", cols="20")
    body = [["캐릭터명", "랭킹딜량", "버프점수"]] + (data or [])
    ws.update("A1", body, value_input_option="RAW")

# ===== 실행 =====
data = scrape_one(QUERY_NAME)
upload_to_sheet(SHEET_NAME, data)
print(f"{SHEET_NAME} 업로드 완료! (총 {len(data)}건)")

try:
    driver.quit()
except:
    pass

print("모든 작업 완료!")
