<div align="center">

# 🔭 TrendRadar

**自动追踪 GitHub 热点 + 全球 AI 资讯,用大模型分析趋势,每日生成「值得现在做、能火」的开源项目建议。**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/github/license/bohesocool/trend-radar?color=blue)](LICENSE)
[![Last Commit](https://img.shields.io/github/last-commit/bohesocool/trend-radar)](https://github.com/bohesocool/trend-radar/commits)
[![Stars](https://img.shields.io/github/stars/bohesocool/trend-radar?style=social)](https://github.com/bohesocool/trend-radar/stargazers)

</div>

---

## 这是什么

每天有海量技术热点散落在 GitHub、Hacker News、Reddit、arXiv……但**「现在做什么开源项目能火」**这个问题,没人帮你回答。

TrendRadar 把这条链路自动化:

```
多源采集  →  LLM 趋势分析  →  项目建议生成  →  Web 仪表盘展示 + 可选推送
```

它每天自动采集各平台热点,交给大模型分析出**热点主题 / 热度走势 / 机会缺口**,再生成几个**可直接落地、附带市场分析与传播策略**的开源项目创意,最后呈现在一个轻量的 Web 仪表盘上。

---

## ✨ 功能特性

- 🌐 **多源采集** — GitHub Trending、Hacker News、Reddit、arXiv 开箱即用,Twitter/X 可选开启,统一归一化入库。
- 🧠 **LLM 趋势分析** — 输出热点主题、1–100 热度评分、趋势方向(rising / peak / sustained / cooling)、深度洞察与建议。
- 💡 **项目建议生成** — 每条建议含一句话亮点、目标用户、技术栈、类似项目对比、预估 star、病毒传播因子;详情页可**按需 AI 生成**架构设计与 README 营销策略。
- 📊 **Web 仪表盘** — 深色主题、**SPA 局部导航(切页无刷新)**、7 天热度趋势图、响应式布局,移动端友好。
- ⏰ **定时调度** — APScheduler 驱动,每日 08:00 跑日报、每周一 09:00 跑周报。
- 🔔 **可选推送** — 通过 HTTP Webhook 触发日报/周报流程,便于接入外部 cron 或消息渠道。
- 🔐 **密码鉴权 + 在线设置** — 固定密码登录,设置页可直接修改 LLM 与采集参数。
- 🐳 **Docker 一键部署** — 多阶段构建,单容器即可运行。

---

## 🖼️ 界面预览

> 📷 仪表盘 · 趋势详情 · 项目建议详情
>
> <!-- 把截图放进 docs/screenshots/ 后,替换下面这一行 -->
> _（截图待补充:运行起来后将仪表盘截图放入 `docs/screenshots/` 并在此引用）_

---

## 🚀 快速开始

### 方式一:Docker(推荐)

```bash
# 1. 准备配置
cp .env.example .env
# 编辑 .env,至少填入 NEWAPI_BASE_URL / NEWAPI_API_KEY / NEWAPI_MODEL 和登录密码

# 2. 启动
docker compose up -d --build

# 3. 访问
open http://localhost:8088
```

> 💡 修改了代码或静态资源后,需 `docker compose up -d --build` 重新构建镜像才会生效
> (compose 只挂载了 `data/`、`config.yaml`、`.env`,代码是打进镜像的)。

### 方式二:本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 配置
cp .env.example .env        # 填入 NewAPI key、登录密码等

# 初始化数据库
python scripts/init_db.py

# 手动跑一次日报(采集 + 分析 + 生成)
python scripts/run_daily.py

# 启动 Web 仪表盘
python -m trend_radar.web.app   # → http://localhost:8088
```

---

## ⚙️ 配置

**密钥与密码** 放在 `.env`(见 `.env.example`):

| 变量 | 说明 |
|------|------|
| `NEWAPI_BASE_URL` | LLM API 地址(NewAPI / OpenAI 兼容端点),不含 `/v1` 后缀 |
| `NEWAPI_API_KEY` | LLM API Key |
| `NEWAPI_MODEL` | 模型名称 |
| `TRENDRADAR_PASSWORD` | Web 仪表盘登录密码 |

**采集 / 分析 / 调度参数** 放在 `config.yaml`,可控制各数据源开关、采集语言、HN 最低热度、arXiv 分类、每日建议数量、定时 cron 等。其中 LLM 与采集的常用项也可在 **设置页** 在线修改。

---

## 🏗️ 架构

```
┌───────────┐   ┌───────────┐   ┌────────────┐   ┌───────────────┐
│ Collector │ → │ Analyzer  │ → │ Generator  │ → │ Web / Pusher  │
│ 多源采集   │   │ LLM 分析   │   │ 项目建议生成 │   │ 仪表盘 / 推送   │
└─────┬─────┘   └─────┬─────┘   └─────┬──────┘   └───────┬───────┘
      │               │               │                  │
      ▼               ▼               ▼                  ▼
   SQLite          NewAPI          结构化建议         FastAPI + SPA
                  (LLM 调用)                          (深色仪表盘)
            ┌──────────────────────────────────────────────┐
            │  Scheduler (APScheduler)  每日 08:00 / 周一 09:00 │
            └──────────────────────────────────────────────┘
```

完整设计文档(模块详解、数据模型、Prompt 设计、增长策略)见 **[DESIGN.md](DESIGN.md)**。

---

## 🛠️ 技术栈

| 层 | 技术 |
|----|------|
| 语言 | Python 3.11+ |
| Web 框架 | FastAPI + Uvicorn |
| 前端 | 原生 HTML / CSS / JS(SPA 局部导航)+ Chart.js |
| 数据库 | SQLite(stdlib `sqlite3`) |
| 采集 | httpx + BeautifulSoup4 + lxml + feedparser |
| LLM | openai SDK(指向 NewAPI / OpenAI 兼容端点) |
| 调度 | APScheduler |
| 部署 | Docker / docker-compose |

---

## 📈 Star History

<div align="center">

[![Star History Chart](https://api.star-history.com/svg?repos=bohesocool/trend-radar&type=Date)](https://star-history.com/#bohesocool/trend-radar&Date)

</div>

---

## 📄 License

本项目采用 [MIT License](LICENSE) 开源。

---

<div align="center">
<sub>用 🔭 TrendRadar,把「下一个能火的开源项目」从灵感变成计划。</sub>
</div>
