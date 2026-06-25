# TrendRadar 优化 Spec & Plan

> 在新会话中执行：让 agent 读取此文件，然后按 Plan 逐项实施。
> 项目路径: `/root/workspace/trend-radar/`
> Docker 部署: `docker compose up -d --build` (改完代码后需重建)

---

## 用户反馈 (6 项)

### 1. 登录按钮很突兀
- 登录页按钮样式跟整体 Linear 暗色主题不协调，看起来像硬塞上去的
- 需要检查 `trend_radar/web/templates/login.html` 的按钮样式，调整到跟整体设计一致
- 参考 Linear 设计系统: 按钮应该用 `rgba(255,255,255,0.02)` 背景 + 半透明边框，品牌色 `#5e6ad2` 只用于 hover 状态，不要一上来就是一个大蓝按钮

### 2. 前端需要白天主题
- 当前只有暗色主题 (Linear dark)，需要增加亮色主题切换
- 顶部栏或侧边栏加一个主题切换开关 (🌙/☀️)
- 亮色主题参考 Linear 的 light mode tokens:
  - 背景: `#f7f8f8`, `#f3f4f5`, `#ffffff`
  - 文字: `#171717`, `#5d5d5d`, `#8a8f98`
  - 边框: `#d0d6e0`, `#e6e6e6`
- 主题选择持久化到 `localStorage`
- CSS 用 `[data-theme="light"]` 覆盖 `:root` 变量

### 3. 设置界面
- 新增 `/settings` 页面，侧边栏加入口
- 设置项分两组:
  **AI 配置:**
  - API Base URL (当前: https://x666.me)
  - API Key (密码框，不回显)
  - 模型名称 (当前: glm-5.2)
  - 保存后写入 .env 并重启容器
  **采集配置:**
  - 日报建议数量 (当前: 3)
  - GitHub 采集语言 (当前: python)
  - HN 最低热度分 (当前: 100)
  - arXiv 分类 (当前: cs.AI, cs.CL, cs.LG)
  - Reddit 子版列表
  - Twitter 开关
- 设置通过 `GET/POST /api/settings` 读写
- 后端: 新增 `trend_radar/web/settings_api.py`，读写 config.yaml + .env

### 4. 切换页面很慢/转圈圈不出结果
- 趋势详情页 (`/trends`) 请求 `/api/trends/{date}` 返回数据量大 (266条)，前端渲染慢
- 优化方案:
  - API 端分页: `/api/trends/{date}?page=1&limit=50`
  - 前端虚拟滚动或懒加载
  - 按数据源分 tab，默认只加载第一个 tab
  - 加 loading 进度提示 (不是空白转圈，显示"正在加载 GitHub 数据...")

### 5. 项目建议为空 ("暂无建议")
- 原因: LLM (glm-5.2) 生成项目建议时返回的 JSON 被截断，解析失败
- 已做的修复: JSON 解析器增强容错 (尾部逗号、括号补全)
- 还需要做的:
  - 减小单次请求的输出量: 每次只生成 1 个建议 (循环调用 N 次)
  - 给 suggestion_engine 的 prompt 增加明确约束: "scaffold_files 中的代码不要超过 50 行"
  - 增加 max_tokens 到 12000 (当前 8000 可能不够)
  - 失败时记录 LLM 原始返回到日志，方便排查
  - 前端显示"建议生成中..."而不是直接显示空

### 6. 没有手动触发按钮
- 仪表盘页面需要加一个"立即运行日报"按钮
- 点击后调用 `POST /api/trigger/daily` (带 Bearer token)
- 按钮状态: 待机 → 运行中(转圈+禁用) → 完成(显示结果摘要) → 失败(显示错误)
- 运行中显示进度: "采集中..." → "分析中..." → "生成建议中..." → "完成"
- 可以通过 WebSocket 或轮询 `/api/health` + 结果接口实现进度反馈
- 简单方案: 按钮点击后 fetch POST，等待响应，期间显示 loading

---

## 实施计划

### Phase 1: 前端体验 (优先级最高)
1. 修复登录页按钮样式 → Linear 风格 ghost button
2. 增加亮色主题 + 切换开关
3. 仪表盘加"立即运行日报"按钮 + loading 状态
4. 趋势详情页分页/分 tab 优化

### Phase 2: 设置界面
5. 新增 `/settings` 页面 + 侧边栏入口
6. 后端 `GET/POST /api/settings` 读写配置
7. AI 配置修改后写入 .env 并重启容器

### Phase 3: 项目建议生成修复
8. suggestion_engine: 每次只生成 1 个建议，循环调用
9. LLM prompt: 限制 scaffold 代码长度
10. max_tokens 增加到 12000
11. 失败时记录原始返回

### Phase 4: 验证
12. Docker 重建
13. 登录 → 仪表盘 → 点击运行日报 → 查看建议
14. 切换主题 → 趋势详情 → 设置页面

---

## 关键文件

| 文件 | 用途 |
|------|------|
| `trend_radar/web/templates/login.html` | 登录页 (改按钮样式) |
| `trend_radar/web/templates/dashboard.html` | 仪表盘 (加运行按钮) |
| `trend_radar/web/templates/settings.html` | 新建: 设置页面 |
| `trend_radar/web/static/css/style.css` | 加亮色主题变量 |
| `trend_radar/web/static/js/app.js` | 加主题切换 + 运行按钮 + 分页 |
| `trend_radar/web/app.py` | 加 /settings 路由 + /api/settings 端点 |
| `trend_radar/generator/suggestion_engine.py` | 改为逐个生成 |
| `trend_radar/analyzer/llm_client.py` | max_tokens 12000 |
| `config.yaml` | 配置项 |
| `.env` | AI 密码等 |

## 当前部署信息
- 容器: `trend-radar` (docker compose)
- 端口: 8088
- 密码: `trendradar2026`
- 模型: `glm-5.2`
- API: `https://x666.me`
- 数据库: `/app/data/trend_radar.db` (volume mount: `./data:/app/data`)
- 开机自启: systemd `trend-radar.service` → `docker compose up -d`