"""HTTP API that exposes the download queue/log/config to the Vue UI."""
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS

from log_file import LOG_FILE
from saturn_dowload_main import (
    get_all_from_file,
    get_config_path,
    is_worker_running,
    saturn_download_main,
    set_config_path,
)

app = Flask(__name__)
CORS(app)


@app.get("/api/status")
def status():
    queue = get_all_from_file()
    running = is_worker_running()
    current = queue[0] if (queue and running) else None
    pending = queue[1:] if current else queue
    return jsonify({
        "current": current,
        "queue": pending,
        "running": running,
        "path": get_config_path(),
    })


@app.post("/api/queue")
def add_to_queue():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "URL mancante"}), 400
    saturn_download_main(url)
    return jsonify({"ok": True})


@app.get("/api/config")
def read_config():
    return jsonify({"path": get_config_path()})


@app.post("/api/config")
def write_config():
    data = request.get_json(silent=True) or {}
    path = (data.get("path") or "").strip()
    if not path:
        return jsonify({"error": "Path mancante"}), 400
    set_config_path(path)
    return jsonify({"ok": True, "path": path})


@app.get("/api/logs")
def read_logs():
    lines_param = request.args.get("lines", default="300")
    try:
        limit = int(lines_param)
    except ValueError:
        limit = 300

    log_path = Path(LOG_FILE)
    if not log_path.is_file():
        return jsonify({"lines": []})

    with open(log_path, "r", encoding="utf-8") as f:
        lines = [line.rstrip("\n") for line in f]

    return jsonify({"lines": lines[-limit:] if limit > 0 else lines})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
