from pathlib import Path

def test_create_audit_event_returns_202(client):
    response = client.post(
        "/tasks/audit",
        json = {"event":"pytest-background-task"}
    )
    assert response.status_code == 202
    assert response.json() == {
        "status":"accepted",
        "event" : "pytest-background-task",
    }
def test_write_audit_log_creates_file():
    from app.tasks.audit import write_audit_log
    path = Path("logs/audit.log")
    before = path.read_text(encoding = "utf-8") if path.exists() else ""
    write_audit_log("direct-audit-test")
    after = path.read_text(encoding = "utf-8")
    assert "direct-audit-test" in after
    assert len(after) > len(before)