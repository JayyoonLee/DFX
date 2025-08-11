# -*- coding: utf-8 -*-
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
import os
import time

# ===== 설정 =====
QUERY_NAME = "니치니치"   # 검색할 이름 (고정)
SHEET_NAME = "니치니치"   # 업로드할 시트명 (고정)
SPREADSHEET_ID = "1tAHVNClKju6lzQm_PYhN7A1m5Hm0QRmejd_TdbWT_tw"

# ===== 크롬드라이버 / 구글 시트 인증 =====
# (로컬 chromedriver를 쓰는 경우: repo 루트의 ./chromedriver 사용)
chromedriver_path = os.path.join(os.getcwd(), "chromedriver")
options = webdriver.ChromeOptions()
options.add_argument('--headless=new')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')

# GitHub Actions에서 setup-chrome이 CHROME_BIN을 줄 수 있음
chrome_bin = os.environ.get("CHROME_BIN")
if chrome_bin:
    options.binary_location = chrome_bin

driver = webdriver.Chrome(service=Service(chromedriver_path), options=options)

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key(SPREADSHEET_ID)

# ===== 크롤링 (한 개만) =====
url = f"https://dundam.xyz/search?server=adven&name={QUERY_NAME}"
driver.get(url)
time.sleep(2)

cards = driver.find_elements(By.CSS_SELECTOR, "div.scon")
results = []

for card in cards:
    # 캐릭터명
    try:
        name_elem = card.find_element(By.CSS_SELECTOR, ".seh_name > .name")
        name = name_elem.text.split("\n")[0].strip()
    except Exception:
        name = ""

    # 랭킹딜량
    ranking_damage = ""
    try:
        stat_a = card.find_element(By.CSS_SELECTOR, "ul.stat_a")
        for statc in stat_a.find_elements(By.CSS_SELECTOR, "div.statc"):
            label = statc.find_element(By.CSS_SELECTOR, "span.tl").text.strip()
            val = statc.find_element(By.CSS_SELECTOR, "span.val").text.strip()
            if "랭킹" in label:
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
            label = statc.find_element(By.CSS_SELECTOR, "span.tl").text.strip()
            val = statc.find_element(By.CSS_SELECTOR, "span.val").text.strip()
            scores[label] = val
        buff_score = scores.get("버프점수") or scores.get("4인") or ""
    except Exception:
        pass

    results.append([name, ranking_damage, buff_score])

# ===== 시트에 누적 append =====
try:
    worksheet = spreadsheet.worksheet(SHEET_NAME)
except gspread.exceptions.WorksheetNotFound:
    worksheet = spreadsheet.add_worksheet(title=SHEET_NAME, rows="200", cols="20")

# 헤더가 없으면 한 번만 추가
try:
    if not worksheet.acell("A1").value:
        worksheet.append_row(["캐릭터명", "랭킹딜량", "버프점수"], value_input_option="RAW")
except Exception:
    # acell 실패시에도 헤더 보장
    worksheet.append_row(["캐릭터명", "랭킹딜량", "버프점수"], value_input_option="RAW")

# 데이터 누적
if results:
    worksheet.append_rows(results, value_input_option="RAW")

print(f"{SHEET_NAME} 업로드 완료! (총 {len(results)}건)")

try:
    driver.quit()
except Exception:
    pass

print("모든 작업 완료!")
