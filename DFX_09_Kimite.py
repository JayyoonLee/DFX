# -*- coding: utf-8 -*-
import os, time, re, gspread
from urllib.parse import quote
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# ===== 고정 설정 =====
QUERY_NAME  = "키미테모험단"   # 검색 이름 (하나만)
SHEET_NAME  = "키미테모험단"   # 업로드 시트명 (고정)
SPREADSHEET_ID = "1tAHVNClKju6lzQm_PYhN7A1m5Hm0QRmejd_TdbWT_tw"
CHROMEDRIVER_PATH = os.path.join(os.getcwd(), "chromedriver")  # 리포 루트의 드라이버

# ===== Chrome / Driver =====
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
chrome_bin = os.environ.get("CHROME_BIN")
if chrome_bin:
    options.binary_location = chrome_bin

driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=options)
wait = WebDriverWait(driver, 6)
try:
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"})
except Exception:
    pass

# ===== Google Sheets =====
scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key(SPREADSHEET_ID)

def is_cf_challenge() -> bool:
    t = (driver.title or "").lower()
    if "just a moment" in t or "attention required" in t:
        return True
    s = (driver.page_source or "").lower()
    return ("challenge-error-text" in s) or ("cf-challenge" in s)

# ===== 크롤링 (단일) =====
def scrape_one(name: str):
    # 안전하게 URL 인코딩 (헤드리스 환경 보호)
    url = f"https://dundam.xyz/search?server=adven&name={quote(name)}"
    rows = []

    # 가벼운 재시도 2회 (CF 걸리면 잠깐 대기 후 새로고침)
    for attempt in range(1, 3):
        driver.get(url)
        try:
            WebDriverWait(driver, 3).until(lambda d: d.execute_script("return document.readyState")=="complete")
        except TimeoutException:
            pass

        if is_cf_challenge():
            wait_s = 8 * attempt  # 8s -> 16s
            print(f"[CF] challenge for '{name}'. waiting {wait_s}s...")
            time.sleep(wait_s)
            driver.refresh()
            try:
                WebDriverWait(driver, 3).until(lambda d: d.execute_script("return document.readyState")=="complete")
            except TimeoutException:
                pass
            if is_cf_challenge():
                continue  # 다음 시도

        # 결과 카드 등장 대기(최대 3초)
        try:
            WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.scon")))
        except TimeoutException:
            continue

        cards = driver.find_elements(By.CSS_SELECTOR, "div.scon")
        if not cards:
            continue

        for card in cards:
            # 캐릭터명
            try:
                nm = card.find_element(By.CSS_SELECTOR, ".seh_name > .name").text.split("\n")[0].strip()
            except Exception:
                nm = ""
            # 랭킹딜량
            rk = ""
            try:
                stat_a = card.find_element(By.CSS_SELECTOR, "ul.stat_a")
                for sc in stat_a.find_elements(By.CSS_SELECTOR, "div.statc"):
                    tl = sc.find_element(By.CSS_SELECTOR, "span.tl").text.strip()
                    val = sc.find_element(By.CSS_SELECTOR, "span.val").text.strip()
                    if "랭킹" in tl:
                        rk = val; break
            except Exception:
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
            except Exception:
                pass
            rows.append([nm, rk, bf])
        break  # 파싱 성공했으면 종료

    if not rows:
        print(f"[WARN] '{name}' 0건. title='{driver.title}' url='{driver.current_url}'")
    return rows

# ===== 업로드 (append 누적) =====
def upload_append(sheet_name: str, data: list[list[str]]):
    sheet_name = re.sub(r'[:\\/\?\*\[\]]', "_", (sheet_name or "").strip())[:100] or "EMPTY_NAME"
    try:
        ws = spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=sheet_name, rows="200", cols="20")
        ws.append_row(["캐릭터명","랭킹딜량","버프점수"], value_input_option="RAW")
    # 헤더가 비어있을 수 있으니 보정
    if not ws.get_all_values():
        ws.append_row(["캐릭터명","랭킹딜량","버프점수"], value_input_option="RAW")
    if data:
        ws.append_rows(data, value_input_option="RAW")

# ===== 실행 =====
data = scrape_one(QUERY_NAME)
upload_append(SHEET_NAME, data)
print(f"{SHEET_NAME} 업로드 완료! (총 {len(data)}건)")

try:
    driver.quit()
except Exception:
    pass
