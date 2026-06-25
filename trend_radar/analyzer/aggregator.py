"""数据聚合器 — 合并多源数据、去重、计算热度分。"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from typing import Any

from trend_radar.models import TrendItem

# 数据源权重
_SOURCE_WEIGHTS = {
    "github": 1.0,
    "hackernews": 0.8,
    "reddit": 0.6,
    "twitter": 0.7,
    "arxiv": 0.5,
}


def calculate_heat_score(item: TrendItem) -> float:
    """计算单条数据的热度分。"""
    weight = _SOURCE_WEIGHTS.get(item.source, 0.5)
    popularity = item.popularity if item.popularity > 0 else 1
    return round(weight * math.log10(popularity + 10), 2)


def aggregate_by_topic(items: list[TrendItem]) -> list[dict[str, Any]]:
    """按 tag 聚合数据，返回每个 tag 的汇总信息。"""
    topic_map: dict[str, list[TrendItem]] = defaultdict(list)
    for item in items:
        for tag in item.tags:
            topic_map[tag].append(item)

    topics: list[dict[str, Any]] = []
    for tag, grouped in topic_map.items():
        if len(grouped) < 2:  # 至少两个源提到才算趋势
            continue
        total_heat = sum(calculate_heat_score(i) for i in grouped)
        sources = list({i.source for i in grouped})
        topics.append(
            {
                "tag": tag,
                "item_count": len(grouped),
                "source_count": len(sources),
                "sources": sources,
                "total_heat": round(total_heat, 2),
                "avg_heat": round(total_heat / len(grouped), 2),
                "top_items": [
                    {"title": i.title, "source": i.source, "popularity": i.popularity, "url": i.url}
                    for i in sorted(grouped, key=lambda x: x.popularity, reverse=True)[:3]
                ],
            }
        )
    topics.sort(key=lambda t: t["total_heat"], reverse=True)
    return topics


def format_items_for_llm(items: list[TrendItem]) -> str:
    """将采集数据格式化为 LLM 可读的文本。"""
    # 按数据源分组
    by_source: dict[str, list[TrendItem]] = defaultdict(list)
    for item in items:
        by_source[item.source].append(item)

    sections: list[str] = []
    source_labels = {
        "github": "GitHub Trending",
        "hackernews": "Hacker News",
        "reddit": "Reddit",
        "twitter": "Twitter/X AI",
        "arxiv": "arXiv 最新论文",
    }

    for source, label in source_labels.items():
        grouped = by_source.get(source, [])
        if not grouped:
            continue
        lines = [f"\n【{label}】"]
        for item in sorted(grouped, key=lambda x: x.popularity, reverse=True)[:20]:
            if source == "github":
                lines.append(
                    f"- {item.title}: {item.description} ⭐{item.popularity} lang={item.language}"
                )
            elif source == "hackernews":
                comments = item.extra.get("num_comments", 0)
                lines.append(
                    f"- {item.title}: {item.popularity} points | {comments} comments\n  {item.url}"
                )
            elif source == "reddit":
                sub = item.extra.get("subreddit", "")
                comments = item.extra.get("num_comments", 0)
                lines.append(
                    f"- [{sub}] {item.title}: {item.popularity} upvotes | {comments} comments"
                )
            elif source == "twitter":
                lines.append(f"- {item.title}")
            elif source == "arxiv":
                authors = ", ".join(item.extra.get("authors", []))
                lines.append(f"- {item.title}\n  Authors: {authors}\n  {item.description[:200]}")
        sections.append("\n".join(lines))

    return "\n".join(sections)