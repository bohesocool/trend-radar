"""Hacker News 采集器 — 使用 HN Algolia API 搜索 AI 相关近期帖子。

用 `/search_by_date` 端点 + `numericFilters=created_at_i>...` 锁定最近的时间窗
(默认近 24 小时)，避免 `/search` 按相关度返回历史高分老帖。
points 字段不支持服务端过滤，所以在客户端按 min_points 过滤。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from loguru import logger

from trend_radar.collectors.base import BaseCollector
from trend_radar.models import TrendItem

_API_BASE = "https://hn.algolia.com/api/v1"


class HackerNewsCollector(BaseCollector):
    source_name = "hackernews"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.min_points: int = config.get("min_points", 100)
        self.ai_keywords: list[str] = config.get("ai_keywords", [])
        self.window_hours: int = config.get("window_hours", 24)

    async def collect(self) -> list[TrendItem]:
        items: list[TrendItem] = []
        since_ts = int((datetime.now(timezone.utc) - timedelta(hours=self.window_hours)).timestamp())
        async with httpx.AsyncClient(timeout=30) as client:
            for kw in self.ai_keywords:
                try:
                    resp = await client.get(
                        f"{_API_BASE}/search_by_date",
                        params={
                            "query": kw,
                            "tags": "story",
                            "numericFilters": f"created_at_i>{since_ts}",
                            "hitsPerPage": 50,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    for hit in data.get("hits", []):
                        points = hit.get("points", 0) or 0
                        if points < self.min_points:
                            continue  # 客户端过滤
                        items.append(
                            TrendItem(
                                source=self.source_name,
                                title=hit.get("title", ""),
                                url=hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}",
                                description=hit.get("story_text", "")[:200] if hit.get("story_text") else "",
                                tags=self._extract_tags(hit.get("title", "")),
                                popularity=points,
                                language=None,
                                extra={
                                    "hn_id": hit.get("objectID"),
                                    "num_comments": hit.get("num_comments", 0),
                                    "author": hit.get("author"),
                                    "keyword": kw,
                                },
                            )
                        )
                except Exception as e:
                    logger.warning(f"HN 采集失败 [{kw}]: {e}")

        # 去重 (同一帖子可能被多个关键词命中)
        seen: set[str] = set()
        unique: list[TrendItem] = []
        for item in items:
            if item.url not in seen:
                seen.add(item.url)
                unique.append(item)
        logger.info(
            f"Hacker News: 采集到 {len(unique)} 个帖子 "
            f"(去重后, min_points={self.min_points}, 近{self.window_hours}h)"
        )
        return unique

    @staticmethod
    def _extract_tags(title: str) -> list[str]:
        text = title.lower()
        tags = []
        for kw, label in [
            ("ai", "AI"), ("llm", "LLM"), ("gpt", "GPT"), ("agent", "Agent"),
            ("model", "Model"), ("transformer", "Transformer"), ("diffusion", "Diffusion"),
            ("rag", "RAG"), ("fine-tune", "Fine-tune"), ("embedding", "Embedding"),
        ]:
            if kw in text:
                tags.append(label)
        return tags[:5]