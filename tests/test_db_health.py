import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.deps.db import get_db
from app.main import app

def test_debug_db_ping_returns_ok(client):
    response = client.get("/debug/db-ping")

    assert response.status_code ==200
    body = response.json()
    assert body["code"] == "OK"
    assert body["msg"] == "success"
    assert body["data"]["database"] == "ok"

class BrokenSession:
    def execute(self,_statement):
        raise SQLAlchemyError("simulated database outage")
@pytest.fixture
def broken_db_client(client):
    def override_get_db():
        yield BrokenSession()
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db,None)
def test_debug_db_ping_returns_503_when_db_unavailbale(broken_db_client):
    response = broken_db_client.get("/debug/db-ping")
    assert response.status_code == 503
    body = response.json()
    assert body["detail"]["code"] == "DB_UNAVAILABLE"
    assert body["detail"]["message"] == "database unavailable"