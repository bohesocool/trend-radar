"""鉴权模块 — 固定密码 + 简单 session token。"""

from __future__ import annotations

import os
import secrets
import time
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# session token 有效期 (秒)
SESSION_TTL = 86400 * 30  # 30 天

# 内存中的 session 存储 (进程重启后失效，需重新登录)
_active_sessions: dict[str, float] = {}  # token -> expire_timestamp

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
        _active_sessions[token] = time.time() + SESSION_TTL
        _cleanup_sessions()
        return token
    return None


def verify_token(token: str) -> bool:
    """验证 session token 是否有效。"""
    expire = _active_sessions.get(token)
    if expire is None:
        return False
    if time.time() > expire:
        _active_sessions.pop(token, None)
        return False
    return True


def _cleanup_sessions() -> None:
    """清理过期 session。"""
    now = time.time()
    expired = [t for t, exp in _active_sessions.items() if now > exp]
    for t in expired:
        _active_sessions.pop(t, None)


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