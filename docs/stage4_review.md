# Stage 4 Review

## Result

- Review date: 2026-08-20
- Result: [填写 passed 或 failed]
- Stage D baseline commit: `c4f471e`
- Final documentation commit: the Git commit containing this document
- Alembic head: `7c1a8796e34b`

Stage 4 established a PostgreSQL-backed FastAPI service with Argon2 registration, username/password login, JWT user authentication, an independent API Key gateway boundary, a vendor-neutral model Provider layer, Qwen non-streaming and streaming calls, structured output, bounded retry behavior, and a Python 3.14 API/Worker runtime.

Registration and login use only `username + password`. Email login and identifier routing are not part of the final contract.

## Runtime

- API Python version: `[填写完整版本]`
- Worker Python version: `[填写完整版本]`
- Application image: `month3-api:day120`
- Application image ID: `[填写 image ID]`
- Base image digest: `[填写 python:3.14-slim digest]`
- API and Worker image IDs identical: [填写 yes/no]
- Python 3.14 import/compile verification: [填写 passed/failed]
- Ruff under Python 3.14: [填写 passed/failed]
- mypy target/runtime 3.14: [填写 passed/failed]
- Full pytest under Python 3.14: [填写 passed/failed 和测试数量]

The ECS host Python was not upgraded. Python 3.14 is isolated to the application image.

## Database

- Database: PostgreSQL 17 Alpine in Compose
- Persistent storage: named volume `postgres_data`
- Existing database upgrade: passed
- Current revision: `7c1a8796e34b (head)`
- `alembic check`: no new upgrade operations detected
- Empty-database replay from base to head: passed
- Tables: `alembic_version`, `users`, `conversations`, `messages`
- Final user fields: `id`, `username`, `password_hash`, `status`, `created_at`
- Email field absent: yes
- `ix_users_username` unique index: present
- `ck_users_status` check constraint: present
- Product volume deleted or recreated: no

## Authentication boundary

- Username/password registration: passed
- Username/password login: passed
- Argon2 password verification: passed
- JWT `/users/me`: passed
- JWT own-user route: passed
- Cross-user access returns `403 USER_FORBIDDEN`: passed
- Missing/invalid/expired JWT returns 401: passed
- Token rejected after user becomes disabled: passed
- JWT cannot replace API Key: passed
- API Key cannot replace JWT: passed
- Temporary smoke users removed: passed
- Password, hash, JWT and Authorization logging scan: passed

## Qwen Provider

- Ordinary request uses `max_completion_tokens`: passed
- Ordinary request omits `max_tokens`: passed
- Structured request omits both output-limit fields: passed
- Non-streaming contract: passed
- Streaming `text_delta`, `usage`, `done` contract: passed
- Stream cancellation closes upstream response: passed
- Mock Provider capability and vendor-error boundary: passed
- Retryable 429 matrix: passed
- Non-retryable and unknown 429 matrix: passed
- `Retry-After` parsed only for retryable 429: passed
- Non-retryable 429 attempted once: passed
- Real non-streaming smoke: [填写 passed，或 skipped 及明确原因]
- Real streaming smoke: [填写 passed，或 skipped 及明确原因]

The official Alibaba Cloud Model Studio error-code page was reviewed on 2026-08-20. Raw Provider responses, prompts, answers and credentials were not retained.

## Rollback exercise

- Compatible rollback image: `month3-api:day120-py310-rollback`
- Rollback Python version: `[填写完整 3.10 版本]`
- API health under rollback image: passed
- Database ping under rollback image: passed
- Worker started under rollback image: passed
- Alembic revision unchanged: `7c1a8796e34b`
- Database downgrade performed: no
- `postgres_data` removed or recreated: no
- Restored image: `month3-api:day120`
- API and Worker restored to Python 3.14: passed
- Health and database ping after restore: passed

## Quality gates

- Authentication专项 tests: [填写 passed 和数量]
- Provider/Qwen专项 tests: [填写 passed 和数量]
- Full pytest: [填写 passed 和数量]
- Ruff: passed
- mypy: passed
- `git diff --check`: passed
- Tracked-secret scan: passed
- Worktree clean after push: [填写 yes/no]

## Security and operations decisions

- Secrets remain in `.env` and are not committed.
- PostgreSQL and Redis are reachable only on the Compose network.
- API and Nginx remain bound to loopback in the current deployment.
- API and Worker use the same application image.
- Provider retries are bounded and owned by the execution layer.
- Existing PostgreSQL data is retained in the named volume.

## Deferred work

- Refresh token, token rotation and logout/revocation remain scheduled for Day232/233.
- Login rate limiting and automatic account lockout are deferred for the current small-user deployment.
- SSO, OAuth, MFA and RBAC are not required by the current product scope.
- A second model Provider, model routing and local cost attribution remain deferred.

## Final decision

Stage 4 is [填写 accepted/not accepted]. [填写一句事实依据；若未通过，列出阻塞项。]