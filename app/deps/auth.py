from fastapi import Header,HTTPException,status
from app.config import settings
def verify_api_key(x_api_key: str | None = Header(default=None))->str:
    if x_api_key is None:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail={"code":"API_KEY_MISSING","message":"x-api-key header required"},
        )
    if x_api_key!=settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code":"API_KEY_INVALID","message":"invalid api key"},
        )
    return x_api_key