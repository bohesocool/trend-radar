"""Reddit 采集器 — 抓取 r/MachineLearning 等子版热门帖子。

Reddit 的 .json 端点对服务器 IP 普遍返回 403，
所以改用 RSS feed (.rss) 作为主要采集方式，RSS 不会被封。
"""

from __future__ import annotations

from typing import Any

import feedparser
from loguru import logger

from trend_radar.collectors.base import BaseCollector
from trend_radar.models import TrendItem


class RedditCollector(BaseCollector):
    source_name = "reddit"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.subreddits: list[str] = config.get("subreddits", ["MachineLearning"])
        self.limit: int = config.get("limit", 25)

    async def collect(self) -> list[TrendItem]:
        items: list[TrendItem] = []
        for sub in self.subreddits:
            try:
                # 用 RSS feed 替代 .json (不会被 403)
                url = f"https://www.reddit.com/r/{sub}/.rss?limit={self.limit}"
                feed = feedparser.parse(url)
                for entry in feed.entries[: self.limit]:
                    # 解析 upvotes — RSS 里没有直接的 upvote 数，用 score 或默认 0
                    popularity = 0
                    # feedparser 可能解析出一些自定义标签
                    tags_list = [t.get("term", "") for t in entry.get("tags", [])][:5]

                    items.append(
                        TrendItem(
                            source=self.source_name,
                            title=entry.get("title", ""),
                            url=entry.get("link", ""),
                            description=entry.get("summary", "")[:200] if entry.get("summary") else "",
                            tags=tags_list or self._extract_tags(entry.get("title", "")),
                            popularity=popularity,
                            language=None,
                            extra={
                                "subreddit": sub,
                                "author": entry.get("author", ""),
                                "published": entry.get("published", ""),
                            },
                        )
                    )
            except Exception as e:
                logger.warning(f"Reddit 采集失败 [r/{sub}]: {e}")
        logger.info(f"Reddit: 采集到 {len(items)} 个帖子")
        return items

    @staticmethod
    def _extract_tags(title: str) -> list[str]:
        text = title.lower()
        tags = []
        for kw, label in [
            ("ai", "AI"), ("llm", "LLM"), ("gpt", "GPT"), ("agent", "Agent"),
            ("model", "Model"), ("training", "Training"), ("dataset", "Dataset"),
            ("benchmark", "Benchmark"), ("open source", "OpenSource"),
        ]:
            if kw in text:
                tags.append(label)
        return tags[:5]