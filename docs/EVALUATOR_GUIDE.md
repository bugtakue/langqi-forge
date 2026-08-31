# Evaluator guide · 3 分钟看懂琅岐铸造

## 0:00–0:30：它解决什么

通用 Coding Agent 每次都从空白开始，已经验证过的工程能力不会自动变成下一次可审计的经验。Langqi Forge 把一次受约束的模型决策路由到版本化能力内核，再用公开黑盒和对抗复验决定该能力能否被“铸成胶囊”。胶囊可影响后续路由，但永远不免除新制品的复验。

一句话：**复用经验，不复用信心。**

## 0:30–1:15：找到真正的 Agent

1. [`planner.py`](../factory26_harness/planner.py) 定义唯一强制函数 `select_build_contract`。模型必须选域、给出能力标签、风险和验收焦点；拒答、错域或参数漂移都不能过门。
2. [`capabilities.py`](../factory26_harness/capabilities.py) 对每个原子需求执行闭世界覆盖。模型不能因为“看起来很像”就把未知需求塞进旧内核。
3. [`agent.py`](../factory26_harness/agent.py) 只在存在未覆盖语义时打开，并被路径、字节、工具次数、无进展轮次和回滚事务限制。

## 1:15–2:00：查看可证伪记忆

[`capability_memory.py`](../factory26_harness/capability_memory.py) 只在所需 profile 全绿后铸造能力胶囊：GitHub 必须同时通过 baseline 和改名/并发对抗，Spreadsheet 必须通过 baseline。胶囊绑定：

- 生成 run id、Harness revision 和应用源码 SHA；
- 需求、测试包、compact feedback 与原始 Playwright JSON；
- 能力版本、行为条款和明确排除项；
- `skips_revalidation: false`。

评测失败时则保留每个归一化根因的一个最小观测反例，而不是把一整段日志假装成学习。

## 2:00–2:40：独立验证，不信生成者自述

- [`qualification.py`](../factory26_harness/qualification.py) 从双域制品重算资格门。
- [`evidence.py`](../factory26_harness/evidence.py) 导出前不信旧的 `qualification.json`，会再算一次。
- [`verify_evidence.py`](../factory26_harness/verify_evidence.py) 只使用导出包内文件，第三次重算核心检查和脱敏轨迹。
- [`judge_report.py`](../factory26_harness/judge_report.py) 只是只读展示层；无关或伪造的资格 JSON 无法让它显示 `QUALIFIED`。

资格门不接受“`expected=101/102`”这类统计自报：它逐项复核 spec ID、文件、project、result/retry、固定 inventory SHA、Playwright 1.62.1 运行时树、夹具 SHA 和由原始需求编译出的 Planner Prompt SHA。证据中如仍有 password/cookie/session/header/JWT/连接字符串等未脱敏材料，即使哈希链被重封也会被拒绝。

## 2:40–3:00：声明边界

仓库当前的 [`evidence/final`](../evidence/final/README.md) 是 2026-08-31 用阿里云百炼 `qwen-plus` 生成的历史 v1 生产证据，对应当时锁定提交；它不冒充当前 v2 候选的最终证据。当前 v2 已在干净提交上顺序通过 304/304 本地黑盒，但在新的双域百炼轨迹、v2 资格门和独立验证器全部通过前，只称 `LOCAL CANDIDATE`。

公开 GUI 全绿不保证隐藏测试、Top 20 或获奖；证据包也不会冒充比赛平台的硬件计量。
