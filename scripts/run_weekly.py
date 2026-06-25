#!/usr/bin/env python3
"""手动触发周报。"""

import asyncio
import sys
from pathlib import Path

# Windows 默认 GBK 控制台无法打印 emoji，强制 stdout 用 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trend_radar.scheduler import run_weekly

if __name__ == "__main__":
    result = asyncio.run(run_weekly())
    print(f"\n✅ 周报生成完成")
    print(f"   报告路径: data/reports/.../weekly.md")