"""JWT 鉴权模块 — 简单的 token 校验。"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# 从环境变量读取 JWT secret，如果没有则自动生成一个
JWT_SECRET = os.environ.get("TRENDRADAR_JWT_SECRET") or secrets.token_hex(32)
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24 * 30  # 30 天过期

security = HTTPBearer(auto_error=False)


def create_token(data: dict | None = None) -> str:
    """创建 JWT token。"""
    payload = {
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": datetime.now(timezone.utc),
        "sub": "trendradar-user",
        **(data or {}),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    """验证 JWT token，返回 payload。"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 已过期，请重新登录",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 Token",
        )


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """FastAPI 依赖项：要求有效的 Bearer token。"""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证信息",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_token(credentials.credentials)


# ===== CLI 入口 =====

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="TrendRadar JWT Auth")
    parser.add_argument("--generate", action="store_true", help="生成一个新的 JWT token")
    args = parser.parse_args()

    if args.generate:
        token = create_token()
        print(f"\n✅ JWT Token 已生成 (30 天有效期):\n")
        print(token)
        print(f"\n请将此 token 用于 TrendRadar 登录页面。")
        print(f"环境变量 TRENDRADAR_JWT_SECRET 可用于固定 secret (否则每次重启会变)。")
    else:
        parser.print_help()