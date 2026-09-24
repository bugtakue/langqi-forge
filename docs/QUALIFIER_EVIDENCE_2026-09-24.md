# 2026-09-24 本地验证记录

本页按验证发生顺序追加。早期段落里「当前镜像尚未取得」等状态由文末较新的验证记录更新；每段运行结论仅适用于它明确列出的源码提交、ZIP 与环境。

## 已完成协议运行使用的源码与包

- 源码分支：`codex/factory26-compliant-20260924`。
- 本轮已验证源码提交：`56fe00befd5d2d47c727056315ff1c02282ec67f`。之前的 `28a013f6e7d11100db3c7fffdb84ba298343c5bc` 协议验证仍保留为历史记录。
- 本轮 ZIP：`dist/langqi-forge-qualifier.zip`，SHA-256 `1ef3b6150d14ed224c7472862dfe1b0fa14121bc25fa096bf358f0fbb2f5aba6`。13 个文件（含哈希清单），不含任务专用模板或旧实现。
- 该 ZIP 是以下协议运行的精确输入。后续若提交新 commit，即使只更新文档，打包器的来源 revision 也会改变；新的 ZIP 应在交付时单独标明哈希并再做一次运行确认。

## 验证层级

1. Python 保留测试 45/45 通过；包含模型缺失时失败关闭、Runner 预填文件兼容、通用存储并发、包白名单、轨迹哈希。
2. 主办方本地模拟器 `--prepare-only` 解包成功，清单验证得到上述源码提交。
3. 使用**本机已有的旧版 ARC-Bench Runner 基础镜像**加主办方当前 `local_runner.py` 包装，在自建一条「Example heading」协议夹具上运行成功。源码位于 `tests/protocol_gateway.py` 与 `tests/protocol_requirements/requirements.yaml`；它不是大模型，也不是比赛题目。
4. arm64 协议运行工作区：`../factory26-local-simulation/runs/qualifier-protocol-final-20260924/`；amd64 协议运行工作区：`../factory26-local-simulation/runs/qualifier-protocol-amd64-20260924/`。两者 `local-result.json` 均记录 `container_exit_code=0`、`evaluation_status=skipped`、`score=null`，并留下完整哈希链轨迹；它们未提供 Playwright 测试。
5. 加入独立的 `tests/protocol_playwright/REQ-1.spec.ts` 后，以**同一个本轮 ZIP**做 arm64 本地模拟器浏览器链路验证：`../factory26-local-simulation/runs/qualifier-protocol-gui-20260924/`。`local-result.json` 记录 `container_exit_code=0`、`evaluation_status=completed`、`passed=1`、`failed=0`、`score=null`；浏览器确实访问了协议夹具产生的页面。这里的 1/1 只证明 ZIP → 模型接口 → 源码修改 → 部署 → Playwright 的连通性，不是公开练习或比赛通过率。
6. GUI 协议运行的 `.arc/harness-report.json` 记录 1 条夹具需求已实现、4 次模型协议请求以及结构/包策略/交互/前端构建/后端启动健康检查全通过；`.arc/production-trace.jsonl` 共 26 条，哈希链校验有效。Meter 使用本机拒绝连接的地址隔离，所以 Token 成本与分数为 `null`。

## 明确不能据此声称的内容

- 没有使用真实大模型完成 BookStack/Keep，**没有这两道公开练习的 GUI 通过率、成本或官方得分**。
- 假模型只用于证明 ZIP、接口、工具调用、源码修改、构建和 Runner 部署链路，不反映生成复杂产品的能力。
- 此次完整运行的基础镜像来自本机旧版，不能替代当前主办方镜像的最终兼容性验证。当前镜像下载/构建和正式平台验证仍待完成。
- 后续源码增加了可选的视觉参考工具及对应单元测试；本节上述 ZIP 和协议 GUI 运行不含此改动。新包须以另行记录的 SHA 和运行目录为准，**视觉工具尚未用真实视觉模型或主办方 GUI 练习验证**。
- 未登录 ARC-Bench 队长账号、未建立正式比赛队伍、未上传和提交项目。登录页用该报名邮箱与 Chrome 当前保存的密码尝试一次后显示“密码错误”；没有继续猜测或重设。

下一步是取得本地练习可用的模型 API Key，用主办方当前模拟镜像在 BookStack 与 Keep 分别实跑；只有独立 GUI 结果出来，才能讨论竞争力与正式提交版本。

## 可选视觉参考版本补充验证

- 代码版本：`c97f354efca987ea607bdf078d41607bbac62a68`；ZIP：`dist/langqi-forge-qualifier.zip`，SHA-256 `b6e8266a6dd04bae648e2b1319199ed955b27b220979cbd9e8031c36d7f89933`，14 个文件（含哈希清单）。打包时工作树干净，包内清单绑定该代码版本。
- Python 单元测试 48/48 通过。新增测试覆盖视觉参考路径白名单、重复图片缓存、一次视觉请求、Token 记录、原图和密钥不进轨迹、哈希链完整性。
- 公开练习需求的图片发现检查：BookStack 的 19/19 张明确引用图片可读；Keep 的 22 个图片引用中 20 张可读，`label_filtered_list.png` 和 `search_keyword.png` 在主办方公开需求目录里不存在。不存在的图片不会暴露给模型视觉工具。
- arm64 本地旧基础镜像 + 当前模拟器包装：`../factory26-local-simulation/runs/qualifier-visual-capable-gui-20260924/`，协议夹具 `container_exit_code=0`，Playwright `1/1`，26 条生产轨迹哈希链有效，来源 revision 与上述 ZIP 匹配。
- amd64 旧基础镜像在本机 ARM 主机经 QEMU 仿真：`../factory26-local-simulation/runs/qualifier-visual-capable-amd64-protocol-20260924/` 的生成、构建、启动、健康检查通过，`container_exit_code=0`，GUI 评测跳过。另一次带 GUI 的 `../factory26-local-simulation/runs/qualifier-visual-capable-amd64-gui-20260924/` 中，同一生成应用的 agent 报告为 `local-contract-passed`，但 Playwright 在创建页面前报 `browserContext.newPage: Target page, context or browser has been closed`；这是本机跨架构浏览器仿真失败，不能算应用的功能测试失败，也不能用来证明正式 x86 环境表现。
- 上述所有运行仍只使用自建协议网关，不是实际编码模型；视觉描述链路只有模拟响应单元测试，未用真实视觉模型；`score=null` 或本机 GUI 仿真的 `score=0` 都不是官方成绩。

## ARC-Bench 官方运行时 SDK 接入验证

- 官方 [Runtime API 文档](https://arc-bench.com/api-doc) 要求通过 SDK 高层方法写运行状态、可追溯表和 Git 历史，不手工构造平台事件。本版使用主办方开源的 [`arcbench-runtime`](https://github.com/octos-org/arcbench-runtime) `0.1.0`，并保留独立哈希链作为补充审计；版本代码提交为 `d0f209a88a2500ee504f72a1fb9fc3b5a11c2d03`。
- 本版协议 ZIP：`dist/langqi-forge-qualifier.zip`，SHA-256 `b980d91ec3baf3b87d8fc1a9db1da8b2ce5d2e1c53aed9a8ec007a2af55e13ca`，15 个文件（含哈希清单）；`unzip -t` 全部通过。
- 在含该 SDK 的本地虚拟环境中，Python 单元测试 54/54 通过。新增测试直接验证 SDK 高层调用生成运行事件、`requirements`/`node_states` 追溯表和两次 Git 提交；Runner 内缺 SDK 时失败关闭。
- 使用上述精确 ZIP，在本机旧版 Runner 基础镜像 + 当前 `local_runner.py` 包装上执行自建协议夹具，运行目录为 `../factory26-local-simulation/runs/qualifier-sdk-gui-20260924/`。Runner 从 PyPI 镜像安装 `arcbench-runtime==0.1.0` 成功，随后 Agent 完成 4 次夹具模型接口请求，`container_exit_code=0`，Playwright `1/1`，`score=null`、Token 成本为 `null`。
- 该运行产生 `.arc/runner-events.jsonl` 共 42 行（含 Runner 自身事件），其中 SDK 明确记录 `running → REQ-1 implementing → REQ-1 implemented → completed`；`.arc/traceability/requirements.json` 包含 `ROOT` 和 `REQ-1`，`node_states.json` 的 `REQ-1` 为 `IMPLEMENTED`；生成项目 Git 历史有通用基线和第 1 批实现两个提交。独立 `.arc/production-trace.jsonl` 为 27 行，哈希链校验有效。
- SDK 的 `completed` 仅指智能体本地构建/启动合同完成；它没有给 `REQ-1` 发送 `test_passed`，真实 GUI 判断交给平台。夹具 1/1 不是 BookStack/Keep 或正式赛成绩；当前镜像也不是已核实的最新主办方基础镜像。正式账号登录、项目上传与提交均未做。

## 公开任务规模与模型预算核对

- 对本地模拟包现有需求树实际解析：BookStack 为 34 条原子需求、默认 9 批；Keep 为 32 条、默认 8 批。两项合计 17 批。旧的固定 64 次请求、12 万输入 Token 安全上限可能在完成所有批次前耗尽，不能据协议夹具的 4 次请求推断真实任务可完赛。
- 新版按「实际批次数 + 最多修复轮数」乘每阶段允许回合数设置全局请求安全上限，并同步放大累计 Token 安全上限；本地公开任务在默认参数下相当于每道分别有 220/200 个允许模型回合（含各自最多 2 轮修复），不是要求模型实际用满。显式环境变量上限仍优先，以防预算失控。模型响应若刚好触发累计 Token 上限，该次已产生的用量仍计入报告及脱敏轨迹。
- 这只是修复可完成性和计量准确性，**不是对真实模型成本、两个任务通过率或晋级概率的验证**；真实模型 Key/练习券仍未在本地环境可用，且当前 Runner 镜像未核实为最新。

## 当前主办方基础镜像与当时参赛包兼容性

- 参赛包源码提交 `df7f2a935932a918b6d0d220f235260969ebda6b`；ZIP `dist/langqi-forge-qualifier.zip` 的 SHA-256 为 `1aa239e29ea5e3dfa672d3de4c5549199c9046a624b7ebef324e92edc8ce5cf7`，15 个文件，`unzip -t` 通过；单元测试 55/55 通过。该 ZIP 的来源清单绑定上述源码提交，后续文档提交不改变已验证 ZIP 的源码内容。
- 已取得主办方 Docker Hub `gyataro/arcbench-runner:local-base`：本机基础镜像 ID `sha256:da61a60c2d488c1077a2cffb3f109eb312edd745ae402adecb15f2d33111f7fc`，仓库摘要 `sha256:40e003ed470dbd4c120b9019876ba77303d38dc8b34be7f6e313fe0563dd14de`，平台 `linux/amd64`。依本地模拟器脚本构建包装镜像 `arcbench-local-current:20260924`。这是取得镜像时的摘要，不保证主办方之后不更新标签。
- 用该包装镜像走完整 `local_submit.py` 时，Runner 在**启动参赛智能体之前**的 Chromium 预检失败。运行目录 `../factory26-local-simulation/runs/qualifier-budget-current-runner-20260924/`，`container_exit_code=1`；错误包含 `qemu: uncaught target signal 5` 与 `inotify_init() failed: Function not implemented`。本机是 arm64，当前镜像只提供 amd64，因此这里不能据失败判定参赛代码或正式 x86 环境的 GUI 表现。
- 绕开这项与智能体无关的浏览器预检后，将**同一 ZIP**在上述当前 amd64 基础镜像里直接运行主办方 `run_submission.py` 使用的入口/参数/环境合同：从镜像配置的 PyPI 镜像安装 `arcbench-runtime==0.1.0` 成功，使用自建模型协议夹具运行一条测试需求。运行目录 `../factory26-local-simulation/runs/qualifier-current-base-direct-20260924/`；报告 `status=local-contract-passed`、`arcbench_runtime=official-sdk`、`model_requests=4`，结构、包策略、交互策略、JavaScript 语法、前端构建、后端启动健康检查 6/6 通过。SDK 写入平台事件和需求状态，生成项目 Git 历史有初始提交及批次提交；独立生产轨迹 27/27 行哈希链有效，未发现未脱敏密钥。
- 这个**直启兼容性试验不是完整 Runner/浏览器试验，也不是 BookStack、Keep 或正式赛成绩**。它证明当前基础镜像能安装参赛依赖、执行该 ZIP、与 SDK 交互并完成本地构建启动合同；完整当前 Runner GUI 仍需能运行 amd64 Chromium 的环境，真实模型完成公开练习仍需可用的练习模型凭据。

## 通用浏览器交互探针与此前候选包

- 为补上「能构建、能启动，但用户操作可能失效」的验收盲点，新增 `browser_probe`：只在当前源码通过 quick/full 后，使用 Runner 自带 Chromium 对**生成的本地应用**执行有界语义控件操作、刷新和可见文本断言；拦截浏览器外部 HTTP 请求，不提供任意脚本、远程网址或隐藏测试读取。每批最多 3 次，若已经使用探针但没有完成带断言的动作、探针失败或后来改动源码，则该批不得仅凭旧探针完成。报告分别记录 `behavioral_probe_tested`（本地探针）与 `behavioral_gui_tested=false`（没有独立平台 GUI 成绩）。
- 第一次包含探针的协议 ZIP 在旧版 arm64 Runner 中失败关闭：宽范围的 Playwright 依赖让 pip 安装新版 Python Playwright，却保留旧版 Chromium 二进制；浏览器无法启动，模拟智能体没有虚报完成。修复为不在参赛 `requirements.txt` 覆盖 Runner 预装 Playwright；本机独立环境才自行安装匹配的 Python 包和 Chromium。这个失败是依赖版本适配证据，**不是比赛任务失败**。
- 最终候选运行源码提交为 `d9d99e2c40723ac88d08d832104360e5cf4e9cd0`；ZIP `dist/langqi-forge-qualifier.zip` 的 SHA-256 是 `3d73edea56b787b3503edf183d438f258352b848e069389224de6c9e98768353`，16 个文件，`unzip -t` 通过。此后只追加本证据文档；ZIP 清单仍精确绑定该运行源码提交。主机单元测试 58/58 通过（其中需容器浏览器的 1 项在主机跳过），在 arm64 Runner 容器内浏览器探针相关 3/3 项全部运行并通过。
- **同一最终 ZIP** 在旧版 arm64 Runner + 当前本地模拟器包装的完整协议运行：`../factory26-local-simulation/runs/qualifier-browser-probe-final-20260924/`。自建模型协议夹具提出 5 次模型接口请求，其中一次 `browser_probe` 实际点击 `Try` 按钮，页面显示 `Clicked` 并命中显式断言；智能体报告 `local-contract-passed`、`arcbench_runtime=official-sdk`、`behavioral_probe_tested=true`、6/6 本地检查通过。后续独立 Playwright 协议测试为 1/1，容器退出码 0；`score=null`、Token/费用为 `null`，**不是公开练习或正式赛成绩**。生产轨迹 31/31 行哈希链有效，未发现未脱敏密钥。
- **同一最终 ZIP** 在当前主办方 amd64 基础镜像（上节所列摘要）直启：`../factory26-local-simulation/runs/qualifier-current-base-final-direct-20260924/`。官方 SDK 可安装且正常记录，4 次自建模型协议请求后 `local-contract-passed`，6/6 构建/启动检查通过；此直启夹具没有调用浏览器探针，报告明确为 `behavioral_probe_tested=false`。完整新版 Runner 在本机仍卡于 arm64→amd64 QEMU 的 Chromium 预检，不能由直启结果替代它的 GUI 验证。
- 同一最终 ZIP 又分别完成 BookStack、Keep 公开练习需求的**解包/预备工作区**检查，目录为 `../factory26-local-simulation/runs/qualifier-browser-final-{bookstack,keep}-preflight-20260924/`。需求解析分别得到 34 条/9 批、32 条/8 批；这一步没有调用模型、部署应用或执行 GUI 测试，只证明最终包可进入两题的本地运行准备流程。
- 当前仍未取得真实模型对 BookStack 和 Keep 的生成结果、两题综合 GUI 通过率、真实开销、官方得分或晋级资格；正式队长账号也未登录，项目未上传或正式提交。

## 长会话证据保全与当前候选包（本页最新）

- 长会话超出上下文上限时，精简检查点现在保留浏览器探针的已用/剩余次数、需要重验状态、已验证源码版本，以及最近一次行为断言和页面错误摘要；原始逐步观察仍保存在哈希链轨迹中。对应测试覆盖精简结果的有界摘要和检查点字段，防止压缩后将失败探针误认为通过，或重复消耗探针额度。
- 当前运行源码提交 `6228749c6259991725709c3627b2443d1dddcdf8`；同一参赛 ZIP `dist/langqi-forge-qualifier.zip` 的 SHA-256 为 `d68a703053e1c2562274c2aa93f0b8f58f556582a1f4d95bcd0f6c754752bd4f`，16 个文件，`unzip -t` 通过。主机单元测试运行 59 项，58 项通过、1 项因主机未装 Playwright/Chromium 而跳过；该浏览器集成测试在 arm64 Runner 容器里连同探针测试 3/3 通过。
- 该**精确 ZIP** 在旧版 arm64 Runner 的完整协议模拟目录 `../factory26-local-simulation/runs/qualifier-context-probe-final-20260924/` 再次完成模型协议调用、源码修改、一次带断言的浏览器点击、构建启动及独立 Playwright 1/1；容器退出码 0，SDK 正常，生产轨迹 31/31 行哈希链有效且未发现未脱敏密钥。`score=null` 且 Meter 不可用；这仍只是自建协议夹具，不是公开题性能。
- 该**精确 ZIP** 在当前主办方 amd64 基础镜像的直启目录 `../factory26-local-simulation/runs/qualifier-context-current-base-direct-20260924/` 完成 4 次自建模型请求、官方 SDK 记录和 6/6 构建/启动检查；该直启没有浏览器探针，仍不能替代因本机 QEMU Chromium 预检失败而缺失的完整当前 Runner GUI 试验。BookStack、Keep 的预备工作区也已用此包分别解包成功：`../factory26-local-simulation/runs/qualifier-context-{bookstack,keep}-preflight-20260924/`，仍未运行真实模型或测试。
- 此后只追加本证据文档；最终候选 ZIP 的源码身份继续由其内置清单绑定上述 `6228749c...` 提交。真实模型两题结果、费用与官方成绩仍缺失，账号登录、上传、正式提交均未进行。

## 2026-09-25 模型故障恢复与新候选包

- 新源码提交 `7b00deb0846b6abd8e4c4f2a6fe1496d3299f86f`；新 ZIP `dist/langqi-forge-qualifier.zip` 的 SHA-256 为 `afb4d480d9d178714e6983bbd6fd51d1efdd2ba31512c25b8bd9d5f405753a98`，16 个文件，`unzip -t` 通过。包内来源清单绑定这次源码提交，不包含协议测试、密钥或题目专用业务代码。后续只提交本页记录，不改变已验证 ZIP 的源码内容。
- 修正模型网关的失败恢复：临时 HTTP 408/425/429/5xx 及连接中断最多尝试 3 次；遵守有界 `Retry-After`；认证失败、非临时 4xx 与格式错误的 200 响应不再重复请求。提供商错误正文不进入轨迹。报告分别记录成功模型响应 `model_requests` 和实际 `model_http_attempts`，后者包括重试，**两者都不是平台账单**。本机假 HTTP 服务测试覆盖 429→503→恢复、401 不重试且不记录错误正文、超长等待失败关闭、HTTP 日期与格式错误响应不重试。主机单元测试共 64 项，63 项通过、1 项因主机无 Playwright/Chromium 跳过。
- 该**精确新 ZIP** 在旧版 arm64 Runner + 当前本地模拟器包装中运行自建模型协议夹具，目录 `../factory26-local-simulation/runs/qualifier-retry-browser-20260925/`。容器退出码 0，独立 Playwright 1/1，`score=null`、费用与 Token 账单为 `null`；模型协议请求 5 次、HTTP 尝试 5 次，浏览器探针点击并断言通过，本地 6/6 结构/构建/启动检查通过，官方 SDK 正常写入，生产轨迹 31/31 行哈希链有效且未发现未脱敏密钥。
- 同一 ZIP 在本机缓存的主办方 amd64 基础镜像包装 `arcbench-local-current:20260924` 下**直启**，目录 `../factory26-local-simulation/runs/qualifier-retry-current-base-direct-20260925/`：容器退出码 0，模型协议请求及 HTTP 尝试各 4 次，SDK 正常，本地 6/6 检查通过，生产轨迹 27/27 行哈希链有效且未发现未脱敏密钥。此直启不做浏览器探针，也不等于完整当前 Runner；本机 ARM→amd64 QEMU 仍无法通过当前 Runner 的 Chromium 预检。镜像标签与摘要仅代表已缓存版本，不证明主办方后续没有更新。
- 上述两个运行均使用**自建、固定响应的协议网关**，不是实际编码大模型；1/1 只是协议夹具，不是 BookStack/Keep 的通过率、公开赛排名或获奖概率。尚未取得真实模型的两道公开练习结果、真实成本与官方成绩；ARC-Bench 账号未登录，项目未上传、未正式提交。

## 2026-09-25 正式赛口径核对与异步浏览器探针

- 直接查看 [ARC-Bench 比赛公开列表](https://arc-bench.com/competition)：正式赛 `Agentic Software Factory Hackathon` 标为开放，列出 **2 项任务、200 个测试**；进入详情后，未登录页面只显示先登录并确认队伍的门槛，未展示正式任务包或测试正文。因此 200 是当前公开列表的口径，不是我们运行或验证过的测试数。BookStack/Keep 的 34+32 个公开基准测试属于练习，不能代替正式赛题。已缓存主办方基础镜像的 Docker Hub 摘要仍为 `sha256:40e003ed470dbd4c120b9019876ba77303d38dc8b34be7f6e313fe0563dd14de`，只证明这次检查没有发现该标签漂移。
- [赛事官网](https://create.gosim.org/factory26/)当前写明初赛 9 月 24–30 日、排行榜前 20 进入决赛；自动采集 GUI 通过率、Token 效率和完成时间，权重尚待公布。官网 FAQ 称只需提交智能体，和此前提交页截图的 Demo 字段不一致；当前 ARC-Bench 正式赛详情被登录/队伍确认阻断，故不能断言 Demo 已取消或成为强制项。
- 探针原先在打开首页及每次操作后固定等待 150 毫秒，可能把异步渲染或延迟反馈误判为失败。现对首页可见内容、每步正反文本断言再给至多 2 秒的有界等待，不改变隐藏测试或外部评分。源码提交 `669d2c8a6c73495361328e78e1339e32b6f9ffff`。主机单元测试 65 项中 63 项通过、2 项因缺 Playwright/Chromium 跳过；两项浏览器集成测试连同其余探针测试在旧版 arm64 Runner 的实际 Chromium 环境里 4/4 通过，包含首页与点击反馈各延迟 400 毫秒的情形。
- 本次精确 ZIP `dist/langqi-forge-qualifier.zip` 的 SHA-256 为 `be7fe7e62fc440aef714a7b47df3e28822de2031de4f2eed1ac9515a3779bdf7`，16 个文件，`unzip -t` 通过，清单绑定上述源码提交。该 ZIP 在旧版 arm64 Runner + 当前模拟器包装的自建协议夹具中运行，目录 `../factory26-local-simulation/runs/qualifier-async-browser-20260925/`：容器退出码 0，模型接口 5 次、浏览器探针真实点击及文本断言通过、独立 Playwright 1/1，SDK 正常，本地 6/6 检查通过，生产轨迹 31/31 行哈希链有效且未发现未脱敏密钥。`score=null`，模型费用未知；这仍不是正式赛或真实编码模型的能力测量。
- 新 ZIP 未在本机完成当前 amd64 Runner 的完整 GUI 运行；ARM→amd64 QEMU 浏览器预检的旧障碍仍在。没有 ARC-Bench 正式赛登录、上传、提交、真实模型 BookStack/Keep 练习结果或 200 项正式赛成绩。

## 2026-09-25 跨批次源码交接

- 对公开练习需求树做静态编排检查：BookStack 34 条默认分 9 批，Keep 32 条分 8 批；BookStack 某些批次跨仪表盘/书架、书架/图书、图书/章节等模块边界。先前每批重开模型会话时只提示固定五个入口文件，主流程没有传入先前批次新增的功能模块路径。这是代码层面可直接确认的上下文断裂风险，但尚不能据此估算实际 GUI 分数。
- 提交 `b7b3b9c377c400acce24a4b72a42720a04d8cae6` 将此前成功批次**实际由工具编辑**的源码路径作为有界索引交给下一批：最近修改优先，最多 60 个路径，路径正文合计不超过 4,000 字符；文件名作为不可信数据包裹，模型必须再按需读取内容。`implementation_batch_started.prior_source_paths` 同步记录交接清单，不将文件名视为验收证明。
- 新增两批主流程集成测试，验证第一批写出的新模块进入第二批提示词与哈希链轨迹；另测顺序/上限/标签转义。主机单元测试运行 68 项，66 项通过、2 项因主机缺 Playwright/Chromium 跳过。
- 新精确 ZIP `dist/langqi-forge-qualifier.zip`：SHA-256 `e9cfe63f30cc6ef7c9e60a08d6eb0e970640be12eba07b446e3feaf15724cf0b`，16 个文件，`unzip -t` 通过，包内清单绑定 `b7b3b9c...`。该 ZIP 在旧版 arm64 Runner + 当前本地模拟器包装上执行**单批自建协议夹具**，目录 `../factory26-local-simulation/runs/qualifier-handoff-browser-20260925/`：容器退出码 0，模型协议请求 5 次，浏览器探针通过，独立 Playwright 1/1，官方 SDK 正常，本地检查 6/6，生产轨迹 31/31 行完整且未发现未脱敏密钥。单批协议运行只验证新包无回归；跨批交接由上述两批集成测试验证，二者都不能证明真实大模型解题效果。
- 同一精确 ZIP 在本机缓存的主办方当前 amd64 基础镜像包装 `arcbench-local-current:20260924` 下直启，目录 `../factory26-local-simulation/runs/qualifier-handoff-current-base-direct-20260925/`：进程退出码 0，模型协议请求/HTTP 尝试各 4 次，官方 SDK 正常，本地 6/6 检查通过，生产轨迹 27/27 行有效且未发现未脱敏密钥。这个直启不运行浏览器探针，不能代替本机因 QEMU 浏览器预检失败而缺失的当前 Runner 完整 GUI 试验。
- 真实模型 BookStack/Keep 练习结果、正式赛 200 测试成绩、实际 Token 效率和费用仍缺失；本轮没有账号登录、上传或提交。

## 2026-09-25 审计完成条件收紧（当前候选包）

- 源码提交 `c4d14061c575656d384d58d056df9aaf2f20ca1a` 修正一个完成条件漏洞：过去进入逐需求审计后，模型只需再调用一次成功的 `run_validation`，主循环就直接记录“审计完成”，即使没有模型审计结论。现在必须在最新修改已校验、旧探针无待重验的前提下，收到以 `AUDIT PASS:` 开头的无工具回复；再次校验、空回复和 `AUDIT BLOCKED` 不会结束批次。轨迹增加 `acceptance_audit_self_reported=true`，明确这仍是模型自审，不能冒充逐需求独立 GUI 测试。回归测试覆盖重复校验和明确未通过均失败关闭。
- 当前精确 ZIP 为 `dist/langqi-forge-qualifier.zip`，SHA-256 `a85aea1042d902dae22c80f83be64ab42d9545b6aaad817965b4fc991009ca21`，16 个文件，来源清单绑定上述源码提交，`unzip -t` 通过；后续只追加本证据文档，不改变已验证 ZIP 的源码身份。主机单元测试共 69 项，67 项通过、2 项因本机缺 Playwright/Chromium 跳过；浏览器相关测试在旧版 arm64 Runner 容器里 4/4 通过。
- 该**精确 ZIP** 在旧版 arm64 Runner + 当前本地模拟器包装的完整协议运行目录 `../factory26-local-simulation/runs/qualifier-audit-protocol-20260925/`：自建固定响应模型夹具请求 5 次，浏览器探针点击并断言通过，独立 Playwright 1/1，容器退出码 0，官方 SDK 接入正常，本地检查 6/6，生产轨迹 31/31 行哈希链有效且未发现未脱敏夹具密钥；`score=null`，平台 Token/费用计量不可用。
- 同一 ZIP 在本机缓存的主办方 amd64 基础镜像包装 `arcbench-local-current:20260924` **直启**，目录 `../factory26-local-simulation/runs/qualifier-audit-current-direct-20260925/`：进程退出码 0，自建模型请求/HTTP 尝试各 4 次，官方 SDK 正常，本地检查 6/6，轨迹 27/27 行有效。直启未运行浏览器探针，不能替代受本机 ARM→amd64 QEMU Chromium 预检限制的完整当前 Runner GUI 试验。
- 两次协议运行都只证明参赛包、模型接口、写文件、构建启动、审计结束条件及 SDK/轨迹链路正常；夹具 1/1 **不是**真实编码模型的 BookStack/Keep 成绩、正式赛成绩或获奖依据。账号登录、正式上传与提交仍未执行；实际模型练习凭据与正式队伍访问仍待解决。

## 2026-09-25 SDK 失败事件与当前候选包

- 源码提交 `33f3f3d43db749a1ade4436bf9366e28a04b983f`。检查主办方 `arcbench-runtime==0.1.0` 的真实行为后确认：`mark_implementation_done` 同时修改 Git 跟踪的 `.arc/traceability/node_states.json`，因此“先 Git 提交、再标记需求完成”会留下脏状态，不能这样调整。保留 SDK 的同批提交顺序；实测提交失败后按运行异常路径发送 `mark_implementation_failed`，最终需求状态为 `FAILED`，运行状态为 `failed`。新增的修复是将需求级与运行级失败事件分开尝试：需求级事件写入异常时，仍尝试运行级失败事件，并把 SDK 错误记在本地报告和哈希链轨迹中。回归测试覆盖真实 SDK 提交失败路径及两个事件写入失败的隔离。
- 当前精确 ZIP `dist/langqi-forge-qualifier.zip`：SHA-256 `18671d0842b58e19298c813b68f8c08466fc8eb2694556b75d8b6e1445e38529`，16 个文件，来源清单绑定上述源码提交，`unzip -t` 通过；后续仅追加本证据文档。主机单元测试 74 项，72 项通过、2 项因本机缺 Playwright/Chromium 跳过；旧版 arm64 Runner 容器里的浏览器测试 4/4 通过。
- 同一 ZIP 在旧版 arm64 Runner + 当前本地模拟器包装的完整协议运行目录 `../factory26-local-simulation/runs/qualifier-failure-report-protocol-20260925/`：自建固定响应模型夹具请求 5 次，本地浏览器探针带断言通过，独立 Playwright 1/1，容器退出码 0，官方 SDK 接入正常，本地结构/构建/启动检查 6/6，独立生产轨迹 31/31 行哈希链有效。`score=null`，Meter Token/费用不可用。这里的 1/1 依旧只是协议夹具，不是实际模型的公开练习或正式赛成绩。
- 同一精确 ZIP 在本机缓存的主办方 amd64 基础镜像包装 `arcbench-local-current:20260924` 下**直启**，目录 `../factory26-local-simulation/runs/qualifier-failure-report-current-direct-20260925/`：进程退出码 0，固定响应夹具模型请求/HTTP 尝试各 4 次，官方 SDK 正常，本地检查 6/6，轨迹 27/27 行哈希链有效。这个直启没有浏览器探针，不替代当前完整 Runner 的 GUI 运行；本机 ARM→amd64 QEMU 的 Chromium 预检障碍仍未消除。真实模型 BookStack/Keep 测试、正式队伍登录及提交都仍未完成。

## 2026-09-25 同一 ZIP 的两批端到端协议验证

- 新增**只在本仓库测试目录**的 `tests/protocol_gateway_two_batch.py`、`tests/protocol_requirements_two_batch/` 和 `tests/protocol_playwright_two_batch/`，没有写入参赛 ZIP。固定响应夹具在两批间重开模型上下文：第一批新增 `frontend/src/first-feature.js`；第二批接口收到的 Prompt 必须含该文件的交接路径，随后实际调用 `read_files` 读取它，再新增 `second-feature.js` 并扩展页面。若无交接路径，夹具返回错误而不是假装完成。运行时设 `FACTORY26_BATCH_SIZE=1`，仅用于强制两个测试需求分批。
- **成功路径**直接使用上节 SHA-256 为 `18671d08...` 的精确 ZIP，在旧版 arm64 Runner + 当前本地模拟器包装运行于 `../factory26-local-simulation/runs/qualifier-two-batch-protocol-20260925/`：容器退出码 0，固定响应夹具模型请求 10 次，两批各自完成一次带可见文本断言的浏览器探针，独立 Playwright 2/2，本地检查 6/6。SDK 需求状态 `REQ-1/REQ-2` 均为 `IMPLEMENTED`；生成项目有初始提交及两笔独立批次提交。`implementation_batch_started` 明确记录第二批的 `prior_source_paths` 含第一批新增模块；独立生产轨迹 58/58 行哈希链有效，未发现未脱敏夹具密钥。`score=null`，Meter 计量不可用。
- **故意失败路径**仍用同一 ZIP 和需求，但固定响应夹具在第二批拒绝实施，运行于 `../factory26-local-simulation/runs/qualifier-two-batch-fail-20260925/`：容器退出码 1、独立 GUI 测试未运行，报告 `status=failed`、`implemented_requirements=[REQ-1]`、`failed_requirements=[REQ-2]`。SDK 最终状态分别为 `IMPLEMENTED` / `FAILED`，运行级事件为 `running → failed`；第一批 Git 提交保留，未产生第二批成功提交。生产轨迹 46/46 行哈希链有效。这是有意注入的失败，不是参赛包在正常输入下的能力测试。
- 网关自身另有单元测试：第二批若未收到前批模块路径就返回 HTTP 422；收到后会读该模块并发出实际编辑工具调用；故意失败模式明确回 `AUDIT BLOCKED`。当前主机单元测试共 75 项，73 项通过、2 项因本机缺 Playwright/Chromium 跳过；浏览器环境的 4 项独立测试已在前述旧版 arm64 Runner 容器内运行通过。
- 两条路径共同证明的是**编排、跨批文件交接、状态、提交、行为探针及失败记录**，并不测量真实编码模型对 BookStack、Keep 或正式赛任务的完成度。正式赛账号、上传与提交仍未触碰。

## 2026-09-25 《参赛须知》评分与成本口径复核（覆盖上文旧官网概述）

- 重新逐页检查用户提供的 4 页《参赛须知.pdf》，源文件 SHA-256 `5da6b57e40cec8925b536a4535087286839b4e853df54fda37a6f169206b314e`，PDF 元数据创建于 2026-09-20。第 1–2 页明确：初赛 9 月 24 日 0:00 至 9 月 30 日 23:59；每次正式提交**同时运行两个任务**，正式评测用平台内置模型 API Key，不需上传个人 Key；队长账号发起，暂定 ¥500 比赛券，不限提交次数但同队不可并行，最终采用历史最高有效分。个人 Key 的练习提交不计最终分；本地环境无隐藏测试。
- 第 2–3 页给出明确公式，而非先前官网概述的“权重待公布”：`p=100×合计通过数/合计测试数`，`b=双任务人民币开销之和`，`b₀=1.2` 元/百分点；`p=0` 时 `S=0`，否则 `S=p/(b/(b₀p))^α`（`b≤b₀p`、`α=0.1`）或 `S=p/(b/(b₀p))^β`（`b>b₀p`、`β=0.2`）。榜单先比 `S`，再比 `p`，再比低 `b`，最后才比更早提交时间；前 20 晋级。第 3 页另定单任务最长运行 48 小时。**完成时间不是独立评分维度**；之前 README 对“时间维度和权重待公布”的表述已更正。用户提供 PDF 是一份版本化材料，主办方若在平台更新规则还须再核对。
- 本地模拟器 `local_submit.py::calculate_submission_score` 的参数与分段公式和 PDF 一致，但它计算的是**单题调试分**，不能直接当作正式双题总分。例：`p=80,b=96` 得 80 分；`p=80,b=192` 约 69.64 分；`p=80,b=120` 约 76.51 分，`p=84,b=140` 约 78.66 分。由此可见，在这些具体例子里提高 GUI 通过率比单纯省 Token 更值钱；这不等于任何未实测的模型/Prompt 一定能取得相应提升。Meter 不可用时分数应保持 `null`，不可把未知费用当零。
- 第 3–4 页重申：通用脚手架允许、任务预制代码禁止；必须实际调用大模型；参考图用于理解但功能测试以需求和场景为准；不得读取隐藏测试或绕过网络限制。当前包的通用 scaffold、运行时模型调用、参考图白名单与本地探针是按这些边界设计；**真实模型的泛化效果仍需公开练习和官方评分验证**。

## 2026-09-25 当前镜像生成物 + 旧镜像浏览器的隔离诊断

- 未改动参赛 ZIP：SHA-256 仍为 `18671d0842b58e19298c813b68f8c08466fc8eb2694556b75d8b6e1445e38529`，包内来源清单绑定 `33f3f3d43db749a1ade4436bf9366e28a04b983f`。新脚本只在仓库 `scripts/`，不在 ZIP 白名单内。
- `../factory26-local-simulation/runs/qualifier-current-gen-legacy-gui-20260925/` 由当前模拟器 `--prepare-only` 放入单需求协议夹具和一条公开浏览器断言，随后用本机缓存的当前 amd64 基础镜像直启**精确 ZIP**生成应用，固定响应假模型请求/尝试各 4 次，报告 `local-contract-passed`、6/6 本地检查通过；27/27 条生产轨迹通过完整哈希封印校验。此阶段没有运行当前 Runner 的 GUI 预检。
- 该生成物再放入本机缓存的旧 arm64 浏览器镜像，使用 `--network none`、无模型密钥、非 root 用户及独立公开测试配置。首次诊断因容器缺可写 HOME，Chromium 在断言前报 crashpad 启动错误，报告为 0 通过/1 异常；保留此失败报告。补齐可写 HOME 后，`hybrid-playwright-isolated-config-report.json` 记录公开协议断言 1/1 通过、0 异常。最终缩小挂载范围为仅只读 `scripts/`，以 `minimal-mount` 标签重跑仍为 1/1 通过、0 异常；`bash -n` 通过，重复标签时脚本拒绝覆盖旧报告。复现脚本与限制见[跨架构公开 GUI 诊断](HYBRID_PUBLIC_GUI.md)。
- 这是**当前基础镜像生成 + 旧镜像浏览器**的混合本地诊断，不是当前完整 Runner，也不是两道公开练习或正式隐藏测试；自建夹具不测量真实模型编程能力，模型费用与正式分数仍为未知。本次 shell 环境未配置可直接用于练习的模型 Key，尚未获得 BookStack/Keep 的真实模型成绩。

## 2026-09-25 显式视觉引用补全与新 ZIP 回归

- 源码提交 `ed146fe667897391bd0b758d891f22d2ffdfb0eb` 修复通用需求读取漏项：批次参考图清单原先只扫描描述文字，现在也扫描原子需求 `visual_reference`，并将父级文件夹的显式引用继承到原子需求。文件仍须通过 `reference/` 路径、签名、大小、非软链及视觉网关配置检查；不增加题目预制页面或绕过调用预算。单元测试分别覆盖父级/原子字段清单和实际运行批次工具可见性。全套 77 项测试中 75 项通过、2 项因本机缺匹配的浏览器环境跳过。
- 对公开 BookStack/Keep 需求做只读输入审计：分别为 34/32 条原子需求，默认四条一批时单批规格文本最长 5,081/4,261 字符；最长父级描述 273/224 字符、最长原子描述 351/396 字符、最长场景步骤 278/231 字符，均未触及当前提示词字段截断上限。引用图片路径分别有 19/22 个，其中实际存在 19/20 个；Keep 的 `reference/label_filtered_list.png` 与 `reference/search_keyword.png` 在本地公开材料中缺失，不能假装已读到图片。这只证明公开需求可被读取，不证明应用已实现。
- 从干净源码树打包的精确候选为 `dist/langqi-forge-qualifier.zip`，SHA-256 `63e6c602adbbbfbe9efc4274f03b555f465fbff90ffdfb1af7ebeb72efc7845f`，16 个文件，清单绑定上述源码提交，`unzip -t` 通过。测试、文档、诊断脚本和公开任务材料均不在 ZIP 中。
- 该精确 ZIP 在旧版 arm64 Runner + 当前本地模拟器包装的协议运行目录 `../factory26-local-simulation/runs/qualifier-visual-field-protocol-20260925/` 中，容器退出码 0，独立协议夹具 Playwright 1/1，模型固定响应请求/尝试各 5 次，浏览器探针通过，SDK 需求状态 `IMPLEMENTED`、运行状态完成，生产轨迹 31/31 行哈希链有效。Meter 返回 HTTP 401，费用和分数均为 `null`；1/1 不是公开练习或正式赛通过率。
- 同一 ZIP 在本机缓存的当前 amd64 基础镜像中直启生成，目录 `../factory26-local-simulation/runs/qualifier-visual-field-current-direct-20260925/`：本地 6/6 检查通过，固定响应请求/尝试各 4 次，SDK 运行完成、轨迹 27/27 行有效。再用旧 arm64 浏览器镜像的隔离诊断跑该生成物，公开协议夹具断言 1/1。直启绕开了当前 Runner 在 ARM→amd64 QEMU 的 Chromium 预检，因此**不是当前完整 Runner**；仍没有真实编码模型、BookStack/Keep GUI 通过率或正式成绩。

## 2026-09-25 浏览器自测不再污染独立评测的种子状态

- 源码提交 `f187596de994af6b66f81b3eb50e46690f1a9df9` 修复一个会直接伤害 GUI 通过率的缺陷：此前 `browser_probe` 在原生成项目上启动后端，点击新增/删除会持久化到原 `backend/data/state.json`，随后 SDK 提交与独立评测会继承被自测改过的种子。现在探针先把 `frontend/`、`backend/` 复制到临时目录，再只在副本里安装依赖、启动后端和执行语义操作；不复制 `node_modules`/控制目录，拒绝软链、特殊文件与超过文件数/体积上限的复制。相对路径的应用状态写入随临时副本销毁，不改原项目。此措施不是后端进程网络沙箱。
- 新增普通复制/软链拒绝测试和真实 Chromium 状态变更测试：探针点击后临时后端显示 `count=1`，原项目仍为 `count=0`，原项目也未被探针安装依赖。主机全套 79 项：76 项通过、3 项因缺浏览器跳过；在旧 arm64 浏览器容器内临时安装与参赛包相同的 `arcbench-runtime==0.1.0` 后，79/79 全通过。首次未装 SDK 的完整容器测试有 1 项环境依赖报错，补齐后重跑通过，保留该过程而不把首次报错当成代码回归。
- 从干净源码树生成的**新精确 ZIP**为 `dist/langqi-forge-qualifier.zip`，SHA-256 `6911807b0a1c93c61aefd57372f9670bbcf9d3d0f67e00fbbad58e6d1c45bfc8`，16 个文件，包内清单绑定上述源码提交，`unzip -t` 通过；新夹具、测试与文档不在 ZIP 内。
- 同一 ZIP 在旧版 arm64 Runner + 当前本地模拟器包装的**会写持久状态**协议夹具运行于 `../factory26-local-simulation/runs/qualifier-probe-isolation-protocol-20260925/`：容器退出码 0、固定响应模型请求/尝试各 5 次、SDK 需求 `IMPLEMENTED`、运行完成，探针轨迹明确记录 `workspace_isolated=true`，37/37 行哈希链有效。探针断言 `count=1` 后，独立 Playwright 在自身动作前从 `/api/state` 仍读到种子 `count=0`，之后点击并读到 `count=1`，独立测试 1/1。SDK 的 Git 提交快照中 `backend/data/state.json` 是 `{"count":0}`；本地工作树在独立测试后是 `{"count":1}`，二者顺序与隔离合同一致。Meter 指向本地拒绝连接地址，费用和分数均为 `null`，不能把 1/1 当成真实模型成绩。
- 同一新 ZIP 在缓存的当前 amd64 基础镜像直启普通单批协议夹具，目录 `../factory26-local-simulation/runs/qualifier-probe-isolation-current-direct-20260925/`：固定响应请求/尝试各 4 次，本地 6/6 检查通过，SDK 运行完成，生产轨迹 27/27 行有效；随后旧 arm64 浏览器隔离诊断 1/1。此路径不运行当前完整 Runner 的 Chromium 预检，也不测量真实模型对 BookStack/Keep 的能力。

## 2026-09-25 后端启动健康检查也必须隔离

- 新增一个会在服务**启动时**把 `backend/data/state.json` 从 `{"count":0}` 写成 `{"count":1}` 的通用回归夹具。修改前单独调用 `startup_check` 时，健康检查虽然通过，却实际污染原种子，测试先以 `1 != 0` 失败。源码提交 `0ca2d47fc3077289bb28b5098cd7b107c3656f27` 将浏览器探针和启动健康检查共用 `factory26_harness/isolation.py` 的临时应用副本；同一测试改后通过，原种子仍为 0。构建检查仍在原项目产生必需的 `frontend/dist`，因此不能把此修复称为对任意构建脚本副作用的完全隔离。
- 主机全套 80 项测试为 77 通过、3 项浏览器环境依赖跳过；旧 arm64 浏览器镜像内临时安装参赛包锁定的 `arcbench-runtime==0.1.0` 后，80/80 全通过。新的精确 ZIP `dist/langqi-forge-qualifier.zip` SHA-256 为 `e35dedaf38d12ca813546f331092d24347b865719c4d1237d49d89cab15dbc5b`，17 个文件，哈希清单绑定上述源码提交，`unzip -t` 通过；新增的共享隔离模块进入白名单，测试夹具未进入 ZIP。
- 该 ZIP 在旧版 arm64 Runner + 当前本地模拟器包装运行同一有状态协议夹具，目录 `../factory26-local-simulation/runs/qualifier-startup-isolation-protocol-20260925/`：容器退出码 0、固定响应模型请求/尝试各 5 次、SDK 完成、6/6 本地检查通过，独立 Playwright 先读到 `count=0` 再自行改成 1，测试 1/1；SDK Git 提交快照仍为 `count=0`，37/37 行生产轨迹有效。Meter 指向拒绝连接的本地地址，费用和分数 `null`。
- 同一 ZIP 在缓存的当前 amd64 基础镜像直启普通协议夹具，目录 `../factory26-local-simulation/runs/qualifier-startup-isolation-current-direct-20260925/`：固定响应请求/尝试各 4 次，6/6 本地检查通过，SDK 完成，轨迹 27/27 行有效；借旧 arm64 浏览器镜像进行隔离诊断 1/1。该混合路径不等于当前完整 Runner，不提供真实模型的公开练习或正式赛成绩。

## 2026-09-25 官网账号与公开榜单复核

- 只读核对[主办方官网](https://create.gosim.org/factory26/)当前前端文案：报名网站账号与 ARC-Bench 账号分开，报名密码不会自动成为 ARC-Bench 密码；官网说明 ARC-Bench 登录方式另行通知。官网同时提示因参赛反馈及平台运行情况调整了初赛、决赛开始时间；当前页面的赛程文案为初赛 9/24–9/30、决赛 10/5–10/7。本项是官网当前展示，不代替队长收到的正式通知；如再次变更，以最新主办方通知为准。
- [ARC-Bench 登录页](https://arc-bench.com/login)公开界面需要邮箱、密码；本轮未发现可用的自助密码重置入口。先前注册表单出现“邮箱已被使用”只能说明该邮箱无法再注册，**不证明**队长知道密码或现在已登录。用户此前明确要求协助登录，因此只对 Chrome 中**已填好**的邮箱和密码做了一次正常登录尝试，页面明确返回“密码错误”；没有猜测、读取密码明文、继续重试、重新注册或重置。Chrome 密码管理器页面处于超时锁定状态，未解锁或查看条目。队长应先查主办方发送的 ARC-Bench 开通邮件/通知；仍无凭据时由队长走官方支持渠道请求恢复。
- [官网公开榜单快照](https://create.gosim.org/factory26/arcbench-leaderboard.json)的 `competition.id=arc-bench-lite`，`updatedAt=2026-09-24T16:32:14.704Z`，读取时有 53 条记录；网站明确标注“公开赛榜单，非正式初赛排名”。其 66 项测试和可见成本/分数均不能当作正式两任务、200 项测试的排名，也不能当作本参赛包的成绩。部分快照行显示零模型成本与满分；原因未经核实，不据此优化或推断对手实力。
- [官方 Runtime API](https://arc-bench.com/api-doc)仍要求 Python 根入口 `main.py`、`requirements.txt` 和 `arcbench_agent_runtime` 高层 SDK，不允许手写事件载荷；与当前 ZIP 合同一致。本地主办方模拟器 `HEAD` 与远端 `origin/HEAD` 同为 `4e62690ef0af48601150f248e1f993a300533357`，未发现因模拟器上游更新而必须重打包的变化。
- 本轮 shell 环境没有练习用模型 Key，剪贴板为空；因此没有运行真实编码模型的 BookStack/Keep，不能补出真实 GUI 通过率或成本。当前 ZIP 未改动，SHA-256 仍为 `e35dedaf38d12ca813546f331092d24347b865719c4d1237d49d89cab15dbc5b`。**未能登录**，也没有上传或提交。

## 2026-09-25 前端构建自检也必须隔离

- 审计发现 `frontend_build_check` 之前在原生成项目里执行 `npm run build`。新增通用回归夹具：构建脚本先正常生成 `dist/index.html`，再把相对路径 `backend/data/state.json` 的 `count` 从 0 加到 1。修改前，构建检查返回通过而原种子实际变成 1，测试以 `1 != 0` 失败；这会让之后的独立 GUI 评测从错误种子开始。源码提交 `d181509207163976c89f5a8e68154064d535cc70` 改为在有界临时应用副本中安装依赖和构建，验证构建结果无软链、特殊文件或超限内容后，仅把新鲜 `frontend/dist/` 晋升回原项目；原种子保持 0。另有回归用例确认带软链的构建输出会失败关闭、不晋升；原有无操作构建不能靠陈旧 `dist` 通过、模型密钥不进入构建子进程的测试继续通过。
- 主机完整单测为 **82 项：79 通过、3 项因本机缺匹配浏览器环境跳过**。从干净源码树打包的精确 `dist/langqi-forge-qualifier.zip` SHA-256 为 `258655fde48d37b15c32f996b9e3c9294c756ab6df921285639d0c4c2891c281`，17 个文件，清单绑定上述源码提交，`unzip -t` 通过。旧 ZIP 哈希不再代表当前候选。
- 该精确 ZIP 在旧版 arm64 Runner + 当前本地模拟器包装的有状态固定响应协议夹具运行于 `../factory26-local-simulation/runs/qualifier-build-isolation-protocol-20260925/`：容器退出码 0、模型协议请求/尝试各 5 次、官方 SDK 接入正常、本地 6/6 检查通过、独立 Playwright **1/1**。37/37 条生产轨迹通过完整哈希封印校验且未发现未脱敏夹具密钥；SDK Git 提交里的 `backend/data/state.json` 仍为 `{"count":0}`，独立浏览器测试操作后的工作树为 `{"count":1}`。成本与分数因 Meter 不可用为 `null`；这里的 1/1 只证明协议与种子隔离，不是实际编码模型的公开练习成绩。
- 同一精确 ZIP 在本机缓存的当前 amd64 基础镜像 `arcbench-local-current:20260924` 中绕过 ARM→amd64 QEMU Chromium 预检，按主办方 `run_submission.py` 的依赖安装、环境和生成入口直启，目录为 `../factory26-local-simulation/runs/qualifier-build-isolation-current-direct-20260925/`：固定响应夹具请求/尝试各 4 次，SDK 状态 `IMPLEMENTED`，本地 6/6 检查通过，27/27 条轨迹有效。该生成物再借旧 arm64 浏览器镜像以无网络、无模型密钥方式执行一条公开协议断言，报告 `hybrid-playwright-build-isolation-20260925-report.json` 为 expected=1、unexpected=0、skipped=0。**当前基础镜像直启 + 旧镜像浏览器**不是当前完整 Runner，不能替代正式赛、BookStack/Keep 真模型成绩或隐藏测试。
- 本次修复只隔离本智能体自行执行的相对路径构建副作用，并不构成对构建脚本的进程网络沙箱或对平台以后独立构建的控制。正式账号登录仍失败，未上传或提交；下一项能改变竞争力判断的证据仍是真实模型在两道公开练习上的独立 GUI 通过率与费用。

## 2026-09-25 拒绝会改写应用种子的构建脚本

- 上节的隔离仍有漏判：自检在临时副本中运行构建，即使脚本改写 `backend/data/state.json`，原项目也不会被污染，因而旧检查会返回通过；但缓存的当前 amd64 Runner 的 `run_web_template` 随后会在**原生成项目**执行 `npm install` 和 `npm run build`，同一脚本将重演副作用。先把原有“构建时改写种子”用例改为要求失败，修改前确实因返回通过而红灯。源码提交 `e42d791388b3980031eb472375edba0113143465` 在临时副本里对构建前后的应用源码与种子作哈希清单比对；`frontend/dist/` 之外的新增、删除或改写一律令构建检查失败且不晋升 `dist`。回归同时覆盖后端种子改写、前端源码改写和后端新文件；正常生成 `dist` 仍可通过。
- 主机全套单测 **84 项：81 通过、3 项因本机浏览器环境跳过**，`git diff --check` 通过。从干净源码树打包的精确 `dist/langqi-forge-qualifier.zip` SHA-256 为 `13677294278cee719885ef71f95563381b0abc74422c117667aceb00d34c2edf`，17 个文件，包内来源清单绑定上述源码提交，`unzip -t` 全部通过。上节的 ZIP 已过时。
- 同一精确 ZIP 在旧版 arm64 Runner + 当前本地模拟器包装的有状态固定响应夹具运行于 `../factory26-local-simulation/runs/qualifier-build-mutation-gate-20260925/`：容器退出码 0、SDK 需求状态 `IMPLEMENTED`、本地 6/6 检查通过、独立 Playwright **1/1**、生产轨迹 37/37 行通过封印校验。Git 提交里的 `backend/data/state.json` 仍为 `{"count":0}`；独立浏览器操作后的工作树为 `{"count":1}`，符合夹具预期。Meter 连接被拒，分数与成本为 `null`。
- 同一 ZIP 在缓存的当前 amd64 基础镜像 `arcbench-local-current:20260924` 按主办方 `run_submission.py` 的依赖安装与生成入口直启，目录 `../factory26-local-simulation/runs/qualifier-build-mutation-gate-current-direct-20260925/`：固定响应模型请求/HTTP 尝试各 4 次，SDK 状态 `IMPLEMENTED`、本地 6/6 检查通过，生产轨迹 27/27 行有效。该生成物经旧 arm64 浏览器镜像的无网络混合诊断，`hybrid-playwright-build-mutation-gate-20260925-report.json` 为 expected=1、unexpected=0、skipped=0。**当前镜像生成 + 旧镜像浏览器不是当前完整 Runner**，不能替代真实模型公开练习或正式隐藏测试。
- 这个闸门是对临时副本中 `npm run build` 的可见文件事后比对，不能防止绝对路径、网络副作用或 `npm install` 生命周期脚本，也不保证不同平台环境下构建完全一致；不能称为任意生成代码的完整沙箱。当前仍没有真实编码模型的 BookStack/Keep 独立 GUI 通过率和费用，未登录、未上传、未提交。

## 2026-09-25 官网赛程与平台计分复核

- [GOSIM 规则页](https://create.gosim.org/factory26/rules)当前写明初赛 **9/24–9/30**、决赛 **10/5–10/7**；最初留在浏览器里的首页标签曾显示旧的 9/21 与 10/1，重新载入后也更新为新赛程。初赛前 20 进入决赛。只读打开登录账号的队伍资料，队伍名称确认为「琅岐岛民」；未修改或保存资料。
- [ARC-Bench 竞赛页](https://arc-bench.com/competition)当前把正式赛标为 2 任务、200 测试。其「排行榜计分方式」弹窗给出的合理开销是 `0.4 × N × p / 100`，最低计费 ¥0.10、成本比率钳在 0.01–100，实际开销不高于合理开销时指数 0.1，超出时 0.2；综合榜只给同一份提交完成全部任务的运行计分，并按得分、通过率、较低开销、较早提交时间排序。以当前 `N=200` 推导合理开销为 `0.8p`，与 9/20《参赛须知》的 `1.2p` 不一致；前文的 PDF 公式与示例属历史材料，不应再用来规划正式预算。GOSIM 规则页仍称完成时间是采集指标但权重待公布，故也不能由这个榜单弹窗推出最终所有赛制细节。
- 正式赛详情页在未登录 ARC-Bench 时只显示「确认队伍后进入比赛」和登录入口；GOSIM 官网登录不等于 ARC-Bench 登录。当前 shell 中 `OPENAI_API_KEY`、`DASHSCOPE_API_KEY`、`BAILIAN_API_KEY` 均未配置，系统剪贴板为空；插件目录也未找到可直连百炼或 ARC-Bench 的插件。因此本轮没有真实编码模型的公开练习费用/通过率，亦未在 ARC-Bench 登录、上传或提交。上述官网只读核验没有改变参赛 ZIP：SHA-256 仍为 `13677294278cee719885ef71f95563381b0abc74422c117667aceb00d34c2edf`。

## 2026-09-25 当前 Runner 独立部署函数复验

- 主办方本地模拟器远端 `origin/HEAD` 仍为 `4e62690ef0af48601150f248e1f993a300533357`，与本地相同；Docker Hub `gyataro/arcbench-runner:local-base` 的当前 manifest 配置摘要 `sha256:da61a60c2d488c1077a2cffb3f109eb312edd745ae402adecb15f2d33111f7fc` 与本机缓存镜像 ID 相同，未发现这两个输入源在本轮发生更新。此核验不证明平台后台实际部署的 Runner 与公开本地镜像逐字节相同。
- 在上一轮由**精确 ZIP** `13677294...`、固定响应假模型、当前 amd64 基础镜像生成的工作区 `../factory26-local-simulation/runs/qualifier-build-mutation-gate-current-direct-20260925/`，单独调用该镜像 `/opt/arcbench/run_submission.py::run_web_template`：日志记录前端 `npm run build` 退出码 0、后端 `npm install` 退出码 0、`npm run start` 后 `/api/health` 返回 `{"ready":true}`，函数正常返回。随后用旧 arm64 浏览器镜像在该**重建后的生成物**上作无网络协议诊断，`hybrid-playwright-current-web-template-20260925-report.json` 为 expected=1、unexpected=0、skipped=0。这验证了当前公开 Runner 的部署函数与参赛包生成物在本机仿真下相容，但浏览器仍跨镜像，**不是当前完整 Runner 的正式 GUI 结果**。
- 曾另在新工作区 `../factory26-local-simulation/runs/qualifier-current-web-template-20260925/` 尝试让有状态协议夹具在当前 amd64 镜像里连浏览器探针一起生成。源码修改与模型协议调用开始后，探针的 Chromium 在 ARM→amd64 QEMU 下以 `SIGTRAP` 中止，随后智能体耗尽 20 回合并报告未验证；这是一次**失败的本机运行**，不能记为候选成功，也不能由此推断真实 x86 Runner 或应用逻辑失败。保留失败日志及 66 行轨迹用于排查，不重用为分数。当前完整 Runner 的 x86 独立 GUI 与真实编码模型公开练习仍缺证据。

## 2026-09-25 最终修复轮的浏览器证据不得沿用旧值

- 源码提交 `53b54e4bac4599593a52cb9503a52ef282522f2f` 修正报告口径：若最后的修复轮改动了源码却没有重新执行带断言的浏览器探针，最终 `behavioral_probe_tested` 必须为 `false`；每轮修复的改动文件、探针调用次数和验证状态独立写入 `browser_probe_repairs` 与生产轨迹。先新增会失败的回归测试，再实现该逻辑。主机全套 **86 项：83 通过、3 项因本机浏览器环境跳过**。这只确保报告不沿用旧探针结果，不会自动补跑探针，更不等于应用行为已通过独立 GUI 测试。
- 精确候选包 `dist/langqi-forge-qualifier.zip` 的 SHA-256 为 `2cd73cb568095c754a915a0341020dcbefd3e7dc2aea3e14d379a4b2bdf65363`，17 个文件，内置清单绑定上述源码提交且记载打包时源码工作树干净；`unzip -t` 全部通过。之后仅追加本证据页，不重打包已验证 ZIP。
- 用**该精确 ZIP** 在旧版 arm64 Runner + 当前本地模拟器包装执行有状态固定响应夹具，工作区为 `../factory26-local-simulation/runs/qualifier-repair-probe-audit-20260925/`：容器退出码 0，固定响应模型接口请求/HTTP 尝试各 5 次，官方 SDK 的 `REQ-1` 状态为 `IMPLEMENTED`，本地 6/6 检查和独立 Playwright 1/1，37/37 条生产轨迹封印验证有效。报告 `behavioral_probe_tested=true`、`browser_probe_repairs=[]`；此夹具没有触发最终修复，修复分支由上述单元/集成回归覆盖。SDK Git 提交里的种子为 `count=0`，独立 GUI 操作后的工作区为 `count=1`，符合夹具预期。Meter 不可用，费用和得分为 `null`。
- 同一 ZIP 在缓存的当前 amd64 基础镜像 `arcbench-local-current:20260924` 按主办方 `run_submission.py` 的依赖安装、生成入口及**独立 `run_web_template` 部署函数**直启，工作区为 `../factory26-local-simulation/runs/qualifier-repair-probe-current-direct-20260925/`：固定响应请求/尝试各 4 次，SDK 正常，本地 6/6 检查通过，27/27 条生产轨迹封印验证有效；前端构建、后端依赖安装、应用启动和 HTTP 健康检查均成功。其报告诚实记录 `behavioral_probe_tested=false`，因为这条普通协议夹具没有调用探针。再以旧 arm64 浏览器镜像、无网络和无模型密钥方式对该生成物做混合诊断，Playwright expected=1、unexpected=0、skipped=0。**当前镜像生成部署 + 旧镜像浏览器不是当前完整 Runner**。
- 本轮复核 [ARC-Bench 登录页](https://arc-bench.com/login) 仍只看到邮箱、密码、登录和注册链接，没有自助找回入口。用户提供的 [《参赛须知.pdf》](/Users/zerongliu/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/rongrongege_80ce/temp/RWTemp/2026-09/352a5833bfb15b147b4d7bceaa00417f/参赛须知.pdf) 第 1–2 页说明正式提交由队长账号发起、平台提供模型 API Key，但**不包含找回原账号密码的方法**。GOSIM 官网 FAQ 仍写 ARC-Bench 开放与登录方式另行通知。未猜测密码、未修改凭据、未上传或提交。
- 当前 shell 环境没有可用的真实编码模型 Key，剪贴板为空；本节所有生成均由自建固定响应协议服务驱动，不能据 1/1 协议夹具推断 BookStack/Keep 通过率、正式比赛成绩、成本或获奖概率。真实模型公开练习、队长账号恢复与完整当前 x86 Runner GUI 仍待处理。

## 2026-09-25 失败批次隔离与部分实现保全

- 审计发现旧流程在任一需求批次未验证时非零退出；主办方 Runner 会跳过部署与 Playwright，因此此前完成的其它功能也得不到独立测试。源码提交 `d0fff07720e10aad3e5918e9e103d1f57deb1c9c` 改为每批在系统临时目录的私有应用副本上执行；验证完成才将 `frontend/` 与 `backend/` 晋升到生成项目。失败批次丢弃未验证代码并标记需求 `FAILED`，阻断依赖它的节点，但继续尝试不依赖它的后续需求。最终若无任何有效实现仍非零退出；若有部分实现且最终构建启动通过，报告 `local-contract-partial`，SDK 保留失败节点状态并允许 Runner 做独立 GUI 测试。源码副本在模型执行时不放在正式输出目录旁，避免相对路径构建脚本直接污染原工作区。全套主机单测 **89 项：86 通过、3 项本机浏览器环境跳过**；新增测试覆盖失败代码不晋升、独立需求继续、依赖阻断、空实现失败关闭，以及终末失败状态进入 SDK Git 提交。
- 从该干净源码提交构建的精确候选 ZIP 为 `dist/langqi-forge-qualifier.zip`，SHA-256 `0c3dbac700b94e19dfddb335454b08e481b547e6b8fdcbc8055140a1dc1907f6`，17 个文件，清单绑定上述源码提交。后续增加的双批测试环境文件与本证据记录不进入 ZIP；需使用本节哈希区分旧包。
- 该精确 ZIP 在旧版 arm64 Runner + 当前本地模拟器包装下，用固定响应**双批协议夹具**完整生成、部署并执行独立 Playwright：`../factory26-local-simulation/runs/qualifier-transaction-full-20260925/` 为 2/2，本地 6/6 检查通过，两批 SDK 状态均为 `IMPLEMENTED`，58/58 行生产轨迹封印有效。夹具只能证明多批次代码交接与运行合同，不能证明真实模型能力。
- 同一 ZIP 的故意失败夹具 `../factory26-local-simulation/runs/qualifier-transaction-partial-20260925/` 让第二批模型一直不产生实现。智能体报告 `local-contract-partial`、已实现 `REQ-1`、失败 `REQ-2`，SDK Git 快照中两节点分别为 `IMPLEMENTED` 与 `FAILED`；Runner **仍部署并执行**独立 Playwright，夹具结果 1/2，77/77 行轨迹封印有效。`local-result.json` 的 `container_exit_code=1` 是因为 Playwright 有一项未通过，**不是智能体在第二批失败时退出而跳过测试**；`evaluation_status=completed`。该 1/2 是故意安排的协议夹具，不是 BookStack/Keep 或正式赛 50% 成绩。
- 同一 ZIP 在缓存的当前公开 amd64 基础镜像 `arcbench-local-current:20260924` 中按主办方 `run_submission.py` 的依赖安装、生成入口和独立部署函数直启，工作区 `../factory26-local-simulation/runs/qualifier-transaction-current-direct-20260925/`：固定响应模型请求 4 次、本地 6/6 检查、前端构建/后端启动/健康检查均成功，27/27 行轨迹有效。生成物再借旧 arm64 浏览器镜像无网络、无模型密钥做混合诊断 1/1；这仍**不是当前完整 Runner 的 x86 GUI 试验**。
- 以上三条路径的 Meter 均不可用，费用和正式分数为 `null`。当前仍没有真实编码模型对 BookStack/Keep 的独立 GUI 通过率与成本，也没有登录 ARC-Bench、上传或正式提交。部分实现保全只避免一批失败导致其它有效代码无法接受测试，不保证任何正式任务获得部分分数。
