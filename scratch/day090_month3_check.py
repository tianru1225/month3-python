CHECKS = [
    "local quality: py_compile, ruff, mypy, pytest",   # 本地质量四道闸门
    "compose services: nginx, api, redis, worker",      # 四个容器是否都 Up
    "direct API: /health, /items, /debug/db-ping",      # 直连 8001 的核心接口
    "nginx API: /api/health, /api/debug/db-ping, /api/openapi.json",  # 走 Nginx 反代
    "trace id: X-Request-ID response header",           # 链路追踪是否回显
    "auth: valid and invalid x-api-key",                # 鉴权放行与拦截
    "rq worker: enqueue job and worker completes it",   # 后台任务被消费
    "rate limit: X-Real-IP buckets are isolated",       # 限流按 IP 分桶隔离
    "failure drill: database outage returns DB_UNAVAILABLE",  # 故障注入降级
    "month review: notes/month3_review.md",             # 月度复盘文件已生成
]

# enumerate 给每项配序号，start=1 让序号从 1 开始而不是 0
for index, check in enumerate(CHECKS, start=1):
    print(f"{index}. {check}")  # 拼成 "1. local quality: ..." 这样的行