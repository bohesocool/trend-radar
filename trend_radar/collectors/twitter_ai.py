"""Twitter/X AI 领域大V动态采集器。

由于 Twitter API 收费且限制严格，Nitter 公共实例已基本失效，
这里使用 RSS 桥接服务 (RSSHub) 作为备选方案。

可用方案：
1. RSSHub 公共实例: https://rsshub.app/twitter/user/{username}
2. 自建 RSSHub: 配置 twitter.rsshub_base
3. Twitter API v2 (需要 Bearer token, 收费)

如果所有方案都不可用，返回空列表（不影响其他采集器运行）。
"""

from __future__ import annotations

from typing import Any

import feedparser
from loguru import logger

from trend_radar.collectors.base import BaseCollector
from trend_radar.models import TrendItem

# RSSHub 公共实例 (可用性不稳定，逐个尝试)
_RSSHUB_INSTANCES = [
    "https://rsshub.app",
    "https://rss.shab.fun",
    "https://rsshub.rssforever.com",
]


class TwitterAICollector(BaseCollector):
    source_name = "twitter"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.accounts: list[str] = config.get("accounts", [])
        self.method: str = config.get("method", "rsshub")
        self.custom_rsshub: str | None = config.get("rsshub_base")

    async def collect(self) -> list[TrendItem]:
        if not self.accounts:
            return []
        items: list[TrendItem] = []

        # 优先使用自定义 RSSHub
        bases = [self.custom_rsshub] if self.custom_rsshub else _RSSHUB_INSTANCES

        for account in self.accounts:
            handle = account.lstrip("@")
            for base in bases:
                if not base:
                    continue
                url = f"{base}/twitter/user/{handle}"
                try:
                    feed = feedparser.parse(url)
                    if feed.entries:
                        for entry in feed.entries[:5]:
                            content = entry.get("summary", "") or entry.get("title", "")
                            # 去除 HTML 标签
                            import re
                            content = re.sub(r"<[^>]+>", "", content).strip()
                            items.append(
                                TrendItem(
                                    source=self.source_name,
                                    title=f"@{handle}: {content[:80]}",
                                    url=entry.get("link", f"https://x.com/{handle}"),
                                    description=content[:300],
                                    tags=self._extract_tags(content),
                                    popularity=0,  # RSSHub 不提供点赞数
                                    language=None,
                                    extra={
                                        "author": handle,
                                        "method": "rsshub",
                                        "published": entry.get("published", ""),
                                    },
                                )
                            )
                        break  # 成功获取就不再尝试下一个实例
                except Exception:
                    continue

        logger.info(f"Twitter/X: 采集到 {len(items)} 条动态")
        if not items:
            logger.warning(
                "Twitter/X 采集为空 — Nitter 已失效，请配置自建 RSSHub "
                "(twitter.rsshub_base) 或使用 Twitter API v2"
            )
        return items

    @staticmethod
    def _extract_tags(text: str) -> list[str]:
        text_lower = text.lower()
        tags = []
        for kw, label in [
            ("ai", "AI"), ("llm", "LLM"), ("gpt", "GPT"), ("agent", "Agent"),
            ("model", "Model"), ("release", "Release"), ("open source", "OpenSource"),
            ("benchmark", "Benchmark"), ("scaling", "Scaling"),
        ]:
            if kw in text_lower:
                tags.append(label)
        return tags[:5]