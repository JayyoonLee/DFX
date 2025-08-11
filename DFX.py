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
QUERY_NAME = "니치니치"  # 검색할 이름
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
def upload_to_sheet(title, data):
    title = re.sub(r'[:\\/\?\*\[\]]', "_", (title or "").strip())[:100] or "EMPTY_NAME"
    try:
        ws = spreadsheet.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows="200", cols="20")
    body = [["캐릭터명", "랭킹딜량", "버프점수"]] + (data or [])
    ws.update("A1", body, value_input_option="RAW")

# ===== 실행 =====
data = scrape_one(QUERY_NAME)
upload_to_sheet(QUERY_NAME, data)
print(f"{QUERY_NAME} 업로드 완료! (총 {len(data)}건)")

try:
    driver.quit()
except:
    pass

print("모든 작업 완료!")
# -*- coding: utf-8 -*-
"""
DFX.py
- GitHub Actions에서 실행
- 로컬 리포 루트의 ./chromedriver 강제 사용
- Cloudflare 챌린지 감지/대기/재시도
- 결과는 스프레드시트의 각 시트(이름=쿼리)로 업로드
"""

import os
import re
import time
import random
from typing import List

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
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument(
    "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0 Safari/537.36"
)

# Actions의 setup-chrome이 넘겨주는 경로가 있으면 사용
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
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"}
    )
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

def human_pause(base: float = 2.0, jitter: float = 1.5) -> None:
    """사람처럼 랜덤 쉬기"""
    time.sleep(base + random.uniform(0, jitter))

def is_cf_challenge() -> bool:
    """Cloudflare 챌린지 페이지 감지"""
    try:
        t = (driver.title or "").lower()
        if "just a moment" in t or "attention required" in t:
            return True
        src = (driver.page_source or "").lower()
        return ("challenge-error-text" in src) or ("cf-chl-bypass" in src) or ("cf-challenge" in src)
    except Exception:
        return False


# ================== 크롤러 ==================
def scrape_one(query_name: str) -> List[List[str]]:
    """ 검색 결과 → [ [캐릭터명, 랭킹딜량, 버프점수], ... ] """
    url = f"https://dundam.xyz/search?server=adven&name={query_name}"
    rows: List[List[str]] = []

    max_attempts = 4        # 챌린지 포함 최대 재시도
    cf_wait_base = 12.0     # 챌린지 감지 시 대기(초) (증가적용)

    for attempt in range(1, max_attempts + 1):
        driver.get(url)

        # 문서 로드 완료까지만 짧게
        try:
            WebDriverWait(driver, 6).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except TimeoutException:
            pass

        # CF 챌린지 대응
        if is_cf_challenge():
            wait_s = cf_wait_base * attempt  # 12s, 24s, 36s, 48s...
            print(f"[CF] challenge detected for '{query_name}'. waiting {wait_s:.1f}s and retry...")
            time.sleep(wait_s)
            driver.refresh()
            human_pause(1.0, 1.0)
            if is_cf_challenge():
                # 다음 루프로 재시도
                continue

        # 결과 카드 등장 대기 (너무 오래 안 기다림)
        try:
            WebDriverWait(driver, 6).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.scon"))
            )
        except TimeoutException:
            # 잠깐 쉬고 재시도
            human_pause(1.0, 1.0)
            continue

        cards = driver.find_elements(By.CSS_SELECTOR, "div.scon")
        if not cards:
            # 잠깐 쉬고 재시도
            human_pause(1.2, 1.0)
            continue

        # --------- 파싱 ----------
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

        # 파싱 성공 → 루프 종료
        if rows:
            break

    if not rows:
        # 디버그: 0건이면 간단 정보 찍기(로그에서 확인)
        try:
            snippet = (driver.title + " | " + driver.current_url)[:200]
        except Exception:
            snippet = "n/a"
        print(f"[WARN] '{query_name}' 0건. info: {snippet}")
    else:
        # 다음 요청 전 쿨다운 (봇탐지 완화)
        human_pause(3.0, 2.5)

    return rows


def upload_to_sheet(title: str, data: List[List[str]]) -> None:
    title = sanitize_title(title)
    try:
        ws = spreadsheet.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows="200", cols="20")

    body = [["캐릭터명", "랭킹딜량", "버프점수"]] + (data or [])
    ws.update("A1", body, value_input_option="RAW")


# ================== 워밍업(선택) ==================
# 첫 접속 때 챌린지가 자주 떠서, 루트로 먼저 접속 후 8초 대기
try:
    driver.get("https://dundam.xyz/")
    time.sleep(8)
except Exception:
    pass


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

