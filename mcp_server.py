"""
mcp_server.py
Device Test MCP Server

Claude가 직접 테스트 인프라를 제어:
  - 앱 목록 조회 / 테스트 실행 / 결과 분석
  - Appium 직접 조작 (연결 · 탭 · 스크롤 · 스크린샷)
  - 실패 시 Vision AI 분석 + ui_map 자동 수정

실행: python mcp_server.py  (Claude Code가 stdio로 자동 호출)
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

BASE_DIR      = Path(__file__).parent
UI_MAP_DIR    = BASE_DIR / "ui_maps"
LOG_PATH      = BASE_DIR / "result_log.json"
APPIUM_SERVER = "http://127.0.0.1:4723"
ANDROID_HOME  = str(Path.home() / "Library/Android/sdk")

mcp = FastMCP("device-test")

# ── Appium 세션 (connect_device 후 사용) ──────────────
_driver = None
_connected_package: str | None = None


def _drv():
    if _driver is None:
        raise RuntimeError("기기 미연결 — connect_device() 먼저 호출하세요")
    return _driver


# ══════════════════════════════════════════════════════
# 앱 / 시나리오 조회
# ══════════════════════════════════════════════════════

@mcp.tool()
def list_apps() -> str:
    """ui_maps/ 폴더에서 테스트 가능한 앱과 시나리오 목록 반환"""
    apps = []
    for f in sorted(UI_MAP_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            apps.append({
                "package":       data.get("package", f.stem),
                "app":           data.get("app", f.stem),
                "element_count": data.get("element_count", 0),
                "scenarios": [
                    {"id": s["id"], "name": s["name"]}
                    for s in data.get("scenarios", [])
                ],
            })
        except Exception:
            pass
    return json.dumps(apps, ensure_ascii=False, indent=2)


@mcp.tool()
def get_ui_map(package: str) -> str:
    """특정 앱의 ui_map JSON 전체 반환 (elements + scenarios)"""
    path = UI_MAP_DIR / f"{package}.json"
    if not path.exists():
        return json.dumps({"error": f"ui_map 없음: {package}"})
    return path.read_text()


# ══════════════════════════════════════════════════════
# 테스트 실행
# ══════════════════════════════════════════════════════

@mcp.tool()
def run_test(package: str, scenario_id: str = "all") -> str:
    """
    run_app.py를 실행해 테스트 수행.
    완료 후 result_log.json 내용을 함께 반환.
    """
    env = {**os.environ, "ANDROID_HOME": ANDROID_HOME, "ANDROID_SDK_ROOT": ANDROID_HOME}
    cmd = [sys.executable, str(BASE_DIR / "run_app.py"), package, scenario_id]

    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(BASE_DIR))
    output = (proc.stdout + proc.stderr)[-3000:]

    result = None
    if LOG_PATH.exists():
        try:
            result = json.loads(LOG_PATH.read_text())
        except Exception:
            pass

    return json.dumps({"stdout": output, "result": result}, ensure_ascii=False, indent=2)


@mcp.tool()
def get_test_result() -> str:
    """마지막 테스트 결과(result_log.json) 반환"""
    if not LOG_PATH.exists():
        return json.dumps({"error": "결과 없음"})
    return LOG_PATH.read_text()


# ══════════════════════════════════════════════════════
# Appium 직접 제어
# ══════════════════════════════════════════════════════

@mcp.tool()
def connect_device(package: str) -> str:
    """
    Appium으로 기기에 연결.
    이후 tap / swipe / screenshot 등 직접 조작 가능.
    """
    global _driver, _connected_package

    from appium import webdriver
    from appium.options.android.uiautomator2.base import UiAutomator2Options

    if _driver:
        try:
            _driver.quit()
        except Exception:
            pass

    ui_map_path = UI_MAP_DIR / f"{package}.json"
    if not ui_map_path.exists():
        return json.dumps({"error": f"ui_map 없음: {package}"})

    data = json.loads(ui_map_path.read_text())
    opts = UiAutomator2Options()
    opts.platform_name       = "Android"
    opts.automation_name     = "UiAutomator2"
    opts.app_package         = package
    opts.app_activity        = data.get("activity", ".MainActivity")
    opts.no_reset            = True
    opts.new_command_timeout = 300

    _driver = webdriver.Remote(APPIUM_SERVER, options=opts)
    _connected_package = package
    time.sleep(2)
    return json.dumps({"status": "connected", "package": package})


@mcp.tool()
def disconnect_device() -> str:
    """Appium 세션 종료"""
    global _driver, _connected_package
    if _driver:
        _driver.quit()
        _driver = None
        _connected_package = None
    return json.dumps({"status": "disconnected"})


@mcp.tool()
def launch_app(package: str = "") -> str:
    """앱 강제 종료 후 재실행"""
    driver = _drv()
    pkg = package or _connected_package
    driver.terminate_app(pkg)
    time.sleep(1)
    driver.activate_app(pkg)
    time.sleep(2)
    return json.dumps({"launched": pkg})


@mcp.tool()
def take_screenshot() -> str:
    """현재 화면 스크린샷 저장 → 저장 경로 반환"""
    driver = _drv()
    ts   = datetime.now().strftime("%H%M%S")
    path = str(BASE_DIR / f"mcp_shot_{ts}.png")
    driver.save_screenshot(path)
    return json.dumps({"path": path})


@mcp.tool()
def get_page_source() -> str:
    """현재 화면 XML dump 반환 (element 탐색용, 최대 8000자)"""
    return _drv().page_source[:8000]


@mcp.tool()
def tap(x: int, y: int) -> str:
    """화면 좌표 탭"""
    _drv().tap([(x, y)])
    time.sleep(0.5)
    return json.dumps({"tapped": {"x": x, "y": y}})


@mcp.tool()
def swipe_up() -> str:
    """위→아래 스와이프 (스크롤 다운)"""
    _drv().swipe(540, 1200, 540, 500, 500)
    time.sleep(0.7)
    return json.dumps({"status": "swiped"})


@mcp.tool()
def click_element(resource_id: str = "", xpath: str = "", content_desc: str = "") -> str:
    """
    resource_id / xpath / content_desc 중 하나로 element 클릭.
    우선순위: resource_id → xpath → content_desc
    """
    from appium.webdriver.common.appiumby import AppiumBy
    from selenium.common.exceptions import NoSuchElementException

    driver = _drv()
    strategies = []
    if resource_id:
        strategies.append((AppiumBy.ID, resource_id))
    if xpath:
        strategies.append((AppiumBy.XPATH, xpath))
    if content_desc:
        strategies.append((AppiumBy.XPATH, f'//*[@content-desc="{content_desc}"]'))

    for by, val in strategies:
        try:
            el = driver.find_element(by, val)
            el.click()
            return json.dumps({"clicked": f"{by}={val}"})
        except NoSuchElementException:
            continue

    return json.dumps({"error": "element 미발견", "tried": len(strategies)})


# ══════════════════════════════════════════════════════
# AI 분석
# ══════════════════════════════════════════════════════

@mcp.tool()
def analyze_screenshot_with_ai(screenshot_path: str, question: str) -> str:
    """
    스크린샷을 Claude Vision으로 분석.
    question에 원하는 내용을 자유롭게 입력.
    """
    from ai_helper import analyze_screenshot
    return analyze_screenshot(screenshot_path, question)


@mcp.tool()
def analyze_failure_with_ai(screenshot_path: str, error_detail: str, step_desc: str) -> str:
    """
    테스트 실패 스크린샷 + 에러 내용을 AI로 분석.
    복구 방법과 탭 좌표를 제안.
    반환: {screen_state, failure_reason, recovery, coordinates}
    """
    from ai_helper import analyze_test_failure
    result = analyze_test_failure(screenshot_path, error_detail, step_desc)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def find_element_on_screen(screenshot_path: str, element_description: str) -> str:
    """
    스크린샷에서 설명에 맞는 element를 찾아 좌표 반환.
    반환: {"coordinates": [x, y]} 또는 {"coordinates": null}
    """
    from ai_helper import find_element_coordinates
    coords = find_element_coordinates(screenshot_path, element_description)
    return json.dumps({"coordinates": list(coords) if coords else None})


# ══════════════════════════════════════════════════════
# ui_map 수정
# ══════════════════════════════════════════════════════

@mcp.tool()
def update_ui_map_element(package: str, element_key: str, field: str, value: str) -> str:
    """
    ui_map의 특정 element 필드 업데이트.
    field 예: bounds, xpath, resource_id, content_desc
    AI가 복구한 좌표를 영구 저장할 때 사용.
    """
    path = UI_MAP_DIR / f"{package}.json"
    if not path.exists():
        return json.dumps({"error": f"ui_map 없음: {package}"})

    data = json.loads(path.read_text())
    if element_key not in data.get("elements", {}):
        return json.dumps({"error": f"element '{element_key}' 없음"})

    data["elements"][element_key][field] = value
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return json.dumps({"updated": package, "element": element_key, "field": field, "value": value})


if __name__ == "__main__":
    mcp.run(transport="stdio")
