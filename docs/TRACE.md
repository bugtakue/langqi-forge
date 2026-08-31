# Production trace contract

每个生成制品都包含 `.arc/production-trace.jsonl`。一行一个不可变 JSON 事件，`sequence` 从 1 连续递增；公开证据只替换本机绝对路径，不删除 Prompt、回复、工具参数或失败。

## 评委关心的四类证据

| 要求 | 轨迹事件 | 内容 |
|---|---|---|
| Prompts | `agent_session_started`, `model_request` | 完整 user Prompt；完整 system/user messages；工具 schema |
| 工具调用 | `agent_tool_call`, `deterministic_scaffold`, `validation_result`, `public_evaluation_*` | 模型函数参数、生成文件、构建/启动/健康检查与 Playwright |
| Agent 迭代 | `agent_session_started`, `agent_session_completed`, `run_completed` | 阶段、迭代序号、Planner / Coding Agent 分项计数与 Token |
| 人工干预点 | `human_intervention_checkpoint` | 是否需要人工、次数和失败时策略 |

此外：

- `model_response` 保留百炼 response id、模型名、endpoint host、原始 tool call 与 usage。
- `execution_route_selected` 说明模型决策如何改变执行路线。
- `qualification_gate_completed` 绑定每份关键证据的 SHA-256 与失败检查。
- 所有名称包含 `api_key`、`authorization`、`secret`、`access_token` 的字段都会在写盘前递归替换为 `[REDACTED]`。

## 最终运行的人工边界

最终 GitHub 与 Spreadsheet 生产运行均为：

- Planner 迭代：1
- Coding Agent 迭代：0
- 人工干预：0

`人工干预=0` 不是省略字段。运行在路由确定后写入显式 checkpoint：最终资格执行必须自主完成；任何异常关闭发布门，不在评分运行中请求人手改代码。开发期修复历史单列在 `docs/BASELINE.md`，不混入最终生产轨迹。

## 公开文件

- `evidence/final/github/production-trace.jsonl`
- `evidence/final/sheet/production-trace.jsonl`
- `evidence/final/qualification.json`
- `evidence/final/manifest.json`

公开任务测试源码不在仓库中；compact GUI feedback 与资格报告足以证明测试计数、并发模式、耗时和结果，原始 Playwright 报告仍保留在本地生成制品中。
