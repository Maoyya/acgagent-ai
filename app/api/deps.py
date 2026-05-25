from fastapi import Header, HTTPException


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    from app.config import settings

    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


async def get_user_id(x_user_id: str = Header(None, alias="X-User-Id")) -> str | None:
    return x_user_id
