from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

def get_client_ip(request: Request) -> str:
    x_real_ip = request.headers.get("X-Real-IP")
    if x_real_ip:
        return x_real_ip
    return get_remote_address(request)
limiter = Limiter(key_func=get_client_ip)