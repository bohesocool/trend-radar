"""鉴权模块 — 固定密码 + 持久化 session token (SQLite)。"""

from __future__ import annotations

import os
import secrets
import time
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from trend_radar import db

# session token 有效期 (秒)
SESSION_TTL = 86400 * 30  # 30 天

security = HTTPBearer(auto_error=False)


def _get_password() -> str:
    """运行时读取密码 (确保 dotenv 已加载)。"""
    # 先尝试从环境变量直接读
    pwd = os.environ.get("TRENDRADAR_PASSWORD")
    if pwd:
        return pwd
    # 如果环境变量没有，尝试从 .env 文件加载
    from dotenv import load_dotenv
    from pathlib import Path
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    load_dotenv(env_path)
    return os.environ.get("TRENDRADAR_PASSWORD", "trendradar123")


def login(password: str) -> str | None:
    """验证密码，成功返回 session token，失败返回 None。"""
    if password == _get_password():
        token = secrets.token_hex(24)
        db.save_session(token, time.time() + SESSION_TTL)
        # 顺带清理过期 session，避免表无限增长
        try:
            db.cleanup_expired_sessions(time.time())
        except Exception:
            pass
        return token
    return None


def verify_token(token: str) -> bool:
    """验证 session token 是否有效。"""
    expire = db.get_session_expire(token)
    if expire is None:
        return False
    if time.time() > expire:
        db.delete_session(token)
        return False
    return True


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> bool:
    """FastAPI 依赖项：要求有效的 Bearer token。"""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not verify_token(credentials.credentials):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录已过期，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True