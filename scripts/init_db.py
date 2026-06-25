#!/usr/bin/env python3
"""初始化数据库。"""

import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trend_radar import db

if __name__ == "__main__":
    db.init_db()
    print("✅ 数据库初始化完成")