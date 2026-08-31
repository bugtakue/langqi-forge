# Harness architecture

## 核心判断

Langqi Forge 把“Agent 必须参与”与“成熟能力不应每次重写”同时成立：模型负责不确定性高、需要语义判断的控制面；确定性编译器和能力内核负责高频、可验证的数据面。

正式运行只有三条路线：

1. `planner-approved-deterministic-kernel`：模型通过函数工具确认领域与完整覆盖，执行版本化内核；这是 GitHub / Spreadsheet 的合格路径。
2. `planner-routed-bounded-code-agent`：需求不在已知内核覆盖内，进入受限代码 Agent。
3. `planner-disagreement-safe-deterministic-kernel` 或 `planner-failure-safe-deterministic-kernel`：已知领域在模型异常时仍可生成软件，但发布门必定失败。

第三条路线故意把“可用性”和“可发布性”拆开。模型故障不应把已有软件毁掉，也不能被隐藏成一次成功 Agent 运行。

## 规划 Agent

规划阶段只允许一个函数：

```text
select_build_contract(
  domain,
  kernel_eligible,
  capability_tags,
  risks,
  validation_focus,
  rationale
)
```

输入是有长度上限的需求摘要，而不是整个工作区。需求文本被标为不可信数据，不能要求 Agent 忽略系统指令或调用额外工具。正式稳定领域限制一次成功模型请求，输出上限 700 Token。

## 代码 Agent

未知能力才打开代码 Agent。它只能操作生成工作区中的 `frontend/` 与 `backend/`，并受以下约束：

- 文件路径白名单与仓库边界；
- 工具 schema 校验；
- 最大迭代数和全局模型请求预算；
- 连续三轮无有效工作区工具调用即熔断；
- 每轮写入、命令、模型回复和 Token 全量留痕；
- 失败聚类后按根因生成最小修复包，避免每条 GUI 失败重复调用模型。

## 验证层

验证分四层，低成本失败先返回：

1. 包结构、依赖与可构建性；
2. 独立 smoke port 启动与 `/api/health`；
3. 完整 Playwright GUI，4 workers、文件内完全并发；
4. 对抗夹具与 fail-closed 资格门。

资格门同时绑定需求 SHA-256、模型工具决策、调用/尝试次数、Token 范围、GUI 测试计数、并发模式、耗时与失败统计。局部修复测试不能替代最终全量测试。

## 关键失败语义

| 失败 | 运行结果 | 发布结果 |
|---|---|---|
| 模型拒答或坏 JSON | 已知领域安全生成；未知领域停止 | 失败 |
| 模型选错领域 | 编译器保留已知稳定内核 | 失败 |
| 模型未调用规定工具 | 不接受 JSON 说明冒充正式决策 | 失败 |
| HTTP 重试 | 可以恢复生成 | 当前证据门失败 |
| GUI skipped / flaky / unexpected | 保留报告与修复包 | 失败 |
| 需求哈希变化 | 可以重新编译 | 旧资格证据失效 |

## 为什么不是普通 Claude Code / GPT 直接写代码

通用 Coding Agent 在陌生任务上有价值，但会把每次运行都变成一次开放式软件开发。这里的竞争指标同时包含 GUI 通过率、模型 Token 与墙钟时间，因此 Harness 应学习并冻结已经验证的能力，把模型预算留给规格分流、未知能力和根因修复。这是软件工厂的“经验编译”，不是聊天界面的另一层包装。
