"""配置加载：读取 config.yaml + .env，合并为运行时配置对象。"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config.yaml"


def _expand_env(value: Any) -> Any:
    """递归替换字符串中的 ${VAR} 为环境变量值。"""
    if isinstance(value, str):
        return re.sub(
            r"\$\{(\w+)\}",
            lambda m: os.environ.get(m.group(1), m.group(0)),
            value,
        )
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def load_config() -> dict[str, Any]:
    """加载并返回完整配置字典。"""
    load_dotenv(_PROJECT_ROOT / ".env")
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _expand_env(raw)


# 全局单例
_config: dict[str, Any] | None = None


def get_config() -> dict[str, Any]:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config() -> dict[str, Any]:
    """重新从磁盘加载配置 (清空单例缓存)。设置页写完 config.yaml 后调用，
    使后续读取拿到最新值。"""
    global _config
    _config = load_config()
    return _config


def get_project_root() -> Path:
    return _PROJECT_ROOT
