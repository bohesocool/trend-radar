#!/usr/bin/env python3
"""初始化数据库。"""

import sys
from pathlib import Path

# Windows 默认 GBK 控制台无法打印 emoji，强制 stdout 用 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trend_radar import db

if __name__ == "__main__":
    db.init_db()
    print("✅ 数据库初始化完成")