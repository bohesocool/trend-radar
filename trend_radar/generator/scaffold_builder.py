"""脚手架构建器 — 将 LLM 生成的 scaffold_files 写入磁盘。"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from trend_radar.config import get_project_root
from trend_radar.models import ProjectSuggestion


def build_scaffold(suggestion: ProjectSuggestion, date_str: str, output_dir: Path | None = None) -> Path:
    """将项目建议的脚手架文件写入磁盘。

    返回写入的目录路径。
    """
    if not suggestion.scaffold_files:
        logger.info(f"项目 {suggestion.name} 无脚手架文件，跳过")
        return Path()

    base = output_dir or (get_project_root() / "data" / "reports" / date_str / "scaffolds")
    project_dir = base / suggestion.name
    project_dir.mkdir(parents=True, exist_ok=True)

    for filename, content in suggestion.scaffold_files.items():
        filepath = project_dir / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        logger.debug(f"写入脚手架文件: {filepath}")

    logger.info(f"脚手架已生成: {project_dir}")
    return project_dir


def build_all_scaffolds(suggestions: list[ProjectSuggestion], date_str: str) -> list[Path]:
    """批量生成脚手架。"""
    dirs: list[Path] = []
    for s in suggestions:
        d = build_scaffold(s, date_str)
        if d:
            dirs.append(d)
    return dirs