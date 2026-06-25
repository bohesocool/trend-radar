"""采集器包初始化。"""

from trend_radar.collectors.base import BaseCollector
from trend_radar.collectors.github_trending import GitHubTrendingCollector
from trend_radar.collectors.hackernews import HackerNewsCollector
from trend_radar.collectors.reddit import RedditCollector
from trend_radar.collectors.arxiv_papers import ArxivCollector
from trend_radar.collectors.twitter_ai import TwitterAICollector

__all__ = [
    "BaseCollector",
    "GitHubTrendingCollector",
    "HackerNewsCollector",
    "RedditCollector",
    "ArxivCollector",
    "TwitterAICollector",
]
