"""AI 输出语言设置 — 统一读取 generator.output_language 并提供 prompt 后缀。

集中在此处，避免 trend_analyzer / suggestion_engine 各自重复读取逻辑。默认中文。
"""

from __future__ import annotations

from trend_radar.config import get_config

_LANGUAGE_NAMES = {"zh": "中文", "en": "英文"}


def get_output_language() -> str:
    """返回 AI 输出语言代码 (zh / en)，默认 zh。"""
    lang = get_config().get("generator", {}).get("output_language", "zh")
    return lang if lang in _LANGUAGE_NAMES else "zh"


def language_instruction() -> str:
    """拼成 prompt 指令尾句：除了项目名必须保持英文小写连字符外，正文用所选语言。"""
    lang = get_output_language()
    name = _LANGUAGE_NAMES[lang]
    return (
        f"所有正文内容（描述、分析、tagline、README 策略、架构说明、项目文档等）"
        f"必须用{name}撰写。唯一例外：项目名 (name) 始终保持英文小写连字符形式，不要翻译。"
    )