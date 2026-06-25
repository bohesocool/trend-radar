"""项目建议生成引擎 — 基于趋势分析生成具体可执行的项目建议。

分两层：
1. generate_suggestions(): 轻量报告，只产出基础+市场+技术分析（不含脚手架/详细架构），
   JSON 短，几乎不会因截断而失败。用于日报主流程。
2. generate_architecture() / generate_readme_strategy(): 按需在详情页点按钮时单独调用，
   各自一个聚焦 prompt，生成更重的内容。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from loguru import logger

from trend_radar.analyzer.llm_client import LLMClient
from trend_radar.models import Opportunity, ProjectSuggestion, TrendAnalysis

_SYSTEM_PROMPT = """你是一名开源项目创业顾问，擅长找到「能在 GitHub 上病毒式传播」的项目方向。
你的目标是：基于趋势分析结果，生成具体、可执行、有差异化的项目建议。

每个建议必须包含：
1. 吸引人的项目名和 tagline
2. 与现有项目的差异化分析
3. 具体技术方案 (tech stack + 核心功能)
4. MVP 功能和时间线

GitHub star 增长策略：
- 命名：短小好记 ≤15字符，能直觉暗示功能
- 时机：蹭热点论文 (arXiv <7天)，补空白 (有讨论无实现)，跨界组合
- 病毒因子：CLI > Web > 库；视觉冲击力；低门槛 (一行命令能用)；有趣 > 有用

必须严格按照 JSON 格式回复。"""

_USER_PROMPT_TEMPLATE = """基于以下 {date} 的趋势分析结果，生成 1 个具体的项目建议。

【趋势概述】
{summary}

【热点主题】
{hot_topics}

【新兴机会】
{opportunities}

请输出 JSON（只包含 1 个建议）：
```json
{{
  "suggestions": [
    {{
      "name": "项目名 (英文,小写,连字符)",
      "tagline": "一句话亮点",
      "category": "cli 或 web 或 library 或 bot 或 tool",
      "description": "详细描述(200字以内)",
      "target_audience": "目标用户群体",
      "similar_projects": [
        {{"name": "项目名", "stars": "约多少star", "our_advantage": "我们的差异化优势"}}
      ],
      "estimated_stars": "预估star范围",
      "viral_hooks": ["病毒传播因素1", "因素2"],
      "tech_stack": ["Python", "Click", "httpx"],
      "key_features": ["核心功能1", "功能2", "功能3"],
      "mvp_features": ["MVP该做的功能1", "功能2"],
      "timeline": "2-3天可出MVP",
      "difficulty": "easy 或 medium 或 hard"
    }}
  ]
}}
```

要求：
- 只生成 1 个建议
- 这是一份轻量报告，不要输出脚手架代码、目录结构或 README 文案（这些会在详情页按需生成）
- 项目名要检查不会与知名项目重名
- {index_hint}"""


def generate_suggestions(analysis: TrendAnalysis, n: int = 5) -> list[ProjectSuggestion]:
    """基于趋势分析生成轻量项目建议。每次只生成 1 个，循环调用 N 次以提高成功率。"""
    if not analysis.hot_topics and not analysis.emerging_opportunities:
        logger.warning("无趋势数据，跳过建议生成")
        return []

    hot_topics_text = "\n".join(
        f"- {ht.topic} (热度:{ht.heat_score}, 趋势:{ht.trend}): {ht.description}"
        for ht in analysis.hot_topics
    )
    opportunities_text = "\n".join(
        f"- [opp.difficulty] {opp.gap} → {opp.why_now} (预估star: {opp.potential_stars})"
        for opp in analysis.emerging_opportunities
    )

    llm = LLMClient()
    suggestions: list[ProjectSuggestion] = []
    used_names: set[str] = set()
    used_categories: set[str] = set()

    for i in range(n):
        # Build index hint to encourage variety
        index_hint = f"这是第 {i+1}/{n} 个建议，请选择不同的方向"
        if used_names:
            index_hint += f"，避免与已生成的项目重复: {', '.join(list(used_names)[:5])}"
        if used_categories:
            index_hint += f"，尝试不同于已使用的分类: {', '.join(used_categories)}"
        if i > 0:
            index_hint += "，优先选择 trending=rising 的主题"

        user_prompt = _USER_PROMPT_TEMPLATE.format(
            date=analysis.date,
            summary=analysis.daily_summary,
            hot_topics=hot_topics_text,
            opportunities=opportunities_text,
            index_hint=index_hint,
        )

        logger.info(f"调用 LLM 生成第 {i+1}/{n} 个项目建议...")
        try:
            result = llm.chat_json(_SYSTEM_PROMPT, user_prompt)
            s_list = result.get("suggestions", [])
            if not s_list:
                logger.warning(f"第 {i+1} 个建议: LLM 返回空 suggestions 列表")
                continue
            s_data = s_list[0]
            suggestion = _parse_suggestion(s_data)
            if suggestion.name in used_names:
                logger.warning(f"第 {i+1} 个建议: 项目名 '{suggestion.name}' 已存在，跳过")
                continue
            used_names.add(suggestion.name)
            used_categories.add(suggestion.category)
            suggestions.append(suggestion)
            logger.info(f"第 {i+1} 个建议生成成功: {suggestion.name}")
        except Exception as e:
            logger.error(f"第 {i+1} 个建议生成失败: {e}")
            continue

    # 如果全部失败，至少重试 3 次确保出 1 个
    if not suggestions:
        logger.warning("所有建议生成失败，启动兜底重试...")
        for retry_i in range(3):
            logger.info(f"兜底重试第 {retry_i+1}/3 次...")
            try:
                retry_hint = "这是最后一次机会，请务必生成一个高质量的项目建议"
                retry_prompt = _USER_PROMPT_TEMPLATE.format(
                    date=analysis.date,
                    summary=analysis.daily_summary,
                    hot_topics=hot_topics_text,
                    opportunities=opportunities_text,
                    index_hint=retry_hint,
                )
                result = llm.chat_json(_SYSTEM_PROMPT, retry_prompt)
                s_list = result.get("suggestions", [])
                if s_list:
                    suggestion = _parse_suggestion(s_list[0])
                    suggestions.append(suggestion)
                    logger.info(f"兜底重试成功: {suggestion.name}")
                    break
            except Exception as e:
                logger.error(f"兜底重试第 {retry_i+1} 次失败: {e}")
                continue

    logger.info(f"共生成 {len(suggestions)}/{n} 个项目建议")
    return suggestions


# ===== 按需生成（详情页点按钮时调用） =====

_ARCH_SYSTEM_PROMPT = """你是一名资深软件架构师。基于给定的项目建议，输出清晰、可落地的技术架构与目录结构。
必须严格按照 JSON 格式回复。"""

_ARCH_USER_TEMPLATE = """为以下项目设计架构与目录结构：

项目名: {name}
一句话: {tagline}
分类: {category}
描述: {description}
技术栈: {tech_stack}
核心功能: {key_features}

请输出 JSON：
```json
{{
  "architecture": "详细架构说明：模块划分、数据流、关键技术选型与理由（300字以内，可用换行）",
  "repo_structure": "推荐目录结构，用 markdown 代码块形式的目录树，并对关键文件加一行注释"
}}
```
要求：架构要具体到模块和数据流，目录结构要可直接照着建。"""


_README_SYSTEM_PROMPT = """你是一名擅长开源项目营销的增长顾问。基于给定的项目建议，输出能驱动 GitHub star 增长的 README 策略与命名建议。
必须严格按照 JSON 格式回复。"""

_README_USER_TEMPLATE = """为以下项目设计 README 营销策略与命名建议：

项目名: {name}
一句话: {tagline}
分类: {category}
描述: {description}
目标用户: {target_audience}
病毒因子: {viral_hooks}

请输出 JSON：
```json
{{
  "readme_strategy": "README 该怎么写才能吸引 star：第一行 tagline、GIF 动图位置、一键安装命令、对比表格、使用示例等具体建议（300字以内，可用换行）",
  "naming_tips": "命名建议：为什么这个名字好/可以怎么调整，以及备选名"
}}
```"""


def generate_architecture(suggestion: ProjectSuggestion) -> dict[str, str]:
    """按需生成架构与目录结构。返回 {'architecture', 'repo_structure'}。"""
    llm = LLMClient()
    user_prompt = _ARCH_USER_TEMPLATE.format(
        name=suggestion.name,
        tagline=suggestion.tagline,
        category=suggestion.category,
        description=suggestion.description,
        tech_stack=", ".join(suggestion.tech_stack),
        key_features=", ".join(suggestion.key_features),
    )
    result = llm.chat_json(_ARCH_SYSTEM_PROMPT, user_prompt)
    return {
        "architecture": result.get("architecture", ""),
        "repo_structure": result.get("repo_structure", ""),
    }


def generate_readme_strategy(suggestion: ProjectSuggestion) -> dict[str, str]:
    """按需生成 README 营销策略与命名建议。返回 {'readme_strategy', 'naming_tips'}。"""
    llm = LLMClient()
    user_prompt = _README_USER_TEMPLATE.format(
        name=suggestion.name,
        tagline=suggestion.tagline,
        category=suggestion.category,
        description=suggestion.description,
        target_audience=suggestion.target_audience,
        viral_hooks=", ".join(suggestion.viral_hooks),
    )
    result = llm.chat_json(_README_SYSTEM_PROMPT, user_prompt)
    return {
        "readme_strategy": result.get("readme_strategy", ""),
        "naming_tips": result.get("naming_tips", ""),
    }


def _parse_suggestion(data: dict[str, Any]) -> ProjectSuggestion:
    return ProjectSuggestion(
        name=data.get("name", "unnamed"),
        tagline=data.get("tagline", ""),
        category=data.get("category", "tool"),
        description=data.get("description", ""),
        target_audience=data.get("target_audience", ""),
        similar_projects=data.get("similar_projects", []),
        estimated_stars=data.get("estimated_stars", ""),
        viral_hooks=data.get("viral_hooks", []),
        tech_stack=data.get("tech_stack", []),
        key_features=data.get("key_features", []),
        architecture=data.get("architecture", ""),
        mvp_features=data.get("mvp_features", []),
        timeline=data.get("timeline", ""),
        difficulty=data.get("difficulty", "medium"),
        repo_structure=data.get("repo_structure", ""),
        readme_strategy=data.get("readme_strategy", ""),
        naming_tips=data.get("naming_tips", ""),
    )
