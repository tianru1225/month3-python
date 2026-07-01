from datetime import datetime
from pathlib import Path

RQ_LOG_PATH = Path("logs/rq_jobs.log")
def write_rq_log(message: str) ->str:
    RQ_LOG_PATH.parent.mkdir(parents = True,exist_ok = True)
    timestamp = datetime.now().isoformat(timespec = "seconds")
    line = f"{timestamp} {message}\n"
    with RQ_LOG_PATH.open("a",encoding = "utf-8") as file:
        file.write(line)
    return f"written:{message}"
    
def fail_rq_job(message: str) -> str:
    raise RuntimeError(f"rq job failed: {message}")