from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re

# --- Selenium 옵션 보강 ---
options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1920,1080")
options.add_argument(
    "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0 Safari/537.36"
)

chrome_bin = os.environ.get("CHROME_BIN")
if chrome_bin:
    options.binary_location = chrome_bin

# 자동화 흔적 최소화
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)

driver = webdriver.Chrome(service=Service(os.path.join(os.getcwd(), "chromedriver")), options=options)
wait = WebDriverWait(driver, 15)

# CDP로 navigator.webdriver 제거
try:
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
        Object.defineProperty(navigator, 'webdriver', {
          get: () => undefined
        });
        """
    })
except Exception:
    pass


def scrape_one(query_name: str):
    url = f"https://dundam.xyz/search?server=adven&name={query_name}"
    rows = []

    # 최대 3회 재시도
    for attempt in range(3):
        driver.get(url)
        try:
            # 결과 카드(이름 요소) 로드 대기
            wait.until(EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, "div.scon .seh_name > .name")
            ))
        except Exception:
            # 다음 시도
            continue

        cards = driver.find_elements(By.CSS_SELECTOR, "div.scon")
        if not cards:
            continue

        for card in cards:
            try:
                name = card.find_element(By.CSS_SELECTOR, ".seh_name > .name").text.split("\n")[0].strip()
            except Exception:
                name = ""

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

        if rows:  # 성공적으로 긁었으면 종료
            break

    # 디버그: 실패 시 HTML 일부 출력(로그에서 확인)
    if not rows:
        html_snip = driver.page_source[:1200].replace("\n", " ")
        print(f"[WARN] {query_name} 결과 0건. HTML 앞부분: {html_snip}")

    return rows


def upload_to_sheet(title: str, data: list[list[str]]):
    # 시트명 정제(금지문자 -> _)
    title = re.sub(r'[:\\\\/\\?\\*\\[\\]]', '_', title.strip())[:100] or "EMPTY_NAME"
    try:
        ws = spreadsheet.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows="200", cols="20")

    # 한번에 업데이트(헤더+데이터)
    body = [["캐릭터명", "랭킹딜량", "버프점수"]] + (data or [])
    ws.update("A1", body, value_input_option="RAW")


# === 메인 루프 ===
row = 6
while True:
    cell_addr = f"A{row}"
    value = sheet_for_url.acell(cell_addr).value
    if not value:
        break

    name = value.strip()
    data = scrape_one(name)
    upload_to_sheet(name, data)
    print(f"{name} 업로드 완료! (총 {len(data)}건)")
    row += 4
