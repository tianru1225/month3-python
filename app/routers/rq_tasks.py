from fastapi import APIRouter,status,HTTPException
from redis import Redis
from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.job import Job

from app.tasks.rq_jobs import write_rq_log,fail_rq_job
from app.schemas.rq_task import RQTaskRequest,RQTaskResponse,RQJobStatusResponse
from app.config import settings

router = APIRouter(prefix = "/rq",tags= ["rq"])
redis_conn = Redis(host=settings.redis_host,port=settings.redis_port,db=settings.redis_db)
queue = Queue("default",connection = redis_conn)

def job_status_text(job: Job) -> str:
    job_status = job.get_status(refresh=True)
    return job_status.value if hasattr(job_status,"value") else str(job_status)

@router.post(
    "/jobs",
    response_model = RQTaskResponse,
    status_code = status.HTTP_202_ACCEPTED,
    summary="投递RQ后台任务",
    description="把任务写入Redis队列,由独立rq worker异步执行,返回job_id供后续查询任务状态",
    responses={
        202:{"description":"任务已入队,返回job_id"},
    },
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
    summary="查询 RQ 任务状态",
    description="根据 job_id 查询任务当前状态、执行结果或失败 traceback。",
    responses = {
        200: {"description": "任务存在,返回状态"},
        404:{"description":"任务不存在"},
    }
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
    summary="投递一个会失败的 RQ 测试任务",
    description="把一个故意抛出 RuntimeError 的任务写入 Redis 队列,用于验证 failed 状态和 error traceback 是否能被查询。",
    responses={
        202: {"description": "失败测试任务已入队,返回 job_id"},
    },
)
def enqueue_failed_rq_job(payload:RQTaskRequest):
    job = queue.enqueue(fail_rq_job,payload.message)
    return{
        "status":job_status_text(job),
        "job_id":job.id,
    }
