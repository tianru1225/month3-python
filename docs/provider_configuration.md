# Qwen Provider 配置说明

## 密钥边界

密钥配置：`DASHSCOPE_API_KEY`。

在 `Settings` 中以 Pydantic `SecretStr` 加载，配置对象的 `repr()` 与
`model_dump()` 默认显示为掩码。应用代码不得打印、记录、序列化或返回其明文。
全项目只有 `QwenAdapter` 可以调用 `get_secret_value()`，且只在初始化时取一次，
用于构造上游 Authorization header。

非密钥运行配置：`QWEN_BASE_URL`、`QWEN_MODEL`、`QWEN_CONNECT_TIMEOUT_SECONDS`、
`QWEN_READ_TIMEOUT_SECONDS`、`QWEN_WRITE_TIMEOUT_SECONDS`、
`QWEN_POOL_TIMEOUT_SECONDS`、`QWEN_MAX_OUTPUT_TOKENS`。

密钥与非密钥由同一个 Settings 类读取，但字段类型、展示行为和明文使用边界不同。
同一入口不等于同一等级。

## 本地与 ECS 配置

从模板创建 `.env`，真实密钥只写入 `.env`：

```bash
cp .env.example .env
chmod 600 .env
```

`.env` 已被 `.gitignore` 忽略，不进入 Git。其内容不得粘贴到测试输出、任务笔记、
shell 历史、截图、聊天消息或应用日志中。

允许在没有 `DASHSCOPE_API_KEY` 的情况下启动应用，以保留健康检查、数据库命令、
OpenAPI 和不调用 Qwen 的本地测试。但密钥为空时，Qwen 请求必须在发出 HTTP
之前失败。

## 密钥轮换

1. 在 Qwen 平台创建新密钥。
2. 修改 ECS `.env` 中的 `DASHSCOPE_API_KEY`，过程中不打印。
3. 重启应用进程。
4. 执行一次最小非流式调用和一次最小流式调用。
5. 在 Qwen 控制台确认新调用已出现。
6. 确认无误后再吊销旧密钥。

顺序不可颠倒。新密钥通过验证之前吊销旧密钥会直接造成服务中断。

密钥一旦进入 Git 历史，仅删除当前工作区文件无效：历史对象仍存在于仓库中，
任何一次 clone 都会带走。必须先吊销或轮换，再处理历史。

## 日志边界

允许记录：Provider 名称、模型名、HTTP 状态类别、request id、是否可重试、
延迟、token 数量。

禁止记录：Authorization header、API Key、完整 `.env`、Prompt、模型回答、
厂商原始错误响应体。

`SecretStr` 只能防止配置对象的意外展示。调用 `get_secret_value()` 之后得到的
是普通字符串，因此不能记录请求 header，也不能开启会输出 Authorization 的
HTTP 调试日志。

## 成本数据

本地成本账本与价格配置按 Day114 决策暂缓。当前账号级用量和账单数据由 Qwen
控制台提供，其详细请求日志保留约 14 天。只有当模型调用能够归属到具体用户、
项目和业务操作时，才重新考虑应用侧的成本归因表。