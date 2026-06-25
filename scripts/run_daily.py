#!/usr/bin/env python3
"""手动触发日报。"""

import asyncio
import sys
from pathlib import Path

# Windows 默认 GBK 控制台无法打印 emoji，强制 stdout 用 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trend_radar.scheduler import run_daily

if __name__ == "__main__":
    report = asyncio.run(run_daily())
    print(f"\n✅ 日报完成: {report.date}")
    print(f"   热点: {len(report.analysis.hot_topics)} 个")
    print(f"   建议: {len(report.suggestions)} 个")
    print(f"   报告路径: data/reports/{report.date}/daily.md")