# Day141：真实 Markdown 驱动项目验收

## 范围与基线

- 代码基线：022841d26724a3fdd9e04fbaa339429a0cc0f29b。
- 状态：已执行，以下为 2026-09-23 ECS 实测结果。
- 本日不修改产品代码、数据库结构或接口。
- 输入为真实 UTF-8 Markdown 笔记，不是临时编造的小样例。
- 本日只创建项目并准备可用资料，不生成计划、不调用大模型。
- 验收数据保留给 Day142，不执行数据库或资料卷清理。

## 实际结果

| 项目 | 真实结果 |
| --- | --- |
| 执行日期 | 2026-09-23（UTC） |
| 源文件大小 / SHA-256 | 107649 字节 / cd8c74ef130fd264d092ad84878a8a6a11a0a446875aa38ee472b6e105cf9181；传输后 Windows 与 ECS 两端哈希一致 |
| username / user_id | day141-20260923T075934Z-5189 / 30 |
| project_id / material_id / version_id | 10 / 10 / 10 |
| summary.json 位置 | artifacts/day141-20260923T075934Z-5189/summary.json |
| 注册 / 登录 | 201 / 200 |
| 创建项目 / 上传 Markdown | 201 / 201；上传后为 UPLOADED，大小与哈希与本地一致 |
| 首次绑定 / 重复绑定 | 201 / 200，同一 binding ID |
| 绑定列表 | 200，一条有效绑定，unbound_at 为空 |
| UPLOADED 时可用门禁 | 409 MATERIAL_READY_REQUIRED（gate_before_parse: rejected as expected） |
| 未登录读取项目 | 401 |
| 首次投递解析 | 202，返回 job_id |
| 最终 parse_status | QUEUED → READY；未观察到 PARSING，属正常 |
| READY 后重复解析 | 200，同一 job_id，状态 READY |
| 原文件哈希 / 解析文本一致性 | 存储原文件 SHA-256 与上传记录一致；解析文本与原文逐字一致 |
| READY 门禁 / 来源块定位 | 通过，仅返回 version_id=10；line_count=4329，block_count=894；全部来源块的字符偏移切片与行号核对通过 |
| 专项回归 / 全量 pytest | 80 passed / 394 passed，与基线一致 |
| Ruff / mypy / bash -n / git diff --check | All checks passed / Success: no issues found in 106 source files / 无输出 / 无输出 |
| Alembic current / check | d139f2a3b4c5 (head) / No new upgrade operations detected. |

不记录密码、JWT、.env、完整响应、资料正文或存储对象键。提交和推送记录由验收时附终端输出，不在提交前捏造最终哈希。

## 本日能力边界

1. 上传成功只表示原文件和元数据已保存，不能把 UPLOADED 当作 READY。
2. 创建项目、上传、绑定、投递分别是独立请求，不是一个跨请求事务。
3. 202 表示解析已受理，不表示解析已完成；实际状态由 PostgreSQL 中的资料版本记录返回。
4. API 与 worker 共用 material_data 卷，Redis/RQ 负责传递任务，worker 负责解析。
5. 项目绑定关联 Material；本次通过门禁取得的具体 MaterialVersion ID 和哈希用于后续来源追溯。
6. READY 门禁目前是 Service，不存在专门的 HTTP 路由。本次容器调用验证了该 Service，但不等于未来计划接口已经强制接入它。
7. Markdown 来源块是解析定位结果，不是 Embedding，也不是向量索引。后续 RAG 分块可以在此基础上进行。
8. 项目学习目标由用户填写，本日没有从笔记自动生成项目目标或计划，也不执行 Markdown 中的代码。

## TXT/PDF 后续适配边界

当前代码只允许 .md/.markdown，MIME 为 text/markdown 或 text/plain，单文件上限 10 MiB。text/plain 是允许的 Markdown MIME，不代表 .txt 已受支持。当前 .txt/.pdf 会被上传服务以 415 / MATERIAL_FORMAT_UNSUPPORTED 拒绝。

旧 docs/material_source_contract.md 描述了更早的三格式目标，与当前 Markdown-only 实现存在差异。本日按最新总计划的 Day141 范围执行，不宣称三格式已实现，也不顺带扩写解析器。

后续如正式增加 TXT：扩展上传格式校验、保存 UTF-8 原文和行号/偏移定位，并增加对应测试。
后续如正式增加文本型 PDF：提取文本层，保留页码定位；无文本层、损坏、加密且无法读取的文件应明确拒绝，不静默进入 READY。
扫描 PDF、OCR、DOCX 不进入本日范围。云解析 API 也不是本日必需依赖。

## 原理自述

- 为什么绑定成功不代表可以开始生成正式计划？
  绑定只说明项目关联了这份资料，资料本身可能仍是 UPLOADED 或 FAILED；只有门禁确认版本为 READY 且解析产物有效，才能作为计划依据。
- 为什么 POST parse 返回 202 后还要 GET 查询？
  202 只表示任务已放进 RQ 队列，解析由另一个进程 worker 异步完成；真实结果要从 PostgreSQL 的版本记录里查。
- 为什么资料属于用户，资料绑定属于项目，具体来源指向资料版本？
  同一份资料可被用户的多个项目复用；“哪个项目用哪份资料”是项目自己的事；资料更新会产生新版本，来源必须指向当时的具体版本和哈希，才能准确追溯。
- 如果 worker 没有挂载资料卷，会在哪个环节失败？
  worker 读取原文件时就找不到文件，版本变为 FAILED，smoke 在轮询阶段停止；即使写出了产物，API 容器也看不到，第二次门禁会失败。
- 原文件、解析文本、来源块、未来向量块分别负责什么？
  原文件是证据原件，用哈希锚定；解析文本是规范化后的可读内容；来源块按文档结构切分并带行号和偏移，用于引用定位；向量块将来按 token 预算切分用于检索，本日尚未实现。
