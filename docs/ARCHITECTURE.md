# Harness architecture

## 核心判断

Langqi Forge 同时坚持两件事：Agent 必须真正作出路由决策；已经被反复验证的能力不应每次从零重写。

因此，模型负责不确定性高的控制面；确定性规格编译器、版本化能力内核和证据门负责可验证的数据面。两者之间不是“模型说可以就可以”，而是一份可机检的闭世界契约。

## 规划与执行路由

Planner 只能调用 `select_build_contract`，而且该函数在正式请求中被强制选择。输入包含：

- 压缩后的原子需求摘要；
- 当前领域可用的版本化能力和行为边界；
- 明确不可用或越界的能力；
- 覆盖编译器的逐节点结果。

正常路由如下：

| 条件 | 路由 | 发布资格 |
|---|---|---|
| 已知域，本地覆盖完整，Planner 精确批准 | `planner-approved-deterministic-kernel` | 可继续验证 |
| 同上，且有版本一致的能力胶囊 | `planner-approved-capability-memory-kernel` | 可继续验证；不跳过任何复验 |
| 已知域只有部分能力未覆盖 | `planner-routed-kernel-plus-delta-agent` | 必须在增量 Agent 完成后重跑全量门 |
| 已知域但 Planner 不批准内核 | `planner-disagreement-bounded-code-agent` | 内核不得冒充被批准；全需求进受限 Agent |
| 未知域 | `planner-routed-bounded-code-agent` | 只有独立黑盒验收后才能上升 |
| 模型失败 | `planner-failure-*` | 已知内核可为可用性生成，但正式资格门必败 |

当 Planner 和本地覆盖分析冲突时，系统不会偷偷改用确定性内核并宣称成功。冲突会显式进入受限 Agent 或失败路由，并写入轨迹。

## 闭世界能力编译

能力覆盖不依赖项目名字或模糊向量相似度。每个原子需求必须被映射到当前 catalog 中的具体能力版本；一旦出现未知节点、排除项、版本不同或 Planner 未覆盖所有必需能力，内核不可全量获准。

这个设计阻止两种作弊式优化：

1. 在已知需求末尾追加一条恶意或未知操作，却让整组需求继承内核覆盖。
2. 因为以前的任务名称相似，就复用一份已过时的模板或证据。

## 受限代码 Agent

只有未覆盖能力才打开代码 Agent。它只能操作生成工作区中的 `frontend/` 与 `backend/`，并受以下约束：

- 路径白名单、symlink 和仓库边界检查；
- 工具 schema、命令、单轮写入和总字节预算；
- 最大迭代数、模型请求预算和连续无进展熔断；
- 每个 batch 先创建 Git checkpoint，任何越界或失败都回滚；
- 中断后只能根据带校验和的 transaction ledger 恢复；
- 失败聚类后按根因产生最小修复包，不按每个测试重复调用模型。

## 反例与可证伪能力胶囊

黑盒评测失败时，系统保留每个归一化失败签名的一个观测代表，记录其相关需求和文件。这是“每类失败的最小观测集”，不冒充数学上的全局最小输入。

当当前制品在规定 profile 全绿后，才能铸造能力胶囊：

- GitHub 需要 `baseline + adversarial`；
- Spreadsheet 需要 `baseline`；
- 胶囊绑定 run id、源码 revision/SHA、需求 SHA、测试包 SHA、原始 GUI 报告 SHA、能力版本、行为条款和排除项；
- 后续运行只在“同域 + 当前所需能力为版本相同子集 + 零未覆盖需求”时匹配；
- 匹配只增加一条先验证据，`reuse_skipped_revalidation` 永远为 `false`。

## 验证与证据层

验证从低成本到高成本分层执行：

1. 包结构、依赖与干净构建；
2. 独立 smoke port 启动和 `/api/health`；
3. 固定公开任务的原始 Playwright JSON，4 workers，文件内完全并发；
4. 改名/并发对抗夹具；
5. 运行封口和发布资格门；
6. 脱敏轨迹的确定性重演和独立证据验证。

`run-envelope.json` 交叉绑定：

- `harness-report`、`planner-contract`、`compiled-plan`；
- 应用源码文件树 SHA；
- 封口轨迹的行数、head 和模型事件哈希；
- 每次 GUI 的 compact feedback、原始 Playwright 报告、测试包和源码；
- 反例和能力胶囊。

证据导出器不信任旧的 `qualification.json`，会对当前制品重算。独立验证器又会在导出包上第二次重算核心规则，并证明公开脱敏轨迹是精确轨迹的确定性转换，而不是另写一份“好看的轨迹”。

## 关键失败语义

| 失败 | 运行结果 | 发布结果 |
|---|---|---|
| 模型拒答、坏 JSON 或未调用指定工具 | 已知域可生成安全基座 | 失败 |
| Planner 选错域或未批准内核 | 不把本地内核冒充为 Agent 决策；进受限 Agent | 只有独立验证后才可重新评定 |
| HTTP 重试 | 可能恢复生成 | 当前稳定域证据门失败 |
| GUI `unexpected / skipped / flaky` | 保留原始报告和反例 | 失败 |
| 同一评测 label 重跑 | 拒绝覆盖旧证据 | 失败 |
| 需求、测试包、源码或轨迹变化 | 旧封口/胶囊不匹配 | 失败 |

## 与 Codex / Claude Code 的可证伪对照

`benchmarks/` 明确分成两个问题：

1. **Factory-system 比赛**：参赛 Harness 可以带自己的能力记忆，这正是系统设计的一部分。
2. **Blank-workspace Agent 比赛**：Codex 和 Claude Code 都从空目录开始，获得同一份只读需求、墙钟和外部评分器，且禁用会话记忆和测试源码。

两种成绩不混在一起；单次结果只描述该版本、该模型、该预算和该任务，不外推成底层模型的普遍排名。
