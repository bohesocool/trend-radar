"""项目建议生成引擎 — 基于趋势分析生成具体可执行的项目建议。"""

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
5. README 营销策略 (好的 README 是 star 增长的关键)
6. 可直接使用的脚手架代码骨架

GitHub star 增长策略：
- 命名：短小好记 ≤15字符，能直觉暗示功能
- README：第一行是亮点 tagline；必须要有 GIF 动图演示位置；一键安装命令；对比表格
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
      "architecture": "简要架构描述",
      "mvp_features": ["MVP该做的功能1", "功能2"],
      "timeline": "2-3天可出MVP",
      "difficulty": "easy 或 medium 或 hard",
      "repo_structure": "推荐目录结构 (markdown格式)",
      "readme_strategy": "README该怎么写才能吸引star",
      "naming_tips": "命名建议",
      "scaffold_files": {{
        "README.md": "完整的README.md内容",
        "main.py": "主程序入口骨架代码",
        "requirements.txt": "依赖列表"
      }}
    }}
  ]
}}
```

要求：
- 只生成 1 个建议
- scaffold_files 中的代码不要超过 50 行（保持精简骨架，不要写完整实现）
- scaffold_files 至少包含 README.md 和主程序文件
- README.md 要写营销型文案，包含安装、使用、对比表格
- 项目名要检查不会与知名项目重名
- scaffold_files 中的代码要可以直接运行 (不能是伪代码)
- {index_hint}"""


def generate_suggestions(analysis: TrendAnalysis, n: int = 5) -> list[ProjectSuggestion]:
    """基于趋势分析生成项目建议。每次只生成 1 个，循环调用 N 次以提高成功率。"""
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
        scaffold_files=data.get("scaffold_files", {}),
    )