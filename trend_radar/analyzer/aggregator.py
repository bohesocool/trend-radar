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
                total = item.extra.get("total_stars", item.popularity)
                rate = item.extra.get("daily_rate", item.popularity)
                new = " 🆕" if item.extra.get("is_new") else ""
                lines.append(
                    f"- {item.title}{new}: {item.description} ⭐{total} (+{rate}/天) lang={item.language}"
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


def format_topics_for_llm(topics: list[dict[str, Any]]) -> str:
    """将跨源聚合的主题格式化为 LLM 可读文本。

    aggregate_by_topic 把"同一 tag 被几个源、几条同时提到"算成了强趋势信号；
    这里把它转成文本喂给 LLM，省得模型从扁平明细里自己重猜跨源关联。
    """
    if not topics:
        return ""
    lines = []
    for t in topics[:15]:  # 限 15 个，避免 prompt 过长
        sources = "+".join(t.get("sources", []))
        lines.append(
            f"- [{t['tag']}] {t['source_count']}源({sources}) 热度{t['total_heat']} 共{t['item_count']}条"
        )
        for it in t.get("top_items", [])[:3]:
            lines.append(f"    · {it['title']} ({it['source']}, 热度{it['popularity']})")
    return "\n".join(lines)