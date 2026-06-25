"""设置 API — 读写 config.yaml + .env 配置。"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from trend_radar.config import get_project_root
from trend_radar.web.auth import require_auth

router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])

_PROJECT_ROOT = get_project_root()
_CONFIG_PATH = _PROJECT_ROOT / "config.yaml"
_ENV_PATH = _PROJECT_ROOT / ".env"


def _read_yaml() -> dict[str, Any]:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _write_yaml(data: dict[str, Any]) -> None:
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _read_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if not _ENV_PATH.exists():
        return env
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            env[key.strip()] = val.strip()
    return env


def _write_env(updates: dict[str, str]) -> None:
    """Update .env file, preserving existing keys and comments."""
    lines: list[str] = []
    existing_keys: set[str] = set()

    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.partition("=")[0].strip()
                existing_keys.add(key)
                if key in updates:
                    lines.append(f"{key}={updates[key]}")
                else:
                    lines.append(line)
            else:
                lines.append(line)

    # Append new keys not already in file
    for key, val in updates.items():
        if key not in existing_keys:
            lines.append(f"{key}={val}")

    _ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _resolve_env_value(raw: str) -> str:
    """Resolve ${VAR} references in a config value using environment variables."""
    return re.sub(
        r"\$\{(\w+)\}",
        lambda m: os.environ.get(m.group(1), m.group(0)),
        raw,
    )


@router.get("/settings")
def get_settings() -> dict[str, Any]:
    """读取当前所有配置。"""
    cfg = _read_yaml()
    env = _read_env()

    # LLM config (resolve env vars for display, but mask the key)
    llm = cfg.get("llm", {})
    api_base = _resolve_env_value(llm.get("api_base", ""))
    api_key = env.get("NEWAPI_API_KEY", "")
    model = _resolve_env_value(llm.get("model", ""))

    # Collectors
    collectors = cfg.get("collectors", {})
    generator = cfg.get("generator", {})

    return {
        "ai": {
            "api_base": api_base,
            "api_key": api_key,
            "model": model,
        },
        "collect": {
            "daily_suggestions": generator.get("daily_suggestions", 3),
            "github_languages": collectors.get("github_trending", {}).get("languages", ["python"]),
            "hn_min_points": collectors.get("hackernews", {}).get("min_points", 100),
            "arxiv_categories": collectors.get("arxiv", {}).get("categories", ["cs.AI", "cs.CL", "cs.LG"]),
            "reddit_subreddits": collectors.get("reddit", {}).get("subreddits", []),
            "twitter_enabled": collectors.get("twitter", {}).get("enabled", False),
        },
    }


class SettingsUpdate(BaseModel):
    ai: dict[str, str] | None = None
    collect: dict[str, Any] | None = None


@router.post("/settings")
def update_settings(req: SettingsUpdate) -> dict[str, str]:
    """更新配置，写入 config.yaml 和 .env。需要重启容器生效。"""
    cfg = _read_yaml()

    # Update AI config → .env
    env_updates: dict[str, str] = {}
    if req.ai:
        api_base = req.ai.get("api_base", "").strip()
        api_key = req.ai.get("api_key", "").strip()
        model = req.ai.get("model", "").strip()

        if api_base:
            # Store base URL without /v1 suffix in env, add it back in config
            base = api_base.rstrip("/")
            if base.endswith("/v1"):
                base = base[:-3]
            env_updates["NEWAPI_BASE_URL"] = base
        if api_key:
            env_updates["NEWAPI_API_KEY"] = api_key
        if model:
            env_updates["NEWAPI_MODEL"] = model

    # Update collect config → config.yaml
    if req.collect:
        collectors = cfg.setdefault("collectors", {})
        generator = cfg.setdefault("generator", {})

        if "daily_suggestions" in req.collect:
            generator["daily_suggestions"] = int(req.collect["daily_suggestions"])
        if "github_languages" in req.collect:
            collectors.setdefault("github_trending", {})["languages"] = req.collect["github_languages"]
        if "hn_min_points" in req.collect:
            collectors.setdefault("hackernews", {})["min_points"] = int(req.collect["hn_min_points"])
        if "arxiv_categories" in req.collect:
            collectors.setdefault("arxiv", {})["categories"] = req.collect["arxiv_categories"]
        if "reddit_subreddits" in req.collect:
            collectors.setdefault("reddit", {})["subreddits"] = req.collect["reddit_subreddits"]
        if "twitter_enabled" in req.collect:
            collectors.setdefault("twitter", {})["enabled"] = bool(req.collect["twitter_enabled"])

    # Write files
    if env_updates:
        _write_env(env_updates)
    _write_yaml(cfg)

    return {"status": "ok", "message": "配置已保存。需要重启容器生效。"}
