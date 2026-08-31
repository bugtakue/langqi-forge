# Production trace contract

每个生成制品都包含 `.arc/production-trace.jsonl`。每行是一个版本 2 JSON 事件，`sequence` 从 1 连续递增，并通过 `previous_hash → hash` 形成完整链。中间任意改动、删行、插行或版本降级都会使验证失败。

## 比赛要求如何落到轨迹

| 要求 | 主要事件 | 可验证内容 |
|---|---|---|
| Prompts | `agent_session_started`, `model_request` | 完整 system/user messages、紧凑需求摘要、工具 schema、强制 tool choice、请求尝试数与超时上限 |
| 工具调用 | `model_response`, `agent_tool_call`, `deterministic_scaffold`, `validation_result`, `public_evaluation_*` | provider response id、原始 tool call、实际应用参数、生成文件、构建/启动/Playwright |
| Agent 迭代 | `agent_session_started`, `agent_session_completed`, `run_completed` | Planner 与 Coding Agent 的阶段、次数、Token、路由和结果 |
| 人工干预点 | `human_intervention_checkpoint` | 是否需要人工、实际次数、失败时是关闭门还是临时改代码 |
| 能力学习 | `counterexample_observed`, `capability_capsule_forged`, `capability_memory_consulted` | 失败聚类、胶囊来源证据、后续匹配和“未跳过复验” |

同时：

- `execution_route_selected` 记录模型决策如何改变内核/增量 Agent 路由。
- `validation_result` 的最后一组结果必须与 `harness-report.json` 完全一致。
- `public_evaluation_completed` 同时绑定 compact feedback、原始 Playwright JSON、逐项 spec inventory、应用源码、测试包、固定夹具和 Playwright 运行时树。
- `run_completed` 内嵌的 report 必须与文件字节语义一致。
- 名称含 `api_key`、`authorization`、`secret`、`access_token`、`password`、`cookie`、`session`、`header`、`connection_string` 等字段在写盘前递归替换为 `[REDACTED]`；Bearer/Basic、云密钥、JWT、Cookie header 和带密码连接串等形式也会从自由文本中脱敏。资格门、证据导出和独立验证均 fail-closed 复扫。

## 运行封口

`.arc/run-envelope.json` 是轨迹与其他制品的交叉索引。它重新计算并绑定：

- 完整应用源码文件树（路径、字节数、SHA-256）；
- `harness-report.json`、`planner-contract.json`、`compiled-plan.json`；
- 轨迹 SHA、head、行数、模型 request/response/tool-call 行哈希与 `run_completed` 行哈希；
- 每次不可覆盖的 GUI label、feedback/raw report SHA、source SHA 和 test-bundle SHA；
- 反例文件与能力胶囊。

封口会在生成完成、每次公开评测、反例记录和胶囊铸造后重新写入，但每次都从当前文件与封口轨迹重建，而不是只追加一个“成功”布尔值。

## 精确轨迹与公开脱敏轨迹

最终证据包保留两份轨迹：

1. `production-trace.jsonl`：精确的源制品轨迹，用于和 `run-envelope.json` 完整交叉校验。
2. `production-trace.sanitized.jsonl`：只把生成项目绝对路径和 Harness 仓库绝对路径替换成固定占位符，然后重建哈希链。Prompt、模型回复、工具参数、Token、失败和评测结果不删除。

独立验证器不只检查两份文件各自的哈希。它会从精确轨迹的 `run_started` 导出两个绝对根路径，重演同一脱敏和 reseal 算法，要求结果与公开轨迹逐字段一致。

公开提交链接应指向脱敏轨迹；精确轨迹与整个证据包用于独立审计。

## 评委报告的边界

`factory26_harness.judge_report` 是只读的展示层，不是新证据源。它只能在 `verify_run_envelope` 和能力胶囊验证通过后，将已封口制品派生成自包含 HTML/JSON。报告不回写项目、不改写轨迹、不重跑评测，也不把未提供的资格结果推断为通过。因此它适合作为评委阅读入口，但最终真值仍由封口制品、资格文件和独立证据验证器共同决定。

## 人工干预边界

参赛合格路径的目标是：

- Planner 迭代：1
- Coding Agent 迭代：0（公开双域全覆盖路由）
- 人工干预：0

`human_intervention_checkpoint` 不是空字段。它明确宣告：最终资格运行必须自主完成；任何异常关闭资格门，不在计时评分运行中临时请人改代码。

开发期的人工决策和修复历史属于研发过程，单独记录在 `docs/BASELINE.md` 与 `docs/HARDENING.md`，不冒充最终运行的 Agent 迭代。

## 证据的能力与边界

证据包可以证明：文件内部自洽、固定公开题绑定、轨迹未被局部改写、脱敏结果可重演、资格规则能从导出文件重算。

它不能凭自己证明：第三方网关的硬件身份、官方计费或最终评分。这些仍以 Factory26 平台记录为外部权威。
