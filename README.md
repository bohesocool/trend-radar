# TrendRadar

> 🔭 自动追踪 GitHub 热点 + 全球 AI 资讯，用大模型分析趋势，每日/每周生成「值得现在做、能火」的项目建议与脚手架。

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置
cp .env.example .env
# 编辑 .env 填入你的 NewAPI key、Bot token 等

# 初始化数据库
python scripts/init_db.py

# 手动运行一次日报
python scripts/run_daily.py

# 启动 Web 仪表盘
python -m trend_radar.web.app
```

## 项目结构

详见 [DESIGN.md](DESIGN.md)
