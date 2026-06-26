"""arXiv 采集器 — 获取 cs.AI/cs.CL/cs.LG 最新论文。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import feedparser
import httpx
from loguru import logger

from trend_radar.collectors.base import BaseCollector
from trend_radar.models import TrendItem

# arXiv API: http://export.arxiv.org/api/query
_ARXIV_API = "https://export.arxiv.org/api/query"


class ArxivCollector(BaseCollector):
    source_name = "arxiv"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.categories: list[str] = config.get("categories", ["cs.AI", "cs.CL", "cs.LG"])
        self.max_results: int = config.get("max_results", 30)

    async def collect(self) -> list[TrendItem]:
        items: list[TrendItem] = []
        cat_query = " OR ".join(f"cat:{c}" for c in self.categories)
        from urllib.parse import urlencode
        params = urlencode({
            "search_query": cat_query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": self.max_results,
        })
        url = f"{_ARXIV_API}?{params}"
        try:
            # 用 httpx 抓取(自带 certifi 证书)，再交给 feedparser 解析。
            # feedparser 自带的 urllib 在部分环境会 SSL 校验失败导致静默返回 0 条。
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
            feed = feedparser.parse(resp.content)
            for entry in feed.entries:
                # 提取摘要前 200 字
                abstract = entry.get("summary", "")
                tags = [t.get("term", "") for t in entry.get("tags", [])][:5]
                items.append(
                    TrendItem(
                        source=self.source_name,
                        title=entry.get("title", "").replace("\n", " ").strip(),
                        url=entry.get("id", ""),
                        description=abstract[:300],
                        tags=tags,
                        popularity=0,  # arXiv 没有 star/point，用 0 占位
                        language=None,
                        extra={
                            "authors": [a.get("name", "") for a in entry.get("authors", [])][:3],
                            "published": entry.get("published", ""),
                            "categories": [t.get("term", "") for t in entry.get("tags", [])],
                        },
                    )
                )
        except Exception as e:
            logger.warning(f"arXiv 采集失败: {e}")
        logger.info(f"arXiv: 采集到 {len(items)} 篇论文")
        return items
