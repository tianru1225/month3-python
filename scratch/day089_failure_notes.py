FAILURE_DRILL = [
    # 正常路径:数据库活着时,探针执行 SELECT 1,返回统一成功体 code=OK
    "normal: /debug/db-ping executes SELECT 1 and returns code=OK",
    # 故障制造:测试用 dependency override 把 get_db 换成假的 BrokenSession
    "failure: test overrides get_db with BrokenSession",
    # 故障触发:BrokenSession 的 execute 一被调用就抛 SQLAlchemyError,模拟数据库挂掉
    "failure: BrokenSession.execute raises SQLAlchemyError",
    # 预期①:路由用 except 捕获住这个数据库异常,不让它裸奔
    "expected: API catches SQLAlchemyError",
    # 预期②:捕获后翻译成 HTTP 503(依赖暂不可用,可重试),而不是 500
    "expected: API returns HTTP 503",
    # 预期③:错误响应里带明确错误码 DB_UNAVAILABLE,契约稳定
    "expected: error detail code is DB_UNAVAILABLE",
    # 边界:绝不把 SQLAlchemy 的原始异常/堆栈暴露给调用方(安全+契约)
    "boundary: do not expose raw database exception to caller",
]

for index, item in enumerate(FAILURE_DRILL, start=1):
    print(f"{index}. {item}")