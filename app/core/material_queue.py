from redis import Redis
from rq import Queue

from app.config import settings

redis_connection = Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    db=settings.redis_db,
)

material_queue = Queue("materials", connection=redis_connection)
