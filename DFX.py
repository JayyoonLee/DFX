import gspread
from oauth2client.service_account import ServiceAccountCredentials
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
import time

# 구글 시트/크롬드라이버 인증 및 연결 (위와 동일)
chromedriver_path = "C:/Users/82109/Downloads/chromedriver-win64/chromedriver.exe"
options = webdriver.ChromeOptions()
options.add_argument('--headless')
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
driver = webdriver.Chrome(service=Service(chromedriver_path), options=options)

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_name(r"C:\Users\82109\OneDrive\바탕 화면\DFX\credentials.json",scope)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key("1tAHVNClKju6lzQm_PYhN7A1m5Hm0QRmejd_TdbWT_tw")

# 반복: B6, B10, B14, ... (B열 6번 행부터 4씩 증가)
sheet_for_url = spreadsheet.worksheet("시트원본")  # 원하는 시트명

row = 6
while True:
    cell_addr = f"A{row}"
    value = sheet_for_url.acell(cell_addr).value
    if not value:  # 값이 없으면 break
        break

    url2 = value.strip()
    url1 = "https://dundam.xyz/search?server=adven&name="
    url = url1 + url2
    driver.get(url)
    time.sleep(2)

    cards = driver.find_elements(By.CSS_SELECTOR, "div.scon")
    results = []

    for card in cards:
        # 캐릭터명 추출
        try:
            name_elem = card.find_element(By.CSS_SELECTOR, '.seh_name > .name')
            name = name_elem.text.split('\n')[0].strip()
        except Exception:
            name = None

        # 랭킹딜량 추출 (ul.stat_a 내부에서 "랭킹" 찾기)
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

        # 버프점수 추출 (ul.stat_b 내부에서 "버프점수"가 우선, 없으면 "4인"을 사용)
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
    # 결과를 해당 url2 시트에 업로드
    try:
        worksheet = spreadsheet.worksheet(url2)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=url2, rows="100", cols="20")

    worksheet.clear()
    worksheet.append_row(["캐릭터명", "랭킹딜량", "버프점수"])

    # [1] 결과 rows 배열 만들기 (한 번에 업로드)
    rows_to_upload = [
        [
            row_data["캐릭터명"] if row_data["캐릭터명"] else "",
            row_data["랭킹딜량"] if row_data["랭킹딜량"] else "",
            row_data["버프점수"] if row_data["버프점수"] else "",
        ]
        for row_data in results
    ]
    if rows_to_upload:
        worksheet.append_rows(rows_to_upload)  # 한 번에 다 업로드

    print(f"{url2} 업로드 완료!")

    row += 4  # 다음 4칸 아래로

driver.quit()
print("모든 작업 완료!")
