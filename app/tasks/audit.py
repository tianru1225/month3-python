from datetime import datetime
from pathlib import Path
AUDIT_LOG_PATH = Path("logs/audit.log")
def write_audit_log(event: str) -> None:
    AUDIT_LOG_PATH.parent.mkdir(parents=True,exist_ok = True)
    timestamp = datetime.now().isoformat(timespec="seconds")
    line = f"{timestamp} {event}\n"
    with AUDIT_LOG_PATH.open("a",encoding = "utf-8") as file:
        file.write(line)