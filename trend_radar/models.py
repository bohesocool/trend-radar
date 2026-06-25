"""数据模型定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class TrendItem:
    """从各数据源采集到的统一数据格式。"""

    source: str  # "github" / "hackernews" / "reddit" / "twitter" / "arxiv"
    title: str
    url: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    popularity: int = 0  # star / points / upvotes
    language: str | None = None  # 仅 github
    extra: dict[str, Any] = field(default_factory=dict)
    collected_at: datetime = field(default_factory=datetime.now)


@dataclass
class HotTopic:
    """LLM 分析出的热点主题。"""

    topic: str
    heat_score: float  # 1-100
    trend: str  # rising / peak / sustained / cooling
    description: str
    detailed_analysis: str = ""
    evidence: list[str] = field(default_factory=list)
    key_insights: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)


@dataclass
class Opportunity:
    """LLM 分析出的新兴机会。"""

    gap: str
    why_now: str
    potential_stars: str
    difficulty: str  # easy / medium / hard
    target_audience: str


@dataclass
class TrendAnalysis:
    """一次完整的趋势分析结果。"""

    date: str  # YYYY-MM-DD
    daily_summary: str
    hot_topics: list[HotTopic] = field(default_factory=list)
    emerging_opportunities: list[Opportunity] = field(default_factory=list)
    raw_items_count: int = 0


@dataclass
class ProjectSuggestion:
    """一个具体的项目建议。"""

    name: str
    tagline: str
    category: str  # cli / web / library / bot / tool
    description: str

    # 市场分析
    target_audience: str = ""
    similar_projects: list[dict[str, Any]] = field(default_factory=list)
    estimated_stars: str = ""
    viral_hooks: list[str] = field(default_factory=list)

    # 技术方案
    tech_stack: list[str] = field(default_factory=list)
    key_features: list[str] = field(default_factory=list)
    architecture: str = ""

    # 执行计划
    mvp_features: list[str] = field(default_factory=list)
    timeline: str = ""
    difficulty: str = "medium"

    # GitHub 优化
    repo_structure: str = ""
    readme_strategy: str = ""
    naming_tips: str = ""


@dataclass
class DailyReport:
    """一份日报。"""

    date: str
    analysis: TrendAnalysis
    suggestions: list[ProjectSuggestion]
    markdown: str = ""
