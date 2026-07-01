"""项目文档生成相关单元测试（纯逻辑，不碰 DB / 鉴权 / 真 LLM）。"""

import json

from unittest.mock import MagicMock

import trend_radar.db as db
import trend_radar.generator.suggestion_engine as se
from trend_radar.analyzer.llm_client import LLMClient
from trend_radar.models import ProjectSuggestion
from trend_radar.web.api import markdown_to_html
from trend_radar.generator.suggestion_engine import _parse_suggestion


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
    assert "&lt;script&gt;" in html  # 钉住实际转义行为


def test_markdown_to_html_strips_dangerous_url_schemes():
    """链接/图片语法的 href/src 不会被 _EscapeHtml 处理，需单独剥离危险 scheme。"""
    md = "![alt](javascript:alert(1)) 和 [x](data:text/html,<script>)"
    html = markdown_to_html(md)
    assert "javascript:" not in html
    assert "data:" not in html


def test_markdown_to_html_strips_entity_encoded_scheme():
    """实体编码冒号 javascript&#58; 浏览器会解码为 javascript:，必须一并挡掉。"""
    html = markdown_to_html("[x](javascript&#58;alert(1))")
    assert "javascript" not in html.lower()


def test_markdown_to_html_strips_control_char_in_scheme():
    """scheme 内插入控制符 (java\\nscript:) 浏览器会去除后解析为 javascript:，必须挡掉。"""
    html = markdown_to_html("[x](java\nscript:alert(1))")
    assert "href" not in html  # 整个 href 被白名单剥离
    assert "javascript" not in html.lower()


def test_markdown_to_html_keeps_safe_links():
    md = "[官网](https://example.com)"
    html = markdown_to_html(md)
    assert 'href="https://example.com"' in html


def test_markdown_to_html_empty_input():
    assert markdown_to_html("") == ""
    assert markdown_to_html(None) == ""


def test_parse_suggestion_reads_project_doc():
    s = _parse_suggestion({"name": "foo", "project_doc": "# Hello"})
    assert s.project_doc == "# Hello"


def test_parse_suggestion_project_doc_defaults_empty():
    s = _parse_suggestion({"name": "foo"})
    assert s.project_doc == ""


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
    assert "核心功能模块" in prompt
    assert "给 AI 编码助手的执行指引" in prompt


def test_build_prompt_includes_existing_context_when_present():
    ctx = {**_EMPTY_CTX, "architecture": "三层架构：采集层/分析层/展示层"}
    prompt = se._build_project_doc_prompt(_suggestion(), ctx)
    assert "三层架构：采集层/分析层/展示层" in prompt


def test_build_prompt_omits_context_block_when_empty():
    prompt = se._build_project_doc_prompt(_suggestion(), _EMPTY_CTX)
    assert "已有架构参考" not in prompt


def test_generate_project_doc_uses_at_least_configured_max_tokens(monkeypatch):
    captured = {}

    class FakeLLM:
        max_tokens = 12000

        def chat(self, system_prompt, user_prompt, max_retries=2, max_tokens=None):
            captured["max_tokens"] = max_tokens
            return "# 长文档"

    monkeypatch.setattr(se, "LLMClient", FakeLLM)

    se.generate_project_doc(_suggestion(), _EMPTY_CTX)

    assert captured["max_tokens"] == 12000


def test_update_suggestion_full_data_merges_with_latest_row(monkeypatch):
    writes = []

    class FakeCursor:
        rowcount = 1

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql, params):
            writes.append(json.loads(params[0]))
            return FakeCursor()

    monkeypatch.setattr(db, "_get_conn", lambda: FakeConn())
    monkeypatch.setattr(
        db,
        "get_suggestion_by_id",
        lambda suggestion_id: {"full_data": json.dumps({"architecture": "keep me"}, ensure_ascii=False)},
    )

    db.update_suggestion_full_data(1, {"project_doc": "# Doc"})

    assert writes == [{"architecture": "keep me", "project_doc": "# Doc"}]
