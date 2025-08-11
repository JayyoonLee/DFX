import os
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ================== Selenium (GitHub Actions 친화) ==================
options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1920,1080")
# GitHub Actions에서 setup-chrome 사용 시 CHROME_BIN이 잡힘. 없으면 기본값 사용
chrome_bin = os.environ.get("CHROME_BIN")
if chrome_bin:
    options.binary_location = chrome_bin

# Selenium Manager가 자동으로 드라이버를 받으므로 Service 경로 지정 불필요
driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 10)  # 엘리먼트 대기 최대 10초


# ================== Google Sheets 인증 ==================
# 권장: 워크플로우에서 secrets로 credentials.json 파일 생성 후 사용
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)

# 환경변수로 관리하면 브랜치/프로젝트 간 재사용 쉬움 (없으면 하드코드된 기본값 사용)
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "1tAHVNClKju6lzQm_PYhN7A1m5Hm0QRmejd_TdbWT_tw")
SOURCE_SHEET = os.environ.get("SOURCE_SHEET", "시트원본")

spreadsheet = client.open_by_key(SPREADSHEET_ID)
sheet_for_url = spreadsheet.worksheet(SOURCE_SHEET)


# ================== 헬퍼 ==================
def scrape_one(query_name: str):
    """단일 캐릭터 검색 결과를 파싱해서 리스트[dict]로 반환."""
    url = f"https://dundam.xyz/search?server=adven&name={query_name}"
    driver.get(url)

    # 결과 카드 영역이 로드될 때까지 대기 (없을 수도 있으니 타임아웃은 허용)
    try:
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.scon")))
    except Exception:
        # 결과 없거나 레이아웃 변경된 경우도 있으므로 계속 진행
        pass

    cards = driver.find_elements(By.CSS_SELECTOR, "div.scon")
    results = []

    for card in cards:
        # 캐릭터명
        try:
            name_elem = card.find_element(By.CSS_SELECTOR, ".seh_name > .name")
            name = name_elem.text.split("\n")[0].strip()
        except Exception:
            name = None

        # 랭킹딜량 (ul.stat_a 내부 '랭킹')
        ranking_damage = None
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

        # 버프점수 (ul.stat_b → '버프점수' 우선, 없으면 '4인')
        buff_score = None
        try:
            stat_b = card.find_element(By.CSS_SELECTOR, "ul.stat_b")
            scores = {}
            for statc in stat_b.find_elements(By.CSS_SELECTOR, "div.statc"):
                label = statc.find_element(By.CSS_SELECTOR, "span.tl").text.strip()
                val = statc.find_element(By.CSS_SELECTOR, "span.val").text.strip()
                scores[label] = val
            buff_score = scores.get("버프점수") or scores.get("4인")
        except Exception:
            pass

        results.append({
            "캐릭터명": name or "",
            "랭킹딜량": ranking_damage or "",
            "버프점수": buff_score or "",
        })

    return results


def upload_to_sheet(title: str, rows: list[dict]):
    """결과를 시트(이름=title)에 업로드. 기존 내용 초기화 후 헤더+데이터."""
    try:
        ws = spreadsheet.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows="200", cols="20")

    ws.clear()
    ws.append_row(["캐릭터명", "랭킹딜량", "버프점수"])

    if rows:
        ws.append_rows([[r["캐릭터명"], r["랭킹딜량"], r["버프점수"]] for r in rows])


# ================== 메인 루프 ==================
row = 6  # A6부터 시작 (4칸 간격)
while True:
    cell_addr = f"A{row}"
    value = sheet_for_url.acell(cell_addr).value
    if not value:
        break

    query_name = value.strip()
    results = scrape_one(query_name)
    upload_to_sheet(query_name, results)
    print(f"{query_name} 업로드 완료! (총 {len(results)}건)")

    row += 4

print("모든 작업 완료!")

# 종료
try:
    driver.quit()
except Exception:
    pass
