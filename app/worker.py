from redis import Redis
from rq import Queue,Worker

from app.config import settings

listen = ["default"]

redis_conn = Redis(
    host = settings.redis_host,
    port = settings.redis_port,
    db = settings.redis_db,
)

if __name__ == "__main__":
    queues = [Queue(name,connection = redis_conn) for name in listen]
    worker = Worker(queues,connection = redis_conn)
    worker.work()