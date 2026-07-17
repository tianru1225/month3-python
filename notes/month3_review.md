# Month3 Review

## 本月完成

- FastAPI 基础接口
- API Key 鉴权
- 统一成功响应 `code/msg/data`
- 错误响应 `detail.code/detail.message`
- `X-Request-ID` 请求追踪
- Router / Service / Repository 分层
- SQLAlchemy 用户模型与多表关系建模
- Alembic 迁移草案
- Redis + RQ 后台任务
- Dockerfile 单容器构建
- Docker Compose 编排 `api/redis/worker/nginx`
- Nginx `/api/` 反向代理
- slowapi 读取 `X-Real-IP`
- 回归测试
- 数据库故障注入

## 当前可访问入口

- API 直连: `http://127.0.0.1:8001`
- Nginx 入口: `http://tianruliu.cn/api`

## 当前服务

- `month3-nginx`
- `month3-api`
- `month3-redis`
- `month3-worker`

## 当前测试

- `pytest -q`: 29 passed

## 当前已知边界

- API 镜像 tag 仍可能是 `month3-api:day086`
- API 仍暴露宿主机 `8001`，后续生产化可只暴露 Nginx
- Redis 当前仅 Compose 内部访问，未做持久化 volume
- 数据库仍是 SQLite `dev.db`
- HTTPS/certbot 当前由宿主机历史配置处理，Nginx 容器当前只验证 HTTP
- CDN 真实 IP 可信代理链留到 Day288
- 前端尚未接入

## 下月重点

- Ollama / 模型服务层
- LLM Provider 抽象
- 聊天接口
- 流式输出
- 模型调用错误处理