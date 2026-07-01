from fastapi import APIRouter,status,HTTPException
from redis import Redis
from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.job import Job

from app.tasks.rq_jobs import write_rq_log,fail_rq_job
from app.schemas.rq_task import RQTaskRequest,RQTaskResponse,RQJobStatusResponse

router = APIRouter(prefix = "/rq",tags= ["rq"])
redis_conn = Redis(host = "127.0.0.1",port = 6379,db=0)
queue = Queue("default",connection = redis_conn)

def job_status_text(job: Job) -> str:
    job_status = job.get_status()
    return job_status.value if hasattr(job_status,"value") else str(job_status)

@router.post(
    "/jobs",
    response_model = RQTaskResponse,
    status_code = status.HTTP_202_ACCEPTED,
)
def enqueue_rq_job(payload: RQTaskRequest):
    job = queue.enqueue(write_rq_log,payload.message)
    return {
        "status":job_status_text(job),
        "job_id":job.id,
    }

@router.get(
    "/jobs/{job_id}",
    response_model = RQJobStatusResponse,
    responses = {404:{"description":"任务不存在"}}
)
def get_rq_job_status(job_id: str):
    try:
        job = Job.fetch(job_id,connection = redis_conn)
    except NoSuchJobError:
        raise HTTPException(
            status_code = status.HTTP_404_NOT_FOUND,
            detail = {"code":"JOB_NOT_FOUND","message":f"job {job_id} not found"},
        )
    return {
        "job_id": job.id,
        "status": job_status_text(job),
        "result": str(job.result) if job.result is not None else None,
        "error": job.exc_info,
    }

@router.post(
    "/jobs/fail",
    response_model = RQTaskResponse,
    status_code = status.HTTP_202_ACCEPTED,
)
def enqueue_failed_rq_job(payload:RQTaskRequest):
    job = queue.enqueue(fail_rq_job,payload.message)
    return{
        "status":job_status_text(job),
        "job_id":job.id,
    }
