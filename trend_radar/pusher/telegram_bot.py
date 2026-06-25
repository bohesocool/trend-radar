"""Telegram Bot 推送。"""

from __future__ import annotations

import httpx
from loguru import logger

from trend_radar.config import get_config


def send_telegram(message: str) -> bool:
    """通过 Telegram Bot API 发送消息。"""
    cfg = get_config().get("pusher", {}).get("telegram", {})
    if not cfg.get("enabled") or not cfg.get("bot_token") or not cfg.get("chat_id"):
        logger.info("Telegram 推送未配置或未启用，跳过")
        return False

    token = cfg["bot_token"]
    chat_id = cfg["chat_id"]
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=15,
        )
        resp.raise_for_status()
        logger.info("✅ Telegram 推送成功")
        return True
    except Exception as e:
        logger.error(f"❌ Telegram 推送失败: {e}")
        # 尝试不带 Markdown
        try:
            resp = httpx.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message},
                timeout=15,
            )
            resp.raise_for_status()
            return True
        except Exception as e2:
            logger.error(f"❌ Telegram 纯文本推送也失败: {e2}")
            return False