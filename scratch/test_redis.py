from app.core.redis_client import redis_client
print(redis_client.ping())
redis_client.set("day079-config", "ok")
print(redis_client.get("day079-config"))
redis_client.delete("day079-config")

