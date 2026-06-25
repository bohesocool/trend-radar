"""TrendRadar Web 应用入口 — FastAPI + 固定密码鉴权 + Webhook 触发。"""

from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from trend_radar.config import get_config
from trend_radar.web.api import router
from trend_radar.web.auth import login, require_auth

_WEB_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _WEB_DIR / "static"
_TEMPLATE_DIR = _WEB_DIR / "templates"

app = FastAPI(title="TrendRadar", version="0.1.0", description="GitHub 趋势 + AI 资讯雷达")

# 静态文件
_STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

# API 路由
app.include_router(router)


# ===== 页面路由 =====

@app.get("/login", response_class=HTMLResponse)
async def login_page() -> str:
    return (_TEMPLATE_DIR / "login.html").read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> str:
    return (_TEMPLATE_DIR / "dashboard.html").read_text(encoding="utf-8")


@app.get("/trends", response_class=HTMLResponse)
async def trends_page() -> str:
    return (_TEMPLATE_DIR / "trends.html").read_text(encoding="utf-8")


@app.get("/suggestions", response_class=HTMLResponse)
async def suggestions_page() -> str:
    return (_TEMPLATE_DIR / "suggestions.html").read_text(encoding="utf-8")


@app.get("/archive", response_class=HTMLResponse)
async def archive_page() -> str:
    return (_TEMPLATE_DIR / "archive.html").read_text(encoding="utf-8")


# ===== 登录端点 =====

class LoginRequest(BaseModel):
    password: str


@app.post("/api/login", response_class=JSONResponse)
async def do_login(req: LoginRequest) -> dict:
    """用固定密码登录，返回 session token。"""
    token = login(req.password)
    if token:
        return {"status": "ok", "token": token}
    raise HTTPException(status_code=401, detail="密码错误")


# ===== Webhook 触发端点 (供 Hermes cron / 外部 HTTP 调用) =====

@app.post("/api/trigger/daily", response_class=JSONResponse)
async def trigger_daily(auth: bool = Depends(require_auth)) -> dict:
    """手动触发日报流程。需要 Bearer token 鉴权。"""
    from trend_radar.scheduler import run_daily

    try:
        report = await run_daily()
        return {
            "status": "ok",
            "date": report.date,
            "hot_topics": len(report.analysis.hot_topics),
            "suggestions": len(report.suggestions),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trigger/weekly", response_class=JSONResponse)
async def trigger_weekly(auth: bool = Depends(require_auth)) -> dict:
    """手动触发周报流程。需要 Bearer token 鉴权。"""
    from trend_radar.scheduler import run_weekly

    try:
        result = await run_weekly()
        return {"status": "ok", "report": result[:200] if isinstance(result, str) else ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trigger/collect", response_class=JSONResponse)
async def trigger_collect(auth: bool = Depends(require_auth)) -> dict:
    """仅执行数据采集 (不做分析/生成/推送)。"""
    from trend_radar.scheduler import run_collect_all

    try:
        items = await run_collect_all()
        return {
            "status": "ok",
            "total_items": len(items),
            "sources": list({i.source for i in items}),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def main() -> None:
    cfg = get_config()["web"]
    uvicorn.run(
        "trend_radar.web.app:app",
        host=cfg["host"],
        port=cfg["port"],
        reload=False,
    )


if __name__ == "__main__":
    main()