# Qwen Provider 配置说明

## 密钥边界

密钥配置：`DASHSCOPE_API_KEY`。

在 `Settings` 中以 Pydantic `SecretStr` 加载，配置对象的 `repr()` 与
`model_dump()` 默认显示为掩码。应用代码不得打印、记录、序列化或返回其明文。
对于 `DASHSCOPE_API_KEY`，只有 `QwenAdapter` 可以调用 `get_secret_value()`，
且只在初始化时取一次，用于构造上游 Authorization header。

非密钥运行配置：`QWEN_BASE_URL`、`QWEN_MODEL`、`QWEN_CONNECT_TIMEOUT_SECONDS`、
`QWEN_READ_TIMEOUT_SECONDS`、`QWEN_WRITE_TIMEOUT_SECONDS`、
`QWEN_POOL_TIMEOUT_SECONDS`、`QWEN_MAX_OUTPUT_TOKENS`。

密钥与非密钥由同一个 Settings 类读取，但字段类型、展示行为和明文使用边界不同。
同一入口不等于同一等级。`DATABASE_URL` 可能包含数据库密码，因此同样使用
`SecretStr`，其明文只允许在 SQLAlchemy Engine 和 Alembic 配置边界读取。

## 本地与 ECS 配置

从模板创建 `.env`，真实密钥只写入 `.env`：

```bash
cp .env.example .env
chmod 600 .env