"""
API 依赖注入。

verify_api_key: 所有 /api/v1/* 路由的认证守卫，校验 X-API-Key Header。
get_user_id: 可选依赖，从 X-User-Id Header 提取用户标识（预留多租户支持）。
"""
import secrets

from fastapi import Header, HTTPException


async def verify_api_key(x_api_key: str | None = Header(None, alias="X-API-Key")) -> str:
    """校验 API Key。所有 v1 路由默认依赖此函数。

    - 缺失/空 key → 401 Missing API key
    - 比对使用 secrets.compare_digest（常数时间，防计时侧信道）；不符 → 401
    """
    from app.config import settings

    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    if not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


async def get_user_id(x_user_id: str | None = Header(None, alias="X-User-Id")) -> str | None:
    """从请求头提取用户 ID，未传递时返回 None。"""
    return x_user_id
