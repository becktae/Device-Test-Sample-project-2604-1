"""
ai_helper.py
Claude Vision API — 스크린샷 분석 및 테스트 실패 복구
"""

import base64
import os
import re
from pathlib import Path

import anthropic


def _client() -> anthropic.Anthropic:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise EnvironmentError("ANTHROPIC_API_KEY 환경변수가 없습니다")
    return anthropic.Anthropic(api_key=key)


def _encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def analyze_screenshot(image_path: str, question: str) -> str:
    """스크린샷 + 질문 → Claude Vision 응답"""
    client = _client()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": _encode_image(image_path),
                    },
                },
                {"type": "text", "text": question},
            ],
        }],
    )
    return msg.content[0].text


def find_element_coordinates(image_path: str, element_desc: str) -> tuple[int, int] | None:
    """
    화면에서 element를 찾아 중심 좌표 반환.
    못 찾으면 None.
    """
    question = f"""이 Android 화면 스크린샷에서 "{element_desc}" 요소를 찾아주세요.

찾았다면 — 반드시 아래 형식으로만 답하세요:
COORDINATES: x=<숫자>, y=<숫자>

찾지 못했다면:
NOT_FOUND: <이유 한 줄>

좌표는 실제 화면 픽셀 기준입니다. 다른 설명 없이 한 줄로만 답하세요."""

    result = analyze_screenshot(image_path, question)
    m = re.search(r"COORDINATES:\s*x=(\d+),\s*y=(\d+)", result)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def analyze_test_failure(screenshot_path: str, error_detail: str, step_desc: str) -> dict:
    """
    테스트 실패 분석.
    반환: {screen_state, failure_reason, recovery, coordinates, raw}
    """
    question = f"""Android 앱 UI 자동화 테스트가 실패했습니다.

실패 단계: {step_desc}
에러 메시지: {error_detail}

이 스크린샷을 보고 아래 형식으로 분석해주세요 (각 항목 한 줄):

SCREEN_STATE: <현재 화면 상태>
FAILURE_REASON: <실패 원인>
RECOVERY: <복구 방법>
COORDINATES: x=<숫자>, y=<숫자>

COORDINATES는 탭으로 문제를 해결할 수 있을 때만 포함하세요.
없으면 COORDINATES 줄 자체를 생략하세요."""

    result = analyze_screenshot(screenshot_path, question)

    parsed: dict = {"raw": result, "screen_state": "", "failure_reason": "", "recovery": "", "coordinates": None}
    for line in result.splitlines():
        if line.startswith("SCREEN_STATE:"):
            parsed["screen_state"] = line.split(":", 1)[1].strip()
        elif line.startswith("FAILURE_REASON:"):
            parsed["failure_reason"] = line.split(":", 1)[1].strip()
        elif line.startswith("RECOVERY:"):
            parsed["recovery"] = line.split(":", 1)[1].strip()
        elif line.startswith("COORDINATES:"):
            m = re.search(r"x=(\d+),\s*y=(\d+)", line)
            if m:
                parsed["coordinates"] = (int(m.group(1)), int(m.group(2)))

    return parsed
