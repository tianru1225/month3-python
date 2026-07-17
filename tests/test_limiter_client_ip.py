from typing import Any
from app.core.limiter import get_client_ip

class DummyClient:
    host = "testclient"

class DummyRequest:
    def __init__(self,headers: dict[str,str]) -> None:
        self.headers = headers
        self.client = DummyClient()

def test_get_client_ip_uses_x_real_ip() -> None:
    request: Any = DummyRequest({"X-Real-IP":"203.0.113.10"})
    assert get_client_ip(request) == "203.0.113.10"

def test_get_client_ip_falls_back_to_remote_address() -> None:
    request: Any = DummyRequest({})
    assert get_client_ip(request) == "testclient"