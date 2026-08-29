from redis import Redis
from rq import Queue, Worker

from app.config import settings

listen = ["materials", "default"]

redis_connection = Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    db=settings.redis_db,
)

if __name__ == "__main__":
    queues = [Queue(name, connection=redis_connection) for name in listen]
    worker = Worker(queues, connection=redis_connection)
    worker.work()
