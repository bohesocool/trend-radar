"""定时任务调度 + 主流程编排。"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from loguru import logger

from trend_radar import db
from trend_radar.analyzer.trend_analyzer import analyze_trends
from trend_radar.analyzer.aggregator import aggregate_by_topic
from trend_radar.collectors import (
    ArxivCollector,
    GitHubTrendingCollector,
    HackerNewsCollector,
    RedditCollector,
    TwitterAICollector,
)
from trend_radar.config import get_config, get_project_root
from trend_radar.generator.scaffold_builder import build_all_scaffolds
from trend_radar.generator.suggestion_engine import generate_suggestions
from trend_radar.models import DailyReport
from trend_radar.pusher.github_sync import sync_scaffold_to_github, sync_to_github
from trend_radar.pusher.message_formatter import render_daily_report_markdown, render_message_summary
from trend_radar.pusher.qq_bot import send_qq
from trend_radar.pusher.telegram_bot import send_telegram


async def run_collect_all() -> list:
    """执行所有数据采集。"""
    cfg = get_config()["collectors"]
    all_items = []

    # 并发采集
    tasks: list[tuple[str, object]] = []
    if cfg.get("github_trending", {}).get("enabled", True):
        tasks.append(("github", GitHubTrendingCollector(cfg["github_trending"])))
    if cfg.get("hackernews", {}).get("enabled", True):
        tasks.append(("hackernews", HackerNewsCollector(cfg["hackernews"])))
    if cfg.get("reddit", {}).get("enabled", True):
        tasks.append(("reddit", RedditCollector(cfg["reddit"])))
    if cfg.get("arxiv", {}).get("enabled", True):
        tasks.append(("arxiv", ArxivCollector(cfg["arxiv"])))
    if cfg.get("twitter", {}).get("enabled", True):
        tasks.append(("twitter", TwitterAICollector(cfg["twitter"])))

    for name, collector in tasks:
        try:
            items = await collector.collect()
            all_items.extend(items)
            logger.info(f"[{name}] 采集 {len(items)} 条")
        except Exception as e:
            logger.error(f"[{name}] 采集异常: {e}")

    return all_items


async def run_daily() -> DailyReport:
    """执行完整的日报流程：采集 → 分析 → 生成建议 → 推送。"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"===== TrendRadar 日报开始 {date_str} =====")

    # 0. 初始化数据库
    db.init_db()

    # 1. 采集
    logger.info("Step 1/5: 数据采集...")
    items = await run_collect_all()
    logger.info(f"共采集 {len(items)} 条数据")
    db.save_trend_items(items, date_str)

    # 2. 分析
    logger.info("Step 2/5: 趋势分析...")
    analysis = analyze_trends(items, date_str)
    db.save_analysis(
        date_str,
        analysis.daily_summary,
        [ht.__dict__ for ht in analysis.hot_topics],
        [opp.__dict__ for opp in analysis.emerging_opportunities],
        analysis.raw_items_count,
    )

    # 3. 生成建议
    logger.info("Step 3/5: 项目建议生成...")
    n = get_config()["generator"]["daily_suggestions"]
    try:
        suggestions = generate_suggestions(analysis, n)
    except Exception as e:
        logger.error(f"项目建议生成失败: {e}")
        suggestions = []
    for s in suggestions:
        db.save_suggestion(
            date_str,
            s.name,
            s.tagline,
            s.category,
            s.description,
            json.dumps(s.__dict__, ensure_ascii=False, default=str),
            json.dumps(s.scaffold_files, ensure_ascii=False),
        )

    # 4. 生成脚手架 + 报告
    logger.info("Step 4/5: 脚手架生成...")
    build_all_scaffolds(suggestions, date_str)

    report = DailyReport(date=date_str, analysis=analysis, suggestions=suggestions)
    report.markdown = render_daily_report_markdown(report)

    # 保存报告到文件
    report_dir = get_project_root() / "data" / "reports" / date_str
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "daily.md").write_text(report.markdown, encoding="utf-8")
    logger.info(f"报告已保存: {report_dir / 'daily.md'}")

    # 5. 推送
    logger.info("Step 5/5: 推送...")
    summary = render_message_summary(report)
    send_telegram(summary)
    send_qq(summary)
    sync_to_github(date_str, report.markdown)
    for s in suggestions:
        if s.scaffold_files:
            sync_scaffold_to_github(date_str, s.name, s.scaffold_files)

    logger.info(f"===== TrendRadar 日报完成 {date_str} =====")
    return report


async def run_weekly() -> str:
    """执行周报：汇总过去 7 天的数据。"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"===== TrendRadar 周报开始 {date_str} =====")

    db.init_db()
    # 读取过去 7 天的分析数据
    summaries = db.get_recent_summaries(limit=7)
    if not summaries:
        logger.warning("周报：过去7天无数据")
        return "无数据"

    # 生成周报 Markdown
    lines = [f"# 🔭 TrendRadar 周报 — {date_str}", "", "## 本周趋势回顾", ""]
    for s in summaries:
        lines.append(f"### {s['date']}")
        lines.append(f"> {s['summary']}")
        lines.append(f"- 采集数据量: {s['raw_items_count']}")
        lines.append("")

    weekly_md = "\n".join(lines)
    report_dir = get_project_root() / "data" / "reports" / date_str
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "weekly.md").write_text(weekly_md, encoding="utf-8")

    # 推送
    send_telegram(weekly_md[:4000])
    send_qq(weekly_md[:4000])
    sync_to_github(date_str, weekly_md)

    logger.info(f"===== TrendRadar 周报完成 {date_str} =====")
    return weekly_md


def run_daily_sync():
    """同步入口 (供 APScheduler 调用)。"""
    asyncio.run(run_daily())


def run_weekly_sync():
    """周报同步入口。"""
    asyncio.run(run_weekly())