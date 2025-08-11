import os
import stat
import time
from pathlib import Path

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ========================= Selenium 설정 =========================
options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--lang=ko-KR")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument(
    "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
# setup-chrome 액션이 CHROME_BIN을 넘겨줌. 로컬에서는 기본 경로 사용.
options.binary_location = os.environ.get("CHROME_BIN", "/usr/bin/google-chrome")

# 리포 루트에 업로드한 리눅스용 chromedriver 사용
DRIVER_PATH = os.path.join(os.getcwd(), "chromedriver")
try:
    os.chmod(DRIVER_PATH, os.stat(DRIVER_PATH).st_mode | stat.S_IEXEC)
except Exception:
    pass  # 이미 권한이 있으면 무시

driver = webdriver.Chrome(service=Service(DRIVER_PATH), options=options)
wait = WebDriverWait(driver, 10)  # 요소 대기 (최대 10초)

# 디버그용 캡처 폴더
SNAP_DIR = Path(os.getcwd()) / "snaps"
SNAP_DIR.mkdir(exist_ok=True)


# ========================= Google Sheets 인증 =========================
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
# 워크플로우에서 만들어진 credentials.json 사용 (로컬도 동일 경로에 두면 OK)
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)

# 스프레드시트/시트 열기
SPREADSHEET_KEY = "1tAHVNClKju6lzQm_PYhN7A1m5Hm0QRmejd_TdbWT_tw"
spreadsheet = client.open_by_key(SPREADSHEET_KEY)
sheet_for_url = spreadsheet.worksheet("시트원본")


# ========================= 스크래핑 함수 =========================
def fetch_cards_for(name: str):
    """이름으로 검색하고 카드 리스트를 반환."""
    url = f"https://dundam.xyz/search?server=adven&name={name}"
    driver.get(url)

    # .scon 요소가 나타날 때까지 대기 (없어도 넘어감)
    try:
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.scon")))
    except Exception:
        pass

    cards = driver.find_elements(By.CSS_SELECTOR, "div.scon")
    print(f"[DEBUG] {name}: cards found = {len(cards)}  title='{driver.title}'")

    if not cards:
        # 디버그 스냅샷 저장
        snap_path = SNAP_DIR / f"snap_{name}.png"
        try:
            driver.save_screenshot(str(snap_path))
            print(f"[DEBUG] no cards -> saved screenshot: {snap_path}")
        except Exception as e:
            print(f"[DEBUG] screenshot failed: {e}")

    return cards


def parse_card(card):
    """카드 하나에서 캐릭터명/랭킹딜량/버프점수 파싱."""
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
            value = statc.find_element(By.CSS_SELECTOR, "span.val").text.strip()
            if "랭킹" in label:
                ranking_damage = value
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
            value = statc.find_element(By.CSS_SELECTOR, "span.val").text.strip()
            scores[label] = value
        buff_score = scores.get("버프점수") or scores.get("4인")
    except Exception:
        pass

    return {
        "캐릭터명": name,
        "랭킹딜량": ranking_damage,
        "버프점수": buff_score,
    }


# ========================= 메인 루프 =========================
try:
    row = 6  # A6부터 시작, 4칸씩 증가
    while True:
        cell_addr = f"A{row}"
        value = sheet_for_url.acell(cell_addr).value
        if not value:
            break

        query_name = value.strip()
        cards = fetch_cards_for(query_name)

        results = [parse_card(c) for c in cards]

        # 결과 업로드: 시트명은 query_name
        try:
            worksheet = spreadsheet.worksheet(query_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=query_name, rows="200", cols="20")

        worksheet.clear()
        worksheet.append_row(["캐릭터명", "랭킹딜량", "버프점수"])

        rows_to_upload = [
            [r.get("캐릭터명") or "", r.get("랭킹딜량") or "", r.get("버프점수") or ""]
            for r in results
        ]
        if rows_to_upload:
            # 명시적으로 RAW로 입력
            worksheet.append_rows(rows_to_upload, value_input_option="RAW")

        print(f"{query_name} 업로드 완료!")
        row += 4

    print("모든 작업 완료!")
finally:
    try:
        driver.quit()
    except Exception:
        pass
