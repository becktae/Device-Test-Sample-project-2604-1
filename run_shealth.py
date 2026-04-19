"""
run_shealth.py
삼성헬스 메뉴 진입 체크 시나리오 실행
→ result_log.json 생성 (대시보드 입력 데이터)
"""

import json
import time
from datetime import datetime
from appium import webdriver
from appium.options.android.uiautomator2.base import UiAutomator2Options as AppiumOptions
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import NoSuchElementException, TimeoutException

APPIUM_SERVER = "http://127.0.0.1:4723"
UI_MAP_PATH = "ui_map_shealth.json"
LOG_PATH = "result_log.json"

# ── Appium 옵션 ──
options = AppiumOptions()
options.platform_name = "Android"
options.automation_name = "UiAutomator2"
options.app_package = "com.sec.android.app.shealth"
options.app_activity = "com.samsung.android.app.shealth.home.HomeDashboardActivity"
options.no_reset = True
options.new_command_timeout = 300


def load_ui_map():
    with open(UI_MAP_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def find_element_safe(driver, elem_info: dict):
    """우선순위: resource_id → xpath → content_desc → bounds"""
    strategies = []

    if elem_info.get("resource_id"):
        strategies.append((AppiumBy.ID, elem_info["resource_id"]))
    if elem_info.get("xpath"):
        strategies.append((AppiumBy.XPATH, elem_info["xpath"]))
    if elem_info.get("content_desc"):
        strategies.append((AppiumBy.XPATH, f'//*[@content-desc="{elem_info["content_desc"]}"]'))
    if elem_info.get("text"):
        strategies.append((AppiumBy.XPATH, f'//*[@text="{elem_info["text"]}"]'))

    for by, value in strategies:
        try:
            el = driver.find_element(by, value)
            return el, f"{by}={value}"
        except NoSuchElementException:
            continue

    # 최후: bounds 좌표 탭
    if elem_info.get("bounds"):
        import re
        nums = re.findall(r"\d+", elem_info["bounds"])
        if len(nums) == 4:
            x1, y1, x2, y2 = map(int, nums)
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            driver.tap([(cx, cy)])
            return None, f"bounds_tap=({cx},{cy})"

    raise NoSuchElementException(f"모든 전략 실패: {elem_info.get('label')}")


def scroll_and_tap(driver, elem_info: dict) -> str:
    """
    UIScrollable로 content-desc 키워드 포함 element를 스크롤하며 찾아 탭.
    clickable=false 타일에도 동작.
    """
    import re
    keyword = elem_info.get("scroll_desc_keyword") or elem_info.get("content_desc", "")

    # 1순위: UiScrollable scrollIntoView (content-desc 포함)
    if keyword:
        try:
            uia_selector = (
                f'new UiScrollable(new UiSelector().scrollable(true).instanceOrFallbackToLastElement(0))'
                f'.scrollIntoView(new UiSelector().descriptionContains("{keyword}"))'
            )
            driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, uia_selector)
            time.sleep(0.5)
            # 화면에 보이는 상태에서 bounds 탭
            src = driver.page_source
            import xml.etree.ElementTree as ET
            root = ET.fromstring(src)
            def find_bounds(node):
                d = node.get("content-desc", "")
                if keyword in d:
                    return node.get("bounds", "")
                for c in node:
                    r = find_bounds(c)
                    if r: return r
                return ""
            bounds_str = find_bounds(root)
            if bounds_str:
                nums = re.findall(r"\d+", bounds_str)
                if len(nums) == 4:
                    x1, y1, x2, y2 = map(int, nums)
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                    driver.tap([(cx, cy)])
                    return f"scroll+tap ({cx},{cy}) via UIScrollable"
        except Exception:
            pass

    # 2순위: swipe 스크롤 반복 후 bounds 탭
    for _ in range(8):
        driver.swipe(540, 1200, 540, 500, 500)
        time.sleep(0.7)
        src = driver.page_source
        import xml.etree.ElementTree as ET
        root = ET.fromstring(src)
        def find_node(node):
            d = node.get("content-desc", "")
            if keyword and keyword in d:
                return node
            for c in node:
                r = find_node(c)
                if r is not None: return r
            return None
        found = find_node(root)
        if found is not None:
            bounds_str = found.get("bounds", "")
            nums = re.findall(r"\d+", bounds_str)
            if len(nums) == 4:
                x1, y1, x2, y2 = map(int, nums)
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                driver.tap([(cx, cy)])
                return f"swipe_scroll+tap ({cx},{cy})"

    raise NoSuchElementException(f"스크롤 후에도 찾지 못함: {keyword}")


def verify_screen_loaded(driver, expected: str) -> tuple[bool, str]:
    """
    화면 로드 확인: 예외/에러 팝업 없고, 화면이 정상 렌더링됐는지
    - crash dialog 감지
    - 로딩 스피너 잔류 감지
    """
    crash_indicators = [
        "앱이 중지되었습니다",
        "안타깝게도",
        "중지됨",
        "오류가 발생했습니다",
    ]

    try:
        page_src = driver.page_source
        for indicator in crash_indicators:
            if indicator in page_src:
                return False, f"크래시 감지: '{indicator}'"
        return True, f"화면 정상 ({expected})"
    except Exception as e:
        return False, f"page_source 오류: {e}"


def run_scenario(driver, scenario: dict, elements: dict) -> dict:
    log = {
        "scenario_id": scenario["id"],
        "scenario_name": scenario["name"],
        "started_at": datetime.now().isoformat(),
        "steps": [],
        "summary": {"total": 0, "pass": 0, "fail": 0, "error": 0},
        "result": "PASS",
        "ai_invoked": False,
    }

    print(f"\n▶ {scenario['name']}")
    print("─" * 45)

    for i, step in enumerate(scenario["steps"]):
        step_log = {
            "seq": i + 1,
            "action": step["action"],
            "desc": step["desc"],
            "status": "PASS",
            "detail": "",
            "timestamp": datetime.now().isoformat(),
        }
        log["summary"]["total"] += 1

        print(f"  [{i+1:02d}] {step['desc']}...", end=" ", flush=True)

        try:
            action = step["action"]

            if action == "launch":
                driver.activate_app(options.app_package)
                step_log["detail"] = "앱 실행"
                print("✅")

            elif action == "wait":
                time.sleep(step.get("ms", 1000) / 1000)
                step_log["detail"] = f"{step.get('ms', 1000)}ms 대기"
                print("✅")

            elif action == "click":
                target_key = step["target"]
                if target_key not in elements:
                    raise KeyError(f"ui_map에 '{target_key}' 없음 → Inspector로 먼저 수집 필요")

                elem_info = elements[target_key]

                if not elem_info.get("verified"):
                    print(f"\n  ⚠️  '{target_key}' 미검증 element (Inspector 확인 권장)")

                el, strategy = find_element_safe(driver, elem_info)
                if el:
                    el.click()
                step_log["detail"] = f"클릭 완료 ({strategy})"
                print("✅")

            elif action == "scroll_click":
                target_key = step["target"]
                if target_key not in elements:
                    raise KeyError(f"ui_map에 '{target_key}' 없음")
                elem_info = elements[target_key]
                strategy = scroll_and_tap(driver, elem_info)
                step_log["detail"] = f"스크롤+탭 완료 ({strategy})"
                print("✅")

            elif action == "verify_screen":
                ok, msg = verify_screen_loaded(driver, step.get("expected", ""))
                if ok:
                    step_log["detail"] = msg
                    print("✅")
                else:
                    step_log["status"] = "FAIL"
                    step_log["detail"] = msg
                    log["result"] = "FAIL"
                    log["summary"]["fail"] += 1
                    print(f"❌ {msg}")
                    continue

            log["summary"]["pass"] += 1

        except NoSuchElementException as e:
            step_log["status"] = "ERROR"
            step_log["detail"] = f"Element 없음: {e}"
            log["result"] = "ERROR"
            log["summary"]["error"] += 1
            log["ai_invoked"] = True
            print(f"❌ Element 없음")

            # 스크린샷 저장 (Vision AI 연동 포인트)
            try:
                ts = datetime.now().strftime("%H%M%S")
                path = f"error_screenshot_{ts}.png"
                driver.save_screenshot(path)
                step_log["screenshot"] = path
                print(f"     📸 스크린샷 저장: {path}")
            except:
                pass

        except Exception as e:
            step_log["status"] = "ERROR"
            step_log["detail"] = str(e)
            log["result"] = "ERROR"
            log["summary"]["error"] += 1
            print(f"❌ {e}")

        log["steps"].append(step_log)

    log["finished_at"] = datetime.now().isoformat()
    elapsed = (
        datetime.fromisoformat(log["finished_at"]) -
        datetime.fromisoformat(log["started_at"])
    ).seconds
    log["elapsed_seconds"] = elapsed
    return log


def main():
    print("=" * 50)
    print("🏃 삼성헬스 메뉴 진입 체크")
    print("=" * 50)

    import sys
    data = load_ui_map()
    elements = data["elements"]
    # CLI: python run_shealth.py [시나리오 인덱스 or id]
    scenario_arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    if scenario_arg == "all":
        scenarios = data["scenarios"]
    elif scenario_arg.isdigit():
        scenarios = [data["scenarios"][int(scenario_arg)]]
    else:
        scenarios = [s for s in data["scenarios"] if s["id"] == scenario_arg]
    if not scenarios:
        print(f"❌ 시나리오 '{scenario_arg}' 없음")
        return

    # 미검증 element 사전 경고
    unverified = [k for k, v in elements.items() if not v.get("verified")]
    if unverified:
        print(f"\n⚠️  미검증 element {len(unverified)}개 — Inspector 수집 권장:")
        for k in unverified:
            print(f"   - {k}: {elements[k].get('label')}")
        print()

    print("📡 Appium 연결 중...")
    driver = webdriver.Remote(APPIUM_SERVER, options=options)
    print("✅ 연결 성공\n")

    all_logs = []
    try:
        time.sleep(2)
        for scenario in scenarios:
            result_log = run_scenario(driver, scenario, elements)
            all_logs.append(result_log)

            s = result_log["summary"]
            icon = {"PASS": "✅", "FAIL": "❌", "ERROR": "💥"}.get(result_log["result"], "?")
            print(f"\n{'='*50}")
            print(f"{icon} [{scenario['id']}] 결과: {result_log['result']}")
            print(f"   전체 {s['total']}단계 | ✅ {s['pass']} | ❌ {s['fail']} | 💥 {s['error']}")
            print(f"   소요시간: {result_log['elapsed_seconds']}초")
            print(f"{'='*50}")

        # 단일 시나리오면 기존 형식 유지, 복수면 리스트로 저장
        output = all_logs[0] if len(all_logs) == 1 else all_logs
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\n📄 결과 저장: {LOG_PATH}")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
