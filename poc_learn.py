"""
poc_learn.py
Phase 1: Appium Inspector XML dump → ui_map.json 저장

사용법:
  python poc_learn.py

실행 전 확인:
  - Appium Server 실행 중 (appium)
  - Android 단말 USB 연결 + 디버깅 활성화
  - adb devices 로 단말 인식 확인
"""

import json
import time
from datetime import datetime
from appium import webdriver
from appium.options.android.uiautomator2.base import UiAutomator2Options as AppiumOptions
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ──────────────────────────────────────────
# Appium 연결 설정
# ──────────────────────────────────────────
APPIUM_SERVER = "http://127.0.0.1:4723"

options = AppiumOptions()
options.platform_name = "Android"
options.automation_name = "UiAutomator2"

# 계산기 앱 패키지 (삼성/AOSP 공통 시도)
# 삼성: com.sec.android.app.popupcalculator
# AOSP: com.android.calculator2
options.app_package = "com.sec.android.app.popupcalculator"
options.app_activity = ".Calculator"
options.no_reset = True


def dump_screen_xml(driver) -> str:
    """현재 화면의 XML 소스 추출"""
    return driver.page_source


def parse_elements(xml_source: str) -> dict:
    """
    XML에서 핵심 element를 추출하여 map 구성
    계산기 앱 기준: 숫자 버튼, 연산자, equals, 결과창
    """
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_source)
    element_map = {}

    # 관심 대상 text 목록 (계산기 기준)
    targets = {
        # 숫자
        "0": "btn_0", "1": "btn_1", "2": "btn_2", "3": "btn_3",
        "4": "btn_4", "5": "btn_5", "6": "btn_6", "7": "btn_7",
        "8": "btn_8", "9": "btn_9",
        # 연산자
        "+": "btn_plus", "-": "btn_minus",
        "×": "btn_multiply", "÷": "btn_divide",
        "=": "btn_equals",
        # 기타
        "C": "btn_clear", "AC": "btn_all_clear",
        "DEL": "btn_delete", "⌫": "btn_delete",
    }

    def traverse(node, depth=0):
        text = node.get("text", "").strip()
        content_desc = node.get("content-desc", "").strip()
        resource_id = node.get("resource-id", "")
        bounds = node.get("bounds", "")
        clickable = node.get("clickable", "false")

        label = text or content_desc

        if label in targets and clickable == "true":
            key = targets[label]
            element_map[key] = {
                "text": label,
                "resource_id": resource_id,
                "bounds": bounds,
                "xpath": f'//*[@text="{label}"]',
                "clickable": True,
                "learned_at": datetime.now().isoformat(),
            }
            print(f"  ✅ Found: [{key}] text='{label}' bounds={bounds}")

        # 결과 표시창 분리 저장
        # formula_display: 입력/결과값 (= 후 결과가 여기 표시됨)
        # preview_display: 미리보기 (= 누르기 전 실시간 계산 결과)
        class_name = node.get("class", "")
        if "EditText" in class_name and resource_id:
            element_map["formula_display"] = {
                "text": text,
                "resource_id": resource_id,
                "bounds": bounds,
                "xpath": f'//*[@resource-id="{resource_id}"]',
                "clickable": False,
                "learned_at": datetime.now().isoformat(),
            }
            print(f"  📺 Found formula display: resource_id='{resource_id}'")
        elif "TextView" in class_name and resource_id and "result" in resource_id.lower():
            element_map["result_display"] = {
                "text": text,
                "resource_id": resource_id,
                "bounds": bounds,
                "xpath": f'//*[@resource-id="{resource_id}"]',
                "clickable": False,
                "learned_at": datetime.now().isoformat(),
            }
            print(f"  📺 Found result display: resource_id='{resource_id}'")

        for child in node:
            traverse(child, depth + 1)

    traverse(root)
    return element_map


def save_ui_map(element_map: dict, path: str = "ui_map.json"):
    """element map을 JSON으로 저장"""
    output = {
        "app": "calculator",
        "package": options.app_package,
        "learned_at": datetime.now().isoformat(),
        "element_count": len(element_map),
        "elements": element_map,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n💾 ui_map.json 저장 완료 ({len(element_map)}개 element)")


def main():
    print("=" * 50)
    print("🔬 PoC Phase 1: UI 학습 시작")
    print("=" * 50)

    print(f"\n📡 Appium 서버 연결 중... {APPIUM_SERVER}")
    driver = webdriver.Remote(APPIUM_SERVER, options=options)
    print("✅ 연결 성공")

    try:
        print("\n⏳ 앱 로딩 대기 (2초)...")
        time.sleep(2)

        print("\n📸 화면 XML dump 추출 중...")
        xml_source = dump_screen_xml(driver)

        # 원본 XML 저장 (디버깅용)
        with open("screen_dump.xml", "w", encoding="utf-8") as f:
            f.write(xml_source)
        print("📄 screen_dump.xml 저장됨 (디버깅용)")

        print("\n🔍 Element 파싱 중...")
        element_map = parse_elements(xml_source)

        if not element_map:
            print("\n⚠️  Element를 찾지 못했습니다.")
            print("   → 앱 패키지명을 확인하세요:")
            print("   adb shell pm list packages | grep calc")
            return

        save_ui_map(element_map)

        print("\n" + "=" * 50)
        print("✅ Phase 1 완료! ui_map.json이 생성되었습니다.")
        print("   다음: python poc_run.py")
        print("=" * 50)

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
