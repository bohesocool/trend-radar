"""FastAPI REST API 路由。"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from typing import Any

import markdown as md_lib
from markdown.extensions import Extension

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from trend_radar import db
from trend_radar.web.auth import require_auth


class _EscapeHtml(Extension):
    """移除 Markdown 的 raw-HTML 处理器，使原始 HTML 被转义而非透传。

    Python-Markdown 默认会原样保留 <script> 等标签（safe_mode 已废弃），
    上游文档推荐用此类删除 html_block 预处理器与 html 行内处理器来实现转义。
    """

    def extendMarkdown(self, md):
        md.preprocessors.deregister("html_block")
        md.inlinePatterns.deregister("html")


def markdown_to_html(md_text: str | None) -> str:
    """把 Markdown 文本渲染成安全 HTML（启用 fenced_code 与 tables 扩展）。

    通过 _EscapeHtml 扩展转义原始 HTML，因此不会产出 <script> 等可执行标签。
    用于详情页「完整项目文档」的在线预览。
    """
    if not md_text:
        return ""
    return md_lib.markdown(
        md_text,
        extensions=["fenced_code", "tables", "nl2br", _EscapeHtml()],
        output_format="html",
    )


router = APIRouter(prefix="/api")


class DeleteSuggestionsBody(BaseModel):
    ids: list[int]


class PinSuggestionBody(BaseModel):
    pinned: bool


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
            "pinned": bool(s.get("pinned")),
            "tech_stack": full.get("tech_stack", []),
            "estimated_stars": full.get("estimated_stars", ""),
            "difficulty": full.get("difficulty", ""),
            "timeline": full.get("timeline", ""),
            "key_features": full.get("key_features", []),
            "viral_hooks": full.get("viral_hooks", []),
            "similar_projects": full.get("similar_projects", []),
            "readme_strategy": full.get("readme_strategy", ""),
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


@router.get("/suggestion/{suggestion_id}")
def get_suggestion(suggestion_id: int) -> dict[str, Any]:
    """获取单个项目建议的完整数据（供详情页使用）。"""
    row = db.get_suggestion_by_id(suggestion_id)
    if not row:
        raise HTTPException(status_code=404, detail="无此建议")
    full = json.loads(row.get("full_data", "{}"))
    full["id"] = row["id"]
    full["date"] = row["date"]
    full["pinned"] = bool(row.get("pinned"))
    return full


@router.delete("/suggestions")
def delete_suggestions(body: DeleteSuggestionsBody, auth: bool = Depends(require_auth)) -> dict[str, int]:
    """批量删除项目建议（永久）。单个删除传单元素列表即可。"""
    deleted = db.delete_suggestions(body.ids)
    return {"deleted": deleted}


@router.post("/suggestion/{suggestion_id}/pin")
def pin_suggestion(
    suggestion_id: int, body: PinSuggestionBody, auth: bool = Depends(require_auth)
) -> dict[str, Any]:
    """设置/取消置顶。"""
    if not db.get_suggestion_by_id(suggestion_id):
        raise HTTPException(status_code=404, detail="无此建议")
    db.set_suggestion_pinned(suggestion_id, body.pinned)
    return {"id": suggestion_id, "pinned": body.pinned}


@router.post("/suggestion/{suggestion_id}/regenerate")
def regenerate_suggestion(suggestion_id: int, auth: bool = Depends(require_auth)) -> dict[str, Any]:
    """基于该建议所属日期的趋势分析，重新调 AI 生成一个新点子并替换当前卡（id/置顶保留）。"""
    from trend_radar.generator.suggestion_engine import generate_suggestions
    from trend_radar.models import HotTopic, Opportunity, TrendAnalysis

    row = db.get_suggestion_by_id(suggestion_id)
    if not row:
        raise HTTPException(status_code=404, detail="无此建议")

    date = row["date"]
    analysis_row = db.get_analysis_by_date(date)
    if not analysis_row:
        raise HTTPException(status_code=400, detail="该日期缺少趋势分析，无法重新生成")

    def _build(cls, d):
        # 仅保留 dataclass 已知字段，兼容历史数据的字段漂移
        fields = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in fields})

    hot_topics = [_build(HotTopic, d) for d in json.loads(analysis_row.get("hot_topics", "[]"))]
    opportunities = [_build(Opportunity, d) for d in json.loads(analysis_row.get("opportunities", "[]"))]
    analysis = TrendAnalysis(
        date=date,
        daily_summary=analysis_row.get("summary", ""),
        hot_topics=hot_topics,
        emerging_opportunities=opportunities,
        raw_items_count=analysis_row.get("raw_items_count", 0),
    )

    # 取回当天的原始采集数据，让重新生成也能拿到真实仓库/帖子参照
    raw_items = db.get_trend_items_by_date(date)

    try:
        generated = generate_suggestions(analysis, 1, raw_items=raw_items)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重新生成失败: {e}")
    if not generated:
        raise HTTPException(status_code=500, detail="重新生成失败：AI 未返回有效建议")

    s = generated[0]
    db.replace_suggestion(suggestion_id, s.name, s.tagline, s.category, s.description, s.__dict__)
    return {"id": suggestion_id, "name": s.name}


@router.post("/suggestion/{suggestion_id}/architecture")
def gen_suggestion_architecture(suggestion_id: int, auth: bool = Depends(require_auth)) -> dict[str, Any]:
    """按需生成架构与目录结构，存回 full_data 并返回。"""
    return _generate_and_store(suggestion_id, "architecture")


@router.post("/suggestion/{suggestion_id}/readme")
def gen_suggestion_readme(suggestion_id: int, auth: bool = Depends(require_auth)) -> dict[str, Any]:
    """按需生成 README 营销策略与命名建议，存回 full_data 并返回。"""
    return _generate_and_store(suggestion_id, "readme")


def _generate_and_store(suggestion_id: int, kind: str) -> dict[str, Any]:
    from trend_radar.generator.suggestion_engine import (
        _parse_suggestion,
        generate_architecture,
        generate_readme_strategy,
    )

    row = db.get_suggestion_by_id(suggestion_id)
    if not row:
        raise HTTPException(status_code=404, detail="无此建议")
    full = json.loads(row.get("full_data", "{}"))
    suggestion = _parse_suggestion(full)

    try:
        if kind == "architecture":
            generated = generate_architecture(suggestion)
        else:
            generated = generate_readme_strategy(suggestion)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成失败: {e}")

    full.update(generated)
    db.update_suggestion_full_data(suggestion_id, full)
    return generated


@router.get("/trends/{date}")
def get_trends_by_date(date: str, source: str | None = None) -> list[dict[str, Any]]:
    """获取指定日期的原始采集数据。可选按 source 过滤。"""
    items = db.get_trend_items_by_date(date)
    if source:
        items = [i for i in items if i.get("source") == source]
    return items


@router.get("/trends/{date}/summary")
def get_trends_summary(date: str) -> dict[str, Any]:
    """获取指定日期各数据源的条目计数（返回的是保留后的数量）。"""
    items = db.get_trend_items_by_date(date)
    counts: dict[str, int] = {}
    for item in items:
        src = item.get("source") or "unknown"
        counts[src] = counts.get(src, 0) + 1
    return {"date": date, "total": len(items), "sources": counts}


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