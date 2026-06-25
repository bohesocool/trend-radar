"""Hacker News 采集器 — 使用 HN Algolia API 搜索 AI 相关热门帖子。

注意: HN Algolia API 的 `points` 字段不支持 numericFilters 过滤，
所以用 search 端点获取结果后在客户端按 min_points 过滤。
"""

from __future__ import annotations

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

    async def collect(self) -> list[TrendItem]:
        items: list[TrendItem] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for kw in self.ai_keywords:
                try:
                    resp = await client.get(
                        f"{_API_BASE}/search",
                        params={
                            "query": kw,
                            "tags": "story",
                            "hitsPerPage": 20,
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
        logger.info(f"Hacker News: 采集到 {len(unique)} 个帖子 (去重后, min_points={self.min_points})")
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