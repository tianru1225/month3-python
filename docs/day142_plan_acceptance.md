# Day142：手工发布计划验收

> 状态：已通过。
>
> 执行日期：2026-09-28。
>
> 起始基线：`8cd881374f426048aed7a1ce506cfbdbe5952751`。
>
> 验收提交：`5f3c87b24497dedb9229326d87eabf8cacfed0ce`。

## 结果

| 项目 | 结果 |
| --- | --- |
| 起始基线 | HEAD 与 origin/main 一致，均为 `8cd8813` |
| 服务状态 | api、worker、nginx、postgres、redis 均在运行，postgres healthy |
| 用户 / 项目 ID | 30 / 10 |
| READY 资料版本 ID | 10 |
| 资料哈希 | `cd8c74ef130fd264d092ad84878a8a6a11a0a446875aa38ee472b6e105cf9181` |
| 计划 ID / 版本 ID | 8 / 12 |
| 版本号 | 1 |
| 创建 DRAFT | 通过，来源 MANUAL，未记录模型信息 |
| 固定任务数量 | 3（task_id 11、12、13） |
| 任务日期 | 2026-09-28、2026-09-29、2026-09-30 |
| 前置关系数量 | 2（11 → 12，12 → 13） |
| 发布 PUBLISHED | 通过，is_current=true，已记录发布时间和确认用户 |
| current 版本查询 | 通过，返回版本 12 |
| 发布后写入门禁 | 通过，返回 409 PLAN_VERSION_IMMUTABLE |
| 专项 Service smoke | passed |
| Shell 语法检查 | `bash -n` 无输出 |
| 计划/任务回归测试 | 33 passed |
| 全量测试 | 394 passed |
| Ruff | All checks passed |
| mypy | Success: no issues found in 106 source files |
| 空白字符检查 | `git show --check` 无输出 |
| Alembic current | `d139f2a3b4c5 (head)` |
| Alembic check | No new upgrade operations detected |
| 提交文件 | 仅 `scripts/day142_manual_plan_smoke.sh`（100755）和 `docs/day142_plan_acceptance.md` |
| 推送结果 | `8cd8813..5f3c87b`，HEAD 与 origin/main 一致，工作区干净 |

## 本日结论

本日证明 READY 资料可以作为人工计划的来源快照，并且计划版本可以经历 DRAFT -> PUBLISHED。任务内容是固定人工输入，不是模型输出。发布后版本不可原地追加任务，后续修改必须创建新的草稿版本。

本日没有修改 `app/`、`migrations/` 或既有测试，没有新增迁移。

## Day143 使用的数据

| 项目 | 值 |
| --- | --- |
| project_id | 10 |
| plan_id | 8 |
| plan_version_id | 12 |
| task_ids | 11、12、13 |

Day143 在这批数据上实现今日任务查询，不重新创建计划数据。

## 不在本日范围

- 没有计划 Router；
- 没有自动计划生成；
- 没有 LLM 或 RAG；
- 没有今日任务 API；
- 没有 TXT/PDF 支持扩展；
- 没有修改已发布版本。

## 原理问题

1. 为什么要先验证 READY 资料，再创建正式计划草案？

   计划的内容来自资料。资料没处理完或已损坏时建计划，计划就没有可靠依据。先过门禁，保证计划一开始就建立在可用的资料上。

2. 为什么固定计划内容要保存 material_version_id 和 content_hash？

   资料以后可能会更新。保存版本 ID 能知道计划用的是哪一版，保存哈希能证明当时的内容确实是这一份。以后资料变了，可以据此判断计划是否需要重新生成。

3. 为什么任务要先写入 DRAFT 版本，再发布？

   草稿阶段可以随意增删和调整任务，确认无误后再发布。这样用户看到的永远是完整的计划，不会看到写了一半的版本。

4. 为什么发布后的版本不能直接添加任务？

   用户已经在按发布的版本学习，原地修改会让学习记录对应不上原来的计划，历史也无法追溯。要修改就新建一个草稿版本，改好后再发布，旧版本原样保留。

5. 为什么 Day142 不需要模型，也不需要计划 Router？

   今天只验证计划和任务的数据流程是否正确。用固定数据可以排除模型输出不稳定的干扰；直接调用 Service 就能验证数据库链路，Router 等到真正需要对外提供接口时再加。