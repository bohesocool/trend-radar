# TrendRadar 🔭

> 自动追踪 GitHub 热点 + 全球 AI 资讯，用大模型分析趋势，每日/每周生成「值得现在做、能火」的项目建议与脚手架。

---

## 一、项目愿景

**一句话**：告诉你"现在做什么开源项目能上 GitHub Trending"，并直接给你脚手架代码。

**核心闭环**：

```
数据采集 → 趋势分析 → 项目建议生成 → 模板脚手架 → 报告推送 + 前端展示
```

---

## 二、系统架构总览

```
┌─────────────────────────────────────────────────────────┐
│                     TrendRadar 系统架构                      │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │ Collector │  │ Analyzer │  │ Generator│  │  Pusher  │ │
│  │ 数据采集层 │→│ 趋势分析层 │→│ 项目生成层 │→│  推送层   │ │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘  └────┬────┘ │
│        │             │             │             │       │
│        ▼             ▼             ▼             ▼       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │ SQLite/  │  │ NewAPI   │  │ Jinja2   │  │ QQ/Telegram│
│  │ JSON存储  │  │ LLM 调用  │  │ 模板引擎  │  │ Web前端  │ │
│  └──────────┘  └──────────┘  └──────────┘  └─────────┘ │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │              Scheduler (APScheduler)                  │ │
│  │    每日 08:00 采集+分析 | 每周一 09:00 周报汇总       │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## 三、核心模块详解

### 3.1 数据采集层 (Collector)

负责从多个数据源自动抓取热点信息，归一化存储。

| 数据源 | 采集内容 | 采集方式 | 频率 |
|--------|---------|---------|------|
| GitHub Trending | 每日/每周热门仓库（语言、star、fork、描述、标签） | 爬取 trending 页面 + GitHub API | 每日 |
| Hacker News | 热门 AI/编程相关帖子及讨论 | HN Algolia API | 每日 |
| Reddit r/MachineLearning | 热门帖子及讨论 | Reddit JSON API (无需认证) | 每日 |
| Twitter/X AI 大V | AI 领域意见领袖的最新动态 | Nitter/划爽荐 API | 每日 |
| arXiv | AI/ML 最新论文（cs.AI, cs.CL, cs.LG） | arXiv API | 每日 |

**采集数据统一格式**：

```python
@dataclass
class TrendItem:
    source: str          # "github" / "hackernews" / "reddit" / "twitter" / "arxiv"
    title: str
    url: str
    description: str
    tags: list[str]      # ["AI", "LLM", "agent"]
    popularity: int      # 统一热度分 (star/points/upvotes)
    language: str | None # 编程语言 (仅 github)
    extra: dict          # 源特定字段
    collected_at: datetime
```

**存储**：SQLite，轻量稳定，无需额外服务。

```sql
CREATE TABLE trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,           -- 采集日期 (YYYY-MM-DD)
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    description TEXT,
    tags TEXT,                    -- JSON array
    popularity INTEGER DEFAULT 0,
    language TEXT,
    extra TEXT,                   -- JSON
    created_at TEXT DEFAULT (datetime('now'))
);
```

---

### 3.2 趋势分析层 (Analyzer)

将采集到的原始数据喂给 LLM，生成结构化的趋势分析。

**分析流程**：

1. **去重与聚合**：同一主题在不同源出现 → 合并加权
2. **LLM 分析**（通过 NewAPI）：

   **Prompt 结构**：

   ```
   你是一名 GitHub 趋势分析师和开源项目策略顾问。
   
   以下是今日采集到的技术热点数据：
   
   【GitHub Trending】
   - {repo_name}: {description} ⭐{stars} 🍴{forks} lang={language}
   ...
   
   【Hacker News】
   - {title}: {points} points | {comments} comments
   ...
   
   【Reddit r/MachineLearning】
   - {title}: {upvotes} upvotes
   ...   
   【Twitter/X AI 领域】
   - {author}: {content}
   ...
   
   【arXiv 最新论文】
   - {title}: {abstract_summary}
   ...
   
   请输出以下内容（JSON 格式）：
   
   {
     "daily_summary": "今日技术趋势概述（2-3句）",
     "hot_topics": [
       {
         "topic": "主题名称",
         "heat_score": 1-100,
         "trend": "rising|peak|sustained|cooling",
         "description": "为什么这个问题热",
         "evidence": ["GitHub:xxx", "HN:xxx", "arXiv:xxx"],
         "languages": ["Python", "Rust"]
       }
     ],
     "emerging_opportunities": [
       {
         "gap": "当前缺少什么样的开源项目",
         "why_now": "为什么现在做时机最好",
         "potential_stars": "预估能获得多少 star (range)",
         "difficulty": "easy|medium|hard",
         "target_audience": "目标用户群体"
       }
     ]
   }
   ```

3. **热度评分算法**：多源加权合并

   ```python
   def calculate_heat_score(item: TrendItem) -> float:
       source_weights = {
           "github": 1.0,
           "hackernews": 0.8,
           "reddit": 0.6,
           "twitter": 0.7,
           "arxiv": 0.5,
       }
       # 热度 = 源权重 × log(popularity) × 时间衰减因子
       base = source_weights[item.source] * math.log10(item.popularity + 10)
       return round(base, 2)
   ```

---

### 3.3 项目建议生成层 (Generator)

基于趋势分析结果，生成**具体可执行的项目建议** + **脚手架模板**。

**生成的每个项目建议包含**：

```python
@dataclass
class ProjectSuggestion:
    name: str               # 建议项目名 (如 "lolcat-ai")
    tagline: str            # 一句话亮点 (如 "用 LLM 给终端输出上色")
    category: str           # cli / web / library / bot / tool
    description: str        # 详细描述 (200字)
    
    # 市场分析
    target_audience: str
    similar_projects: list[dict]  # 现有类似项目 + star数 + 我们的差异化
    estimated_stars: str          # "500-2000 in 1 month"
    viral_hooks: list[str]       # 什么因素能病毒式传播
    
    # 技术方案
    tech_stack: list[str]        # ["Python", "FastAPI", "Click"]
    key_features: list[str]      # 核心功能列表
    architecture: str           # 简要架构描述
    
    # 执行计划
    mvp_features: list[str]     # MVP该做哪些功能
    timeline: str               # "2-3 天可出 MVP"
    difficulty: str             # easy / medium / hard
    
    # GitHub 优化建议
    repo_structure: str         # 推荐目录结构
    readme_strategy: str        # README 该怎么写
    naming_tips: str            # 命名建议
    
    # 脚手架文件
    scaffold_files: dict[str, str]  # {"README.md": "...", "main.py": "..."}
```

**LLM 生成 Prompt 要点**：

- 要求 LLM 参考当前 GitHub Trending 上已火的项目特征
- 要求每个建议都附差异化分析（我们能比现有项目好在哪）
- 要求生成可直接写入文件的项目脚手架代码
- 要求给出 README 营销文案（好的 README = star 的关键）

---

### 建议生成器目标分两类：

| 类型 | 频率 | 内容 |
|------|------|------|
| **日报** | 每日 | 3-5 个项目建议 (轻量级，抓热点) |
| **周报** | 每周一 | 8-12 个建议 + 趋势总结 + 上周回顾 |

---

### 3.4 推送与分发层 (Pusher)

**三种分发渠道**：

1. **消息推送** (QQ Bot / Telegram Bot)
   - 日报：精简摘要 (3-5 个建议，每个 3-5 行)
   - 周报：完整报告摘要 + 链接

2. **GitHub 仓库自动同步**
   - 仓库 `trend-radar-reports` 存放所有报告
   - 目录结构 `reports/2025-06-25/daily.md`
   - 项目脚手架放到 `scaffolds/2025-06-25/{project-name}/`

3. **Web 前端仪表盘** ⭐（核心卖点）
   - 精美的单页应用，展示每日/每周趋势报告
   - 可以浏览历史报告
   - 可以一键下载项目脚手架
   - 实时热度可视化

---

### 3.5 Web 前端仪表盘

**技术**：FastAPI 后端 + 原生 HTML/CSS/JS（不引入重前端框架，保持轻量）

**页面结构**：

```
TrendRadar Dashboard
├── 首页 (Dashboard)
│   ├── 今日概览卡片 (今日热点数、建议数、趋势方向)
│   ├── 热点趋势图 (最近 7 天热度走势)
│   └── 今日推荐项目卡片 (3-5 个)
│
├── 趋势详情 (Trends)
│   ├── 分源展示 (GitHub / HN / Reddit / Twitter / arXiv)
│   ├── 热度排行耄榜
│   └── 时间线视图
│
├── 项目建议 (Suggestions)
│   ├── 建议列表 (卡片式)
│   ├── 建议详情 (展开后的完整分析)
│   └── 一键下载脚手架
│
├── 历史报告 (Archive)
│   ├── 按日期浏览
│   └── 周报汇总
│
└── 关于 (About)
```

**设计风格**：

- 深色主题 (dark mode default) + 渐变色点缀
- 卡片式布局，hover 效果
- 热度进度条 + 词云 + 简洁图表 (Chart.js)
- 响应式设计，移动端友好

---

## 四、项目目录结构

```
trend-radar/
├── README.md
├── pyproject.toml              # 项目配置 (用 uv 或 pip)
├── requirements.txt
├── .env.example                # 环境变量模板
├── config.yaml                 # 主配置文件
│
├── trend_radar/                 # 主包
│   ├── __init__.py
│   ├── config.py               # 配置加载
│   ├── models.py               # 数据模型 (dataclass)
│   ├── db.py                   # SQLite 数据库操作
│   │
│   ├── collectors/             # 数据采集层
│   │   ├── __init__.py
│   │   ├── base.py             # BaseCollector 抽象类
│   │   ├── github_trending.py
│   │   ├── hackernews.py
│   │   ├── reddit.py
│   │   ├── twitter_ai.py
│   │   └── arxiv_papers.py
│   │
│   ├── analyzer/               # 趋势分析层
│   │   ├── __init__.py
│   │   ├── aggregator.py       # 数据聚合 + 去重
│   │   ├── llm_client.py       # NewAPI 调用封装
│   │   └── trend_analyzer.py   # LLM 趋势分析
│   │
│   ├── generator/              # 项目建议生成层
│   │   ├── __init__.py
│   │   ├── suggestion_engine.py
│   │   ├── scaffold_builder.py # 脚手架生成
│   │   └── templates/          # Jinja2 模板
│   │       ├── README.md.j2
│   │       ├── main.py.j2
│   │       ├── pyproject.toml.j2
│   │       └── ...
│   │
│   ├── pusher/                 # 推送层
│   │   ├── __init__.py
│   │   ├── message_formatter.py
│   │   ├── qq_bot.py
│   │   ├── telegram_bot.py
│   │   └── github_sync.py
│   │
│   ├── web/                    # Web 前端
│   │   ├── __init__.py
│   │   ├── app.py              # FastAPI 应用
│   │   ├── api.py              # REST API 路由
│   │   ├── static/
│   │   │   ├── css/
│   │   │   │   └── style.css
│   │   │   ├── js/
│   │   │   │   └── app.js
│   │   │   └── img/
│   │   └── templates/
│   │       ├── base.html
│   │       ├── dashboard.html
│   │       ├── trends.html
│   │       ├── suggestions.html
│   │       └── archive.html
│   │
│   └── scheduler.py            # 定时任务调度
│
├── data/                       # 运行时数据 (gitignored)
│   ├── trend_radar.db          # SQLite 数据库
│   └── reports/                # 生成的报告
│       └── 2025-06-25/
│           ├── daily.md
│           └── scaffolds/
│               └── {project}/
│
├── scripts/
│   ├── run_daily.py            # 手动触发日报
│   ├── run_weekly.py           # 手动触发周报
│   └── init_db.py              # 初始化数据库
│
└── tests/
    └── ...
```

---

## 五、配置系统 (config.yaml)

```yaml
# TrendRadar 配置

# 数据采集
collectors:
  github_trending:
    enabled: true
    languages: ["python", "typescript", "rust", "go"]  # 空列表 = 全部
    since: "daily"  # daily / weekly
  hackernews:
    enabled: true
    min_points: 100
    ai_keywords: ["AI", "LLM", "GPT", "agent", "model", "transformer"]
  reddit:
    enabled: true
    subreddits: ["MachineLearning", "artificial", "LocalLLaMA"]
    limit: 25
  twitter:
    enabled: true
    accounts: ["@karpathy", "@_jasonwei", "@swyxk", "@cxiao"]
    method: "nitter"  # nitter / api
  arxiv:
    enabled: true
    categories: ["cs.AI", "cs.CL", "cs.LG"]
    max_results: 30

# LLM 分析
llm:
  api_base: "http://localhost:3002/v1"  # NewAPI 地址
  api_key: "${NEWAPI_KEY}"               # 从环境变量读取
  model: "gpt-5.4-mini"
  temperature: 0.7
  max_tokens: 8000

# 生成器
generator:
  daily_suggestions: 5     # 日报生成几个建议
  weekly_suggestions: 12   # 周报生成几个建议
  generate_scaffold: true  # 是否生成脚手架代码
  languages: ["python"]    # 脚手架默认语言

# 推送
pusher:
  qq_bot:
    enabled: true
    webhook: "${QQ_BOT_WEBHOOK}"
  telegram:
    enabled: true
    bot_token: "${TG_BOT_TOKEN}"
    chat_id: "${TG_CHAT_ID}"
  github:
    enabled: true
    token: "${GH_TOKEN}"
    repo: "your-username/trend-radar-reports"

# 定时任务
scheduler:
  daily:
    enabled: true
    cron: "0 8 * * *"       # 每天早上8点 (系统时区)
  weekly:
    enabled: true
    cron: "0 9 * * 1"      # 每周一早上9点

# Web 服务
web:
  host: "0.0.0.0"
  port: 8088
```

---

## 六、执行计划

### Phase 1：核心骨架 (MVP)
- [ ] 项目结构搭建
- [ ] 配置系统
- [ ] SQLite 数据库 schema
- [ ] GitHub Trending 采集器
- [ ] Hacker News 采集器
- [ ] arXiv 采集器
- [ ] LLM 调用封装 (NewAPI)
- [ ] 基础趋势分析 + 日报生成
- [ ] Markdown 报告输出

### Phase 2：数据源扩展
- [ ] Reddit 采集器
- [ ] Twitter/X 采集器
- [ ] 数据聚合与去重算法
- [ ] 周报汇总生成

### Phase 3：项目建议 + 脚手架
- [ ] 项目建议生成引擎
- [ ] Jinja2 脚手架模板
- [ ] 一键生成脚手架骨架代码
- [ ] README 营销文案生成

### Phase 4：推送与分发
- [ ] 报告消息格式化
- [ ] QQ Bot 推送
- [ ] Telegram Bot 推送
- [ ] GitHub 仓库自动同步报告

### Phase 5：Web 前端仪表盘
- [ ] FastAPI 后端 API
- [ ] 精美前端页面
- [ ] 热度可视化图表
- [ ] 历史报告浏览
- [ ] 脚手架下载

### Phase 6：定时调度与生产化
- [ ] APScheduler 集成
- [ ] 错误重试与日志
- [ ] Dockerfile + docker-compose
- [ ] systemd 部署

---

## 七、关键设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 语言 | Python | 生态最全 (爬虫/LLM/Web全覆盖)，开发速度快 |
| 数据库 | SQLite | 轻量，无需额外服务，单文件备份方便 |
| LLM 接入 | 复用 NewAPI | 成本低，已有基础设施，模型灵活切换 |
| 前端框架 | 原生 HTML/CSS/JS + Chart.js | 保持轻量，项目本身就是工具类，不能太重 |
| 模板引擎 | Jinja2 | Python 生态标准选择，生成脚手架天然适合 |
| 定时调度 | APScheduler | 纯 Python，轻量，够用 |
| 推送协议 | QQ Bot + Telegram Bot | 用户已有这些渠道 |

---

## 八、GitHub "火起来"策略 (内置在 LLM Prompt 中)

系统在生成项目建议时，会内置以下 "star 增长" 策略：

1. **命名策略**：
   - 短小好记 (≤15 字符)
   - 能直觉暗示功能 (如 "lolcat-ai")
   - 检查 GitHub 无同名热门项目

2. **README 策略**：
   - 第一行 = 亮点 tagline
   - Top: GIF/动图演示 (最高 star 增长因子)
   - 一键安装命令 (`pip install` 或 `curl`)
   - 使用场景 + 对比表格 (vs 现有方案)
   - 徽章 shield.io (stars, license, version)

3. **时机策略**：
   - 蹭热点论文 (arXiv 上发布 <7 天的论文)
   - 补空白 (有讨论无实现的需求)
   - 跨界组合 (AI + 传统领域)

4. **病毒式传播因子**：
   - CLI 工具 > Web 应用 > 库 (star 增长速度)
   - 视觉冲击力 (终端动画/网页 demo)
   - 低门槛 (一行命令能用起来)
   - 有趣 > 有用 (带梗/玩存在于趋势词)

---

## 九、技术选型总结

| 组件 | 技术 | 版本 |
|------|------|------|
| 语言 | Python | 3.11+ |
| HTTP 客户端 | httpx | 同步+异步 |
| HTML 爬取 | BeautifulSoup4 + lxml | |
| 模板 | Jinja2 | |
| Web 框架 | FastAPI + Uvicorn | |
| 前端图表 | Chart.js (CDN) | |
| 定时任务 | APScheduler | |
| 数据库 | SQLite (stdlib sqlite3) | |
| LLM SDK | openai (指向 NewAPI) | |
| 配置 | YAML (PyYAML) | |
| 日志 | loguru | |

---

*最后更新: 2026-06-25*