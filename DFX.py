# -*- coding: utf-8 -*-
import os
import re
import time

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# ================== Chrome / chromedriver (로컬 고정) ==================
DRIVER_PATH = os.path.join(os.getcwd(), "chromedriver")
if not os.path.exists(DRIVER_PATH):
    raise FileNotFoundError(f"chromedriver not found: {DRIVER_PATH} (repo 루트에 두세요)")

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1920,1080")
options.add_argument("--lang=ko-KR")
options.add_argument(
    "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0 Safari/537.36"
)
# Actions에서 setup-chrome이 넘겨주는 경로가 있으면 사용
chrome_bin = os.environ.get("CHROME_BIN")
if chrome_bin:
    options.binary_location = chrome_bin
# 자동화 흔적 최소화
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)

driver = webdriver.Chrome(service=Service(DRIVER_PATH), options=options)
wait = WebDriverWait(driver, 10)

# navigator.webdriver 감추기
try:
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    })
except Exception:
    pass

# ================== Google Sheets 인증/열기 ==================
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

# ================== 유틸 ==================
FORBIDDEN = r'[:\\/\?\*\[\]]'
def sanitize_title(name: str) -> str:
    title = re.sub(FORBIDDEN, "_", (name or "").strip())
    return title[:100] or "EMPTY_NAME"

# ================== 크롤러 ==================
def scrape_one(query_name: str):
    """ 검색 결과 → [ [캐릭터명, 랭킹딜량, 버프점수], ... ] """
    url = f"https://dundam.xyz/search?server=adven&name={query_name}"
    rows = []

    # 가벼운 재시도 2회
    for _ in range(2):
        driver.get(url)
        try:
            # 문서 로드 완료까지만 짧게
            WebDriverWait(driver, 6).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except TimeoutException:
            pass

        # 결과 카드/컨테이너 등장 대기(최대 6초)
        try:
            WebDriverWait(driver, 6).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.scon"))
            )
        except TimeoutException:
            continue

        cards = driver.find_elements(By.CSS_SELECTOR, "div.scon")
        if not cards:
            continue

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

        if rows:
            break

    # 디버그: 0건이면 HTML 일부를 로그로
    if not rows:
        snippet = driver.page_source[:1000].replace("\n", " ")
        print(f"[WARN] '{query_name}' 결과 0건. HTML 앞부분: {snippet}")
    return rows

def upload_to_sheet(title: str, data: list[list[str]]):
    title = sanitize_title(title)
    try:
        ws = spreadsheet.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows="200", cols="20")

    body = [["캐릭터명", "랭킹딜량", "버프점수"]] + (data or [])
    ws.update("A1", body, value_input_option="RAW")

# ================== 메인 ==================
row = 6  # A6부터, 4칸 간격
while True:
    cell_addr = f"A{row}"
    value = sheet_for_url.acell(cell_addr).value
    if not value:
        break

    query = value.strip()
    data = scrape_one(query)
    upload_to_sheet(query, data)
    print(f"{query} 업로드 완료! (총 {len(data)}건)")
    row += 4

try:
    driver.quit()
except Exception:
    pass

print("모든 작업 완료!")
