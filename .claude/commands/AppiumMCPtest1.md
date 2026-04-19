# AppiumMCPtest1 스킬

이 프로젝트의 Android UI 자동화 테스트를 실행하고 결과를 분석하는 전체 워크플로우를 수행합니다.

## 실행 순서

### 1단계 — 환경 점검

다음을 순서대로 확인합니다:

```bash
# Appium 서버 상태 확인
curl -s http://127.0.0.1:4723/status

# ADB 기기 연결 확인
adb devices
```

- Appium 미실행 시: "Appium 서버를 먼저 실행하세요 (`appium`)" 안내
- 기기 미연결 시: "ADB 기기가 없습니다. USB 디버깅을 확인하세요" 안내
- 둘 다 정상이면 2단계로 진행

### 2단계 — 테스트 대상 확인

`$ARGUMENTS`가 있으면 해당 앱/시나리오를 사용합니다.  
없으면 `ui_maps/` 폴더의 앱 목록을 보여주고 선택을 받습니다.

`$ARGUMENTS` 형식 예시:
- `삼성헬스` → com.sec.android.app.shealth, 전체 시나리오
- `삼성헬스 blood_oxygen_tap_check` → 특정 시나리오만
- `com.sec.android.app.shealth` → 패키지명 직접 입력

### 3단계 — 테스트 실행

```bash
cd "/Users/becktae/project/Device test Claude"
ANDROID_HOME=/Users/becktae/Library/Android/sdk \
ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}" \
python3 run_app.py <package> <scenario_id>
```

실행 중 콘솔 출력을 그대로 보여줍니다.

### 4단계 — 결과 분석

테스트 완료 후 `result_log.json`을 읽어 아래 형식으로 요약합니다:

```
📊 테스트 결과 요약
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
앱       : <app_name>
시나리오  : <scenario_id>
결과      : ✅ PASS / ❌ FAIL / 💥 ERROR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
전체 단계 : N
  ✅ 성공  : N
  ❌ 실패  : N
  💥 오류  : N
소요 시간 : Ns
AI 개입   : 있음 / 없음
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 5단계 — 실패/오류 심층 분석 (오류 있을 때만)

실패한 스텝이 있으면 수집된 아티팩트를 분석합니다:

1. **스크린샷** (`error_*.png`) — 실패 순간 화면 확인
2. **XML dump** (`error_*.xml`) — 화면 element 구조 분석
3. **logcat** (`error_*.logcat.txt`) — 앱 크래시·ANR·Exception 로그 확인

각 실패 스텝에 대해:
- 실패 원인 설명
- AI가 복구를 시도했는지 여부
- AI 복구 결과 (`ai_analysis.coordinates`, `ai_analysis.failure_reason`)
- 재발 방지를 위한 ui_map 수정 제안

### 6단계 — 후속 액션 제안

결과에 따라 다음 중 하나를 제안합니다:

- **PASS**: "모든 테스트 통과. 대시보드에서 확인: http://100.103.93.8:5000"
- **FAIL/ERROR + AI 복구 성공**: "AI가 자동 복구했습니다. ui_map을 업데이트할까요?"
- **FAIL/ERROR + 복구 실패**: "수동 확인이 필요합니다. Inspector로 element를 다시 수집할까요?"

---

## 빠른 참조

| 명령 | 설명 |
|------|------|
| `/AppiumMCPtest1` | 앱 목록 보여주고 선택 |
| `/AppiumMCPtest1 삼성헬스` | 삼성헬스 전체 시나리오 실행 |
| `/AppiumMCPtest1 삼성헬스 blood_oxygen_tap_check` | 특정 시나리오만 실행 |

---

## 프로젝트 경로

- 프로젝트 루트: `/Users/becktae/project/Device test Claude`
- UI 맵: `ui_maps/<package>.json`
- 결과 로그: `result_log.json`
- 웹 대시보드: `http://100.103.93.8:5000`
- Appium 서버: `http://127.0.0.1:4723`
