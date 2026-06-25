"""TrendRadar Web 应用入口 — FastAPI + JWT 鉴权 + Webhook 触发。"""

from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from trend_radar.config import get_config
from trend_radar.web.api import router
from trend_radar.web.auth import create_token, require_auth

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


# ===== Webhook 触发端点 (供 Hermes cron / 外部 HTTP 调用) =====

@app.post("/api/trigger/daily", response_class=JSONResponse)
async def trigger_daily(user: dict = Depends(require_auth)) -> dict:
    """手动触发日报流程。

    需要 Bearer token 鉴权。
    可通过 HTTP POST 请求触发:
    curl -X POST http://localhost:8088/api/trigger/daily \
         -H "Authorization: Bearer <token>"
    """
    import asyncio
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
async def trigger_weekly(user: dict = Depends(require_auth)) -> dict:
    """手动触发周报流程。需要 Bearer token 鉴权。"""
    import asyncio
    from trend_radar.scheduler import run_weekly

    try:
        result = await run_weekly()
        return {"status": "ok", "report": result[:200] if isinstance(result, str) else ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trigger/collect", response_class=JSONResponse)
async def trigger_collect(user: dict = Depends(require_auth)) -> dict:
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


# ===== Token 生成端点 =====

@app.get("/api/token/generate", response_class=JSONResponse)
async def generate_token() -> dict:
    """生成一个新的 JWT token (首次设置用)。

    安全提示: 这个端点不需要鉴权，建议在部署后关闭或改为需要管理员密码。
    生产环境请通过 CLI `python -m trend_radar.web.auth --generate` 获取 token。
    """
    token = create_token()
    return {"token": token, "hint": "请妥善保管此 token, 它用于访问 TrendRadar API。"}


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