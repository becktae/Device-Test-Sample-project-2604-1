"""
run_app.py
범용 테스트 러너 — ui_maps/<package>.json 기반으로 시나리오 실행

사용법:
  python run_app.py <package> [scenario_id]
  python run_app.py com.sec.android.app.shealth all
  python run_app.py com.sec.android.app.shealth blood_oxygen_tap_check
"""

import json
import sys
import time
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from appium import webdriver
from appium.options.android.uiautomator2.base import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import NoSuchElementException

BASE_DIR    = Path(__file__).parent
UI_MAP_DIR  = BASE_DIR / "ui_maps"
LOG_PATH    = BASE_DIR / "result_log.json"
APPIUM_SERVER = "http://127.0.0.1:4723"


# ── Element 조작 ──────────────────────────────────────

def find_element_safe(driver, elem_info: dict):
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
            return driver.find_element(by, value), f"{by}={value}"
        except NoSuchElementException:
            continue

    if elem_info.get("bounds"):
        nums = re.findall(r"\d+", elem_info["bounds"])
        if len(nums) == 4:
            x1, y1, x2, y2 = map(int, nums)
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            driver.tap([(cx, cy)])
            return None, f"bounds_tap=({cx},{cy})"

    raise NoSuchElementException(f"모든 전략 실패: {elem_info.get('label')}")


def scroll_and_tap(driver, elem_info: dict) -> str:
    keyword = elem_info.get("scroll_desc_keyword") or elem_info.get("content_desc", "")

    if keyword:
        try:
            uia = (
                f'new UiScrollable(new UiSelector().scrollable(true).instanceOrFallbackToLastElement(0))'
                f'.scrollIntoView(new UiSelector().descriptionContains("{keyword}"))'
            )
            driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, uia)
            time.sleep(0.5)
            src = driver.page_source
            root = ET.fromstring(src)
            def find_bounds(node):
                if keyword in node.get("content-desc", ""):
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
                    driver.tap([((x1 + x2) // 2, (y1 + y2) // 2)])
                    return f"UIScrollable+tap via '{keyword}'"
        except Exception:
            pass

    for _ in range(8):
        driver.swipe(540, 1200, 540, 500, 500)
        time.sleep(0.7)
        root = ET.fromstring(driver.page_source)
        def find_node(node):
            if keyword and keyword in node.get("content-desc", ""):
                return node
            for c in node:
                r = find_node(c)
                if r is not None: return r
            return None
        found = find_node(root)
        if found is not None:
            nums = re.findall(r"\d+", found.get("bounds", ""))
            if len(nums) == 4:
                x1, y1, x2, y2 = map(int, nums)
                driver.tap([((x1 + x2) // 2, (y1 + y2) // 2)])
                return f"swipe_scroll+tap"

    raise NoSuchElementException(f"스크롤 후에도 미발견: {keyword}")


def verify_screen_loaded(driver) -> tuple[bool, str]:
    crash_keywords = ["앱이 중지되었습니다", "안타깝게도", "중지됨", "오류가 발생했습니다"]
    try:
        src = driver.page_source
        for kw in crash_keywords:
            if kw in src:
                return False, f"크래시 감지: '{kw}'"
        return True, "화면 정상"
    except Exception as e:
        return False, f"page_source 오류: {e}"


# ── 시나리오 실행 ──────────────────────────────────────

def run_scenario(driver, scenario: dict, elements: dict, package: str) -> dict:
    log = {
        "scenario_id":   scenario["id"],
        "scenario_name": scenario["name"],
        "package":       package,
        "started_at":    datetime.now().isoformat(),
        "steps":         [],
        "summary":       {"total": 0, "pass": 0, "fail": 0, "error": 0},
        "result":        "PASS",
        "ai_invoked":    False,
    }

    print(f"\n▶ {scenario['name']}")
    print("─" * 45)

    for i, step in enumerate(scenario["steps"]):
        step_log = {
            "seq":       i + 1,
            "action":    step["action"],
            "target":    step.get("target", ""),
            "desc":      step["desc"],
            "status":    "PASS",
            "detail":    "",
            "timestamp": datetime.now().isoformat(),
        }
        log["summary"]["total"] += 1
        print(f"  [{i+1:02d}] {step['desc']}...", end=" ", flush=True)

        try:
            action = step["action"]

            if action == "launch":
                driver.terminate_app(package)
                time.sleep(1)
                driver.activate_app(package)
                step_log["detail"] = "앱 강제 종료 후 재실행"
                print("✅")

            elif action == "wait":
                time.sleep(step.get("ms", 1000) / 1000)
                step_log["detail"] = f"{step.get('ms', 1000)}ms 대기"
                print("✅")

            elif action == "click":
                key = step["target"]
                if key not in elements:
                    raise KeyError(f"ui_map에 '{key}' 없음")
                elem_info = elements[key]
                if not elem_info.get("verified"):
                    print(f"\n  ⚠️  '{key}' 미검증 element", end=" ")
                el, strategy = find_element_safe(driver, elem_info)
                if el:
                    el.click()
                step_log["detail"] = f"클릭 완료 ({strategy})"
                print("✅")

            elif action == "scroll_click":
                key = step["target"]
                if key not in elements:
                    raise KeyError(f"ui_map에 '{key}' 없음")
                strategy = scroll_and_tap(driver, elements[key])
                step_log["detail"] = f"스크롤+탭 ({strategy})"
                print("✅")

            elif action == "verify_screen":
                ok, msg = verify_screen_loaded(driver)
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

        except Exception as e:
            step_log["status"] = "ERROR"
            step_log["detail"] = str(e)
            log["result"] = "ERROR"
            log["summary"]["error"] += 1
            log["ai_invoked"] = True
            print(f"❌ {e}")

            try:
                ts = datetime.now().strftime("%H%M%S")
                path = str(BASE_DIR / f"error_{ts}.png")
                driver.save_screenshot(path)
                step_log["screenshot"] = path
                print(f"     📸 {path}")
            except Exception:
                pass

        log["steps"].append(step_log)

    log["finished_at"] = datetime.now().isoformat()
    log["elapsed_seconds"] = (
        datetime.fromisoformat(log["finished_at"]) -
        datetime.fromisoformat(log["started_at"])
    ).seconds
    return log


# ── 메인 ──────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("사용법: python run_app.py <package> [scenario_id]")
        sys.exit(1)

    package     = sys.argv[1]
    scenario_id = sys.argv[2] if len(sys.argv) > 2 else "all"

    ui_map_path = UI_MAP_DIR / f"{package}.json"
    if not ui_map_path.exists():
        print(f"❌ ui_map 없음: {ui_map_path}")
        print(f"   먼저 실행: python app_scanner.py <앱이름>")
        sys.exit(1)

    data     = json.loads(ui_map_path.read_text())
    elements = data["elements"]
    activity = data.get("activity", ".MainActivity")

    # 시나리오 선택
    all_scenarios = data.get("scenarios", [])
    if not all_scenarios:
        print(f"❌ {ui_map_path.name}에 scenarios 없음")
        sys.exit(1)

    if scenario_id == "all":
        scenarios = all_scenarios
    else:
        scenarios = [s for s in all_scenarios if s["id"] == scenario_id]
    if not scenarios:
        print(f"❌ 시나리오 '{scenario_id}' 없음")
        sys.exit(1)

    # 미검증 element 경고
    unverified = [k for k, v in elements.items() if not v.get("verified")]
    if unverified:
        print(f"\n⚠️  미검증 element {len(unverified)}개: {unverified[:5]}")

    print("=" * 50)
    print(f"🚀 테스트 시작: {data.get('app', package)}")
    print(f"   패키지: {package}")
    print(f"   시나리오: {[s['id'] for s in scenarios]}")
    print("=" * 50)

    # Appium 연결
    opts = UiAutomator2Options()
    opts.platform_name       = "Android"
    opts.automation_name     = "UiAutomator2"
    opts.app_package         = package
    opts.app_activity        = activity
    opts.no_reset            = True
    opts.new_command_timeout = 300

    print(f"\n📡 Appium 연결 중...")
    driver = webdriver.Remote(APPIUM_SERVER, options=opts)
    print(f"✅ 연결 성공\n")

    all_logs = []
    try:
        time.sleep(2)
        for scenario in scenarios:
            result_log = run_scenario(driver, scenario, elements, package)
            all_logs.append(result_log)

            s    = result_log["summary"]
            icon = {"PASS": "✅", "FAIL": "❌", "ERROR": "💥"}.get(result_log["result"], "?")
            print(f"\n{'='*50}")
            print(f"{icon} [{result_log['scenario_id']}] {result_log['result']}")
            print(f"   {s['total']}단계 | ✅{s['pass']} ❌{s['fail']} 💥{s['error']} | {result_log['elapsed_seconds']}초")
            print(f"{'='*50}")

        output = all_logs[0] if len(all_logs) == 1 else all_logs
        LOG_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2))
        print(f"\n📄 결과 저장: {LOG_PATH}")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
