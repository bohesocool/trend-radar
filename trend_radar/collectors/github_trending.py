"""GitHub Trending 采集器 — 爬取 github.com/trending 页面。"""

from __future__ import annotations

import re
from typing import Any

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from trend_radar.collectors.base import BaseCollector
from trend_radar.models import TrendItem


class GitHubTrendingCollector(BaseCollector):
    source_name = "github"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.languages: list[str] = config.get("languages", [])
        self.since: str = config.get("since", "daily")

    async def collect(self) -> list[TrendItem]:
        items: list[TrendItem] = []
        langs = self.languages or [""]  # 空字符串 = 全语言
        async with httpx.AsyncClient(
            timeout=30,
            headers={"Accept-Language": "en-US,en;q=0.9"},
            follow_redirects=True,
        ) as client:
            for lang in langs:
                url = "https://github.com/trending"
                if lang:
                    url += f"/{lang}"
                url += f"?since={self.since}"
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    items.extend(self._parse_html(resp.text, lang or "all"))
                except Exception as e:
                    logger.warning(f"GitHub Trending 采集失败 [{lang}]: {e}")
        logger.info(f"GitHub Trending: 采集到 {len(items)} 个仓库")
        return items

    def _parse_html(self, html: str, lang_label: str) -> list[TrendItem]:
        soup = BeautifulSoup(html, "lxml")
        items: list[TrendItem] = []
        for article in soup.select("article.Box-row"):
            h2 = article.select_one("h2 a")
            if not h2:
                continue
            repo_path = h2.get("href", "").strip("/")
            name = repo_path.split("/")[-1] if "/" in repo_path else repo_path

            desc_el = article.select_one("p")
            description = desc_el.get_text(strip=True) if desc_el else ""

            # star / fork
            stars = 0
            forks = 0
            lang_in_repo = None
            for link in article.select("a.Link"):
                href = link.get("href", "")
                if href.endswith("/stargazers"):
                    stars = self._parse_count(link.get_text(strip=True))
                elif href.endswith("/forks"):
                    forks = self._parse_count(link.get_text(strip=True))

            lang_span = article.select_one("[itemprop='programmingLanguage']")
            if lang_span:
                lang_in_repo = lang_span.get_text(strip=True)

            # 今日新增 star
            today_stars = 0
            last_div = article.select("div.f6")
            for div in last_div:
                text = div.get_text(strip=True)
                m = re.search(r"(\d+)\s*stars?\s*today", text)
                if m:
                    today_stars = int(m.group(1))

            items.append(
                TrendItem(
                    source=self.source_name,
                    title=repo_path,
                    url=f"https://github.com/{repo_path}",
                    description=description,
                    tags=self._extract_tags(name, description),
                    popularity=stars,
                    language=lang_in_repo or lang_label,
                    extra={
                        "forks": forks,
                        "today_stars": today_stars,
                        "language_filter": lang_label,
                    },
                )
            )
        return items

    @staticmethod
    def _parse_count(text: str) -> int:
        text = text.replace(",", "").replace("k", "000").strip()
        try:
            return int(float(text))
        except ValueError:
            return 0

    @staticmethod
    def _extract_tags(name: str, desc: str) -> list[str]:
        text = f"{name} {desc}".lower()
        keyword_map = {
            "ai": "AI",
            "llm": "LLM",
            "gpt": "GPT",
            "agent": "Agent",
            "rag": "RAG",
            "cli": "CLI",
            "web": "Web",
            "api": "API",
            "rust": "Rust",
            "python": "Python",
            "typescript": "TypeScript",
            "go ": "Go",
            "docker": "Docker",
            "k8s": "K8s",
            "game": "Game",
            "terminal": "Terminal",
            "automation": "Automation",
        }
        tags = []
        for kw, label in keyword_map.items():
            if kw in text:
                tags.append(label)
        return tags[:5]
