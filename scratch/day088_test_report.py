REGRESSION_CHECKS = [
    "debug 接口自动生成的 request_id 与响应头一致",
    "boom 接口保持 TEAPOT 错误契约",
    "boom 错误响应保留 x-request-id 请求头",
    "items 查不到时保持 ITEM_NOT_FOUND 错误契约",
    "items 创建成功保持统一响应体契约",
    "users 创建后再查询的往返一致",
    "users 用户名重复返回 USER_ALREADY_EXISTS",
    "users 邮箱重复返回 USER_ALREADY_EXISTS",
    "openapi 包含全部核心路径",
    "openapi 核心路径保持正确的 HTTP 方法",
]
for index,check in enumerate(REGRESSION_CHECKS):
    print(f"{index}.{check}")