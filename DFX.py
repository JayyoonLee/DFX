import os
import stat
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# ============ Selenium 설정 (리눅스/GitHub Actions 호환) ============
options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
# setup-chrome 액션이 설정한 경로가 환경변수로 들어오면 그걸 사용
options.binary_location = os.environ.get("CHROME_BIN", "/usr/bin/google-chrome")

# 리포 루트에 업로드한 chromedriver 사용 (확장자 없음, 리눅스용)
DRIVER_PATH = os.path.join(os.getcwd(), "chromedriver")

# 웹으로 올리면 실행 권한이 빠질 수 있으므로 강제로 실행 권한 부여
try:
    os.chmod(DRIVER_PATH, os.stat(DRIVER_PATH).st_mode | stat.S_IEXEC)
except Exception:
    pass  # 권한이 이미 있거나 로컬 실행 환경에서 불필요할 수 있음

driver = webdriver.Chrome(service=Service(DRIVER_PATH), options=options)

# ============ Google Sheets 인증 ============
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
# 워크플로우에서 secrets로 만든 credentials.json 사용 (로컬도 동일 경로에 두면 됨)
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)

# 스프레드시트/시트 열기
spreadsheet = client.open_by_key("1tAHVNClKju6lzQm_PYhN7A1m5Hm0QRmejd_TdbWT_tw")
sheet_for_url = spreadsheet.worksheet("시트원본")

# ============ 스크래핑 루프 ============
row = 6  # A6부터 시작, 4칸씩 증가
while True:
    cell_addr = f"A{row}"
    value = sheet_for_url.acell(cell_addr).value
    if not value:
        break

    query_name = value.strip()
    url = f"https://dundam.xyz/search?server=adven&name={query_name}"
    driver.get(url)
    time.sleep(2.0)  # 간단 대기 (사이트 느리면 3~4로 늘려도 됨)

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

        results.append({
            "캐릭터명": name,
            "랭킹딜량": ranking_damage,
            "버프점수": buff_score
        })

    # 결과 업로드: 시트명은 query_name
    try:
        worksheet = spreadsheet.worksheet(query_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=query_name, rows="200", cols="20")

    worksheet.clear()
    worksheet.append_row(["캐릭터명", "랭킹딜량", "버프점수"])

    rows_to_upload = [
        [
            r.get("캐릭터명") or "",
            r.get("랭킹딜량") or "",
            r.get("버프점수") or "",
        ]
        for r in results
    ]
    if rows_to_upload:
        worksheet.append_rows(rows_to_upload)

    print(f"{query_name} 업로드 완료!")
    row += 4

print("모든 작업 완료!")

# 종료 (CI 환경이면 없어도 대부분 문제 없지만, 깔끔하게 닫자)
try:
    driver.quit()
except Exception:
    pass
