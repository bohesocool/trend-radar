# 完整项目 MD 文档生成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在项目建议详情页新增「完整项目文档」按需生成能力，产出一份详细到可直接交给 Claude Code / Codex 搭项目的 Markdown 文档（含各功能模块职责），支持在线预览与下载。

**Architecture:** 复用现有「架构 / README」按需生成模式：后端单次 LLM 调用产出纯 Markdown（走 `chat()` 不走 `chat_json`，规避 JSON 截断），存入 `full_data.project_doc`（不动 DB schema）；后端用 `markdown` 库渲染成 HTML 返回前端；前端详情页加第三个 section，内联渲染 HTML + 下载 / 复制按钮。生成时把已有的 architecture / readme 作为上下文喂给 AI，由其统筹重写进整篇文档。

**Tech Stack:** Python 3.10 / FastAPI / openai SDK / markdown 库（已装 3.4.1）/ 原生 JS SPA。

**关键背景（务必先读）：**
- 分层生成刻意存在（`suggestion_engine.py` 顶部注释）：`generate_suggestions()` 轻量、`generate_architecture()` / `generate_readme_strategy()` 按需。本次新增的 `generate_project_doc()` 与后两者同层。
- `LLMClient.chat()`（`llm_client.py`）返回原始文本；`chat_json()` 才走 JSON 解析 + 截断兜底。**本次必须用 `chat()`**。
- `full_data` 是 `suggestions` 表的一个 JSON 列，按需生成的 architecture / readme_strategy 等都塞这里，无需建表。
- 前端详情页 `genSectionHTML` + `_genSection` 会把内容经 `renderTextBlock` → `esc()` 转义，**不能用于 HTML 内容**。`project_doc_html` 是预渲染 HTML，必须用专属渲染路径。
- 静态资源带版本号指纹（`app.py:_compute_asset_version`），改 CSS/JS 后 URL 自动换号，无需手动刷新缓存。

---

## 文件结构

| 文件 | 责任 | 动作 |
|---|---|---|
| `requirements.txt` | 声明 markdown 依赖 | 改 |
| `trend_radar/models.py` | `ProjectSuggestion` 加 `project_doc` 字段 | 改 |
| `trend_radar/analyzer/llm_client.py` | `chat()` 加可选 `max_tokens` | 改 |
| `trend_radar/generator/suggestion_engine.py` | +`generate_project_doc` +`_build_project_doc_prompt` + prompt | 改 |
| `trend_radar/web/api.py` | +`markdown_to_html` +POST 端点 +GET 注入 html +`_generate_and_store` 分支 | 改 |
| `trend_radar/web/static/js/app.js` | 详情页 +1 section +专属渲染 +下载/复制 | 改 |
| `trend_radar/web/static/css/style.css` | `.markdown-body` 排版样式 | 改 |
| `tests/test_project_doc.py` | 纯逻辑单元测试 | 建文件 |

测试策略：本仓库**无测试目录**，本次引入轻量 `tests/`，只覆盖**纯逻辑**（markdown 渲染、prompt 构造、模型解析、LLM 调用 monkeypatch），不触碰 DB / 鉴权 / 真 LLM。端点与 UI 用手动验证。

---

### Task 1: 添加 markdown 依赖并实现 `markdown_to_html`

**Files:**
- Modify: `requirements.txt`
- Modify: `trend_radar/web/api.py:1-16`（顶部 import 区）
- Create: `tests/test_project_doc.py`

- [ ] **Step 1: 在 requirements.txt 的 Utils 段加依赖**

把 `requirements.txt` 的最后一段改为：

```
# Utils
python-dotenv>=1.0
feedparser>=6.0      # arXiv RSS / Reddit RSS
markdown>=3.4        # 项目文档 Markdown → HTML 渲染
```

- [ ] **Step 2: 写失败测试 `markdown_to_html`**

创建 `tests/test_project_doc.py`：

```python
"""项目文档生成相关单元测试（纯逻辑，不碰 DB / 鉴权 / 真 LLM）。"""

from trend_radar.web.api import markdown_to_html


def test_markdown_to_html_renders_headings_lists_code():
    md = "# 标题\n\n- 条目一\n- 条目二\n\n```python\nprint(1)\n```"
    html = markdown_to_html(md)
    assert "<h1>标题</h1>" in html
    assert "<li>条目一</li>" in html
    assert "<li>条目二</li>" in html
    assert "<pre>" in html and "print(1)" in html


def test_markdown_to_html_renders_tables():
    md = "| A | B |\n|---|---|\n| 1 | 2 |\n"
    html = markdown_to_html(md)
    assert "<table>" in html
    assert "<td>1</td>" in html


def test_markdown_to_html_escapes_raw_html_by_default():
    md = "正文 <script>alert(1)</script>"
    html = markdown_to_html(md)
    assert "<script>alert(1)</script>" not in html  # 默认转义，不产出可执行标签


def test_markdown_to_html_empty_input():
    assert markdown_to_html("") == ""
    assert markdown_to_html(None) == ""
```

- [ ] **Step 3: 运行测试，确认失败**

Run: `python -m pytest tests/test_project_doc.py -v`
Expected: FAIL — `ImportError: cannot import name 'markdown_to_html'`

- [ ] **Step 4: 实现 `markdown_to_html`**

在 `trend_radar/web/api.py` 顶部 import 区，把现有的：

```python
import dataclasses
import json
from datetime import datetime
from typing import Any
```

改为：

```python
import dataclasses
import json
from datetime import datetime
from typing import Any

import markdown as md_lib
```

然后在 `router = APIRouter(prefix="/api")` 这一行**之前**，插入工具函数：

```python
def markdown_to_html(md_text: str | None) -> str:
    """把 Markdown 文本渲染成安全 HTML（启用 fenced_code 与 tables 扩展）。

    Python-Markdown 默认转义原始 HTML，因此不会产出 <script> 等可执行标签。
    用于详情页「完整项目文档」的在线预览。
    """
    if not md_text:
        return ""
    return md_lib.markdown(
        md_text,
        extensions=["fenced_code", "tables", "nl2br"],
        output_format="html",
    )
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `python -m pytest tests/test_project_doc.py -v`
Expected: PASS（4 passed）

- [ ] **Step 6: 提交**

```bash
git add requirements.txt trend_radar/web/api.py tests/test_project_doc.py
git commit -m "feat(api): 添加 markdown_to_html 工具函数与 markdown 依赖"
```

---

### Task 2: 给 `ProjectSuggestion` 加 `project_doc` 字段

**Files:**
- Modify: `trend_radar/models.py:62-91`
- Modify: `trend_radar/generator/suggestion_engine.py:305-324`（`_parse_suggestion`）
- Test: `tests/test_project_doc.py`

- [ ] **Step 1: 写失败测试（模型字段 + 解析默认值）**

在 `tests/test_project_doc.py` 顶部 import 区追加：

```python
from trend_radar.generator.suggestion_engine import _parse_suggestion
```

在文件末尾追加：

```python
def test_parse_suggestion_reads_project_doc():
    s = _parse_suggestion({"name": "foo", "project_doc": "# Hello"})
    assert s.project_doc == "# Hello"


def test_parse_suggestion_project_doc_defaults_empty():
    s = _parse_suggestion({"name": "foo"})
    assert s.project_doc == ""
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_project_doc.py -v`
Expected: FAIL — `AttributeError`（`ProjectSuggestion` 无 `project_doc`）或 dataclass 不接受该 kwarg。

- [ ] **Step 3: 给模型加字段**

在 `trend_radar/models.py` 的 `ProjectSuggestion` 中，把 `# GitHub 优化` 段：

```python
    # GitHub 优化
    repo_structure: str = ""
    readme_strategy: str = ""
    naming_tips: str = ""
```

改为：

```python
    # GitHub 优化
    repo_structure: str = ""
    readme_strategy: str = ""
    naming_tips: str = ""

    # 完整项目文档（纯 Markdown，按需生成，存于 full_data）
    project_doc: str = ""
```

- [ ] **Step 4: 在 `_parse_suggestion` 里解析该字段**

在 `trend_radar/generator/suggestion_engine.py` 的 `_parse_suggestion`，把：

```python
        readme_strategy=data.get("readme_strategy", ""),
        naming_tips=data.get("naming_tips", ""),
    )
```

改为：

```python
        readme_strategy=data.get("readme_strategy", ""),
        naming_tips=data.get("naming_tips", ""),
        project_doc=data.get("project_doc", ""),
    )
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `python -m pytest tests/test_project_doc.py -v`
Expected: PASS（6 passed）

- [ ] **Step 6: 提交**

```bash
git add trend_radar/models.py trend_radar/generator/suggestion_engine.py tests/test_project_doc.py
git commit -m "feat(models): ProjectSuggestion 增加 project_doc 字段"
```

---

### Task 3: `LLMClient.chat()` 支持可选 `max_tokens`

**Files:**
- Modify: `trend_radar/analyzer/llm_client.py:27-56`
- Test: `tests/test_project_doc.py`

- [ ] **Step 1: 写失败测试（max_tokens 透传到 API 调用）**

在 `tests/test_project_doc.py` 顶部 import 区追加：

```python
from unittest.mock import MagicMock

from trend_radar.analyzer.llm_client import LLMClient
```

在文件末尾追加：

```python
def test_chat_passes_explicit_max_tokens():
    """显式传入 max_tokens 时，应覆盖实例默认值传给 API。"""
    client = LLMClient()
    client.client = MagicMock()
    fake_choice = MagicMock()
    fake_choice.message.content = "hello"
    client.client.chat.completions.create.return_value = MagicMock(choices=[fake_choice])

    client.chat("sys", "usr", max_tokens=8000)

    _, kwargs = client.client.chat.completions.create.call_args
    assert kwargs["max_tokens"] == 8000


def test_chat_uses_default_max_tokens_when_omitted():
    client = LLMClient()
    client.client = MagicMock()
    fake_choice = MagicMock()
    fake_choice.message.content = "hello"
    client.client.chat.completions.create.return_value = MagicMock(choices=[fake_choice])

    client.chat("sys", "usr")

    _, kwargs = client.client.chat.completions.create.call_args
    assert kwargs["max_tokens"] == client.max_tokens
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_project_doc.py -v`
Expected: FAIL — `TypeError: chat() got an unexpected keyword argument 'max_tokens'`

- [ ] **Step 3: 改 `chat()` 签名与调用**

在 `trend_radar/analyzer/llm_client.py`，把：

```python
    def chat(self, system_prompt: str, user_prompt: str, max_retries: int = 2) -> str:
        """调用 chat completions，返回文本响应。失败自动重试。"""
        for attempt in range(max_retries + 1):
            try:
                logger.debug(f"LLM 调用 (attempt {attempt+1}): model={self.model}, system_len={len(system_prompt)}")
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    timeout=120,
                )
```

改为：

```python
    def chat(
        self, system_prompt: str, user_prompt: str, max_retries: int = 2, max_tokens: int | None = None
    ) -> str:
        """调用 chat completions，返回文本响应。失败自动重试。

        max_tokens: 显式覆盖实例默认上限（用于需要更长输出的单次调用，如整篇项目文档）。
        """
        effective_max_tokens = max_tokens if max_tokens is not None else self.max_tokens
        for attempt in range(max_retries + 1):
            try:
                logger.debug(f"LLM 调用 (attempt {attempt+1}): model={self.model}, system_len={len(system_prompt)}")
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=self.temperature,
                    max_tokens=effective_max_tokens,
                    timeout=120,
                )
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/test_project_doc.py -v`
Expected: PASS（8 passed）

- [ ] **Step 5: 提交**

```bash
git add trend_radar/analyzer/llm_client.py tests/test_project_doc.py
git commit -m "feat(llm): chat() 支持可选 max_tokens 覆盖"
```

---

### Task 4: 实现 `generate_project_doc` 与 prompt 构造

**Files:**
- Modify: `trend_radar/generator/suggestion_engine.py`（文件末尾追加）
- Test: `tests/test_project_doc.py`

- [ ] **Step 1: 写失败测试（prompt 构造 + LLM 调用）**

在 `tests/test_project_doc.py` 顶部 import 区追加：

```python
import trend_radar.generator.suggestion_engine as se
from trend_radar.models import ProjectSuggestion
```

在文件末尾追加：

```python
_EMPTY_CTX = {"architecture": "", "repo_structure": "", "readme_strategy": "", "naming_tips": ""}


def _suggestion():
    return ProjectSuggestion(
        name="trend-radar",
        tagline="一句话亮点",
        category="web",
        description="项目描述",
        tech_stack=["Python", "FastAPI"],
        key_features=["功能A", "功能B"],
        mvp_features=["MVP1"],
        timeline="2-3天",
        target_audience="开发者",
    )


def test_build_prompt_includes_name_and_features():
    prompt = se._build_project_doc_prompt(_suggestion(), _EMPTY_CTX)
    assert "trend-radar" in prompt
    assert "功能A" in prompt
    # 竦领性章节标题必须出现在 prompt 里
    assert "核心功能模块" in prompt
    assert "给 AI 编码助手的执行指引" in prompt


def test_build_prompt_includes_existing_context_when_present():
    ctx = {**_EMPTY_CTX, "architecture": "三层架构：采集层/分析层/展示层"}
    prompt = se._build_project_doc_prompt(_suggestion(), ctx)
    assert "三层架构：采集层/分析层/展示层" in prompt


def test_build_prompt_omits_context_block_when_empty():
    prompt = se._build_project_doc_prompt(_suggestion(), _EMPTY_CTX)
    # 已有上下文区块的标题不应出现
    assert "已有架构参考" not in prompt


def test_generate_project_doc_returns_chat_output(monkeypatch):
    """generate_project_doc 应直接返回 chat() 的原始 Markdown，并存入 project_doc。"""
    captured = {}

    class FakeLLM:
        def chat(self, system_prompt, user_prompt, max_retries=2, max_tokens=None):
            captured["user"] = user_prompt
            captured["max_tokens"] = max_tokens
            return "# 项目文档\n\n## 核心功能模块\n..."

    monkeypatch.setattr(se, "LLMClient", FakeLLM)

    md = se.generate_project_doc(_suggestion(), _EMPTY_CTX)
    assert md == "# 项目文档\n\n## 核心功能模块\n..."
    assert "trend-radar" in captured["user"]
    assert captured["max_tokens"] is not None  # 显式传了更大的上限
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_project_doc.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute '_build_project_doc_prompt'`

- [ ] **Step 3: 在 `suggestion_engine.py` 末尾追加 prompt 模板与函数**

在 `trend_radar/generator/suggestion_engine.py` 文件**末尾**（`_parse_suggestion` 之后）追加：

```python
# ===== 完整项目文档（按需生成，直接交付 AI 编码助手） =====

_PROJECT_DOC_SYSTEM_PROMPT = """你是一名资深软件架构师 + 技术文档作者。
基于给定的项目建议，输出一份完整、可落地的项目文档（Markdown 格式），详细到能直接交给 Claude Code / Codex 这类 AI 编码助手据此搭建整个项目。

直接输出 Markdown 正文，不要包裹在 ``` 代码块里，也不要输出任何 JSON 或额外解释。"""

_PROJECT_DOC_USER_TEMPLATE = """为以下项目撰写完整项目文档。

【项目建议】
- 名称：{name}
- 一句话：{tagline}
- 分类：{category}
- 描述：{description}
- 目标用户：{target_audience}
- 技术栈：{tech_stack}
- 核心功能：{key_features}
- MVP 功能：{mvp_features}
- 时间线：{timeline}
{existing_context}

文档必须包含以下章节，每节都要具体、可执行：

## 1. 项目概述
一句话定位、解决什么问题、目标用户是谁、为什么现在做。

## 2. 核心功能模块
逐个列出每个功能模块，每个模块写明：
- 模块名称
- 职责（这个模块负责什么）
- 做什么（具体行为 / 关键流程）
- 输入 / 输出
- 依赖哪些其他模块

## 3. 技术架构
模块如何划分与组合、数据流向、关键技术选型与理由。

## 4. 目录结构
用带注释的目录树表示，可直接照着建仓库。

## 5. 数据模型 / 关键接口
核心数据结构、对外接口（CLI 命令 / API 路径 / 函数签名），给出示例。

## 6. 技术栈
逐项列出依赖及其用途。

## 7. MVP 实现计划
分里程碑，每步给出交付物，先做什么后做什么。

## 8. README 要点 & 命名建议
首行 tagline、安装命令、使用示例、对比表格位置；命名是否合适及备选名。

## 9. 给 AI 编码助手的执行指引
写给 Claude Code / Codex：如何启动这个项目、第一步先实现哪块、有哪些注意事项与约定。"""


def _build_project_doc_prompt(suggestion: ProjectSuggestion, existing_context: dict[str, str]) -> str:
    """拼装生成完整项目文档的 user prompt。

    existing_context: full_data 中已存在的 architecture / repo_structure / readme_strategy /
    naming_tips。有则作为参考喂给 AI（让文档与已生成内容保持一致），全为空则不附。
    """
    arch = (existing_context.get("architecture") or "").strip()
    repo = (existing_context.get("repo_structure") or "").strip()
    readme = (existing_context.get("readme_strategy") or "").strip()
    naming = (existing_context.get("naming_tips") or "").strip()

    parts: list[str] = []
    if arch:
        parts.append(f"已有架构参考：\n{arch}")
    if repo:
        parts.append(f"已有目录结构参考：\n{repo}")
    if readme:
        parts.append(f"已有 README 策略参考：\n{readme}")
    if naming:
        parts.append(f"已有命名建议参考：\n{naming}")
    existing_block = ("\n" + "\n".join(parts) + "\n") if parts else ""

    return _PROJECT_DOC_USER_TEMPLATE.format(
        name=suggestion.name,
        tagline=suggestion.tagline,
        category=suggestion.category,
        description=suggestion.description,
        target_audience=suggestion.target_audience,
        tech_stack=", ".join(suggestion.tech_stack),
        key_features="、".join(suggestion.key_features),
        mvp_features="、".join(suggestion.mvp_features),
        timeline=suggestion.timeline,
        existing_context=existing_block,
    )


def generate_project_doc(suggestion: ProjectSuggestion, existing_context: dict[str, str]) -> str:
    """按需生成完整项目文档（纯 Markdown 字符串）。

    走 llm.chat() 而非 chat_json()：Markdown 是纯文本，不需要也不应经过 JSON 解析，
    从根上规避 JSON 截断 / _parse_json 兜底问题。

    existing_context: full_data 中已生成的 architecture / readme 等字段，有则作为上下文。
    """
    llm = LLMClient()
    prompt = _build_project_doc_prompt(suggestion, existing_context)
    # 整篇文档较长，显式放宽输出上限，避免被默认值截断
    return llm.chat(_PROJECT_DOC_SYSTEM_PROMPT, prompt, max_tokens=8000)
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/test_project_doc.py -v`
Expected: PASS（12 passed）

- [ ] **Step 5: 提交**

```bash
git add trend_radar/generator/suggestion_engine.py tests/test_project_doc.py
git commit -m "feat(generator): 新增 generate_project_doc 生成完整项目文档"
```

---

### Task 5: API 端点 + GET 注入 html + `_generate_and_store` 分支

**Files:**
- Modify: `trend_radar/web/api.py:85-96`（GET /suggestion）与 `:161-196`（架构/README 端点 + `_generate_and_store`）

- [ ] **Step 1: 让 `_generate_and_store` 支持 `project_doc` 分支**

在 `trend_radar/web/api.py` 的 `_generate_and_store`，把：

```python
def _generate_and_store(suggestion_id: int, kind: str) -> dict[str, Any]:
    from trend_radar.generator.suggestion_engine import (
        _parse_suggestion,
        generate_architecture,
        generate_readme_strategy,
    )

    row = db.get_suggestion_by_id(suggestion_id)
    if not row:
        raise HTTPException(status_code=404, detail="无此建议")
    full = json.loads(row.get("full_data", "{}"))
    suggestion = _parse_suggestion(full)

    try:
        if kind == "architecture":
            generated = generate_architecture(suggestion)
        else:
            generated = generate_readme_strategy(suggestion)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成失败: {e}")

    full.update(generated)
    db.update_suggestion_full_data(suggestion_id, full)
    return generated
```

改为：

```python
def _generate_and_store(suggestion_id: int, kind: str) -> dict[str, Any]:
    from trend_radar.generator.suggestion_engine import (
        _parse_suggestion,
        generate_architecture,
        generate_project_doc,
        generate_readme_strategy,
    )

    row = db.get_suggestion_by_id(suggestion_id)
    if not row:
        raise HTTPException(status_code=404, detail="无此建议")
    full = json.loads(row.get("full_data", "{}"))
    suggestion = _parse_suggestion(full)

    try:
        if kind == "architecture":
            generated = generate_architecture(suggestion)
            full.update(generated)
            db.update_suggestion_full_data(suggestion_id, full)
            return generated
        if kind == "readme":
            generated = generate_readme_strategy(suggestion)
            full.update(generated)
            db.update_suggestion_full_data(suggestion_id, full)
            return generated
        if kind == "project_doc":
            # 把已生成的 architecture / readme 等作为上下文喂给 AI，由其统筹重写进整篇文档
            md = generate_project_doc(suggestion, full)
            full["project_doc"] = md
            db.update_suggestion_full_data(suggestion_id, full)
            return {"project_doc": md, "project_doc_html": markdown_to_html(md)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成失败: {e}")

    raise HTTPException(status_code=400, detail=f"未知生成类型: {kind}")
```

- [ ] **Step 2: 新增 POST 端点**

在 `gen_suggestion_readme` 端点之后（`@router.post("/suggestion/{suggestion_id}/readme")` 函数之后、`_generate_and_store` 之前）插入：

```python
@router.post("/suggestion/{suggestion_id}/project-doc")
def gen_suggestion_project_doc(suggestion_id: int, auth: bool = Depends(require_auth)) -> dict[str, Any]:
    """按需生成完整项目文档（Markdown），存回 full_data 并返回 md + html。"""
    return _generate_and_store(suggestion_id, "project_doc")
```

- [ ] **Step 3: 在 GET /suggestion 注入 project_doc_html**

把 `get_suggestion`：

```python
@router.get("/suggestion/{suggestion_id}")
def get_suggestion(suggestion_id: int) -> dict[str, Any]:
    """获取单个项目建议的完整数据（供详情页使用）。"""
    row = db.get_suggestion_by_id(suggestion_id)
    if not row:
        raise HTTPException(status_code=404, detail="无此建议")
    full = json.loads(row.get("full_data", "{}"))
    full["id"] = row["id"]
    full["date"] = row["date"]
    full["pinned"] = bool(row.get("pinned"))
    return full
```

改为：

```python
@router.get("/suggestion/{suggestion_id}")
def get_suggestion(suggestion_id: int) -> dict[str, Any]:
    """获取单个项目建议的完整数据（供详情页使用）。"""
    row = db.get_suggestion_by_id(suggestion_id)
    if not row:
        raise HTTPException(status_code=404, detail="无此建议")
    full = json.loads(row.get("full_data", "{}"))
    full["id"] = row["id"]
    full["date"] = row["date"]
    full["pinned"] = bool(row.get("pinned"))
    if full.get("project_doc"):
        full["project_doc_html"] = markdown_to_html(full["project_doc"])
    return full
```

- [ ] **Step 4: 静态检查导入与语法**

Run: `python -c "from trend_radar.web import api; print('ok')"`
Expected: 输出 `ok`（确认无语法 / 导入错误）

- [ ] **Step 5: 提交**

```bash
git add trend_radar/web/api.py
git commit -m "feat(api): 新增 /suggestion/{id}/project-doc 端点与 html 注入"
```

---

### Task 6: 前端详情页「完整项目文档」section + 下载 / 复制

**Files:**
- Modify: `trend_radar/web/static/js/app.js`（`loadSuggestionDetail` 及其周边）

- [ ] **Step 1: 在详情页顶部加模块状态变量**

在 `app.js` 中（约 1002 行 `let _detailSuggestionId = null;` 处），把：

```js
let _detailSuggestionId = null;
```

改为：

```js
let _detailSuggestionId = null;
let _detailProjectDoc = '';      // 当前详情页已生成的项目文档原始 Markdown（供下载/复制）
let _detailProjectDocName = '';  // 项目名（用于下载文件名）
```

- [ ] **Step 2: 加 section HTML 构造与渲染函数**

在 `genSectionHTML` 函数**之后**（约 1036 行之后，`loadSuggestionDetail` 之前）插入：

```js
/** 「完整项目文档」section 专属渲染：HTML 内容不能走 renderTextBlock（会被 esc 转义）。 */
function renderProjectDocBody(mdHtml) {
  let html = `<div class="project-doc-toolbar">
    <button class="btn btn-ghost btn-sm" id="pd-download">⬇ 下载 .md</button>
    <button class="btn btn-ghost btn-sm" id="pd-copy">📋 复制</button>
  </div>`;
  html += `<div class="markdown-body">${mdHtml}</div>`;
  return html;
}

function genProjectDocSectionHTML(full) {
  const md = full.project_doc || '';
  let inner;
  if (md) {
    _detailProjectDoc = md;
    inner = renderProjectDocBody(full.project_doc_html || '');
  } else {
    inner = `<button class="btn btn-primary" onclick="genProjectDoc(this)">✨ 生成完整项目文档</button>
      <p class="text-tertiary" style="font-size:12px; margin-top:8px;">生成一份可直接交给 Claude Code / Codex 搭建项目的详细文档（含各功能模块职责），约 30-60 秒</p>`;
  }
  return `<div class="card detail-section">
    <div class="section-label">完整项目文档</div>
    <div class="detail-section-body">${inner}</div>
  </div>`;
}

function wireProjectDocToolbar() {
  const dl = document.getElementById('pd-download');
  const cp = document.getElementById('pd-copy');
  if (dl) dl.addEventListener('click', () => {
    const blob = new Blob([_detailProjectDoc], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `项目文档_${_detailProjectDocName || 'project'}.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  });
  if (cp) cp.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(_detailProjectDoc);
      cp.textContent = '✓ 已复制';
      setTimeout(() => { cp.textContent = '📋 复制'; }, 1500);
    } catch (e) {
      alert('复制失败：' + e.message);
    }
  });
}

async function genProjectDoc(btn) {
  if (!_detailSuggestionId) return;
  const body = btn.closest('.detail-section-body');
  const original = btn.textContent;
  btn.disabled = true;
  btn.textContent = '生成中…';
  try {
    const result = await postJSON(`/suggestion/${_detailSuggestionId}/project-doc`);
    if (!result.project_doc) {
      body.innerHTML = '<p class="text-tertiary">未生成内容</p>';
      return;
    }
    _detailProjectDoc = result.project_doc;
    body.innerHTML = renderProjectDocBody(result.project_doc_html || '');
    wireProjectDocToolbar();
  } catch (e) {
    btn.disabled = false;
    btn.textContent = original;
    const err = document.createElement('p');
    err.className = 'error-text';
    err.style.cssText = 'color:var(--danger,#e5484d); font-size:13px; margin-top:8px;';
    err.textContent = '生成失败：' + e.message;
    body.appendChild(err);
  }
}
window.genProjectDoc = genProjectDoc;
```

- [ ] **Step 3: 在详情页插入该 section 并记录项目名**

在 `loadSuggestionDetail` 中，先记录项目名。把：

```js
    const s = await getJSON(`/suggestion/${id}`);
    const keyFeatures = s.key_features || [];
```

改为：

```js
    const s = await getJSON(`/suggestion/${id}`);
    _detailProjectDocName = s.name || '';
    const keyFeatures = s.key_features || [];
```

然后在两个按需 section 之后插入第三个 section。把：

```js
    // On-demand sections
    html += genSectionHTML('架构与目录结构', 'architecture', 'repo_structure', s, '生成架构与目录结构', 'genArchitecture');
    html += genSectionHTML('README 营销策略', 'readme_strategy', 'naming_tips', s, '生成 README 营销策略', 'genReadme');

    setBody(html);
```

改为：

```js
    // On-demand sections
    html += genSectionHTML('架构与目录结构', 'architecture', 'repo_structure', s, '生成架构与目录结构', 'genArchitecture');
    html += genSectionHTML('README 营销策略', 'readme_strategy', 'naming_tips', s, '生成 README 营销策略', 'genReadme');
    html += genProjectDocSectionHTML(s);

    setBody(html);
    wireProjectDocToolbar();  // 若已有文档，绑定下载/复制
```

- [ ] **Step 4: 静态检查 JS 语法**

Run: `node --check trend_radar/web/static/js/app.js`
Expected: 无输出（语法正确）。若本机无 node，跳过此步，靠 Task 8 手动验证。

- [ ] **Step 5: 提交**

```bash
git add trend_radar/web/static/js/app.js
git commit -m "feat(web): 详情页新增「完整项目文档」section 与下载/复制"
```

---

### Task 7: `.markdown-body` 排版样式

**Files:**
- Modify: `trend_radar/web/static/css/style.css`（文件末尾追加）

- [ ] **Step 1: 追加 markdown 渲染样式**

在 `style.css` 文件**末尾**追加：

```css

/* ===== 完整项目文档 Markdown 渲染 ===== */
.project-doc-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.markdown-body {
  font-size: 14px;
  line-height: 1.8;
  color: var(--text-secondary);
  word-break: break-word;
}
.markdown-body h1,
.markdown-body h2,
.markdown-body h3,
.markdown-body h4 {
  color: var(--text-primary);
  font-weight: 600;
  margin: 20px 0 8px;
  line-height: 1.4;
}
.markdown-body h1 { font-size: 20px; }
.markdown-body h2 { font-size: 17px; }
.markdown-body h3 { font-size: 15px; }
.markdown-body p { margin: 8px 0; }
.markdown-body ul,
.markdown-body ol { margin: 8px 0; padding-left: 22px; }
.markdown-body li { margin: 4px 0; }
.markdown-body a { color: var(--brand-hover); text-decoration: none; }
.markdown-body a:hover { text-decoration: underline; }
.markdown-body code {
  background: var(--surface-2, rgba(127, 127, 127, 0.12));
  border-radius: 4px;
  padding: 1px 5px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12.5px;
}
.markdown-body pre {
  background: var(--surface-2, rgba(127, 127, 127, 0.08));
  border: 1px solid var(--border-default);
  border-radius: 6px;
  padding: 14px 16px;
  margin: 10px 0;
  overflow-x: auto;
}
.markdown-body pre code {
  background: none;
  border: none;
  padding: 0;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--text-primary);
  white-space: pre;
}
.markdown-body table {
  border-collapse: collapse;
  width: 100%;
  margin: 10px 0;
  font-size: 13px;
}
.markdown-body th,
.markdown-body td {
  border: 1px solid var(--border-default);
  padding: 6px 10px;
  text-align: left;
}
.markdown-body th { color: var(--text-primary); }
```

- [ ] **Step 2: 提交**

```bash
git add trend_radar/web/static/css/style.css
git commit -m "style: 完整项目文档 Markdown 排版样式"
```

---

### Task 8: 全量测试 + 手动验证

**Files:** 无改动

- [ ] **Step 1: 全量跑测试**

Run: `python -m pytest tests/test_project_doc.py -v`
Expected: PASS（12 passed）

- [ ] **Step 2: 确认 markdown 依赖已装**

Run: `python -c "import markdown; print(markdown.__version__)"`
Expected: 输出 `3.4.1`（或更高）。若报 ModuleNotFoundError，运行 `pip install "markdown>=3.4"`。

- [ ] **Step 3: 启动 Web 应用**

Run: `python -m trend_radar.web.app`（或 `uvicorn trend_radar.web.app:app --port 8088`）
Expected: 服务在 `0.0.0.0:8088` 起来，无报错。

- [ ] **Step 4: 手动验证端到端流程**

浏览器打开 `http://localhost:8088`，登录后进入「项目建议」→ 点开任意一条建议详情页：

1. 确认页面底部出现「完整项目文档」section，带「✨ 生成完整项目文档」按钮。
2. 点击按钮，确认出现「生成中…」，约 30-60 秒后渲染出带标题/列表/目录树/代码块的文档。
3. 点「⬇ 下载 .md」，确认浏览器下载了 `项目文档_<项目名>.md`，用文本编辑器打开确认是规范 Markdown。
4. 点「📋 复制」，确认按钮变「✓ 已复制」，粘贴到任意处确认内容完整。
5. 刷新该详情页，确认文档仍在（从 DB `full_data` 恢复，不重新调 AI），下载/复制按钮仍可用。
6. （可选）把下载的 `.md` 丢给 Claude Code，确认它能据此理解项目并搭建，验证「详细到能用」目标。

- [ ] **Step 5: 最终提交（若有验证中的小修）**

如验证中无改动则跳过；若有，提交：

```bash
git add -A
git commit -m "test: 验证完整项目文档生成端到端"
```

---

## Self-Review（已自检）

**1. Spec 覆盖：**
- 决策 1（功能模块只在 MD 里）：Task 4 prompt 第 2 章「核心功能模块」覆盖 ✓
- 决策 2（单次 LLM 调用产整篇 Markdown）：Task 4 `generate_project_doc` 单次 `chat()` ✓
- 决策 3（有就用没有就略已有上下文）：Task 4 `_build_project_doc_prompt` 按字段 strip 判断 ✓
- 决策 4（存 full_data.project_doc）：Task 5 `full["project_doc"] = md` ✓
- 决策 5（内联卡片 + 生成 + 下载/复制）：Task 6 ✓
- 决策 6（markdown 库渲染）：Task 1 `markdown_to_html` ✓
- MD 章节结构 9 节：Task 4 prompt 全覆盖 ✓
- 依赖 markdown：Task 1 ✓

**2. 占位符扫描：** 无 TBD / TODO / "类似 Task N"。每步含完整代码 ✓

**3. 类型 / 命名一致性：**
- `project_doc`（原始 md）/ `project_doc_html`（html）在 models / api / js 全程一致 ✓
- `generate_project_doc(suggestion, existing_context)` 签名在 Task 4 定义、Task 5 调用一致 ✓
- `chat(system, user, max_retries=2, max_tokens=None)` 在 Task 3 定义、Task 4 + FakeLLM 调用一致 ✓
- `genProjectDoc` / `wireProjectDocToolbar` / `renderProjectDocBody` / `genProjectDocSectionHTML` 在 Task 6 内自洽 ✓

**对设计文档的一处诚实偏离：** 设计稿说「复用 `genSectionHTML` + `_genSection`」，但探索发现该管线会对内容 `esc()` 转义，会破坏预渲染 HTML。故「完整项目文档」用专属渲染函数（`genProjectDocSectionHTML` / `renderProjectDocBody`），交互形状（卡片 + 生成按钮 + 按需存回）仍与现有 section 一致。此为必要修正，已在 Task 6 说明。
