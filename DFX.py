import os
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

# ----- Selenium (GitHub Actions 리눅스 호환) -----
options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
# setup-chrome 액션이 제공하는 경로 사용 (없으면 기본값 시도)
options.binary_location = os.environ.get("CHROME_BIN", "/usr/bin/google-chrome")

# Selenium 4: 드라이버 자동 관리 (chromedriver 경로 지정 불필요)
driver = webdriver.Chrome(options=options)

# ----- Google 인증 -----
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
# 워크플로우에서 secrets로 파일 생성됨
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)

spreadsheet = client.open_by_key("1tAHVNClKju6lzQm_PYhN7A1m5Hm0QRmejd_TdbWT_tw")
sheet_for_url = spreadsheet.worksheet("시트원본")

row = 6
while True:
    cell_addr = f"A{row}"   # ✅ A열 사용
    value = sheet_for_url.acell(cell_addr).value
    if not value:
        break

    url2 = value.strip()
    url = f"https://dundam.xyz/search?server=adven&name={url2}"
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
            name = None

        # 랭킹딜량 (ul.stat_a)
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

    # 결과 시트 업로드
    try:
        worksheet = spreadsheet.worksheet(url2)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=url2, rows="100", cols="20")

    worksheet.clear()
    worksheet.append_row(["캐릭터명", "랭킹딜량", "버프점수"])

    rows_to_upload = [
        [r.get("캐릭터명", "") or "", r.get("랭킹딜량", "") or "", r.get("버프점수", "") or ""]
        for r in results
    ]
    if rows_to_upload:
        worksheet.append_rows(rows_to_upload)

    print(f"{url2} 업로드 완료!")
    row += 4

driver.quit()
print("모든 작업 완료!")
