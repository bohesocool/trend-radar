"""项目文档生成相关单元测试（纯逻辑，不碰 DB / 鉴权 / 真 LLM）。"""

from unittest.mock import MagicMock

from trend_radar.analyzer.llm_client import LLMClient
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
