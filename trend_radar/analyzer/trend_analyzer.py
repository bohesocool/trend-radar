"""趋势分析器 — 调用 LLM 生成趋势分析和项目建议。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from loguru import logger

from trend_radar.analyzer.aggregator import aggregate_by_topic, format_items_for_llm
from trend_radar.analyzer.llm_client import LLMClient
from trend_radar.models import HotTopic, Opportunity, TrendAnalysis, TrendItem

_SYSTEM_PROMPT = """你是一名 GitHub 趋势分析师和开源项目策略顾问。
你的目标是：根据多数据源的技术热点数据，分析当前趋势，并找到「值得现在做，能在 GitHub 上火起来」的开源项目机会。

分析原则：
1. 跨数据源关联：同一主题在 GitHub+HN+arXiv 同时出现 = 强趋势信号
2. 时机优先：新论文+新讨论+无成熟实现 = 最佳机会窗口
3. 可执行性：建议必须是 1-3 人小团队能在 1 周内做出 MVP 的
4. star 增长思维：CLI 工具 > Web 应用 > 库；有趣 > 有用

你必须严格按照要求的 JSON 格式回复，不要输出 JSON 以外的内容。"""


_USER_PROMPT_TEMPLATE = """以下是 {date} 采集到的技术热点数据：

{data}

请分析以上数据并输出以下 JSON：

```json
{{
  "daily_summary": "今日技术趋势概述（2-3句话，点出最值得关注的2-3个方向）",
  "hot_topics": [
    {{
      "topic": "主题名称",
      "heat_score": 1-100的整数,
      "trend": "rising 或 peak 或 sustained 或 cooling",
      "description": "为什么这个方向热（1-2句）",
      "evidence": ["GitHub:xxx项目", "HN:xxx帖子", "arXiv:xxx论文"],
      "languages": ["Python", "TypeScript"]
    }}
  ],
  "emerging_opportunities": [
    {{
      "gap": "当前缺少什么样的开源项目",
      "why_now": "为什么现在做时机最好（1-2句）",
      "potential_stars": "预估star范围，如 '500-2000 in 1 month'",
      "difficulty": "easy 或 medium 或 hard",
      "target_audience": "目标用户群体"
    }}
  ]
}}
```

要求：
- hot_topics: 3-8 个
- emerging_opportunities: 3-5 个
- heat_score 基于数据源数量和热度综合估算
- evidence 要引用具体的数据中的项目/帖子/论文"""


def analyze_trends(items: list[TrendItem], date_str: str | None = None) -> TrendAnalysis:
    """完整趋势分析流程。"""
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")

    if not items:
        logger.warning("无采集数据，跳过分析")
        return TrendAnalysis(date=date_str, daily_summary="今日无数据", raw_items_count=0)

    # 1. 聚合
    topics = aggregate_by_topic(items)
    logger.info(f"聚合出 {len(topics)} 个主题")

    # 2. 格式化数据给 LLM
    data_text = format_items_for_llm(items)

    # 3. 调用 LLM
    llm = LLMClient()
    user_prompt = _USER_PROMPT_TEMPLATE.format(date=date_str, data=data_text)
    logger.info("调用 LLM 进行趋势分析...")
    result = llm.chat_json(_SYSTEM_PROMPT, user_prompt)

    # 4. 解析结果
    analysis = _parse_analysis(result, date_str, len(items))
    logger.info(f"趋势分析完成: {len(analysis.hot_topics)} 热点, {len(analysis.emerging_opportunities)} 机会")
    return analysis


def _parse_analysis(data: dict[str, Any], date_str: str, raw_count: int) -> TrendAnalysis:
    hot_topics: list[HotTopic] = []
    for ht in data.get("hot_topics", []):
        hot_topics.append(
            HotTopic(
                topic=ht.get("topic", ""),
                heat_score=float(ht.get("heat_score", 50)),
                trend=ht.get("trend", "rising"),
                description=ht.get("description", ""),
                evidence=ht.get("evidence", []),
                languages=ht.get("languages", []),
            )
        )

    opportunities: list[Opportunity] = []
    for opp in data.get("emerging_opportunities", []):
        opportunities.append(
            Opportunity(
                gap=opp.get("gap", ""),
                why_now=opp.get("why_now", ""),
                potential_stars=opp.get("potential_stars", ""),
                difficulty=opp.get("difficulty", "medium"),
                target_audience=opp.get("target_audience", ""),
            )
        )

    return TrendAnalysis(
        date=date_str,
        daily_summary=data.get("daily_summary", ""),
        hot_topics=hot_topics,
        emerging_opportunities=opportunities,
        raw_items_count=raw_count,
    )