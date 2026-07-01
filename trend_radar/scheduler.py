"""定时任务调度 + 主流程编排。"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from loguru import logger

from trend_radar import db
from trend_radar.analyzer.trend_analyzer import analyze_trends
from trend_radar.collectors import (
    ArxivCollector,
    GitHubTrendingCollector,
    HackerNewsCollector,
    RedditCollector,
    TwitterAICollector,
)
from trend_radar.config import get_config, get_project_root
from trend_radar.generator.suggestion_engine import generate_suggestions
from trend_radar.models import DailyReport, TrendAnalysis
from trend_radar.pusher.github_sync import sync_to_github
from trend_radar.pusher.message_formatter import render_daily_report_markdown, render_message_summary
from trend_radar.pusher.qq_bot import send_qq
from trend_radar.pusher.telegram_bot import send_telegram


async def run_collect_all(progress=None, total_steps: int = 5) -> list:
    """执行所有数据采集。

    progress: 可选回调 (step:int, total:int, label:str)。采集层不改变 step，
    只在进入各源时用 label 上报"采集中: <源>"，让前端能感知采集阶段进度。
    """
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

    def _emit(label: str) -> None:
        if progress is not None:
            try:
                progress(1, total_steps, label)
            except Exception:
                pass

    _emit(f"采集数据 (0/{len(tasks)})")

    async def _run_one(name: str, collector: object) -> tuple[str, list]:
        try:
            items = await collector.collect()
            logger.info(f"[{name}] 采集 {len(items)} 条")
            return name, items
        except Exception as e:
            logger.error(f"[{name}] 采集异常: {e}")
            return name, []

    # 真正并发：asyncio.gather 同时拉所有源，单源超时不拖累其他源
    results = await asyncio.gather(*[_run_one(n, c) for n, c in tasks])
    done = 0
    for name, items in results:
        done += 1
        _emit(f"采集数据 ({done}/{len(tasks)}) · {name} +{len(items)}")
        all_items.extend(items)

    return all_items


async def run_daily(progress=None) -> DailyReport:
    """执行完整的日报流程：采集 → 分析 → 生成建议 → 推送。

    progress: 可选回调 (step:int, total:int, label:str)，用于向前端实时上报进度。
    """
    total = 5

    def _emit(step: int, label: str) -> None:
        if progress is not None:
            try:
                progress(step, total, label)
            except Exception:  # 进度上报失败不应中断主流程
                pass

    date_str = datetime.now().strftime("%Y-%m-%d")
    logger.info(f"===== TrendRadar 日报开始 {date_str} =====")

    # 0. 初始化数据库
    db.init_db()

    # 1. 采集
    logger.info("Step 1/5: 数据采集...")
    _emit(1, "采集数据")
    items = await run_collect_all(progress=progress, total_steps=total)
    logger.info(f"共采集 {len(items)} 条数据")
    # 跨天新鲜度标记：近 7 天未出现过的 url 记为 NEW
    seen = db.get_seen_urls(date_str, days=7)
    new_count = 0
    for it in items:
        is_new = it.url not in seen
        it.extra["is_new"] = is_new
        if is_new:
            new_count += 1
    logger.info(f"其中 {new_count} 条为近 7 天首次出现 (NEW)")
    db.save_trend_items(items, date_str)

    # 2. 分析
    logger.info("Step 2/5: 趋势分析...")
    _emit(2, "趋势分析")
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
    _emit(3, "生成项目建议")
    n = get_config()["generator"]["daily_suggestions"]
    # 累积追加：同一天可多次运行，每批产出不同点子，前端可挑选最佳。不做清理。
    try:
        suggestions = generate_suggestions(analysis, n, raw_items=items)
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
            s.__dict__,
        )

    # 4. 生成报告
    logger.info("Step 4/5: 报告生成...")
    _emit(4, "生成报告")
    report = DailyReport(date=date_str, analysis=analysis, suggestions=suggestions)
    report.markdown = render_daily_report_markdown(report)

    # 保存报告到文件
    report_dir = get_project_root() / "data" / "reports" / date_str
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "daily.md").write_text(report.markdown, encoding="utf-8")
    logger.info(f"报告已保存: {report_dir / 'daily.md'}")

    # 5. 推送
    logger.info("Step 5/5: 推送...")
    _emit(5, "推送 / 同步")
    await push_report(report)

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
    weekly_report = DailyReport(date=date_str, analysis=TrendAnalysis(date=date_str, daily_summary=""), suggestions=[])
    weekly_report.markdown = weekly_md
    await push_report(weekly_report)

    logger.info(f"===== TrendRadar 周报完成 {date_str} =====")
    return weekly_md


async def push_report(report: DailyReport) -> None:
    """并发推送 + 同步到各渠道，每个渠道独立 try/except，单渠道失败不影响其他。

    Telegram/QQ/GitHub sync 均为同步 IO，用 asyncio.to_thread 包一层避免阻塞事件循环；
    互相之间用 asyncio.gather 并发，总耗时≈最慢的那个渠道而非三者之和。
    """
    summary = render_message_summary(report)

    async def _safe(name: str, fn, *args) -> None:
        try:
            await asyncio.to_thread(fn, *args)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[推送:{name}] 失败 (忽略): {e}")

    await asyncio.gather(
        _safe("telegram", send_telegram, summary),
        _safe("qq", send_qq, summary),
        _safe("github", sync_to_github, report.date, report.markdown),
    )


def run_daily_sync():
    """同步入口 (供 APScheduler 调用)。"""
    asyncio.run(run_daily())


def run_weekly_sync():
    """周报同步入口。"""
    asyncio.run(run_weekly())


# ===== 进程内 APScheduler 调度 =====
# 随 Web 进程启动，读 config.yaml 的 scheduler 段到点触发日报/周报。
# 设置页改完定时时间后调 reload_scheduler() 即时热重载，无需重启容器。

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

_SCHEDULER_TZ = "Asia/Shanghai"
_scheduler: BackgroundScheduler | None = None


def _cron_fields(cron: str) -> dict:
    """把标准 5 段 cron '0 8 * * *' 拆成 CronTrigger 关键字参数。

    顺序: minute hour day month day_of_week
    """
    parts = cron.split()
    if len(parts) != 5:
        raise ValueError(f"非法 cron 表达式 (应为 5 段): {cron}")
    keys = ["minute", "hour", "day", "month", "day_of_week"]
    return dict(zip(keys, parts))


def _apply_jobs(sched: BackgroundScheduler) -> None:
    """按当前 config 注册/刷新 daily、weekly 两个 job。"""
    cfg = get_config().get("scheduler", {})
    daily = cfg.get("daily", {})
    weekly = cfg.get("weekly", {})
    if daily.get("enabled", True):
        sched.add_job(
            run_daily_sync,
            CronTrigger(timezone=_SCHEDULER_TZ, **_cron_fields(daily.get("cron", "0 8 * * *"))),
            id="daily",
            replace_existing=True,
        )
    if weekly.get("enabled", True):
        sched.add_job(
            run_weekly_sync,
            CronTrigger(timezone=_SCHEDULER_TZ, **_cron_fields(weekly.get("cron", "0 9 * * 1"))),
            id="weekly",
            replace_existing=True,
        )


def _remove_disabled(sched: BackgroundScheduler) -> None:
    """移除已被关闭 (enabled=False) 的 job。"""
    cfg = get_config().get("scheduler", {})
    for job_id in ("daily", "weekly"):
        if not cfg.get(job_id, {}).get("enabled", True):
            try:
                sched.remove_job(job_id)
            except Exception:  # job 不存在则忽略
                pass


def start_scheduler() -> None:
    """Web 启动时调用一次：创建并启动 BackgroundScheduler，注册 cron job。"""
    global _scheduler
    if _scheduler is not None:
        return
    sched = BackgroundScheduler(timezone=_SCHEDULER_TZ)
    _apply_jobs(sched)
    sched.start()
    _scheduler = sched
    logger.info(
        f"APScheduler 已启动 (tz={_SCHEDULER_TZ})，已注册 job: "
        f"{[j.id for j in sched.get_jobs()]}"
    )


def reload_scheduler() -> None:
    """设置页保存后调用：按最新 config 重新排 job，立即生效。"""
    if _scheduler is None:
        return
    _apply_jobs(_scheduler)  # replace_existing=True 会覆盖已有 job 的 trigger
    _remove_disabled(_scheduler)
    logger.info(
        f"APScheduler 已热重载，当前 job: "
        f"{[(j.id, str(j.trigger)) for j in _scheduler.get_jobs()]}"
    )