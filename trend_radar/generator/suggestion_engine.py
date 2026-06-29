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
from trend_radar.models import HotTopic, Opportunity, ProjectSuggestion, TrendAnalysis

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

_USER_PROMPT_TEMPLATE = """基于以下 {date} 的趋势分析结果，生成 {n} 个具体、差异化的项目建议。

【趋势概述】
{summary}

【热点主题】
{hot_topics_full}

【新兴机会】
{opportunities}

请输出 JSON（包含 {n} 个建议，suggestions 数组里放 {n} 个对象）：
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
- 生成 {n} 个建议
- 这是一份轻量报告，不要输出脚手架代码、目录结构或 README 文案（这些会在详情页按需生成）
- 项目名要检查不会与知名项目重名
- {diversity_hint}"""


def _format_hot_topics_with_evidence(hot_topics: list[HotTopic], raw_items: list | None) -> str:
    """把热点主题的"接地"字段 + 每个热点命中的原始条目拼成 prompt 文本。

    之前只传 topic/heat/trend/description 四个抽象字段，evidence/insights 等具体信息全丢了，
    导致 similar_projects 只能凭空编造。这里把 evidence 和"该主题下真实在涨的项目"一起喂进去。
    """
    if not hot_topics:
        return ""

    # 预建一个可检索的原始条目池：标题/描述里命中关键词即可关联
    raw_items = raw_items or []
    _RAW_LIMIT_PER_TOPIC = 5

    def _match(topic: str, desc: str) -> list:
        if not raw_items:
            return []
        kws = {w.lower() for w in topic.replace("-", " ").split() if len(w) > 2}
        hits: list = []
        for it in raw_items:
            hay = f"{it.title} {it.description}".lower()
            if any(k in hay for k in kws):
                hits.append(it)
            if len(hits) >= _RAW_LIMIT_PER_TOPIC:
                break
        return hits

    lines: list[str] = []
    for ht in hot_topics:
        lines.append(
            f"- {ht.topic} (热度:{ht.heat_score}, 趋势:{ht.trend}): {ht.description}"
        )
        if ht.evidence:
            lines.append(f"  证据: {'; '.join(ht.evidence)}")
        if ht.key_insights:
            lines.append(f"  洞察: {'; '.join(ht.key_insights)}")
        if ht.recommendations:
            lines.append(f"  建议: {'; '.join(ht.recommendations)}")
        if ht.languages:
            lines.append(f"  语言: {', '.join(ht.languages)}")
        matched = _match(ht.topic, ht.description)
        for it in matched:
            src = getattr(it, "source", "?")
            pop = getattr(it, "popularity", 0)
            lines.append(f"  · [{src}] {it.title} (热度{pop}) — {it.description}")
    return "\n".join(lines)


def generate_suggestions(analysis: TrendAnalysis, n: int = 5, raw_items: list | None = None) -> list[ProjectSuggestion]:
    """基于趋势分析生成轻量项目建议。单次调用让 LLM 连续出 N 条，同上下文自分化，
    避免逐条独立采样导致的雷同换皮。失败时兜底重试。

    raw_items: 当天的原始采集数据（可选）。传入后会把每个热点对应的具体仓库/帖子/论文
    喂给 LLM，让 similar_projects / tech_stack 有真实参照，而非凭空编造。
    """
    if not analysis.hot_topics and not analysis.emerging_opportunities:
        logger.warning("无趋势数据，跳过建议生成")
        return []

    hot_topics_text = "\n".join(
        f"- {ht.topic} (热度:{ht.heat_score}, 趋势:{ht.trend}): {ht.description}"
        for ht in analysis.hot_topics
    )
    opportunities_text = "\n".join(
        f"- [{opp.difficulty}] {opp.gap} → {opp.why_now} (预估star: {opp.potential_stars})"
        for opp in analysis.emerging_opportunities
    )

    # 把热点主题的"接地"字段（evidence/insights/recommendations/languages）以及
    # 每个热点对应的原始采集条目拼进 prompt，让建议不再凭空发挥
    hot_topics_full_text = _format_hot_topics_with_evidence(analysis.hot_topics, raw_items)

    diversity_hint = _diversity_hint(analysis, n)

    def _build_prompt(hint: str) -> str:
        return _USER_PROMPT_TEMPLATE.format(
            date=analysis.date,
            n=n,
            summary=analysis.daily_summary,
            hot_topics=hot_topics_text,
            hot_topics_full=hot_topics_full_text,
            opportunities=opportunities_text,
            diversity_hint=hint,
        )

    def _parse_batch(result: dict[str, Any], existing: list[ProjectSuggestion] | None = None) -> list[ProjectSuggestion]:
        """从一次调用结果里解析建议，去重（含与已有批次的全局去重）+ 限 N 条。"""
        s_list = result.get("suggestions", []) or []
        seen: set[str] = {s.name for s in existing} if existing else set()
        out: list[ProjectSuggestion] = []
        for s_data in s_list:
            suggestion = _parse_suggestion(s_data)
            if not suggestion.name or suggestion.name in seen:
                continue
            seen.add(suggestion.name)
            out.append(suggestion)
            if len(out) >= n:
                break
        return out

    llm = LLMClient()
    suggestions: list[ProjectSuggestion] = []

    # 主调用：单次出 N 条
    logger.info(f"调用 LLM 一次性生成 {n} 个项目建议...")
    try:
        result = llm.chat_json(_SYSTEM_PROMPT, _build_prompt(diversity_hint))
        suggestions = _parse_batch(result)
        logger.info(f"单次调用生成 {len(suggestions)}/{n} 个建议: {[s.name for s in suggestions]}")
    except Exception as e:
        logger.error(f"项目建议生成失败: {e}")

    # 兜底：若数量不足，逐条补齐到 N（仍失败则至少保证 1 条）
    retries = 0
    while len(suggestions) < n and retries < 3:
        retries += 1
        need = n - len(suggestions)
        logger.warning(f"当前 {len(suggestions)}/{n}，启动兜底重试第 {retries}/3 次，补 {need} 条...")
        try:
            hint = _diversity_hint(analysis, need, existing=suggestions)
            result = llm.chat_json(_SYSTEM_PROMPT, _build_prompt(hint))
            extra = _parse_batch(result, existing=suggestions)
            if extra:
                suggestions.extend(extra)
                logger.info(f"兜底第 {retries} 次补充成功，现 {len(suggestions)}/{n}")
        except Exception as e:
            logger.error(f"兜底重试第 {retries} 次失败: {e}")
            continue

    logger.info(f"共生成 {len(suggestions)}/{n} 个项目建议")
    return suggestions


def _diversity_hint(
    analysis: TrendAnalysis, n: int, existing: list[ProjectSuggestion] | None = None
) -> str:
    """构造差异化提示：要求覆盖不同热点/分类/技术栈；若已有建议则点名避开其方向。"""
    parts = [f"这 {n} 个建议必须彼此差异化：覆盖不同的热点主题、不同的 category 与技术栈，优先 trending=rising 的主题"]
    if existing:
        names = ", ".join(s.name for s in existing[:8])
        cats = ", ".join(sorted({s.category for s in existing}))
        parts.append(f"已有建议 [{names}]，分类 [{cats}]，新建议要避开这些方向与命名")
    return "；".join(parts)


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
        project_doc=data.get("project_doc", ""),
    )


# ===== 完整项目文档（按需生成，直接交付 AI 编码助手） =====

_PROJECT_DOC_SYSTEM_PROMPT = """你是一名资深软件架构师 + 技术文档作者。
基于给定的项目建议，输出一份完整、可落地的项目文档（Markdown 格式），详细到能直接交给 Claude Code / Codex 这类 AI 编码助手据此搭建整个项目。

直接输出 Markdown 正文，不要包裹在 ``` 代码块里，也不要输出任何 JSON 或额外解释。"""

_PROJECT_DOC_USER_TEMPLATE = """为以下项目撰写完整项目文档。

【项目建议】
- 名称：{name}
- 一句话：{tagline}
- 分类：{category}
- 描述：{description}
- 目标用户：{target_audience}
- 技术栈：{tech_stack}
- 核心功能：{key_features}
- MVP 功能：{mvp_features}
- 时间线：{timeline}
{existing_context}

文档必须包含以下章节，每节都要具体、可执行：

## 1. 项目概述
一句话定位、解决什么问题、目标用户是谁、为什么现在做。

## 2. 核心功能模块
逐个列出每个功能模块，每个模块写明：
- 模块名称
- 职责（这个模块负责什么）
- 做什么（具体行为 / 关键流程）
- 输入 / 输出
- 依赖哪些其他模块

## 3. 技术架构
模块如何划分与组合、数据流向、关键技术选型与理由。

## 4. 目录结构
用带注释的目录树表示，可直接照着建仓库。

## 5. 数据模型 / 关键接口
核心数据结构、对外接口（CLI 命令 / API 路径 / 函数签名），给出示例。

## 6. 技术栈
逐项列出依赖及其用途。

## 7. MVP 实现计划
分里程碑，每步给出交付物，先做什么后做什么。

## 8. README 要点 & 命名建议
首行 tagline、安装命令、使用示例、对比表格位置；命名是否合适及备选名。

## 9. 给 AI 编码助手的执行指引
写给 Claude Code / Codex：如何启动这个项目、第一步先实现哪块、有哪些注意事项与约定。"""


def _build_project_doc_prompt(suggestion: ProjectSuggestion, existing_context: dict[str, str]) -> str:
    """拼装生成完整项目文档的 user prompt。

    existing_context: full_data 中已存在的 architecture / repo_structure / readme_strategy /
    naming_tips。有则作为参考喂给 AI（让文档与已生成内容保持一致），全为空则不附。
    """
    arch = (existing_context.get("architecture") or "").strip()
    repo = (existing_context.get("repo_structure") or "").strip()
    readme = (existing_context.get("readme_strategy") or "").strip()
    naming = (existing_context.get("naming_tips") or "").strip()

    parts: list[str] = []
    if arch:
        parts.append(f"已有架构参考：\n{arch}")
    if repo:
        parts.append(f"已有目录结构参考：\n{repo}")
    if readme:
        parts.append(f"已有 README 策略参考：\n{readme}")
    if naming:
        parts.append(f"已有命名建议参考：\n{naming}")
    existing_block = ("\n" + "\n".join(parts) + "\n") if parts else ""

    return _PROJECT_DOC_USER_TEMPLATE.format(
        name=suggestion.name,
        tagline=suggestion.tagline,
        category=suggestion.category,
        description=suggestion.description,
        target_audience=suggestion.target_audience,
        tech_stack=", ".join(suggestion.tech_stack),
        key_features="、".join(suggestion.key_features),
        mvp_features="、".join(suggestion.mvp_features),
        timeline=suggestion.timeline,
        existing_context=existing_block,
    )


def generate_project_doc(suggestion: ProjectSuggestion, existing_context: dict[str, str]) -> str:
    """按需生成完整项目文档（纯 Markdown 字符串）。

    走 llm.chat() 而非 chat_json()：Markdown 是纯文本，不需要也不应经过 JSON 解析，
    从根上规避 JSON 截断 / _parse_json 兜底问题。

    existing_context: full_data 中已生成的 architecture / readme 等字段，有则作为上下文。
    """
    llm = LLMClient()
    prompt = _build_project_doc_prompt(suggestion, existing_context)
    # 整篇文档较长，显式放宽输出上限，避免被默认值截断
    return llm.chat(_PROJECT_DOC_SYSTEM_PROMPT, prompt, max_tokens=8000)
