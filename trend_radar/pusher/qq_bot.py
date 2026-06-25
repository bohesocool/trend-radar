"""QQ Bot 推送 (通过 Webhook)。"""

from __future__ import annotations

import httpx
from loguru import logger

from trend_radar.config import get_config


def send_qq(message: str) -> bool:
    """通过 QQ Bot Webhook 发送消息。"""
    cfg = get_config().get("pusher", {}).get("qq_bot", {})
    if not cfg.get("enabled") or not cfg.get("webhook"):
        logger.info("QQ Bot 推送未配置或未启用，跳过")
        return False

    webhook = cfg["webhook"]
    try:
        resp = httpx.post(webhook, json={"content": message}, timeout=15)
        resp.raise_for_status()
        logger.info("✅ QQ Bot 推送成功")
        return True
    except Exception as e:
        logger.error(f"❌ QQ Bot 推送失败: {e}")
        return False