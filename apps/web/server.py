"""
apps/web/server.py — Social Agent Web Server (VPS / headless environment)
Serve apps/ui/ qua browser + REST API endpoints mirror với desktop bridge.py.

Chạy: python apps/web/server.py
Hoặc: uvicorn apps.web.server:app --host 0.0.0.0 --port 8080

Truy cập: http://localhost:8080

NOTE: Endpoints phải mirror với apps/desktop/bridge.py
để apps/ui/app.js hoạt động được trên cả 2 môi trường.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

CONFIG_PATH = str(ROOT / "config.yaml")
UI_DIR = ROOT / "apps" / "ui"

app = FastAPI(title="Social Agent", version="0.2.0", docs_url="/docs")


def _agent():
    from social_agent.agent import SocialAgent
    return SocialAgent(config_path=CONFIG_PATH)


# ── Static UI ────────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(UI_DIR / "index.html"))


# ── API endpoints (mirror bridge.py) ─────────────────────────────────────────

@app.post("/api/get_stats")
def get_stats():
    return _agent().get_stats()


@app.post("/api/get_history")
def get_history(args: dict = {}):
    limit = args.get("limit", 20)
    return _agent().get_history(limit=limit)


@app.post("/api/list_targets")
def list_targets():
    agent = _agent()
    return [
        {"id": k, "name": v.get("name", k), "type": v.get("type"), "enabled": v.get("enabled", True)}
        for k, v in agent._targets.items()
    ]


@app.post("/api/list_topics")
def list_topics():
    agent = _agent()
    return [{"id": k, "name": v.get("name", k)} for k, v in agent._topics.items()]


@app.post("/api/preview")
def preview(args: dict):
    return _agent().preview(
        args.get("topic_id"),
        args.get("format_id"),
        platform=args.get("platform", "facebook"),
    )


@app.post("/api/post_now")
def post_now(args: dict):
    try:
        return _agent().post_now(
            target_id=args["target_id"],
            topic_id=args.get("topic_id"),
            format_id=args.get("format_id"),
            no_image=args.get("no_image", False),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("apps.web.server:app", host="0.0.0.0", port=8080, reload=False)
