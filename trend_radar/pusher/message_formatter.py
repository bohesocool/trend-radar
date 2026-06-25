"""报告格式化 — 将分析结果和建议转为 Markdown 报告和消息摘要。"""

from __future__ import annotations

from trend_radar.models import DailyReport, ProjectSuggestion, TrendAnalysis


def render_daily_report_markdown(report: DailyReport) -> str:
    """将日报渲染为完整 Markdown。"""
    a = report.analysis
    lines = [
        f"# 🔭 TrendRadar 日报 — {report.date}",
        "",
        f"> {a.daily_summary}",
        "",
        "---",
        "",
        "## 📊 今日热点",
        "",
    ]

    for i, ht in enumerate(a.hot_topics, 1):
        trend_emoji = {"rising": "📈", "peak": "🔥", "sustained": "➡️", "cooling": "📉"}.get(ht.trend, "📊")
        lines.append(f"### {trend_emoji} {i}. {ht.topic}")
        lines.append(f"- **热度**: {ht.heat_score}/100 ({ht.trend})")
        lines.append(f"- **描述**: {ht.description}")
        if ht.evidence:
            lines.append(f"- **证据**: {' / '.join(ht.evidence)}")
        if ht.languages:
            lines.append(f"- **语言**: {', '.join(ht.languages)}")
        lines.append("")

    lines.extend(["## 🎯 新兴机会", ""])
    for i, opp in enumerate(a.emerging_opportunities, 1):
        lines.append(f"### {i}. {opp.gap}")
        lines.append(f"- **为什么是现在**: {opp.why_now}")
        lines.append(f"- **预估 Star**: {opp.potential_stars}")
        lines.append(f"- **难度**: {opp.difficulty}")
        lines.append(f"- **目标用户**: {opp.target_audience}")
        lines.append("")

    lines.extend(["## 🚀 项目建议", ""])
    for i, s in enumerate(report.suggestions, 1):
        cat_emoji = {"cli": "⌨️", "web": "🌐", "library": "📚", "bot": "🤖", "tool": "🔧"}.get(s.category, "📦")
        lines.append(f"### {cat_emoji} {i}. {s.name}")
        lines.append(f"> {s.tagline}")
        lines.append("")
        lines.append(f"**描述**: {s.description}")
        lines.append("")
        lines.append(f"- **目标用户**: {s.target_audience}")
        lines.append(f"- **技术栈**: {' / '.join(s.tech_stack)}")
        lines.append(f"- **核心功能**: {', '.join(s.key_features)}")
        lines.append(f"- **预计 Star**: {s.estimated_stars}")
        lines.append(f"- **时间线**: {s.timeline}")
        lines.append(f"- **难度**: {s.difficulty}")
        if s.similar_projects:
            lines.append("")
            lines.append("**类似项目差异化**:")
            lines.append("| 项目 | Star | 我们的优势 |")
            lines.append("|------|------|-----------|")
            for sim in s.similar_projects:
                lines.append(f"| {sim.get('name','')} | {sim.get('stars','')} | {sim.get('our_advantage','')} |")
        if s.viral_hooks:
            lines.append("")
            lines.append(f"**病毒传播因素**: {' / '.join(s.viral_hooks)}")
        lines.append("")

    lines.extend(["---", "", f"*由 TrendRadar 自动生成 | 数据源: {a.raw_items_count} 条原始数据*", ""])

    return "\n".join(lines)


def render_message_summary(report: DailyReport) -> str:
    """生成消息推送用的精简摘要 (适合 QQ/Telegram)。"""
    a = report.analysis
    lines = [f"🔭 TrendRadar 日报 — {report.date}", "", f"{a.daily_summary}", "", "🚀 今日推荐项目:"]

    for i, s in enumerate(report.suggestions[:5], 1):
        lines.append(f"\n{i}. {s.name} — {s.tagline}")
        lines.append(f"   📦 {s.category} | ⭐ {s.estimated_stars} | ⏱ {s.timeline}")
        lines.append(f"   技术栈: {' / '.join(s.tech_stack)}")

    lines.append(f"\n查看完整报告: Web 仪表盘")
    return "\n".join(lines)