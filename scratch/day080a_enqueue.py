from redis import Redis
from rq import Queue

from app.tasks.rq_jobs import write_rq_log

redis_conn = Redis(host = "127.0.0.1",port = 6379,db = 0)
queue = Queue("default",connection = redis_conn)
job = queue.enqueue(write_rq_log,"day80a_rq_job")

print(job.id)
print(job.get_status())

