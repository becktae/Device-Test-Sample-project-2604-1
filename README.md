# Device Test — Appium Android UI 자동화 + AI/MCP

Android 앱을 대상으로 UI 요소를 자동 수집하고, 시나리오 기반 테스트를 실행하며, 실패 시 Claude Vision AI가 자동 복구하는 자동화 프레임워크입니다.  
Claude Code MCP를 통해 AI가 테스트 인프라를 직접 제어합니다.

---

## 대시보드 스크린샷

![Dashboard](dashboard_screenshot.png)

---

## 시스템 구조

```
Device Test
│
├── 📱 Android 단말 (ADB 연결)
│       └── 테스트 대상 앱 (Samsung Health, Calculator …)
│
├── 🔧 Appium Server (http://127.0.0.1:4723)
│       └── UiAutomator2 드라이버 → 앱 조작 / XML dump
│
├── 🗺  UI 맵 수집
│   ├── app_scanner.py       앱 이름 → 패키지 탐색 → XML 수집 → ui_map 저장
│   └── ui_maps/
│       ├── com.sec.android.app.shealth.json
│       └── com.sec.android.app.popupcalculator.json
│
├── 🏃 테스트 실행
│   ├── run_app.py           ui_map 기반 범용 시나리오 러너
│   │                         └── 실패 시 AI 자동 분석 + 복구 재시도
│   └── result_log.json      실행 결과 (자동 생성)
│
├── 🤖 AI / MCP 레이어  ← NEW
│   ├── mcp_server.py        MCP 서버 — Claude가 직접 호출하는 16개 툴
│   ├── ai_helper.py         Claude Vision API — 스크린샷 분석 / 좌표 탐색
│   └── .mcp.json            Claude Code MCP 자동 연결 설정
│
└── 🌐 웹 대시보드
    ├── server.py            Flask 서버 (REST API + SSE 실시간 스트림)
    └── dashboard.html       테스트 컨트롤 + 결과 시각화
```

---

## AI / MCP 연동 구조

```
사용자: "삼성헬스 테스트 실행해줘"
    │
    ▼
Claude Code (MCP Client)
    │  .mcp.json 로 자동 연결
    ▼
mcp_server.py (MCP Server)
    ├── list_apps()            → ui_maps/ 앱 목록 조회
    ├── run_test(package)      → run_app.py 실행
    ├── connect_device()       → Appium 세션 생성
    ├── take_screenshot()      → 현재 화면 캡처
    ├── get_page_source()      → XML dump 조회
    ├── tap(x, y)              → 좌표 직접 탭
    ├── analyze_failure_with_ai() → Claude Vision 실패 분석
    ├── find_element_on_screen()  → 화면에서 element 좌표 탐색
    └── update_ui_map_element()   → 복구 좌표를 ui_map에 영구 저장
```

### 테스트 실패 시 AI 자동 복구 흐름

```
element 탐색 실패
    │
    ├── 📸 스크린샷 저장          error_HHMMSS.png
    ├── 🗂  XML dump 저장          error_HHMMSS.xml
    ├── 📋 ADB logcat 수집         error_HHMMSS.logcat.txt
    │       └── 필터: 패키지명 · AndroidRuntime · FATAL · ANR · Exception
    │
    ├── 🤖 Claude Vision 호출 (claude-haiku-4-5)
    │       ├── 스크린샷 (이미지)
    │       ├── XML element 구조   ← 화면에 무엇이 있는지
    │       ├── logcat 크래시 로그 ← 앱 내부 에러 원인
    │       │
    │       ├── 현재 화면 상태 파악
    │       ├── 실패 원인 분석 (logcat·XML 근거 포함)
    │       └── 복구 좌표 제안
    │
    ├── 🎯 AI 제안 좌표로 tap() 재시도
    │
    └── ✅ 복구 성공 → PASS로 자동 전환
        (실패 시 ERROR 로그 + ai_analysis 기록)
```

---

## 파일 구성

| 파일 | 역할 |
|------|------|
| `app_scanner.py` | 앱 이름으로 패키지 탐색 + XML 수집 + ui_map 생성 |
| `run_app.py` | ui_map 기반 범용 시나리오 실행기 + AI 자동 복구 |
| `mcp_server.py` | **MCP 서버** — Claude가 직접 호출하는 16개 툴 |
| `ai_helper.py` | **Claude Vision API** 래퍼 — 스크린샷/XML/logcat 종합 분석 |
| `.mcp.json` | Claude Code MCP 자동 연결 설정 |
| `.env.example` | 환경변수 템플릿 (API 키 등) |
| `server.py` | Flask 웹 서버 (REST API + SSE 실시간 스트림) |
| `dashboard.html` | 테스트 컨트롤 + 결과 시각화 대시보드 |
| `ui_maps/` | 앱별 UI 맵 JSON |
| `inspector_dumps/` | Appium Inspector 내보내기 XML |

---

## MCP 툴 목록 (16개)

| 카테고리 | 툴 | 설명 |
|---------|-----|------|
| 조회 | `list_apps` | 테스트 가능한 앱 + 시나리오 목록 |
| 조회 | `get_ui_map` | 특정 앱 ui_map 전체 조회 |
| 조회 | `get_test_result` | 마지막 테스트 결과 |
| 실행 | `run_test` | 시나리오 실행 + 결과 반환 |
| Appium | `connect_device` | 기기 Appium 세션 생성 |
| Appium | `disconnect_device` | 세션 종료 |
| Appium | `launch_app` | 앱 강제 종료 후 재실행 |
| Appium | `take_screenshot` | 현재 화면 캡처 |
| Appium | `get_page_source` | 화면 XML dump |
| Appium | `tap` | 좌표 탭 |
| Appium | `swipe_up` | 위로 스크롤 |
| Appium | `click_element` | resource_id/xpath/content_desc로 클릭 |
| AI 분석 | `analyze_screenshot_with_ai` | 스크린샷 자유 질문 분석 |
| AI 분석 | `analyze_failure_with_ai` | 실패 원인 + 복구 좌표 제안 |
| AI 분석 | `find_element_on_screen` | 화면에서 element 좌표 탐색 |
| ui_map | `update_ui_map_element` | element 필드 수정 (AI 복구 좌표 영구 저장) |

---

## 빠른 시작

### 1. 사전 요구사항

```bash
pip install Appium-Python-Client selenium flask mcp anthropic

# Appium 서버 실행
appium

# Android 단말 ADB 연결 확인
adb devices
```

### 2. 환경변수 설정

```bash
export ANTHROPIC_API_KEY="sk-ant-..."   # AI 분석 기능 활성화
export ANDROID_HOME="/Users/<user>/Library/Android/sdk"
```

### 3. UI 맵 수집

```bash
python app_scanner.py "삼성헬스"
# → ui_maps/com.sec.android.app.shealth.json 생성
```

### 4. 웹 대시보드 실행

```bash
python server.py
# → http://localhost:5000
```

### 5. Claude Code에서 MCP로 직접 제어

```bash
cd "Device test Claude"
claude  # .mcp.json 자동 인식 → device-test MCP 연결
```

Claude에게 자연어로 지시:
```
"삼성헬스 테스트 실행해줘"
"테스트 실패 원인 분석해줘"
"혈중 산소 버튼을 화면에서 찾아서 탭해줘"
```

### 6. CLI 직접 실행

```bash
python run_app.py com.sec.android.app.shealth all
python run_app.py com.sec.android.app.shealth blood_oxygen_tap_check
```

---

## 지원 액션 (시나리오 JSON)

| 액션 | 설명 |
|------|------|
| `launch` | 앱 강제 종료 후 재실행 |
| `wait` | 지정 시간(ms) 대기 |
| `click` | element 탐색 후 클릭 (resource_id → xpath → content_desc → bounds 순) |
| `scroll_click` | UIScrollable 스크롤 후 탭 |
| `verify_screen` | 크래시 다이얼로그 감지 |

---

## 실패 시 수집 아티팩트

테스트 스텝이 실패하면 아래 3가지 파일을 자동 저장합니다.

| 파일 | 내용 |
|------|------|
| `error_HHMMSS.png` | 실패 순간 화면 스크린샷 |
| `error_HHMMSS.xml` | 화면 전체 element 구조 (XML dump) |
| `error_HHMMSS.logcat.txt` | ADB logcat — 앱 크래시·ANR·Exception 필터 |

> 이 파일들은 `.gitignore`에 등록되어 저장소에 업로드되지 않습니다.

---

## 결과 형식

```json
{
  "scenario_id": "blood_oxygen_tap_check",
  "result": "PASS",
  "ai_invoked": false,
  "summary": { "total": 7, "pass": 7, "fail": 0, "error": 0 },
  "elapsed_seconds": 27,
  "steps": [
    {
      "seq": 5,
      "action": "scroll_click",
      "desc": "하단 스크롤 후 혈중 산소 카드 탭",
      "status": "PASS",
      "detail": "UIScrollable+tap via '혈중 산소'"
    }
  ]
}
```

AI 복구 시 step에 `screenshot` · `xml_dump` · `logcat` · `ai_analysis` 필드 추가:

```json
{
  "status": "PASS",
  "detail": "AI 복구 성공 — tap(540, 892)",
  "screenshot":  "error_190718.png",
  "xml_dump":    "error_190718.xml",
  "logcat":      "error_190718.logcat.txt",
  "ai_analysis": {
    "screen_state":    "홈 화면, 혈중 산소 카드 하단에 위치",
    "failure_reason":  "스크롤 위치 변경으로 bounds 불일치 (logcat 무관)",
    "recovery":        "화면 중앙 하단 혈중 산소 카드 탭",
    "coordinates":     [540, 892]
  }
}
```

| result | 의미 |
|--------|------|
| `PASS` | 전체 시나리오 성공 |
| `FAIL` | 화면 검증 실패 |
| `ERROR` | element 미탐색 — 아티팩트 3종 저장 + AI 복구 시도 후 기록 |

---

## 장치 스크린샷 (Samsung Health)

![Samsung Health](error_185937.png)
