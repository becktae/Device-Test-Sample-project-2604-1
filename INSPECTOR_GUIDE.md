# Appium Inspector 세팅 & 삼성헬스 UI 수집 가이드

## 1. Appium Inspector 설치

```bash
# Appium Inspector는 별도 GUI 앱
# https://github.com/appium/appium-inspector/releases
# → AppiumInspector-mac-arm64.dmg (Apple Silicon)
# → AppiumInspector-mac-x64.dmg (Intel)
# 다운로드 후 설치
```

---

## 2. Appium Inspector 연결 설정

Appium Server 실행 후 Inspector 실행

### Remote Path 설정
```
Remote Host : 127.0.0.1
Remote Port : 4723
Remote Path : /
```

### Desired Capabilities 입력
```json
{
  "platformName": "Android",
  "appium:automationName": "UiAutomator2",
  "appium:appPackage": "com.samsung.android.shealth",
  "appium:appActivity": "com.samsung.android.shealth.main.MainActivity",
  "appium:noReset": true,
  "appium:newCommandTimeout": 300
}
```

> 💡 noReset: true → 앱 데이터 유지, 로그인 상태 보존

---

## 3. 삼성헬스 패키지 확인

```bash
# 단말에서 실제 패키지명 확인
adb shell pm list packages | grep shealth

# 현재 포커스된 앱 확인 (삼성헬스 실행 후)
adb shell dumpsys window windows | grep mCurrentFocus
```

**알려진 패키지명**
| 버전 | 패키지명 |
|------|---------|
| 최신 | `com.samsung.android.shealth` |
| 구버전 | `com.sec.android.app.shealth` |

---

## 4. Appium Inspector 사용법

### 연결 후 화면 구성
```
┌─────────────────────────────────────────┐
│  [App Screenshot]    │  [XML Tree]      │
│                      │  ▼ LinearLayout  │
│   [클릭하면          │    ▼ FrameLayout │
│    해당 element      │      ▼ TextView  │
│    하이라이트]       │                  │
├──────────────────────┴──────────────────┤
│  Selected Element                        │
│  resource-id: com.samsung...id/menu_home │
│  text: 홈                                │
│  bounds: [0,2100][180,2340]              │
│  xpath: //...[@resource-id='...']        │
└─────────────────────────────────────────┘
```

### 수집 절차 (메뉴별)

1. **Inspector에서 Refresh** (📸 버튼) → 현재 화면 캡처
2. **수집할 element 클릭** (하단 메뉴 탭, 버튼 등)
3. **우측 패널에서 속성 확인**
   - `resource-id` → 가장 신뢰도 높음, 최우선 사용
   - `text` or `content-desc` → 대체 수단
   - `bounds` → 최후 수단 (좌표 탭)
4. **해당 정보를 ui_map.json에 기록**

---

## 5. 삼성헬스 수집 대상 메뉴

Inspector로 아래 화면 진입 후 각각 element 수집

| 메뉴 | 진입 방법 | 수집 대상 |
|------|---------|---------|
| 홈 | 하단 탭 1번 | 탭 버튼 resource-id |
| 운동 | 하단 탭 2번 | 탭 버튼 resource-id |
| 음식 | 하단 탭 3번 | 탭 버튼 resource-id |
| 수면 | 홈 카드 또는 탭 | 진입 버튼 |
| 걸음수 | 홈 카드 | 카드 element |
| 심박수 | 홈 카드 | 카드 element |

---

## 6. Inspector에서 XPath 생성 팁

Inspector 하단에 XPath 자동 생성 기능 있음

**우선순위별 XPath 패턴**
```
# 1순위: resource-id (가장 안정적)
//*[@resource-id='com.samsung.android.shealth:id/tab_home']

# 2순위: content-desc (접근성 레이블)
//*[@content-desc='홈']

# 3순위: text
//*[@text='홈']

# 4순위: bounds 좌표 (최후)
# bounds="[0,2100][180,2340]" → center tap (90, 2220)
```

---

## 7. 수집 후 데이터 저장

Inspector에서 확인한 정보를 `ui_map.json`에 수동 기입:

```json
{
  "tab_home": {
    "text": "홈",
    "resource_id": "com.samsung.android.shealth:id/탭_resource_id",
    "content_desc": "홈",
    "bounds": "[Inspector에서 복사]",
    "xpath": "//*[@resource-id='...']",
    "screen": "main",
    "verified": true,
    "verified_at": "2026-04-19"
  }
}
```

> ✅ `verified: true` = Inspector로 직접 눈으로 확인한 element
