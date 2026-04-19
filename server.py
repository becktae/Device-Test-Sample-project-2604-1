"""
server.py
테스트 대시보드 웹 서버

실행: python server.py
접속: http://localhost:5000
"""

import json
import os
import queue
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

BASE_DIR   = Path(__file__).parent
UI_MAP_DIR = BASE_DIR / "ui_maps"
LOG_PATH   = BASE_DIR / "result_log.json"
ANDROID_HOME = str(Path.home() / "Library/Android/sdk")

app = Flask(__name__)

# ── 전역 테스트 상태 ──────────────────────────────────
_state = {
    "running":    False,
    "package":    None,
    "app_name":   None,
    "scenario_id": None,
    "started_at": None,
    "log_queue":  queue.Queue(),
}
_subscribers: list[queue.Queue] = []
_subscribers_lock = threading.Lock()


def broadcast(item: dict):
    """모든 SSE 구독자에게 메시지 전송"""
    with _subscribers_lock:
        dead = []
        for q in _subscribers:
            try:
                q.put_nowait(item)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _subscribers.remove(q)


# ── API ──────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "dashboard.html")


@app.route("/api/apps")
def list_apps():
    """ui_maps/ 폴더에서 테스트 가능한 앱 목록 반환"""
    apps = []
    if UI_MAP_DIR.exists():
        for f in sorted(UI_MAP_DIR.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                scenarios = data.get("scenarios", [])
                apps.append({
                    "package":        data.get("package", f.stem),
                    "app":            data.get("app", f.stem),
                    "element_count":  data.get("element_count", 0),
                    "verified_count": data.get("verified_count", 0),
                    "scenarios": [
                        {"id": s["id"], "name": s["name"]}
                        for s in scenarios
                    ],
                    "generated_at": data.get("generated_at", ""),
                })
            except Exception:
                pass
    return jsonify(apps)


@app.route("/api/status")
def status():
    return jsonify({
        "running":     _state["running"],
        "package":     _state["package"],
        "app_name":    _state["app_name"],
        "scenario_id": _state["scenario_id"],
        "started_at":  _state["started_at"],
    })


@app.route("/api/run", methods=["POST"])
def run_test():
    if _state["running"]:
        return jsonify({"error": "이미 테스트 실행 중입니다"}), 409

    body        = request.get_json() or {}
    package     = body.get("package", "").strip()
    scenario_id = body.get("scenario_id", "all")
    app_name    = body.get("app_name", package)

    if not package:
        return jsonify({"error": "package 필드 필요"}), 400

    ui_map_path = UI_MAP_DIR / f"{package}.json"
    if not ui_map_path.exists():
        return jsonify({"error": f"ui_map 없음: {package}"}), 404

    _state["running"]     = True
    _state["package"]     = package
    _state["app_name"]    = app_name
    _state["scenario_id"] = scenario_id
    _state["started_at"]  = datetime.now().isoformat()

    # 이전 로그 비우기
    while not _state["log_queue"].empty():
        _state["log_queue"].get_nowait()

    def _run():
        env = {
            **os.environ,
            "ANDROID_HOME":     ANDROID_HOME,
            "ANDROID_SDK_ROOT": ANDROID_HOME,
        }
        cmd = [sys.executable, str(BASE_DIR / "run_app.py"), package, scenario_id]

        broadcast({"type": "start", "package": package, "app_name": app_name})

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, env=env, cwd=str(BASE_DIR), bufsize=1
            )
            for line in proc.stdout:
                text = line.rstrip()
                if text:
                    broadcast({"type": "log", "text": text})
            proc.wait()
            exit_code = proc.returncode
        except Exception as e:
            broadcast({"type": "log", "text": f"❌ 실행 오류: {e}"})
            exit_code = 1

        # 결과 로드
        result = None
        if LOG_PATH.exists():
            try:
                result = json.loads(LOG_PATH.read_text())
            except Exception:
                pass

        _state["running"] = False
        broadcast({"type": "done", "exit_code": exit_code, "result": result})

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started", "package": package, "scenario_id": scenario_id})


@app.route("/api/stream")
def stream():
    """SSE — 테스트 로그 실시간 스트림"""
    client_q: queue.Queue = queue.Queue(maxsize=200)
    with _subscribers_lock:
        _subscribers.append(client_q)

    # 현재 실행 중이면 상태 즉시 전송
    if _state["running"]:
        client_q.put({"type": "status", "running": True,
                      "package": _state["package"], "app_name": _state["app_name"]})

    def event_gen():
        try:
            while True:
                try:
                    item = client_q.get(timeout=25)
                    yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                    if item.get("type") == "done":
                        break
                except queue.Empty:
                    yield "data: {\"type\":\"ping\"}\n\n"
        finally:
            with _subscribers_lock:
                if client_q in _subscribers:
                    _subscribers.remove(client_q)

    return Response(
        event_gen(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/result")
def get_result():
    if not LOG_PATH.exists():
        return jsonify({"error": "결과 없음"}), 404
    return jsonify(json.loads(LOG_PATH.read_text()))


if __name__ == "__main__":
    print("=" * 45)
    print("🖥  테스트 대시보드 서버 시작")
    print("   http://localhost:5000")
    print("=" * 45)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
