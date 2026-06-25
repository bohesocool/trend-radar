"""SQLite 数据库操作。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from trend_radar.config import get_project_root
from trend_radar.models import TrendItem

_DB_PATH = get_project_root() / "data" / "trend_radar.db"


def _get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """创建数据库表。"""
    with _get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS trends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT,
                description TEXT,
                tags TEXT,
                popularity INTEGER DEFAULT 0,
                language TEXT,
                extra TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                summary TEXT,
                hot_topics TEXT,
                opportunities TEXT,
                raw_items_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                name TEXT NOT NULL,
                tagline TEXT,
                category TEXT,
                description TEXT,
                full_data TEXT,
                scaffold_files TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_trends_date ON trends(date);
            CREATE INDEX IF NOT EXISTS idx_suggestions_date ON suggestions(date);
            """
        )


def save_trend_items(items: list[TrendItem], date_str: str | None = None) -> None:
    """批量保存采集到的 TrendItem。先删除同日期旧数据，避免重复。"""
    if not items:
        return
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    with _get_conn() as conn:
        # 先删除同日期旧数据，防止重复运行导致数据翻倍
        conn.execute("DELETE FROM trends WHERE date = ?", (date_str,))
        for item in items:
            conn.execute(
                """
                INSERT INTO trends (date, source, title, url, description, tags, popularity, language, extra)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    date_str,
                    item.source,
                    item.title,
                    item.url,
                    item.description,
                    json.dumps(item.tags, ensure_ascii=False),
                    item.popularity,
                    item.language,
                    json.dumps(item.extra, ensure_ascii=False),
                ),
            )


# 每个数据源最多保留的条目数
_SOURCE_LIMITS = {
    "github": 30,
    "hackernews": 10,
    "reddit": 10,
    "twitter": 10,
    "arxiv": 10,
}
_DEFAULT_LIMIT = 10


def get_trend_items_by_date(date_str: str) -> list[dict[str, Any]]:
    """读取指定日期的采集数据，每源按热度排序后只保留 Top-N。"""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trends WHERE date = ? ORDER BY popularity DESC",
            (date_str,),
        ).fetchall()
    all_items = [dict(r) for r in rows]

    # 每个数据源只保留前 N 条（已按 popularity DESC 排序）
    by_source: dict[str, list[dict[str, Any]]] = {}
    for item in all_items:
        src = item.get("source") or "unknown"
        by_source.setdefault(src, []).append(item)

    limited: list[dict[str, Any]] = []
    for src, items in by_source.items():
        limit = _SOURCE_LIMITS.get(src, _DEFAULT_LIMIT)
        limited.extend(items[:limit])

    # 全部重新按 popularity DESC 排序
    limited.sort(key=lambda x: x.get("popularity", 0), reverse=True)
    return limited


def save_analysis(date_str: str, summary: str, hot_topics: list, opportunities: list, raw_count: int) -> None:
    """保存 LLM 分析结果。"""
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO analyses (date, summary, hot_topics, opportunities, raw_items_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                date_str,
                summary,
                json.dumps(hot_topics, ensure_ascii=False),
                json.dumps(opportunities, ensure_ascii=False),
                raw_count,
            ),
        )


def save_suggestion(date_str: str, name: str, tagline: str, category: str, description: str, full_data: dict, scaffold_files: dict) -> None:
    """保存项目建议。"""
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO suggestions (date, name, tagline, category, description, full_data, scaffold_files)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                date_str,
                name,
                tagline,
                category,
                description,
                json.dumps(full_data, ensure_ascii=False),
                json.dumps(scaffold_files, ensure_ascii=False),
            ),
        )


def get_suggestions_by_date(date_str: str) -> list[dict[str, Any]]:
    """读取指定日期的项目建议。"""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM suggestions WHERE date = ? ORDER BY id",
            (date_str,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_suggestion_by_id(suggestion_id: int) -> dict[str, Any] | None:
    """按 id 读取单个项目建议。"""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM suggestions WHERE id = ?",
            (suggestion_id,),
        ).fetchone()
        return dict(row) if row else None


def update_suggestion_full_data(suggestion_id: int, full_data: dict) -> None:
    """覆盖更新某个建议的 full_data（用于详情页按需补充架构/README 等内容）。"""
    with _get_conn() as conn:
        conn.execute(
            "UPDATE suggestions SET full_data = ? WHERE id = ?",
            (json.dumps(full_data, ensure_ascii=False, default=str), suggestion_id),
        )


def get_analysis_by_date(date_str: str) -> dict[str, Any] | None:
    """读取指定日期的趋势分析。"""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM analyses WHERE date = ?",
            (date_str,),
        ).fetchone()
        return dict(row) if row else None


def list_dates_with_data() -> list[str]:
    """列出有数据的所有日期 (降序)。"""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT date FROM analyses ORDER BY date DESC"
        ).fetchall()
        return [r["date"] for r in rows]


def get_recent_summaries(limit: int = 7) -> list[dict[str, Any]]:
    """获取最近 N 天的摘要。"""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT date, summary, raw_items_count FROM analyses ORDER BY date DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
