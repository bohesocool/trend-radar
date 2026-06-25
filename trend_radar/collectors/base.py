"""采集器抽象基类。"""

from __future__ import annotations

import abc
from typing import Any

from trend_radar.models import TrendItem


class BaseCollector(abc.ABC):
    """所有数据采集器的抽象基类。"""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    @property
    @abc.abstractmethod
    def source_name(self) -> str:
        """数据源标识 (如 'github', 'hackernews')。"""

    @property
    def enabled(self) -> bool:
        return self.config.get("enabled", True)

    @abc.abstractmethod
    async def collect(self) -> list[TrendItem]:
        """执行采集，返回 TrendItem 列表。"""
        ...
