"""
poc_run.py
Phase 2: ui_map.json 기반 시나리오 실행

시나리오: 계산기에서 1 + 1 = 2 검증
  - element map 기반으로 실행 (AI 없음)
  - 실패 시 → Vision AI fallback (예외 처리)
  - 결과를 result_log.json에 저장

사용법:
  python poc_run.py
"""

import json
import time
import base64
from datetime import datetime
from appium import webdriver
from appium.options.android.uiautomator2.base import UiAutomator2Options as AppiumOptions
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException

# ──────────────────────────────────────────
# 설정
# ──────────────────────────────────────────
APPIUM_SERVER = "http://127.0.0.1:4723"
UI_MAP_PATH = "ui_map.json"
LOG_PATH = "result_log.json"

# OpenRouter API (예외 처리 시 Vision AI용)
# 실제 사용 시 환경변수로 관리 권장
OPENROUTER_API_KEY = "your-api-key-here"
VISION_MODEL = "google/gemini-2.0-flash-001"

options = AppiumOptions()
options.platform_name = "Android"
options.automation_name = "UiAutomator2"
options.app_package = "com.sec.android.app.popupcalculator"
options.app_activity = ".Calculator"
options.no_reset = True


# ──────────────────────────────────────────
# 시나리오 정의
# ──────────────────────────────────────────
SCENARIO = {
    "name": "basic_addition_1_plus_1",
    "description": "1 + 1 = 2 검증",
    "steps": [
        {"action": "click", "target": "btn_clear",   "desc": "초기화"},
        {"action": "click", "target": "btn_1",       "desc": "숫자 1 입력"},
        {"action": "click", "target": "btn_plus",    "desc": "+ 입력"},
        {"action": "click", "target": "btn_1",       "desc": "숫자 1 입력"},
        {"action": "click", "target": "btn_equals",  "desc": "= 실행"},
        {"action": "verify", "target": "formula_display", "expected": "2", "desc": "결과 2 확인"},
    ]
}


# ──────────────────────────────────────────
# Element 조작 함수
# ──────────────────────────────────────────
def load_ui_map(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["elements"]


def find_element(driver, elem_info: dict):
    """
    우선순위: resource_id → xpath → bounds 좌표 탭
    """
    # 1순위: resource_id
    if elem_info.get("resource_id"):
        try:
            return driver.find_element(AppiumBy.ID, elem_info["resource_id"])
        except NoSuchElementException:
            pass

    # 2순위: xpath (text 기반)
    if elem_info.get("xpath"):
        try:
            return driver.find_element(AppiumBy.XPATH, elem_info["xpath"])
        except NoSuchElementException:
            pass

    # 3순위: bounds 좌표 탭 (최후 수단, AI 없이)
    if elem_info.get("bounds"):
        bounds = parse_bounds(elem_info["bounds"])
        if bounds:
            cx, cy = bounds
            driver.tap([(cx, cy)])
            return None  # 탭만 실행, element 반환 없음

    raise NoSuchElementException(f"Element를 찾을 수 없음: {elem_info}")


def parse_bounds(bounds_str: str):
    """[x1,y1][x2,y2] → center (cx, cy)"""
    import re
    nums = re.findall(r"\d+", bounds_str)
    if len(nums) == 4:
        x1, y1, x2, y2 = map(int, nums)
        return ((x1 + x2) // 2, (y1 + y2) // 2)
    return None


# ──────────────────────────────────────────
# Vision AI Fallback (예외 시만 호출)
# ──────────────────────────────────────────
def ask_vision_ai(driver, error_context: str) -> str:
    """
    화면 스크린샷 → Vision AI에게 현재 상황 분석 요청
    실제 키가 없으면 스킵됨
    """
    if OPENROUTER_API_KEY == "your-api-key-here":
        return "Vision AI 스킵 (API 키 미설정)"

    import urllib.request
    import urllib.error

    screenshot_b64 = driver.get_screenshot_as_base64()

    payload = {
        "model": VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}
                    },
                    {
                        "type": "text",
                        "text": f"""Android 계산기 앱 테스트 중 오류가 발생했습니다.
오류 상황: {error_context}

현재 화면을 분석하여:
1. 화면 상태 설명
2. 오류 원인 추정
3. 복구 방법 제안

JSON으로만 응답:
{{"screen_state": "", "error_cause": "", "recovery": ""}}"""
                    }
                ]
            }
        ]
    }

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Vision AI 호출 실패: {e}"


# ──────────────────────────────────────────
# 시나리오 실행 엔진
# ──────────────────────────────────────────
def run_scenario(driver, scenario: dict, ui_map: dict) -> dict:
    log = {
        "scenario": scenario["name"],
        "description": scenario["description"],
        "started_at": datetime.now().isoformat(),
        "steps": [],
        "result": "PASS",
        "ai_invoked": False,
    }

    print(f"\n▶ 시나리오 시작: {scenario['description']}")
    print("-" * 40)

    for i, step in enumerate(scenario["steps"]):
        step_log = {
            "step": i + 1,
            "action": step["action"],
            "target": step["target"],
            "desc": step["desc"],
            "status": "PASS",
            "detail": "",
        }

        print(f"  [{i+1}] {step['desc']}...", end=" ")

        try:
            if step["target"] not in ui_map:
                raise KeyError(f"ui_map에 '{step['target']}' 없음")

            elem_info = ui_map[step["target"]]

            if step["action"] == "click":
                element = find_element(driver, elem_info)
                if element:
                    element.click()
                time.sleep(0.3)
                step_log["detail"] = f"클릭 완료 (xpath: {elem_info.get('xpath')})"
                print("✅")

            elif step["action"] == "verify":
                import re
                element = find_element(driver, elem_info)
                if element:
                    raw = element.get_attribute("text") or element.text or ""
                    # Samsung 접근성 레이블 "2 계산 결과" → 첫 번째 숫자 토큰 추출
                    num_match = re.match(r'^-?[\d,]+\.?\d*', raw.strip())
                    actual = num_match.group(0).replace(",", "") if num_match else raw.strip().replace(",", "")
                else:
                    actual = ""
                expected = step["expected"]

                if actual == expected:
                    step_log["detail"] = f"검증 성공: '{actual}' == '{expected}'"
                    print(f"✅ (결과: {actual})")
                else:
                    step_log["status"] = "FAIL"
                    step_log["detail"] = f"검증 실패: 기대값='{expected}', 실제값='{actual}'"
                    log["result"] = "FAIL"
                    print(f"❌ (기대:{expected}, 실제:{actual})")

        except Exception as e:
            step_log["status"] = "ERROR"
            step_log["detail"] = str(e)
            log["result"] = "ERROR"
            print(f"❌ 예외 발생: {e}")

            # ── Vision AI Fallback 투입 ──
            print("  🤖 Vision AI 분석 중...")
            ai_response = ask_vision_ai(driver, str(e))
            step_log["ai_analysis"] = ai_response
            log["ai_invoked"] = True
            print(f"  🤖 AI 분석: {ai_response}")

        log["steps"].append(step_log)
        time.sleep(0.2)

    log["finished_at"] = datetime.now().isoformat()
    return log


# ──────────────────────────────────────────
# 메인
# ──────────────────────────────────────────
def main():
    print("=" * 50)
    print("🚀 PoC Phase 2: 시나리오 실행")
    print("=" * 50)

    # ui_map 로드
    print(f"\n📂 ui_map 로드: {UI_MAP_PATH}")
    try:
        ui_map = load_ui_map(UI_MAP_PATH)
        print(f"✅ {len(ui_map)}개 element 로드됨")
    except FileNotFoundError:
        print("❌ ui_map.json이 없습니다. 먼저 poc_learn.py를 실행하세요.")
        return

    # Appium 연결
    print(f"\n📡 Appium 연결 중...")
    driver = webdriver.Remote(APPIUM_SERVER, options=options)
    print("✅ 연결 성공")

    try:
        time.sleep(2)

        # 시나리오 실행
        result_log = run_scenario(driver, SCENARIO, ui_map)

        # 결과 저장
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(result_log, f, ensure_ascii=False, indent=2)

        # 결과 출력
        print("\n" + "=" * 50)
        status_icon = {"PASS": "✅", "FAIL": "❌", "ERROR": "💥"}.get(result_log["result"], "?")
        print(f"{status_icon} 최종 결과: {result_log['result']}")
        if result_log["ai_invoked"]:
            print("🤖 Vision AI가 예외 처리에 개입했습니다.")
        print(f"📄 상세 로그: {LOG_PATH}")
        print("=" * 50)

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
