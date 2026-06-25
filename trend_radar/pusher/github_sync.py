"""GitHub 仓库自动同步 — 将报告推送到 GitHub 仓库。"""

from __future__ import annotations

import base64

import httpx
from loguru import logger

from trend_radar.config import get_config

_GH_API = "https://api.github.com"


def _gh_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def sync_to_github(date_str: str, report_markdown: str) -> bool:
    """将日报 Markdown 同步到 GitHub 仓库 (data/reports/{date}/daily.md)。"""
    cfg = get_config().get("pusher", {}).get("github", {})
    if not cfg.get("enabled") or not cfg.get("token") or not cfg.get("repo"):
        logger.info("GitHub 同步未配置或未启用，跳过")
        return False

    token = cfg["token"]
    repo = cfg["repo"]
    path = f"data/reports/{date_str}/daily.md"

    return _push_file(token, repo, path, report_markdown, f"Daily report {date_str}")


def _push_file(token: str, repo: str, path: str, content: str, commit_msg: str) -> bool:
    """通过 GitHub API 推送单个文件。"""
    url = f"{_GH_API}/repos/{repo}/contents/{path}"
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")

    # 检查文件是否已存在 (获取 sha)
    sha: str | None = None
    try:
        resp = httpx.get(url, headers=_gh_headers(token), timeout=15)
        if resp.status_code == 200:
            sha = resp.json().get("sha")
    except Exception:
        pass

    body = {"message": commit_msg, "content": encoded}
    if sha:
        body["sha"] = sha

    try:
        resp = httpx.put(url, headers=_gh_headers(token), json=body, timeout=30)
        resp.raise_for_status()
        logger.info(f"✅ GitHub 同步: {path}")
        return True
    except Exception as e:
        logger.error(f"❌ GitHub 同步失败 [{path}]: {e}")
        return False