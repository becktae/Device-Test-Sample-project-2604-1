"""
learn_shealth.py
삼성헬스 각 탭/화면 자동 탐색 → ui_map_shealth.json 자동 업데이트

content-desc, resource-id 기반으로 탭/카드 element 자동 수집
"""

import json
import time
import re
from datetime import datetime
from appium import webdriver
from appium.options.android.uiautomator2.base import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import NoSuchElementException
import xml.etree.ElementTree as ET

APPIUM_SERVER = "http://127.0.0.1:4723"
UI_MAP_PATH = "ui_map_shealth.json"

options = UiAutomator2Options()
options.platform_name = "Android"
options.automation_name = "UiAutomator2"
options.app_package = "com.sec.android.app.shealth"
options.app_activity = "com.samsung.android.app.shealth.home.HomeDashboardActivity"
options.no_reset = True
options.new_command_timeout = 300

# 찾을 레이블 → ui_map 키 매핑
TARGET_LABELS = {
    "홈": "tab_home",
    "운동": "tab_exercise",
    "음식": "tab_food",
    "함께": "tab_together",
    "걸음수": "card_steps",
    "걸음": "card_steps",
    "심박수": "card_heart_rate",
    "수면": "card_sleep",
    "스트레스": "card_stress",
}


def parse_screen(xml_source: str) -> dict:
    root = ET.fromstring(xml_source)
    found = {}

    def traverse(node):
        text = node.get("text", "").strip()
        content_desc = node.get("content-desc", "").strip()
        resource_id = node.get("resource-id", "")
        bounds = node.get("bounds", "")
        clickable = node.get("clickable", "false") == "true"

        for label_text in [text, content_desc]:
            if label_text in TARGET_LABELS and clickable:
                key = TARGET_LABELS[label_text]
                if key not in found:
                    found[key] = {
                        "label": label_text,
                        "text": text,
                        "resource_id": resource_id,
                        "content_desc": content_desc,
                        "bounds": bounds,
                        "xpath": (
                            f'//*[@resource-id="{resource_id}"]' if resource_id
                            else f'//*[@content-desc="{content_desc}"]' if content_desc
                            else f'//*[@text="{text}"]'
                        ),
                        "verified": True,
                        "verified_at": datetime.now().strftime("%Y-%m-%d"),
                    }
                    print(f"  ✅ [{key}] text='{text}' content-desc='{content_desc}' rid='{resource_id}'")

        for child in node:
            traverse(child)

    traverse(root)
    return found


def load_ui_map():
    with open(UI_MAP_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_ui_map(data: dict):
    with open(UI_MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    print("=" * 55)
    print("🔬 삼성헬스 UI 자동 학습")
    print("=" * 55)

    data = load_ui_map()
    elements = data["elements"]

    print(f"\n📡 Appium 연결 중...")
    driver = webdriver.Remote(APPIUM_SERVER, options=options)
    print("✅ 연결 성공")

    try:
        time.sleep(3)
        print("\n📸 홈 화면 스캔...")
        found = parse_screen(driver.page_source)
        elements.update({k: v for k, v in found.items() if v["verified"]})

        # 하단 탭 순서대로 진입하며 추가 수집
        tab_order = ["tab_exercise", "tab_food", "tab_together", "tab_home"]
        for tab_key in tab_order:
            if tab_key not in elements or not elements[tab_key].get("verified"):
                continue
            elem = elements[tab_key]
            print(f"\n  탭 진입: {elem['label']}")
            try:
                by = AppiumBy.ID if elem["resource_id"] else AppiumBy.XPATH
                val = elem["resource_id"] if elem["resource_id"] else elem["xpath"]
                driver.find_element(by, val).click()
                time.sleep(2)
                extra = parse_screen(driver.page_source)
                elements.update({k: v for k, v in extra.items() if v["verified"] and k not in elements})
            except Exception as e:
                print(f"    ⚠️  탭 진입 실패: {e}")

        # 결과 저장
        data["elements"] = elements
        data["updated_at"] = datetime.now().strftime("%Y-%m-%d")
        save_ui_map(data)

        verified = sum(1 for v in elements.values() if v.get("verified"))
        total = len(elements)
        print(f"\n{'='*55}")
        print(f"✅ 학습 완료: {verified}/{total}개 element 수집")
        print(f"💾 {UI_MAP_PATH} 업데이트됨")
        print(f"\n미수집 항목:")
        for k, v in elements.items():
            if not v.get("verified"):
                print(f"  ⚠️  {k}: {v.get('label','?')} → Inspector로 수동 확인 필요")
        print("=" * 55)

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
