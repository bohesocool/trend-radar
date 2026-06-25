#!/usr/bin/env python3
"""手动触发周报。"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trend_radar.scheduler import run_weekly

if __name__ == "__main__":
    result = asyncio.run(run_weekly())
    print(f"\n✅ 周报生成完成")
    print(f"   报告路径: data/reports/.../weekly.md")