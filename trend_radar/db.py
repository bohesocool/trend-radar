"""SQLite 数据库操作。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
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
                pinned INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                expire TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_trends_date ON trends(date);
            CREATE INDEX IF NOT EXISTS idx_suggestions_date ON suggestions(date);
            CREATE INDEX IF NOT EXISTS idx_sessions_expire ON sessions(expire);
            """
        )
        # 旧库迁移：补 pinned 列
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(suggestions)").fetchall()}
        if "pinned" not in cols:
            conn.execute("ALTER TABLE suggestions ADD COLUMN pinned INTEGER DEFAULT 0")


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


def get_seen_urls(before_date: str, days: int = 7) -> set[str]:
    """返回 before_date 之前 days 天内已出现过的 url 集合，用于新鲜度(NEW)判断。"""
    try:
        start = (datetime.strptime(before_date, "%Y-%m-%d") - timedelta(days=days)).strftime("%Y-%m-%d")
    except ValueError:
        return set()
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT url FROM trends WHERE date < ? AND date >= ? AND url IS NOT NULL",
            (before_date, start),
        ).fetchall()
    return {r["url"] for r in rows}


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
    """读取指定日期的采集数据，每源按热度排序后只保留 Top-N。

    排序口径：NEW(首次出现) 优先，其次按 popularity 降序。
    并把 extra 里的 is_new / total_stars / daily_rate 提升到顶层，方便前端展示。
    """
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trends WHERE date = ?",
            (date_str,),
        ).fetchall()
    all_items = [dict(r) for r in rows]

    for item in all_items:
        try:
            extra = json.loads(item.get("extra") or "{}")
        except (json.JSONDecodeError, TypeError):
            extra = {}
        item["is_new"] = bool(extra.get("is_new"))
        if extra.get("total_stars") is not None:
            item["total_stars"] = extra["total_stars"]
        if extra.get("daily_rate") is not None:
            item["daily_rate"] = extra["daily_rate"]

    def _sort_key(x: dict[str, Any]) -> tuple[int, int]:
        return (1 if x.get("is_new") else 0, x.get("popularity", 0) or 0)

    # 每个数据源只保留前 N 条（NEW 优先，再按 popularity）
    by_source: dict[str, list[dict[str, Any]]] = {}
    for item in all_items:
        src = item.get("source") or "unknown"
        by_source.setdefault(src, []).append(item)

    limited: list[dict[str, Any]] = []
    for src, items in by_source.items():
        items.sort(key=_sort_key, reverse=True)
        limit = _SOURCE_LIMITS.get(src, _DEFAULT_LIMIT)
        limited.extend(items[:limit])

    limited.sort(key=_sort_key, reverse=True)
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


def save_suggestion(date_str: str, name: str, tagline: str, category: str, description: str, full_data: dict) -> None:
    """保存项目建议。同一天多次运行日报时累积追加——每批 LLM 产出不同点子，前端可择优。"""
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO suggestions (date, name, tagline, category, description, full_data)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                date_str,
                name,
                tagline,
                category,
                description,
                json.dumps(full_data, ensure_ascii=False),
            ),
        )


def get_suggestions_by_date(date_str: str) -> list[dict[str, Any]]:
    """读取指定日期的项目建议。置顶项排在最前。"""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM suggestions WHERE date = ? ORDER BY pinned DESC, id",
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
    """合并更新某个建议的 full_data（用于详情页按需补充架构/README 等内容）。"""
    row = get_suggestion_by_id(suggestion_id)
    latest: dict[str, Any] = {}
    if row:
        try:
            latest = json.loads(row.get("full_data") or "{}")
        except (json.JSONDecodeError, TypeError):
            latest = {}
    latest.update(full_data)

    with _get_conn() as conn:
        conn.execute(
            "UPDATE suggestions SET full_data = ? WHERE id = ?",
            (json.dumps(latest, ensure_ascii=False, default=str), suggestion_id),
        )


def delete_suggestions(ids: list[int]) -> int:
    """批量删除项目建议（永久）。返回实际删除的行数。"""
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    with _get_conn() as conn:
        cur = conn.execute(
            f"DELETE FROM suggestions WHERE id IN ({placeholders})",
            tuple(ids),
        )
        return cur.rowcount


def set_suggestion_pinned(suggestion_id: int, pinned: bool) -> None:
    """设置某个建议的置顶状态。"""
    with _get_conn() as conn:
        conn.execute(
            "UPDATE suggestions SET pinned = ? WHERE id = ?",
            (1 if pinned else 0, suggestion_id),
        )


def replace_suggestion(
    suggestion_id: int, name: str, tagline: str, category: str, description: str, full_data: dict
) -> None:
    """用新内容替换某个建议（重新生成时用）。保留 id、date、pinned 不变。"""
    with _get_conn() as conn:
        conn.execute(
            """
            UPDATE suggestions
            SET name = ?, tagline = ?, category = ?, description = ?, full_data = ?
            WHERE id = ?
            """,
            (
                name,
                tagline,
                category,
                description,
                json.dumps(full_data, ensure_ascii=False, default=str),
                suggestion_id,
            ),
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


# ===== Session 持久化 =====
# 把登录 token 存进 SQLite，容器/进程重启后仍有效，避免用户被反复踢回登录页。

def save_session(token: str, expire_ts: float) -> None:
    """写入（或刷新）一个 session token 及其过期时间戳（unix 秒）。"""
    with _get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sessions (token, expire) VALUES (?, ?)",
            (token, datetime.utcfromtimestamp(expire_ts).strftime("%Y-%m-%dT%H:%M:%SZ")),
        )


def get_session_expire(token: str) -> float | None:
    """返回 token 的过期时间戳（unix 秒）；不存在则 None。"""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT expire FROM sessions WHERE token = ?", (token,)
        ).fetchone()
    if not row:
        return None
    try:
        return datetime.strptime(row["expire"], "%Y-%m-%dT%H:%M:%SZ").timestamp()
    except (ValueError, TypeError):
        return None


def delete_session(token: str) -> None:
    """删除单个 session（登出用）。"""
    with _get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def cleanup_expired_sessions(now_ts: float) -> None:
    """删除已过期的 session。"""
    cutoff = datetime.utcfromtimestamp(now_ts).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE expire < ?", (cutoff,))
