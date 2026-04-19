"""
app_scanner.py
앱 이름 → 패키지 자동 탐색 → Inspector XML + 실시간 dump 병합 → ui_map 생성

흐름:
  1. 앱 이름으로 패키지 자동 탐색
  2. inspector_dumps/<package>.xml 존재 여부 확인
     - 있으면: Inspector XML 파싱 (skip 실시간 수집)
     - 없으면: Appium 연결 → 화면 스크롤 → 실시간 XML dump
  3. 두 소스 병합 → ui_maps/<package>.json 저장
  4. ui_map 완성 시 바로 테스트에 사용 가능

사용법:
  python app_scanner.py "삼성헬스"
  python app_scanner.py "calculator"
  python app_scanner.py "카카오페이"
"""

import sys
import os
import json
import time
import subprocess
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# ── 경로 설정 ──────────────────────────────────────
BASE_DIR        = Path(__file__).parent
INSPECTOR_DIR   = BASE_DIR / "inspector_dumps"
UI_MAP_DIR      = BASE_DIR / "ui_maps"
APPIUM_SERVER   = "http://127.0.0.1:4723"

INSPECTOR_DIR.mkdir(exist_ok=True)
UI_MAP_DIR.mkdir(exist_ok=True)


# ══════════════════════════════════════════════════
# 1. 패키지 탐색
# ══════════════════════════════════════════════════

def adb(cmd: str) -> str:
    result = subprocess.run(
        f"adb shell {cmd}", shell=True,
        capture_output=True, text=True
    )
    return result.stdout.strip()


def get_all_packages() -> list[dict]:
    """adb pm list packages -f → [{package, apk_path}]"""
    raw = adb("pm list packages -f")
    packages = []
    for line in raw.splitlines():
        # package:/path/to/apk=com.package.name
        m = re.match(r"package:(.+)=(.+)", line.strip())
        if m:
            packages.append({"apk": m.group(1), "package": m.group(2)})
    return packages


def get_launch_activity(package: str) -> str:
    """패키지의 런치 액티비티 반환"""
    raw = adb(f"cmd package query-activities -a android.intent.action.MAIN -c android.intent.category.LAUNCHER")
    lines = raw.splitlines()
    for i, line in enumerate(lines):
        if package in line and "/" in line:
            m = re.search(rf"{re.escape(package)}/(\S+)", line)
            if m:
                return m.group(1)
    # fallback: monkey로 실행 후 현재 액티비티 확인
    adb(f"monkey -p {package} -c android.intent.category.LAUNCHER 1")
    time.sleep(2)
    focus = adb("dumpsys activity activities | grep mResumedActivity")
    m = re.search(rf"{re.escape(package)}/(\S+)", focus)
    return m.group(1) if m else ".MainActivity"


# 한글 앱명 → 패키지 키워드 변환 테이블
KOREAN_KEYWORD_MAP = {
    "삼성": ["samsung", "sec"],
    "헬스": ["health", "shealth", "wellbeing"],
    "헬쓰": ["health", "shealth"],
    "계산기": ["calculator", "calc"],
    "카메라": ["camera"],
    "갤러리": ["gallery", "photos"],
    "캘린더": ["calendar"],
    "설정": ["settings"],
    "전화": ["phone", "dialer", "incall"],
    "메시지": ["message", "sms", "mms"],
    "카카오": ["kakao"],
    "카카오페이": ["kakaopay"],
    "카카오톡": ["kakaotalk", "kakao"],
    "네이버": ["naver"],
    "유튜브": ["youtube"],
    "지도": ["maps"],
    "날씨": ["weather"],
    "시계": ["clock", "alarmclock"],
    "메모": ["memo", "note", "notes"],
    "음악": ["music", "musicplayer"],
    "파일": ["files", "myfiles"],
    "브라우저": ["browser", "internet"],
    "인터넷": ["browser", "internet"],
    "삼성페이": ["samsungpay"],
    "페이": ["pay"],
    "배터리": ["battery"],
    "연락처": ["contacts"],
    "주소록": ["contacts"],
    "앱스토어": ["store", "market"],
    "플레이스토어": ["vending", "market"],
    "구글": ["google"],
    "페이스북": ["facebook"],
    "인스타": ["instagram"],
    "트위터": ["twitter"],
    "쿠팡": ["coupang"],
    "배민": ["baemin"],
    "토스": ["toss"],
    "당근": ["daangn"],
    "네이버지도": ["naver.map", "maps"],
    "카카오맵": ["kakaomap", "daum.maps"],
}


def get_specific_keywords(app_name: str) -> list[list[str]]:
    """
    우선순위별 키워드 그룹 반환
    앞 그룹일수록 구체적 — 매칭 결과가 적을수록 신뢰도 높음
    """
    groups: list[list[str]] = []
    specific = []
    broad = []

    for korean, english_list in KOREAN_KEYWORD_MAP.items():
        if korean in app_name:
            # 구체적 키워드(길이 > 5)와 일반 키워드 분리
            for kw in english_list:
                if len(kw) > 5:
                    specific.append(kw)
                else:
                    broad.append(kw)

    # 영문 원문 단어도 추가
    for w in app_name.lower().split():
        if w.isascii() and len(w) > 3:
            specific.append(w)

    if specific:
        groups.append(specific)
    if broad:
        groups.append(broad)
    return groups


def get_launcher_packages() -> set[str]:
    """런처(사용자 앱)만 반환 — 시스템 서비스 제외"""
    raw = adb("cmd package query-activities -a android.intent.action.MAIN -c android.intent.category.LAUNCHER")
    pkgs = set()
    for line in raw.splitlines():
        m = re.search(r"packageName=(\S+)", line)
        if m:
            pkgs.add(m.group(1))
    return pkgs


def find_package(app_name: str) -> dict | None:
    """
    앱 이름(한/영 모두 가능)으로 패키지 탐색
    전략: 가장 구체적인 키워드 하나씩 시도 → 런처 앱 1개로 좁혀지면 자동 선택
    """
    # 직접 패키지명 입력한 경우
    if "." in app_name and " " not in app_name:
        pkgs = get_all_packages()
        for p in pkgs:
            if p["package"] == app_name:
                print(f"✅ 패키지 직접 지정: {p['package']}")
                return p
        print(f"❌ 패키지 '{app_name}' 기기에 없음")
        return None

    packages = get_all_packages()
    launcher_pkgs = get_launcher_packages()

    # 모든 후보 키워드 수집 (영문 원문 + 한글 매핑)
    all_keywords = []
    for w in app_name.lower().split():
        if w.isascii():
            all_keywords.append(w)
    for korean, english_list in KOREAN_KEYWORD_MAP.items():
        if korean in app_name:
            all_keywords.extend(english_list)

    # 길이 내림차순 정렬 (길수록 구체적)
    all_keywords = sorted(set(all_keywords), key=len, reverse=True)
    print(f"  검색 키워드: {all_keywords}")

    # 각 키워드를 개별로 시도 — 런처 1개로 좁혀지면 즉시 반환
    for kw in all_keywords:
        candidates = [p for p in packages if kw in p["package"].lower()]
        launcher_hit = [p for p in candidates if p["package"] in launcher_pkgs]
        if len(launcher_hit) == 1:
            print(f"✅ 패키지 자동 선택 (키워드: '{kw}'): {launcher_hit[0]['package']}")
            return launcher_hit[0]

    # 자동 선택 실패 → 가장 많이 매칭된 키워드로 목록 표시
    best_candidates = []
    for kw in all_keywords:
        candidates = [p for p in packages if kw in p["package"].lower()]
        launcher_hit = [p for p in candidates if p["package"] in launcher_pkgs]
        result = launcher_hit if launcher_hit else candidates
        if result and len(result) < len(best_candidates or result) + 1:
            best_candidates = result

    if not best_candidates:
        print(f"❌ '{app_name}'에 해당하는 패키지를 찾지 못했습니다.")
        print("   직접 입력: python app_scanner.py com.example.myapp")
        return None

    display = best_candidates[:15]
    print(f"\n🔍 '{app_name}' 후보 {len(display)}개 — 번호를 선택하세요:")
    for i, p in enumerate(display):
        tag = "★" if p["package"] in launcher_pkgs else " "
        print(f"  [{i}]{tag} {p['package']}")
    try:
        idx = int(input("\n선택 (번호 입력): ").strip())
        return display[idx]
    except (ValueError, IndexError):
        print("❌ 잘못된 선택")
        return None


# ══════════════════════════════════════════════════
# 2. Inspector XML 확인
# ══════════════════════════════════════════════════

def get_inspector_xml_path(package: str) -> Path:
    return INSPECTOR_DIR / f"{package}.xml"


def check_inspector_xml(package: str) -> bool:
    path = get_inspector_xml_path(package)
    if path.exists():
        size = path.stat().st_size
        print(f"📋 Inspector XML 발견: {path.name} ({size:,} bytes)")
        return True
    print(f"📋 Inspector XML 없음 → 실시간 수집 실행")
    print(f"   (나중에 추가하려면: {path} 에 저장)")
    return False


# ══════════════════════════════════════════════════
# 3. XML 파싱 (Inspector & 실시간 공통)
# ══════════════════════════════════════════════════

def parse_elements_from_xml(xml_source: str, source: str = "live") -> dict:
    """
    XML에서 의미 있는 element 추출
    source: "inspector" | "live"
    """
    try:
        root = ET.fromstring(xml_source)
    except ET.ParseError as e:
        print(f"  ⚠️  XML 파싱 오류 ({source}): {e}")
        return {}

    elements = {}
    seen_keys = set()

    def traverse(node, depth=0):
        rid     = node.get("resource-id", "")
        desc    = node.get("content-desc", "").strip()
        text    = node.get("text", "").strip()
        bounds  = node.get("bounds", "")
        clickable = node.get("clickable", "false") == "true"
        cls     = node.get("class", "").split(".")[-1]

        # 의미 있는 label 결정
        label = desc or text
        if not label or len(label) > 80:
            for child in node: traverse(child, depth + 1)
            return

        # 중복 방지 키: rid 우선, 없으면 label
        dedup_key = rid if rid else label
        if dedup_key in seen_keys:
            for child in node: traverse(child, depth + 1)
            return
        seen_keys.add(dedup_key)

        # map key 생성: label 기반 snake_case
        map_key = _label_to_key(label, rid)

        elements[map_key] = {
            "label":       label,
            "text":        text,
            "resource_id": rid,
            "content_desc": desc,
            "bounds":      bounds,
            "xpath":       _build_xpath(rid, desc, text),
            "class":       cls,
            "clickable":   clickable,
            "source":      source,
            "verified":    source == "inspector",  # Inspector 출처면 verified
            "verified_at": datetime.now().strftime("%Y-%m-%d") if source == "inspector" else "",
        }

        for child in node: traverse(child, depth + 1)

    traverse(root)
    return elements


def _label_to_key(label: str, rid: str) -> str:
    """label → snake_case key. resource-id 끝 부분 있으면 활용"""
    if rid:
        suffix = rid.split("/")[-1] if "/" in rid else ""
        if suffix and len(suffix) < 40:
            return suffix
    # 한글 포함 label → 음역 없이 핵심 단어만
    clean = re.sub(r"[^\w\s가-힣]", "", label)
    words = clean.split()[:3]
    key = "_".join(w.lower() for w in words if w)
    return key or "element"


def _build_xpath(rid: str, desc: str, text: str) -> str:
    if rid:
        return f'//*[@resource-id="{rid}"]'
    if desc:
        return f'//*[@content-desc="{desc}"]'
    if text:
        return f'//*[@text="{text}"]'
    return ""


# ══════════════════════════════════════════════════
# 4. 실시간 dump (Appium)
# ══════════════════════════════════════════════════

def collect_live_dumps(package: str, activity: str) -> dict:
    """
    Appium으로 앱 연결 → 여러 화면 스크롤하며 XML dump 수집
    """
    try:
        from appium import webdriver
        from appium.options.android.uiautomator2.base import UiAutomator2Options
    except ImportError:
        print("❌ Appium-Python-Client 미설치: pip install Appium-Python-Client")
        return {}

    opts = UiAutomator2Options()
    opts.platform_name = "Android"
    opts.automation_name = "UiAutomator2"
    opts.app_package = package
    opts.app_activity = activity
    opts.no_reset = True
    opts.new_command_timeout = 300

    print(f"\n  📡 Appium 연결 중 ({package})...")
    try:
        driver = webdriver.Remote(APPIUM_SERVER, options=opts)
    except Exception as e:
        print(f"  ❌ Appium 연결 실패: {e}")
        print(f"  → appium 서버가 실행 중인지 확인하세요.")
        return {}

    print("  ✅ 연결 성공")
    merged = {}
    raw_xmls = []

    try:
        time.sleep(3)

        # 최상단 이동
        for _ in range(2):
            driver.swipe(540, 800, 540, 1800, 300)
            time.sleep(0.3)

        # 스크롤 다운하며 각 화면 dump
        print("  📸 화면 스캔 중...")
        for scroll_n in range(8):
            src = driver.page_source
            raw_xmls.append(src)
            parsed = parse_elements_from_xml(src, source="live")
            for k, v in parsed.items():
                if k not in merged:
                    merged[k] = v
                    print(f"    + [{scroll_n}] {k}: {v['label'][:30]}")
            driver.swipe(540, 1300, 540, 500, 500)
            time.sleep(0.8)

        # 원본 XML 합쳐서 저장 (Inspector가 없을 때 참고용)
        combined_xml = "\n<!-- next_screen -->\n".join(raw_xmls)
        live_xml_path = INSPECTOR_DIR / f"{package}.live.xml"
        live_xml_path.write_text(combined_xml, encoding="utf-8")
        print(f"\n  💾 실시간 XML 저장: {live_xml_path.name}")

    finally:
        driver.quit()

    return merged


# ══════════════════════════════════════════════════
# 5. Inspector XML 파싱
# ══════════════════════════════════════════════════

def collect_inspector_elements(package: str) -> dict:
    path = get_inspector_xml_path(package)
    xml_source = path.read_text(encoding="utf-8")
    print(f"  🔍 Inspector XML 파싱 중...")

    # 다중 문서 지원: <!-- next_screen --> 구분자로 분할
    parts = re.split(r"<!--.*?-->", xml_source)
    parts = [p.strip() for p in parts if p.strip().startswith("<")]

    if not parts:
        parts = [xml_source]

    merged = {}
    for i, part in enumerate(parts):
        parsed = parse_elements_from_xml(part, source="inspector")
        for k, v in parsed.items():
            if k not in merged:
                merged[k] = v

    print(f"  ✅ {len(merged)}개 element 파싱 완료 ({len(parts)}개 화면, verified=true)")
    return merged


# ══════════════════════════════════════════════════
# 6. 병합
# ══════════════════════════════════════════════════

def merge_elements(inspector: dict, live: dict) -> dict:
    """
    병합 규칙:
    - Inspector 출처 element → verified=true, 우선 유지
    - Live 출처 element → Inspector에 없으면 추가 (verified=false)
    - 같은 key 충돌 시 Inspector 우선
    """
    merged = {}

    # Inspector 먼저 (우선순위 높음)
    for k, v in inspector.items():
        merged[k] = v

    # Live에서 Inspector에 없는 것만 추가
    added = 0
    for k, v in live.items():
        if k not in merged:
            merged[k] = v
            added += 1
        else:
            # Inspector element에 live 정보로 bounds 보완
            if not merged[k].get("bounds") and v.get("bounds"):
                merged[k]["bounds"] = v["bounds"]

    print(f"\n  🔀 병합 결과: Inspector {len(inspector)}개 + Live 신규 {added}개 = 총 {len(merged)}개")
    return merged


# ══════════════════════════════════════════════════
# 7. ui_map 저장
# ══════════════════════════════════════════════════

def save_ui_map(package: str, activity: str, elements: dict) -> Path:
    output = {
        "app": package.split(".")[-1],
        "package": package,
        "activity": activity,
        "generated_at": datetime.now().isoformat(),
        "element_count": len(elements),
        "verified_count": sum(1 for v in elements.values() if v.get("verified")),
        "note": "verified=true: Inspector 출처 / verified=false: 실시간 dump 출처",
        "elements": elements,
    }
    path = UI_MAP_DIR / f"{package}.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ══════════════════════════════════════════════════
# 8. 메인
# ══════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("사용법: python app_scanner.py <앱 이름>")
        print("예시 : python app_scanner.py '삼성헬스'")
        print("       python app_scanner.py 'calculator'")
        sys.exit(1)

    app_name = " ".join(sys.argv[1:])

    print("=" * 55)
    print(f"🔎 앱 스캐너 시작: '{app_name}'")
    print("=" * 55)

    # ── Step 1: 패키지 탐색 ──
    print("\n[1/4] 패키지 탐색...")
    pkg_info = find_package(app_name)
    if not pkg_info:
        sys.exit(1)
    package = pkg_info["package"]

    # ── Step 2: ui_map 이미 완성됐는지 확인 ──
    ui_map_path = UI_MAP_DIR / f"{package}.json"
    if ui_map_path.exists():
        existing = json.loads(ui_map_path.read_text())
        v_count = existing.get("verified_count", 0)
        total   = existing.get("element_count", 0)
        print(f"\n[✓] ui_map 이미 존재: {ui_map_path.name}")
        print(f"    {v_count}/{total}개 verified")
        ans = input("    다시 수집하시겠습니까? [y/N]: ").strip().lower()
        if ans != "y":
            print(f"\n✅ 기존 ui_map 사용: {ui_map_path}")
            return str(ui_map_path)

    # ── Step 3: 런치 액티비티 확인 ──
    print(f"\n[2/4] 런치 액티비티 탐색...")
    activity = get_launch_activity(package)
    print(f"  ✅ {activity}")

    # ── Step 4: Inspector XML 확인 ──
    print(f"\n[3/4] Inspector XML 확인...")
    has_inspector = check_inspector_xml(package)

    inspector_elements = {}
    live_elements      = {}

    if has_inspector:
        print("\n  → Inspector XML 파싱 (실시간 수집 스킵)")
        inspector_elements = collect_inspector_elements(package)
    else:
        print(f"\n  → 실시간 수집 실행")
        print(f"  💡 나중에 Inspector XML을 추가하면 정확도가 높아집니다:")
        print(f"     저장 위치: inspector_dumps/{package}.xml")

    # 실시간 dump는 항상 보완 수집 (Inspector 있어도 누락분 채우기)
    print(f"\n[4/4] 실시간 XML dump 수집...")
    live_elements = collect_live_dumps(package, activity)

    # ── Step 5: 병합 ──
    print(f"\n[병합] Inspector + Live 결합...")
    merged = merge_elements(inspector_elements, live_elements)

    # ── Step 6: 저장 ──
    saved_path = save_ui_map(package, activity, merged)
    v_count = sum(1 for v in merged.values() if v.get("verified"))

    print(f"\n{'='*55}")
    print(f"✅ ui_map 생성 완료!")
    print(f"   파일   : {saved_path}")
    print(f"   총 element : {len(merged)}개")
    print(f"   verified   : {v_count}개 (Inspector 출처)")
    print(f"   unverified : {len(merged)-v_count}개 (실시간 dump 출처)")
    if not has_inspector:
        print(f"\n💡 Inspector XML 추가 방법:")
        print(f"   1. Appium Inspector 실행 → 앱 연결")
        print(f"   2. 각 화면에서 File → Save XML")
        print(f"   3. 저장 위치: inspector_dumps/{package}.xml")
        print(f"   4. python app_scanner.py '{app_name}' 재실행 → verified 수 증가")
    print("=" * 55)

    return str(saved_path)


if __name__ == "__main__":
    main()
