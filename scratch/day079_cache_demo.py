from app.core.redis_client import redis_client
CACHE_KEY = "day079:user:1"
redis_client.delete(CACHE_KEY)
hits = 0
misses = 0
def get_user_name_from_cache_or_source() ->str:
    global hits,misses
    cached = redis_client.get(CACHE_KEY)
    if cached is not None:
        hits+=1
        return cached
    misses+=1
    value = "alice-from-source"
    redis_client.setex(CACHE_KEY,60,value)
    return value
print(get_user_name_from_cache_or_source())
print(get_user_name_from_cache_or_source())
print({"hits":hits,"misses":misses})
redis_client.delete(CACHE_KEY)
