"""GitHub 采集器 — 两路结合，聚焦「当天 / 近期 AI 涨星最多」。

1. Trending 页面 (github.com/trending)：提供真实的「今日涨星」(today_stars)，
   但只能按语言筛、不能按 AI 主题筛，所以采集后用 AI 关键词过滤。
2. Search API (api.github.com/search/repositories)：用 `topic:` + `created:>近N天`
   锁定「最近新建的 AI 仓库」，弥补 trending 无法按主题筛的缺陷。

排序口径统一为「日均涨星速度」(daily_rate)：
  - trending 仓库 = today_stars（真实当日增量）
  - search 仓库   = 总星数 / 仓库年龄天数（≈ 近期平均涨星速度，单位可比）
这样老牌大仓库不会因总星数高而霸榜，突出的是「当下正在涨」的项目。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from trend_radar.collectors.base import BaseCollector
from trend_radar.models import TrendItem

_SEARCH_API = "https://api.github.com/search/repositories"


class GitHubTrendingCollector(BaseCollector):
    source_name = "github"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.languages: list[str] = config.get("languages", [])
        self.since: str = config.get("since", "daily")
        self.ai_keywords: list[str] = [k.lower() for k in config.get("ai_keywords", [])]
        self.ai_only: bool = config.get("ai_only", True)
        # Search API 相关
        self.search_enabled: bool = config.get("search_enabled", True)
        self.search_queries: list[str] = config.get("search_queries", [])
        self.search_days: int = config.get("search_days", 30)
        self.search_limit: int = config.get("search_limit", 30)
        token = config.get("token") or ""
        # ${GITHUB_TOKEN} 未设置时 config 里会残留原样字符串，视为无 token
        self.token: str | None = None if (not token or token.startswith("${")) else token

    async def collect(self) -> list[TrendItem]:
        headers = {"Accept-Language": "en-US,en;q=0.9"}
        async with httpx.AsyncClient(timeout=30, headers=headers, follow_redirects=True) as client:
            trending = await self._collect_trending(client)
            search = await self._collect_search(client) if self.search_enabled else []

        # 以 trending 的 today_stars 校准同时出现在 search 里的仓库
        today_map = {it.title.lower(): it.extra.get("today_stars") for it in trending}

        merged: dict[str, TrendItem] = {}
        for it in trending:
            merged[it.title.lower()] = it
        for it in search:
            key = it.title.lower()
            if key in merged:
                continue  # trending 数据更准，优先保留
            ts = today_map.get(key)
            if ts:  # 同名仓库也在 trending 里 → 用真实今日涨星
                it.popularity = ts
                it.extra["daily_rate"] = ts
                it.extra["today_stars"] = ts
            merged[key] = it

        items = list(merged.values())
        items.sort(key=lambda x: x.popularity, reverse=True)
        logger.info(
            f"GitHub: 采集 {len(items)} 个仓库 "
            f"(trending={len(trending)}, search={len(search)}, ai_only={self.ai_only})"
        )
        return items

    # ---------- Trending ----------

    async def _collect_trending(self, client: httpx.AsyncClient) -> list[TrendItem]:
        items: list[TrendItem] = []
        langs = self.languages or [""]  # 空字符串 = 全语言
        for lang in langs:
            url = "https://github.com/trending"
            if lang:
                url += f"/{lang}"
            url += f"?since={self.since}"
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                items.extend(self._parse_trending_html(resp.text, lang or "all"))
            except Exception as e:
                logger.warning(f"GitHub Trending 采集失败 [{lang}]: {e}")
        # 按 AI 关键词过滤
        if self.ai_only and self.ai_keywords:
            items = [it for it in items if self._is_ai(it.title, it.description)]
        return items

    def _parse_trending_html(self, html: str, lang_label: str) -> list[TrendItem]:
        soup = BeautifulSoup(html, "lxml")
        items: list[TrendItem] = []
        for article in soup.select("article.Box-row"):
            h2 = article.select_one("h2 a")
            if not h2:
                continue
            repo_path = h2.get("href", "").strip("/")

            desc_el = article.select_one("p")
            description = desc_el.get_text(strip=True) if desc_el else ""

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

            today_stars = 0
            for div in article.select("div.f6"):
                m = re.search(r"([\d,]+)\s*stars?\s*today", div.get_text(strip=True))
                if m:
                    today_stars = int(m.group(1).replace(",", ""))

            items.append(
                TrendItem(
                    source=self.source_name,
                    title=repo_path,
                    url=f"https://github.com/{repo_path}",
                    description=description,
                    tags=self._extract_tags(repo_path, description),
                    popularity=today_stars,  # 排序口径：今日涨星
                    language=lang_in_repo or lang_label,
                    extra={
                        "forks": forks,
                        "total_stars": stars,
                        "today_stars": today_stars,
                        "daily_rate": today_stars,
                        "source_type": "trending",
                        "language_filter": lang_label,
                    },
                )
            )
        return items

    # ---------- Search API ----------

    async def _collect_search(self, client: httpx.AsyncClient) -> list[TrendItem]:
        if not self.search_queries:
            return []
        since_date = (datetime.now(timezone.utc) - timedelta(days=self.search_days)).strftime("%Y-%m-%d")
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        items: list[TrendItem] = []
        for base_q in self.search_queries:
            q = f"{base_q} created:>{since_date}"
            try:
                resp = await client.get(
                    _SEARCH_API,
                    params={"q": q, "sort": "stars", "order": "desc", "per_page": self.search_limit},
                    headers=headers,
                )
                resp.raise_for_status()
                for repo in resp.json().get("items", []):
                    item = self._parse_search_repo(repo)
                    if item:
                        items.append(item)
            except Exception as e:
                logger.warning(f"GitHub Search 采集失败 [{base_q}]: {e}")
        return items

    def _parse_search_repo(self, repo: dict[str, Any]) -> TrendItem | None:
        full_name = repo.get("full_name")
        if not full_name:
            return None
        stars = repo.get("stargazers_count", 0) or 0
        description = repo.get("description") or ""
        # 仓库年龄（天），用于换算近期平均涨星速度
        age_days = 1
        created = repo.get("created_at")
        if created:
            try:
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                age_days = max((datetime.now(timezone.utc) - created_dt).days, 1)
            except ValueError:
                pass
        daily_rate = round(stars / age_days)
        topics = repo.get("topics", []) or []
        return TrendItem(
            source=self.source_name,
            title=full_name,
            url=repo.get("html_url") or f"https://github.com/{full_name}",
            description=description,
            tags=self._extract_tags(full_name, description, topics),
            popularity=daily_rate,  # 排序口径：近期平均涨星速度
            language=repo.get("language"),
            extra={
                "forks": repo.get("forks_count", 0),
                "total_stars": stars,
                "today_stars": None,  # search 无法获知当日增量
                "daily_rate": daily_rate,
                "age_days": age_days,
                "source_type": "search",
                "topics": topics[:8],
            },
        )

    # ---------- helpers ----------

    def _is_ai(self, name: str, desc: str) -> bool:
        text = f"{name} {desc}".lower()
        return any(kw in text for kw in self.ai_keywords)

    @staticmethod
    def _parse_count(text: str) -> int:
        text = text.replace(",", "").replace("k", "000").strip()
        try:
            return int(float(text))
        except ValueError:
            return 0

    @staticmethod
    def _extract_tags(name: str, desc: str, topics: list[str] | None = None) -> list[str]:
        text = f"{name} {desc} {' '.join(topics or [])}".lower()
        keyword_map = {
            "ai": "AI", "llm": "LLM", "gpt": "GPT", "agent": "Agent", "rag": "RAG",
            "cli": "CLI", "web": "Web", "api": "API", "rust": "Rust", "python": "Python",
            "typescript": "TypeScript", "go ": "Go", "docker": "Docker", "k8s": "K8s",
            "game": "Game", "terminal": "Terminal", "automation": "Automation",
        }
        tags = [label for kw, label in keyword_map.items() if kw in text]
        return tags[:5]
