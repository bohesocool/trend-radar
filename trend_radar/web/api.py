"""FastAPI REST API 路由。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from trend_radar import db
from trend_radar.config import get_project_root

router = APIRouter(prefix="/api")


@router.get("/latest")
def get_latest_report() -> dict[str, Any]:
    """获取最新日报数据。"""
    dates = db.list_dates_with_data()
    if not dates:
        return {"date": None, "summary": "", "hot_topics": [], "suggestions": [], "opportunities": []}

    latest = dates[0]
    return get_report_by_date(latest)


@router.get("/report/{date}")
def get_report_by_date(date: str) -> dict[str, Any]:
    """获取指定日期的日报数据。"""
    analysis = db.get_analysis_by_date(date)
    if not analysis:
        raise HTTPException(status_code=404, detail="无此日期报告")

    hot_topics = json.loads(analysis.get("hot_topics", "[]"))
    opportunities = json.loads(analysis.get("opportunities", "[]"))

    suggestions_raw = db.get_suggestions_by_date(date)
    suggestions = []
    for s in suggestions_raw:
        full = json.loads(s.get("full_data", "{}"))
        suggestions.append({
            "id": s["id"],
            "name": s["name"],
            "tagline": s["tagline"],
            "category": s["category"],
            "description": s["description"],
            "tech_stack": full.get("tech_stack", []),
            "estimated_stars": full.get("estimated_stars", ""),
            "difficulty": full.get("difficulty", ""),
            "timeline": full.get("timeline", ""),
            "key_features": full.get("key_features", []),
            "viral_hooks": full.get("viral_hooks", []),
            "similar_projects": full.get("similar_projects", []),
            "readme_strategy": full.get("readme_strategy", ""),
            "has_scaffold": bool(s.get("scaffold_files")),
        })

    return {
        "date": date,
        "summary": analysis.get("summary", ""),
        "raw_items_count": analysis.get("raw_items_count", 0),
        "hot_topics": hot_topics,
        "opportunities": opportunities,
        "suggestions": suggestions,
    }


@router.get("/dates")
def list_dates() -> list[str]:
    """列出有报告的所有日期。"""
    return db.list_dates_with_data()


@router.get("/trends/{date}")
def get_trends_by_date(date: str) -> list[dict[str, Any]]:
    """获取指定日期的原始采集数据。"""
    return db.get_trend_items_by_date(date)


@router.get("/scaffold/{date}/{name}/{filename}", response_class=PlainTextResponse)
def get_scaffold_file(date: str, name: str, filename: str) -> str:
    """下载脚手架文件。"""
    path = get_project_root() / "data" / "reports" / date / "scaffolds" / name / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return path.read_text(encoding="utf-8")


@router.get("/scaffold-files/{date}/{name}")
def list_scaffold_files(date: str, name: str) -> list[str]:
    """列出一个项目脚手架的所有文件。"""
    base = get_project_root() / "data" / "reports" / date / "scaffolds" / name
    if not base.exists():
        return []
    return [f.name for f in base.rglob("*") if f.is_file()]


@router.get("/stats")
def get_overall_stats() -> dict[str, Any]:
    """全局统计。"""
    dates = db.list_dates_with_data()
    recent = db.get_recent_summaries(limit=7)
    return {
        "total_reports": len(dates),
        "latest_date": dates[0] if dates else None,
        "recent_summaries": recent,
    }


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "timestamp": datetime.now().isoformat()}