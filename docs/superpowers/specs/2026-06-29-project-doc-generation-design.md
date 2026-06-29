# 项目建议「完整项目 MD 文档」生成 设计文档

- 日期：2026-06-29
- 范围：TrendRadar 项目建议详情页

## 背景

当前项目建议链路分三层（刻意分层以规避 LLM JSON 截断）：

1. `generate_suggestions()` — 日报主流程，**轻量**：只产出基础 + 市场 + 技术分析，刻意不出架构 / 脚手架（`key_features` 仅一串短词）。
2. `generate_architecture()` — 详情页按需点按钮 → `{architecture, repo_structure}`。
3. `generate_readme_strategy()` — 详情页按需点按钮 → `{readme_strategy, naming_tips}`。

用户反馈两点：

- A. 建议里「功能模块」描述不够清晰 / 详细。
- B. 在「架构与目录结构」之上，还要一份「完整项目 MD 文档」，把架构 + 各功能模块及职责 + 做什么全整合进去，**详细到能直接交给 Claude Code / Codex 搭项目**。

## 决策汇总

| # | 决策 |
|---|---|
| 1 | 详细功能模块**只在新生成的 MD 文档里**产出，日报主流程保持轻量不动。 |
| 2 | **单次 LLM 调用产出整篇 Markdown**，返回 `{project_doc: "...markdown..."}`。 |
| 3 | 生成时**有就用、没有就略**已有 architecture / readme 作为上下文，由 AI 统筹重写进 MD（不机械复制）。 |
| 4 | 存入 `full_data.project_doc`（与 architecture / readme 并列），**不动 DB schema**。 |
| 5 | 前端：内联卡片 + 生成按钮 + 下载 / 复制按钮（与现有 section 同构）。 |
| 6 | 长文档用后端 `markdown` 库渲染成 HTML（新增依赖 `markdown>=3.5`）。 |

## 详细设计

### 1. 数据 / 存储

- `ProjectSuggestion` dataclass 新增字段 `project_doc: str = ""`（纯 markdown 字符串）。
- 纯内存模型字段，**不改 DB 表**：与 `architecture` / `readme_strategy` 一样存在 `suggestions.full_data` 这个 JSON 列里。
- `_parse_suggestion` 增加 `project_doc=data.get("project_doc", "")`，兼容历史数据（历史数据该字段为空，走按需生成）。

### 2. 引擎函数 `generate_project_doc()`（`trend_radar/generator/suggestion_engine.py`）

- 新增 `generate_project_doc(suggestion: ProjectSuggestion, existing_context: dict) -> str`，返回**纯 markdown 字符串**。
- **关键**：用 `llm.chat()`（返回原始文本），**不走 `chat_json`** —— markdown 不需要 JSON 解析，从根上规避 JSON 截断 / `_parse_json` 兜底问题。
- prompt 输入：
  - 建议本身：`name` / `tagline` / `description` / `tech_stack` / `key_features` / `mvp_features` / `timeline` / `target_audience`。
  - `existing_context`（已生成的 architecture / repo_structure / readme_strategy / naming_tips，有就拼进去，空就略）。
- prompt 要求输出的 MD 章节结构（「详细到能给 AI 搭项目」的核心）：
  1. 项目概述（一句话定位 + 解决什么问题 + 目标用户）
  2. **核心功能模块**（每个模块：名称 / 职责 / 做什么 / 输入输出 / 依赖哪些其他模块）— 回应诉求 A
  3. 技术架构（模块划分 + 数据流 + 技术选型理由）
  4. 目录结构（带注释的目录树）
  5. 数据模型 / 关键接口
  6. 技术栈
  7. MVP 实现计划（里程碑 / 每步交付物）
  8. README 要点 & 命名建议
  9. **给 AI 编码助手的执行指引**（如何启动、先做哪块、注意事项）— 专门为 Claude Code / Codex 写
- `max_tokens`：复用默认 12000，单篇 MD 通常足够。

### 3. API（`trend_radar/web/api.py`）

- 新增 `POST /api/suggestion/{id}/project-doc`，结构与现有 `gen_suggestion_architecture` 完全平行：调 `generate_project_doc` → `full.update({"project_doc": ...})` → `db.update_suggestion_full_data` → 返回 `{project_doc, project_doc_html}`。
- 复用现成的 `_generate_and_store` 模式，新增 `"project_doc"` 分支。
- 新增小工具 `markdown_to_html(md: str) -> str`：用 `markdown` 库 + `fenced_code` 扩展，输出安全 HTML。
  - 在 POST 返回和 GET `/suggestion/{id}` 两处都用它生成 `project_doc_html`。
- 所有写操作走 `require_auth`，与现有一致。

### 4. 前端（`trend_radar/web/static/js/app.js`）

- `loadSuggestionDetail` 在「架构与目录结构」「README 营销策略」之后，新增第三个 section：「**完整项目文档**」，按钮「✨ 生成完整项目文档」。
- 复用 `genSectionHTML` + `_genSection`：点按钮 → 调 `/project-doc` → 把返回的 `project_doc_html` 内联渲染。
- section 内额外两个按钮（仅在已生成时显示）：
  - **⬇ 下载 .md**：把 `project_doc`（原始 markdown）做成 Blob 下载，文件名 `项目文档_{name}.md` — 兑现「直接给 Claude Code / Codex」。
  - **📋 复制**：`navigator.clipboard.writeText(project_doc)`。
- `window.genProjectDoc = (btn) => _genSection(btn, 'project-doc')`，与 `genArchitecture` / `genReadme` 同构。
- 详情页加载时若已有 `project_doc`，直接渲染 HTML + 下载 / 复制按钮（不重复调 AI）。

### 5. 依赖

- `requirements.txt` 新增 `markdown>=3.5`。

### 6. 不在本次范围

- 列表页「导出」（多建议摘要 MD）不动。
- 日报主流程的 `key_features` 不升级（决策 1）。
- 不做单独表 / schema 迁移。

## 改动文件清单

1. `trend_radar/models.py` — +1 字段
2. `trend_radar/generator/suggestion_engine.py` — +`generate_project_doc` + prompt
3. `trend_radar/analyzer/llm_client.py` — `chat()` 加可选 `max_tokens`
4. `trend_radar/web/api.py` — +端点 + `markdown_to_html` + GET 注入 html
5. `trend_radar/web/static/js/app.js` — 详情页 +1 section + 下载 / 复制
6. `requirements.txt` — +1 依赖

## 风险与对策

- **单次输出偏长可能被截断**：markdown 为纯文本，不受 JSON 截断逻辑影响；`max_tokens=12000` 单篇 MD 足够。前端检测空内容时给出提示。
- **历史数据无 `project_doc` 字段**：`_parse_suggestion` 默认空串，前端走「点按钮生成」路径，无需迁移。
- **markdown 渲染安全**：`markdown` 库默认禁用 raw HTML，配合 `fenced_code` 扩展即可，不引入 XSS 风险。
