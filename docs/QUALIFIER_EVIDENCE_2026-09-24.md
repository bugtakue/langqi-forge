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

## 2026-09-25 失败批次拆分挽救与空转成本收紧

- 源码提交 `0634f77dce0c886a53a56ddc6427f1dd1fb48208` 给四条需求的默认批次加入一层有界拆分：整批正常结束但未完成时，丢弃其临时编辑，按拓扑顺序将需求分成前后两半，各最多再尝试一次。每半批在独立临时副本中重新生成、校验，成功才晋升并由官方 SDK 提交；失败需求及依赖项保持 `FAILED`。模型请求抛出运行时错误或请求预算已耗尽时不拆分。`--salvage-splits 0` 可关闭，以便后续真实模型练习比较 GUI 收益与新增费用。新增单元测试覆盖成功半批保留、失败半批改动丢弃、依赖阻断、独立项继续、两次额外尝试上限、关闭开关及网关错误不重试。
- 首个精确 ZIP（SHA-256 `0fa8ee8875afe5b759c36e456be505fed840e5e1624fb650f4cdc3f2288920f9`）在旧版 arm64 Runner + 当前本地模拟器包装中，以**自建固定响应假模型**故意让四条需求整批失败、前两条拆批成功、后两条失败。目录 `../factory26-local-simulation/runs/qualifier-split-protocol-20260925/`：智能体 `local-contract-partial`，Runner 仍完成部署和独立 GUI 评测；夹具测试按预期 1 过、1 败。SDK 需求状态 `REQ-1/2=IMPLEMENTED`、`REQ-3/4=FAILED`。由于假模型对失败批次反复回复 `AUDIT BLOCKED`，这一版耗用 **45 次**模型协议请求；这是可见的成本缺陷，不能把固定响应请求数当成真实账单。
- 源码提交 `cb80d5b3db8e646b5db38cf14f23c0005e39cfeb` 收紧 `CodingAgent`：模型以 `AUDIT BLOCKED:` 明确报告未完成时立即结束本次尝试；连续三次无工具、无可接受进展也结束，避免追问到默认 20 回合。工具调用、完成审计、源代码验证门槛不放松。全套本机单元测试 **94 项：91 通过、3 项因本机缺匹配浏览器环境跳过**。
- 当前精确候选 ZIP 为 `dist/langqi-forge-qualifier.zip`，SHA-256 `e61bf05df5996d82e24b298e5599272b86102b015c9d0307b5f9ca515bfe44f1`，17 个白名单文件；`unzip -t` 通过，清单绑定上述 `cb80d5b...` 源码提交。拆批固定响应服务、需求和独立测试只在 `tests/`，**不在 ZIP**。
- 该当前 ZIP 在同一个旧版 arm64 Runner 协议路径运行于 `../factory26-local-simulation/runs/qualifier-split-stall-gated-20260925/`：智能体 `local-contract-partial`、`salvage_attempts=2`、本地结构/策略/语法/构建/启动检查 6/6；SDK 当前与 Git 快照中均为 `REQ-1/2=IMPLEMENTED`、`REQ-3/4=FAILED`；已晋升半批的本地浏览器行为探针通过。Runner 部署后独立 Playwright 按夹具预期 1/2，`evaluation_status=completed`；容器退出码 1 是第二条**故意要求未实现功能**的 GUI 断言失败，不是智能体中途退出。模型协议请求/HTTP 尝试从上一版同夹具的 45/45 降为 **7/7**；44/44 行独立生产轨迹哈希封印有效，测试密钥不在轨迹明文中。Meter 拒绝连接，`score=null`、费用未知。此 1/2 只衡量编排与失败保全，**绝不是正式赛 50% 或真实编码模型成绩**。
- 本次没有真实模型 BookStack/Keep 练习、当前 amd64 Runner 在真实 x86 环境中的完整 GUI 验证、正式队伍登录、上传或提交。默认启用拆批的实际比赛净收益仍须同时比较独立 GUI 通过率与人民币模型开销；固定响应夹具只能说明规则安全性和协议链路，不可作为优于其他选手的证据。

## 2026-09-25 全局架构目录与双批精确包回归

- 静态分析公开练习的需求依赖顺序：BookStack 34 个原子需求分成默认 9 批，Keep 32 个分成 8 批；后期有批次跨越图书/页面或搜索/设置等模块。旧编排每批只给当前四条的详细规格与此前编辑的文件路径，首批看不到未来模块，存在把早期数据结构与导航写死的风险；这是对提示词可见范围的确认，不是实际失败率测量。
- 源码提交 `2a1a83ef972507cf2f0b32fa0a082ab80c51d9f5` 增加从**运行时需求树**编译的全局架构目录：应用名、原子需求 ID、短名称与依赖；不含需求正文、公开测试或题目预制代码，最多 8,000 字符。每批提示词把它放在独立不可信标签中，明确只实施当前 `<untrusted_requirements>` 的方括号 ID。公开 BookStack/Keep 的 34/32 个原子项均完整列入，目录分别为 **2,825/2,422 字符**；大规模合成树的单元测试验证长度上限及截断计数。报告和生产轨迹分别留下目录覆盖数与长度，不将目录当作完成证明。
- 本机全套 **95 项单元测试：92 通过、3 项因本机缺匹配浏览器环境跳过**。精确参赛包 `dist/langqi-forge-qualifier.zip`：SHA-256 `1b7063da372b13a8df5b2a0df515e800890c6514fefdd87cdeffc6d501fba27e`，17 个白名单文件，清单绑定上述源码提交且记录干净树，`unzip -t` 通过；协议服务、公开练习材料及测试不在 ZIP。
- 该**精确 ZIP** 在旧版 arm64 Runner + 当前本地模拟器包装中运行自建固定响应两批夹具，工作区 `../factory26-local-simulation/runs/qualifier-whole-task-outline-protocol-20260925/`。夹具要求首批提示包含未来 `REQ-2` 的目录条目，但不得把 `[REQ-2]` 当作首批活动规格；第二批还须拿到前批新增的源码路径并实际读文件，否则服务返回 HTTP 422。生产轨迹显示首批目录有 `REQ-2`、活动项只有 `REQ-1`；第二批活动项才是 `REQ-2`。模型协议请求/HTTP 尝试各 10 次，SDK 两节点 `IMPLEMENTED`，本地 6/6 检查和行为探针通过，Runner 完成部署与独立 Playwright **2/2**；59/59 行轨迹哈希封印有效，测试密钥不在轨迹明文中。Meter 不可用，`score=null`、模型费用未知。
- 上述 2/2 只说明新目录没有破坏跨批提示、工具编辑、构建、SDK 提交和独立 GUI **协议夹具**。它不是当前完整 amd64 Runner 的真实 x86 运行，也不是实际编码模型的 BookStack/Keep 通过率、正式赛成绩或优于 Claude Code 的证据。本机仍无可用真实模型 API Key；正式账号登录、上传与提交继续由队长后续决定。

## 2026-09-25 截断模型输出的安全恢复

- 审计发现模型请求虽限制每次最大输出 8,192 token，但原客户端没有把 `choices[0].finish_reason` 交给编码循环。如果提供方返回 `length` 且同一响应含不完整工具调用，旧循环可能直接尝试执行半截写入；若没有工具调用，也可能把截断文字当作审计结论。先新增两项失败回归，分别证明旧实现会执行不安全写入、直到第三次才停止空转。
- 源码提交 `8f4c00a927b425893f6021305c2fdc5cfd4b6a1a` 将 `finish_reason` 纳入模型响应与生产轨迹：遇到 `length` 时整条响应的工具调用一律不执行，聊天上下文只保留中性占位而不留下未配对的 tool call，并要求模型改为小块完整编辑；连续两次截断即结束本批，交给既有拆批/失败保全路径。它不改变模型供应商的输出上限，也不保证所有提供方都正确标注截断。新增 HTTP 协议解析测试；全套主机单元测试 **98 项：95 通过、3 项因本机浏览器环境跳过**。
- 从上述干净源码提交打包的精确候选为 `dist/langqi-forge-qualifier.zip`，SHA-256 `e133018789b08f71637285252740d03a33689c2d16fda08fccffe56caa73c7e5`，17 个白名单文件，`unzip -t` 通过。之后的协议夹具改动位于 `tests/` 且不进入 ZIP；当前 ZIP 仍绑定源码提交 `8f4c00a...`。
- 该**精确 ZIP** 在旧版 arm64 Runner + 当前本地模拟器包装、固定响应两批服务下做两次隔离本地运行。基线目录 `../factory26-local-simulation/runs/qualifier-truncation-safe-protocol-20260925/`：模型协议请求 10 次，SDK 两项 `IMPLEMENTED`，本地 6/6 检查、Runner 独立 Playwright **2/2**，生产轨迹 59/59 行封印有效。截断注入目录 `../factory26-local-simulation/runs/qualifier-length-recovery-protocol-20260925/`：假服务首批先返回 `finish_reason=length` 和一个伪 `write_file`，下一次请求必须包含恢复提示且不能携带未配对的工具调用，否则返回 HTTP 422；最终模型协议请求 11 次、SDK 两项 `IMPLEMENTED`、本地 6/6 检查、Runner 独立 Playwright **2/2**、轨迹 62/62 行封印有效，生成项目里**不存在** `frontend/src/TRUNCATED_UNSAFE.js`。截断注入夹具提交为 `d9d21cd`，没有被打入参赛包。
- 两次运行均使用自建固定响应假模型、公开协议自测题、旧版 arm64 Runner；不是百炼真实编码模型、BookStack/Keep 公开练习、当前完整 amd64/x86 Runner 或正式赛。Meter 不可用，两次 `score=null`、费用未知。正式 ARC-Bench 账号未登录，本轮没有上传或提交；要衡量实际竞争力仍需真实模型及独立 GUI 练习。

## 2026-09-25 已验证批次的有界交接

- 核对公开 BookStack/Keep 需求树及现有工具后，参考图像的本地纯像素摘要无法表达文字、结构和交互；缓存的旧版 Runner 没有 OCR、Pillow 或 ImageMagick。暂不加入未经真实收益验证的弱视觉降级或额外依赖，继续保留显式配置 `VISUAL_*` 时的视觉模型检查。当前更直接的跨批缺口是：后来批次虽然知道先前改过哪些文件，却没有先前选择的数据、接口和导航约定；复杂任务重开模型上下文时容易重复设计。此项是架构风险推断，不是已测得的 BookStack/Keep 失败率。
- 源码提交 `4f62b58f25ae3982b7bb13e6368584f4fb1fe263` 要求模型在最后审计摘要里简要说明状态键、API 路由和导航合同；只有**成功且晋升**的批次摘要才保留，至多四条、合计 2,400 字符。下一批在单独的“不可信先前交接”标签中看到摘要，同时被要求先按实际源码核对；摘要不能变成新的需求指令或通过证明。失败批次与丢弃的临时编辑不会交接。新增测试覆盖跨批传递、失败拆批隔离、长度上限及标签注入转义；全套主机 **99 项测试：96 通过，3 项因本机浏览器环境跳过**。
- 从上述干净源码提交打包的精确候选 `dist/langqi-forge-qualifier.zip`，SHA-256 `64b451fa6f71275795aafedea617aa88becfb7127e704db02deded915d3b7035`，17 个白名单文件，来源清单绑定 `4f62b58...`，`unzip -t` 全部通过。该 ZIP 在旧版 arm64 Runner + 当前本地模拟器包装的固定响应双批夹具运行于 `../factory26-local-simulation/runs/qualifier-bounded-handoff-protocol-20260925/`：第二批提示缺少第一批摘要时假服务会返回 HTTP 422；实际轨迹中的交接数从 0→1，第二批提示包含第一批摘要和已改源码路径。容器退出码 0、SDK 两项 `IMPLEMENTED`、模型协议请求 10 次、本地 6/6 检查、独立 Playwright **2/2**，59/59 行生产轨迹封印有效。
- 本轮依然没有真实百炼模型 Key（本机剪贴板为空），故上述固定响应协议夹具不能证明公开 BookStack/Keep 的通过率、费用或相对竞品能力；Meter 不可用，`score=null`。没有登录 ARC-Bench，也没有上传或正式提交。

## 2026-09-25 当前 amd64 Runner 的隔离启动复验

- 用同一精确 ZIP `64b451fa...` 在 Apple Silicon Mac 上调用缓存的当前公开 amd64 Runner `arcbench-local-current:20260924`，工作区 `../factory26-local-simulation/runs/qualifier-bounded-handoff-current-runner-20260925/`。即使不指定测试目录，Runner 仍在启动前的 Chromium 预检处因 ARM→amd64 QEMU `SIGTRAP` 退出：`container_exit_code=1`、`agent_duration_seconds=null`，智能体未启动，不能据此判定参赛包失败，也不能声称完成当前完整 Runner 的 GUI 验证。
- 为隔离这项本机架构故障，在相同当前 amd64 镜像内从精确 ZIP 组装全新工作区 `../factory26-local-simulation/runs/qualifier-bounded-handoff-current-direct-20260925/`，按公开 Runner 的依赖安装与生成入口直接运行，再单独调用其 `run_submission.py::run_web_template` 部署函数。固定响应假模型请求 4 次，官方 SDK 接入为 `official-sdk`，报告 `local-contract-passed`、本地 6/6 检查通过，28/28 行生产轨迹封印有效；前端构建、后端安装、应用启动后 `/api/health` 返回 `{"ready":true}`。这验证当前镜像的生成与部署接口相容，**不是完整 Runner、真实模型或独立 GUI 成绩**。
- 练习 Key 仍未提供；未登录、未上传、未正式提交。当前 amd64 镜像的真实 x86 主机 GUI 路径、BookStack/Keep 真模型通过率和计费仍是未验证项。

## 2026-09-25 多文件源码审计与上下文预算

- 源码提交 `2a9baf016d4b275ba537c9210fd7c8a7aeca26d0` 修复最终验收的两个有确定复现的缺口：旧快照按文件顺序取前 12 KB，一个长文件可遮住全部后续文件；验收提示与快照在长任务中也可把配置的 8,000 字符模型上下文顶到 18,590 字符。现在对最多 24 个已改文件公平分配源码字节预算，截断文件提供首尾摘录及继续 `read_file` 的提示；超过 24 个时明确列出未纳入快照的文件。上下文超限时保留确定性状态检查点，缩小验收提示及源码快照，并在轨迹中记录压缩原因与清单。这仍是模型自审，不能代替独立 GUI 评测；首尾摘录也不能证明中间代码正确，必须按需要继续读文件。
- 新增回归覆盖三层改动文件同时可见、极小快照预算、超出文件数上限和验收上下文限制。本机全套 **103 项测试：100 通过、3 项因本机浏览器环境跳过**；`git diff --check` 与 `unzip -t` 通过。由干净源码树生成的精确候选 ZIP `dist/langqi-forge-qualifier.zip`：SHA-256 `58c054f3f509f19a1c4011d8250dbd64b820277214f2ee1f47e127f114ec3988`，17 个白名单文件，包内清单绑定上述源码提交；测试夹具与证据文档不在 ZIP。
- 该精确 ZIP 在旧版 arm64 Runner + 当前本地模拟器包装的固定响应两批协议回归中，工作区为 `../factory26-local-simulation/runs/qualifier-audit-snapshot-protocol-20260925/`：容器退出码 0，SDK 两项 `IMPLEMENTED`，本地协议生成/部署完成，独立 Playwright **2/2**；生产轨迹 **59/59** 行哈希封印有效、未发现未脱敏测试密钥。该夹具两批均发生验收请求，但没有触发长上下文压缩；压缩路径由单元测试覆盖。Meter 不可用，`score=null`、Token 与费用未知。
- 此 2/2 仅证明精确包没有破坏假模型协议、跨批交接与独立浏览器夹具；不是百炼真实模型的 BookStack/Keep 成绩、当前完整 amd64 Runner 成绩或正式赛分数。本轮没有账号登录、上传或提交；真实模型练习仍需可用 Key，正式提交仍留待队长明确指示。

## 2026-09-25 修订号绑定的最终验收

- 源码提交 `2ffcedb56822bfb9ab1df8b3721608b826df232e` 修正最终审计的时序漏洞：此前模型在同一响应中先 `run_validation` 再改文件，会收到针对未校验源码的验收提示；或者首轮审计后补代码，完成前不会再收到最新版源码审计。两项回归先在旧实现失败，现以 `change_revision` 绑定审计：后续任何实际写入都会撤销旧审计提示并记 `agent_acceptance_audit_invalidated`；只有当前修订号再次通过校验，才发送新的源码快照并允许该版本的 `AUDIT PASS`。这使补丁后的验收多花模型回合，但避免用旧审计结论冒充新代码已审，净得分影响仍待真实模型/计费验证。
- 当前精确 ZIP `dist/langqi-forge-qualifier.zip` SHA-256 `794179f68fdf3fcdd2e3db3e17f9e7e2be9288775b2023f204a2ef90abada69e`，17 个白名单文件，包内清单绑定上述干净源码提交，`unzip -t` 通过；协议夹具与本证据文档不在 ZIP。全套本机 **105 项测试：102 通过、3 项因浏览器环境跳过**。
- 旧版 arm64 Runner + 当前本地模拟器包装的精确 ZIP 协议运行目录为 `../factory26-local-simulation/runs/qualifier-audit-revision-protocol-20260925/`。固定响应假模型在第一批首次审计后额外写入 `frontend/src/audit-repair.js`，并要求再次验证和再次浏览器探针；假服务只有在**最新审计源码快照包含该文件**时才允许 `AUDIT PASS`，否则返回 HTTP 422。实际首批审计修订号 2→失效→3，第二批另有修订号 2 的审计；轨迹 3 次审计请求、1 次旧审计失效、**73/73** 行哈希封印有效，未发现未脱敏夹具密钥。SDK 两项 `IMPLEMENTED`，容器退出码 0，独立 Playwright **2/2**；固定响应协议请求 13 次。Meter 拒绝连接，`score=null`、真实费用未知。
- 以上验证的是时序、协议、构建、部署、跨批与审计留痕，**不是**真实百炼模型完成 BookStack/Keep 的能力、当前完整 amd64 Runner 的 GUI 成绩、正式赛分数或对其他参赛者的优势。ARC-Bench 未登录、未上传、未提交；真实练习仍缺可用模型 Key。

## 2026-09-25 官网边界复核与工作区发现安全

- 只读查看[主办方规则页](https://create.gosim.org/factory26/rules)与 [ARC-Bench 竞赛列表](https://arc-bench.com/competition)：初赛页面仍列 GitHub + Spreadsheets 复刻、9/24–9/30、Top 20 晋级；ARC-Bench 当前公开列表显示正式赛 2 tasks / 200 tests。[正式赛详情](https://arc-bench.com/competitions/hackathon)在未登录状态要求队长确认队伍，不能据此猜测隐藏任务实现或自行提交。[Runtime API 文档](https://arc-bench.com/api-doc)继续要求 Python 根入口 `main.py`、`requirements.txt` 和内置 `arcbench_agent_runtime` 高层 SDK，不允许手写事件载荷。官网通用规则页仍写“三项指标权重待确认”，与队长收到的细化《参赛须知》和平台计分页粒度不同；本轮未据此改写已记录的细化计分口径。官网可读状态是当前观察，后续规则仍可能调整。
- 检查 Harness 工具发现：单文件读取会拒绝越界/敏感路径，但 `search_text` 原先只校验搜索根目录，递归结果若是指向工作区外或 `.env` 的符号链接，仍会读出目标正文；`list_files` 也会列出这些链接。新增先失败回归确实从外部链接读出测试哨兵。源码提交 `58a47a7dbf95df90e054b4476aaa1f654c3104d0` 使列表与搜索逐项验证发现路径并跳过链接；普通安全文件仍可搜索。这是工作区工具的静态访问闸门，不等于对恶意脚本运行时的完整沙箱或 TOCTOU 证明。
- 全套本机 **106 项测试：103 通过、3 项因浏览器环境跳过**，`git diff --check` 通过。干净源码树生成的当前精确候选 `dist/langqi-forge-qualifier.zip`：SHA-256 `25507050a33fc56fdc2c2a955b75d3e4f4fae9249eb899f7414d940c85420f71`，17 个白名单文件，包内清单绑定上述源码提交，`unzip -t` 通过。
- 该精确 ZIP 在旧版 arm64 Runner + 当前本地模拟器包装、固定响应双批假模型下运行于 `../factory26-local-simulation/runs/qualifier-safe-discovery-protocol-20260925/`：容器退出码 0、SDK 两项 `IMPLEMENTED`、独立 Playwright **2/2**、固定响应模型请求 13 次、生产轨迹 **73/73** 行哈希封印有效且未发现未脱敏测试密钥。该正常链路夹具不尝试读符号链接；越界拒绝由新增单元回归直接验证。Meter 不可用，`score=null`、费用未知。尚无真实百炼模型练习、当前完整 amd64 Runner GUI 成绩、ARC-Bench 登录或正式提交。

## 2026-09-25 超长需求的无声截断改为显式分页读取

- 审计发现需求编译和模型提示的多处字段上限：原子描述先裁到 20,000 字符，提示里再裁到 6,000；场景步骤和父级描述也有预览上限。过去模型没有工具取得被省略的原文，可能在不了解必需行为的情况下写代码。源码提交 `50a82adf6163bb8a8ff6219ce51b00189633774e` 对当前批次的缩略节点显式标记，并只为这些节点开放 `read_requirement_spec(requirement_id,start_char)`；分页返回原始需求、完整父级上下文、游标、总长度及 SHA-256，必须按顺序读到 `complete=true` 后才允许源码编辑。普通短需求不增加模型调用。单元测试覆盖父级尾部、原子描述尾部、场景尾部、多短场景、JSON 转义扩大结果和模拟模型工具循环；这项闸门只能证明内容可取得且工具确实读过，不保证模型最终理解或实现正确。
- 本机完整单测 **112 项：109 通过、3 项因浏览器环境跳过**，`git diff --check` 与 `unzip -t` 通过。公开 BookStack/Keep 的 34/32 个原子节点均未被判为缩略，因此现有公开任务提示路径保持不变。新精确包 `dist/langqi-forge-qualifier.zip` 有 17 个白名单文件，SHA-256 `4181a97acc927f087b8a314603f785255e9f69dd7006b07eb949f0b85331055c`；包内清单绑定上述干净源码提交。后续协议夹具提交 `d71af11` 仅在仓库 `tests/`，不进入该 ZIP，亦不改变其哈希。
- 对**该精确 ZIP**，先在旧版 arm64 Runner + 当前模拟器包装做正常双批固定响应回归：`../factory26-local-simulation/runs/qualifier-spec-paging-protocol-20260925/` 的独立 Playwright **2/2**、轨迹 **73/73** 行完整封印。再用含 10,608 字符完整需求文档的合成双批夹具 `../factory26-local-simulation/runs/qualifier-long-spec-protocol-20260925/`：假模型若未暴露分页工具、跳过原文或提前编辑即返回 HTTP 422；实际先连续调用分页工具 **3 次**，再读取和修改源码，SDK 两项 `IMPLEMENTED`、容器退出码 0、本地报告 `local-contract-passed`、独立 Playwright **2/2**。生产轨迹 **71/71** 行哈希链有效，未发现未脱敏测试密钥；模型协议请求 13 次。Meter 不可用，`score=null`，Token 和模型费用未知。
- 上述都是自建固定响应假模型、合成题和旧版 arm64 Runner 的**协议证据**，不是百炼真实模型在 BookStack/Keep 的 GUI 通过率，也不是当前完整 amd64/x86 Runner 或正式赛分数。新分页路径对极大需求还可能触及模型回合上限，应在真实练习里同时核对成功率与成本。本轮没有登录 ARC-Bench、上传参赛包或提交项目；用户明确保留正式提交决定权。

## 2026-09-25 对话压缩后的需求原文可回读

- 继续审计发现，模型历史超过字符预算时，Harness 会用状态检查点替代早先的聊天记录；初次分页读过的原需求正文也可能因此不再处于模型上下文，而旧工具只接受下一个未读游标，无法回看。源码提交 `6e61fb61394a5175054e0e4b087d976844edfa70` 保留“首次必须顺序读到末页才能编辑”的闸门，同时允许首次读完后按 `start_char` 回看任意原文页；上下文压缩检查点列出原需求 ID、长度、哈希、未读游标，最终审计提示则提醒模型不能凭缩略预览审计被省略的行为。单元回归先确认旧版回读失败，再验证新工具回读成功、首次未读完时仍拒绝倒退，以及模拟模型在上下文压缩后回读再编辑。此修复提供检索能力，**不保证**模型自动理解超长文档，也不保证超过轮次预算的大文档能完成。
- 当前精确候选包 `dist/langqi-forge-qualifier.zip` 从上述干净源码提交构建，17 个白名单文件，SHA-256 `89f8d4aa93fcaaecfd27e36c2f4d1c854dc6caa4ab0f9d44b966b37a5a4d7e77`，包内清单记录源码修订和干净树；`unzip -t` 通过。完整主机单测 **113 项：110 通过、3 项因浏览器环境跳过**，`git diff --check` 通过。测试协议修订 `6cd079f` 不进入 ZIP，因此不改变参赛包来源或哈希。
- 对该**同一 ZIP**，旧版 arm64 Runner + 当前本地模拟器包装先以普通合成长需求夹具运行：`../factory26-local-simulation/runs/qualifier-spec-review-protocol-fixed-20260925/` 的独立 Playwright **2/2**。再要求假模型读完三页后重读第 0 页，否则拒绝进入应用编辑：`../factory26-local-simulation/runs/qualifier-spec-review-required-protocol-20260925/` 实际工具游标为 **0→4000→8000→0**，最后一次结果标记 `review=true`；SDK 两项 `IMPLEMENTED`、容器退出码 0、独立 Playwright **2/2**、生产轨迹 **76/76** 行哈希封印有效且未发现未脱敏夹具密钥。固定响应模型协议请求 14 次，Meter 拒绝连接，`score=null`、Token 和费用未知。首次协议尝试 `qualifier-spec-review-protocol-20260925/` 在假服务已读完后仍错误拒绝后续 `read_files`，因此 0/0 且无浏览器报告；修复假服务状态判断后重新运行，保留失败目录，不冒充第一次成功。
- 这些是模拟模型的工具/压缩/部署链路验证；目前仍未取得百炼真实编码模型在公开 BookStack/Keep 的独立 GUI 通过率或费用，也未在真实 x86 上完成当前 amd64 Runner 的全流程。ARC-Bench 未登录、未上传、未提交；正式账号与提交继续留待队长后续指示。

## 2026-09-25 当前官网与精确参赛包对照

- 只读复核[主办方赛制与规则](https://create.gosim.org/factory26/rules)：当前仍列初赛 9/24–9/30、GitHub + Spreadsheets 功能复刻、组织方模型 Token 经统一网关计量；官网将 GUI 测试通过率、Token 效率、完成时间列为自动采集指标，同时写明权重待确认。该网页不提供未登录状态下的隐藏任务或正式计分细则，不据此推断队伍成绩。[ARC-Bench 竞赛列表](https://arc-bench.com/competition)当前公开显示正式赛 2 tasks / 200 tests；[正式赛详情](https://arc-bench.com/competitions/hackathon)在未登录状态要求先登录并由队长确认队伍，本轮没有进入该流程。
- [Runtime API 文档](https://arc-bench.com/api-doc)仍要求 Python 包根目录 `main.py`、`requirements.txt`，运行态通过 `arcbench_agent_runtime` 高层 SDK 更新需求状态、Git 和可追溯数据，不允许自行构造事件。对上节精确 ZIP 在本地旧 Runner 中解出的 `submission/` 再次运行 `verify_source_manifest`：17 个文件集合、逐文件大小/哈希、`main.py`、`requirements.txt` 和源码修订 `6e61fb6...` 均一致；运行目录存在由 SDK/Runner 写入的事件流和追溯目录，生产轨迹已在上节通过 76/76 行封印检查。这证明本地打包及接口链路，不证明真实模型能完成 200 条正式测试。
- ARC-Bench 公开榜单的“查看计分方式”弹窗展示通过率与人民币开销共同影响分数，缺少人民币开销数据的运行不参与该榜；这是当前**公开榜单**的界面说明，不代替官网待确认的正式赛权重。由于本地 Meter 不可用，上述协议运行的 `score=null`、费用未知，不能据 2/2 合成测试推断任何正式排名。
- 对照后未发现需要改动 ZIP 的公开接口差异；下一道缺口仍是可用模型凭证下的真实公开练习及费用数据，以及登录后队伍确认才能看到的正式流程。用户此前要求正式登录、上传和提交留待其后续指示，本轮均未进行。

## 2026-09-25 浏览器外网依赖误报修复

- 重读用户提供的《参赛须知.pdf》四页：参赛智能体须真实调用大模型；通用脚手架可预置，但题目专用答案不可预置；应用运行时网络仅限赛事许可的模型与依赖服务。正式队长账号、平台 Key、隐藏任务及计费仍须依赖平台流程，本地固定响应夹具不能代替正式参赛成绩。此次重读没有发现足以推翻先前打包合同的新规则。
- 审计发现 `browser_probe` 会阻断浏览器访问外网，却只根据 DOM 断言和页面异常设置 `ok`；即使应用偷偷请求 CDN/API 并被拦截，只要界面断言碰巧通过，探针也会报告成功。源码提交 `59bb728a6d793c5ad782da8634c06745a49407cd` 把观察到的 `blocked_external_hosts` 纳入通过条件，并提示编码模型移除 CDN、外部 API/遥测等运行时依赖。这个检查只覆盖探针实际访问的页面与步骤，不是对全部页面或后端网络的完整隔离证明。
- 本机完整单测 **114 项：111 通过、3 项因主机浏览器环境跳过**；旧版 arm64 Runner 的 Chromium 环境运行 `tests.test_browser_probe` 为 **7/7**，其中外网请求虽被应用捕获、DOM 行为正常，探针仍明确判失败；正常异步本地交互仍通过。
- 从干净源码修订 `59bb728...` 构建的精确 ZIP 为 `dist/langqi-forge-qualifier.zip`，SHA-256 `f8c666280457e62714cd38c338b82d0e04c790700e2e4463c29cb55cc7491b9a`，17 个白名单文件，`unzip -t` 全部通过，包内来源清单与该修订一致。后续证据文档提交不进入 ZIP。
- 使用该**精确 ZIP**、旧版 arm64 Runner 与当前本地模拟器包装，在固定响应双批长需求夹具中完整生成、部署并执行独立 Playwright：工作区 `../factory26-local-simulation/runs/qualifier-network-guard-protocol-20260925/`，`container_exit_code=0`、SDK 两项 `IMPLEMENTED`、`behavioral_probe_tested=true`、独立浏览器 **2/2**；生产轨迹 **76/76** 行哈希封印有效。模拟网关请求 14 次。Meter 用假 Key 返回 HTTP 401，`score=null`、真实模型费用未知；该 2/2 仅证明 ZIP 的协议与本地 GUI 夹具，**不是**真实百炼模型完成 BookStack/Keep 的通过率或正式赛成绩。
- 当前仍未取得真实模型 Key 下的公开练习和人民币成本，也没有真实 x86 主机上的当前 amd64 Runner 全流程 GUI 验证。没有登录 ARC-Bench、上传 ZIP 或正式提交，相关决定仍留给队长。

## 2026-09-25 视觉参考共用模型网关

- 本地模拟器 `env.example` 已预填 `VISUAL_MODEL`，但 `VISUAL_API_KEY` 与 `VISUAL_BASE_URL` 默认留空；旧参赛包只有三项视觉变量均显式填写才开放参考图工具。这意味着只填编码模型 Key/网关的练习环境即使有视觉模型名，也不会看本次任务明确引用的截图。公开 BookStack/Keep 需求包含大量 `reference/` 图片，这一配置落差可能影响界面复刻，但实际得分收益仍须真实模型验证。
- 源码提交 `9c7185015b72e9c83a53864ca9f6efbdd7b86cf8` 允许在**显式设置 `VISUAL_MODEL`**时复用已配置的 `OPENAI_API_KEY` / `OPENAI_BASE_URL`；两项完整的 `VISUAL_API_KEY` / `VISUAL_BASE_URL` 仍优先，任一仅填一半时禁止静默回退。独立视觉客户端继续只访问 HTTPS 或本机回环地址；若共用地址不符合安全限制，可选看图工具停用，主编码流程继续。参考图目录若是指向外部的符号链接则拒绝，避免把非任务文件发给视觉网关。模型是否支持该视觉模型、实际识图质量和费用没有被模拟测试证明。
- 主机完整单测 **119 项：116 通过、3 项因浏览器环境跳过**；新增回归覆盖共享凭证实际发起的图像请求（HTTP 客户端模拟）、显式视觉网关优先、不完整配置不回退、链接目录拒绝以及主流程启用/禁用视觉工具。脱敏轨迹不含模拟密钥。由该干净源码提交构建的精确 ZIP `dist/langqi-forge-qualifier.zip` SHA-256 `dfdcb97de12be354af3964655d9a84f9fcce12737bfa51ffdcbc49ac15c4d4b6`，17 个白名单文件，`unzip -t` 通过，包内来源修订一致。
- 该精确 ZIP 在旧版 arm64 Runner + 当前模拟器包装的固定响应双批长需求夹具运行于 `../factory26-local-simulation/runs/qualifier-visual-shared-protocol-20260925/`：传入 `VISUAL_MODEL`，共享编码网关是本机 Docker 桥接 HTTP 地址，因此视觉工具按安全策略停用；主模型协议请求 14 次、SDK 两项 `IMPLEMENTED`、`behavioral_probe_tested=true`、独立 Playwright **2/2**、生产轨迹 **77/77** 行封印有效，`container_exit_code=0`。这证明可选视觉配置失败不会拖垮现有生成链路，**不是**该 Runner 中的真实图像调用或真实百炼模型成绩。假 Key 导致 Meter HTTP 401，`score=null`、费用未知。未登录、未上传、未正式提交。

## 2026-09-25 模型网关故障熔断与已有功能保全

- 审计发现，多批任务一旦在后批遭遇认证失败、持续网关错误或总请求/Token 预算耗尽，旧流程虽然不会拆批重试，却仍会逐个尝试后续独立批次；同样失败的请求会重复耗时，已完成工作也没有明确的终止原因。源码提交 `d10bfcb2e7ecd909af4b3c13051e4702bb1ff0a9` 把网关失败与总预算耗尽标记为终止性异常，当前未验证批次失败、其余需求记为 `FAILED`，不再发模型请求；此前已晋升的实现保留并继续走最终构建/部署/平台独立 GUI。若没有任何有效实现，仍以非零退出并明确报告原故障。普通单批实现失败仍保留原来的拆批与独立需求继续策略。
- 主机完整单测 **121 项：118 通过、3 项因浏览器环境跳过**。新增回归覆盖 401 不重试且不保存服务端错误正文、首次失败不冒充空脚手架、后批失败不继续请求、先前源码保留、SDK `IMPLEMENTED` / `FAILED` 状态与封印轨迹。由该干净源码修订构建的精确 `dist/langqi-forge-qualifier.zip` SHA-256 为 `a0270999e21ff560c9ccd34346d10591705d92a70795353af706b4ff82c53124`；17 个白名单文件、`unzip -t` 通过，包内来源修订一致。
- **故障注入链路**：同一 ZIP 在旧版 arm64 Runner + 当前本地模拟器包装、固定响应双批夹具中运行于 `../factory26-local-simulation/runs/qualifier-gateway-circuit-20260925/`。第一批完成并由 SDK 记为 `IMPLEMENTED`，第二批故意返回 HTTP 401，SDK 记为 `FAILED`；智能体报告 `local-contract-partial`、`model_gateway_stop_reason=attempt 1: HTTP 401`、生成入口退出 0，Runner 仍部署并执行独立 Playwright，结果 **1/2**。`local-result.json` 的 `container_exit_code=1` 来自第二项故意未实现的 GUI 失败，非生成入口失败；`evaluation_status=completed`、`score=null`。模型请求成功 5 次、HTTP 尝试 6 次，说明第二批 401 只尝试一次；生产轨迹 **41/41** 行哈希封印有效，未发现模拟密钥或服务端错误正文。
- **正常链路**：相同 ZIP、相同两批夹具但不注入 401，运行于 `../factory26-local-simulation/runs/qualifier-gateway-normal-20260925/`，模型协议请求/HTTP 尝试均 10 次、SDK 两项 `IMPLEMENTED`、`local-contract-passed`、独立 Playwright **2/2**、生产轨迹 **59/59** 行哈希封印有效，`container_exit_code=0`。两次都是自建固定响应假模型和旧版 arm64 Runner，不是实际百炼模型在 BookStack/Keep 的成绩，也不是当前完整 amd64/x86 Runner 的 GUI 验证；Meter 使用假 Key 均返回 HTTP 401，费用与分数未知。ARC-Bench 仍未登录，项目未上传或正式提交。

## 2026-09-25 最新包在当前镜像的生成与部署复核

- 继续使用上一节**同一精确 ZIP** `dist/langqi-forge-qualifier.zip`，SHA-256 `a0270999e21ff560c9ccd34346d10591705d92a70795353af706b4ff82c53124`；包内来源修订 `d10bfcb2e7ecd909af4b3c13051e4702bb1ff0a9`，17 个白名单文件通过清单逐文件验证。全新工作区：`../factory26-local-simulation/runs/qualifier-current-direct-latest-20260925/`。
- 在本机缓存的当前公开 amd64 基础镜像 `arcbench-local-current:20260924` 中安装包声明的 `arcbench-runtime==0.1.0`，直接运行该 ZIP 的入口。自建固定响应假模型请求与 HTTP 尝试各 **4** 次，智能体退出码 **0**，报告 `local-contract-passed`、官方 SDK `official-sdk`、本地结构/政策/语法/构建/启动检查 **6/6**。其生产轨迹 **28/28** 行通过完整哈希封印，检查范围内没有发现测试用假 Key 明文。
- 在同一当前 amd64 镜像中，对该生成物独立调用公开 Runner 的 `run_submission.py::run_web_template`：前端及后端 `npm install`、前端构建、应用启动均成功，根路径 HTTP 200；再独立请求 `/api/health` 得 HTTP 200 和 `{"ready":true}`。生成报告仍如实标记 `behavioral_probe_tested=false`，因为这个固定响应夹具没有调用浏览器探针。
- 只为本地诊断给该工作区加入一条公开协议断言，使用旧版 arm64 浏览器镜像按 `docs/HYBRID_PUBLIC_GUI.md` 运行，`hybrid-playwright-current-direct-latest-report.json` 为 expected **1**、unexpected **0**、skipped **0**。该断言只检查假模型写出的 `Example` 标题，不代表 BookStack/Keep 或正式任务。
- 当前 amd64 镜像的 Chromium headless-shell 在此 Apple Silicon 主机的 QEMU 下仍于预检崩溃；改试同镜像完整 Chrome 虽能启动浏览器进程，创建页面仍因 QEMU 崩溃，放宽容器 seccomp 和单进程参数均未消除。Docker Desktop 的 Rosetta 模拟当前关闭且另有 7 个容器运行；本轮**没有**修改 Docker 设置、重启服务或中断这些容器。因此“当前镜像直启生成/部署 + 旧镜像浏览器”仍**不是当前完整 Runner**。没有真实模型公开练习成绩、费用、正式赛分数；未登录、未上传、未提交。

## 2026-09-25 源码读取无声截断修复与精确包复测

- 审计发现 `read_files` 默认只给每个文件的前 400 行；短行文件即使还有第 401 行，也可能没有 `content_truncated` 提示。较长的单文件结果还会被通用工具返回上限截成任意字符预览，却仍带着原结果的“未截断”元数据，令后续批次误以为源码已看全。先新增失败回归，再由源码提交 `b2cb572c80dca5f5a050fa309f1ae2eed388ab04` 改成完整行分页、准确的 `next_start_line`，超长单行以 `next_start_char` 精确续读；过大的批量返回只保留哈希和逐文件读取指示。上下文检查点携带未读源码游标，低优先级回合提醒在紧张的上下文预算下不再挤掉验收/源码。它提供可回读能力，不保证真实模型会主动审完每一页。
- 主机全套 **127 项：124 通过、3 项因主机未启浏览器集成而跳过**；旧 arm64 镜像启用真实 Chromium 集成后，`tests.test_browser_probe` **7/7**。`git diff --check` 与 ZIP 解压测试通过。干净源码树构建的精确 `dist/langqi-forge-qualifier.zip` SHA-256 为 `c65070b1cc155b87649f85747c170b8268f094463aa0d578ecdd384e45d3c777`，17 个白名单文件，包内清单绑定上述源码提交。
- **双批正常链路**：同一精确 ZIP 在旧版 arm64 Runner + 当前本地模拟器包装的工作区 `../factory26-local-simulation/runs/qualifier-source-paging-protocol-20260925/` 中，固定响应假模型请求/HTTP 尝试各 **10** 次，SDK 两项需求均 `IMPLEMENTED`、`local-contract-passed`、独立 Playwright **2/2**、容器退出码 0；生产轨迹 **59/59** 行哈希封印有效，未发现未脱敏测试密钥。Meter 使用本地假服务返回 HTTP 404，`score=null`、真实成本未知。
- **当前基础镜像直启链路**：同一 ZIP 在缓存的 `arcbench-local-current:20260924` amd64 镜像的全新工作区 `../factory26-local-simulation/runs/qualifier-paged-current-direct-20260925/` 直接生成，固定响应假模型请求 4 次、官方 SDK 正常、本地检查 **6/6**、生产轨迹 **28/28** 行有效。再独立调用当前镜像的 `run_submission.py::run_web_template`，依赖安装、前端构建和后端启动均成功，`/api/health` 返回 HTTP 200、`{"ready":true}`。借旧 arm64 浏览器镜像的无网络混合诊断对该生成物跑一条公开协议断言 **1/1**，不是当前完整 amd64 Runner 的 GUI 运行。
- 上述 2/2 和 1/1 均来自自建合成题与固定响应假模型，只证明新包的协议链路没有回归。仍没有真实百炼模型在 BookStack/Keep 的公开练习通过率或人民币成本，也没有当前完整 Runner 在真实 x86 环境的 GUI 成绩；ARC-Bench 未登录，未上传或正式提交。

## 2026-09-25 跨批源码续读强化验证

- 保持上一节的**同一精确参赛 ZIP**（SHA-256 `c65070b1cc155b87649f85747c170b8268f094463aa0d578ecdd384e45d3c777`，来源修订 `b2cb572c80dca5f5a050fa309f1ae2eed388ab04`）不变，只扩充仓库测试夹具。第一批假模型写入 502 行的 `frontend/src/first-feature.js`，在第 502 行放置尾部标记；第二批必须先从 `read_files` 发现准确的截断及 `next_start_line`，再实际调用 `read_file` 续读并看见标记，夹具才允许它继续编辑。伪称已读、缺游标或跳过尾部均返回 HTTP 422。新增单元回归检查拒绝与逐页放行逻辑。
- 首次尝试用冗长注释构造大文件，假模型夹具在会话压缩后误判最近工具状态、循环重放，工作区 `../factory26-local-simulation/runs/qualifier-long-source-handoff-protocol-20260925/` 未完成任何批次；这次**失败**不能计作参赛包通过或失败。改为 500 行短注释后，工作区 `../factory26-local-simulation/runs/qualifier-long-source-handoff-short-protocol-20260925/` 用旧版 arm64 Runner + 当前本地模拟器包装完成两批：真实工具调用 `read_file(start_line=198)` 的结果包含第 502 行尾部标记，随后才出现第二批编辑；SDK 两项均为 `IMPLEMENTED`、`local-contract-passed`、独立 Playwright **2/2**、容器退出码 0。固定响应假模型请求 **11** 次；生产轨迹 **63/63** 行哈希封印有效，未发现未脱敏测试密钥。
- 进一步定位首次失败：智能体封印轨迹在第一次压缩时确实记下了 `latest_tool_results=[write_file,replace_text]`，但无记忆的固定响应假模型只找历史 `assistant.tool_calls`，压缩后误以为从未写入。给**测试夹具**增加解析确定性检查点的回归，不改参赛源码或 ZIP。加长到约 50 KB 的首批文件后，用相同 ZIP 在 `../factory26-local-simulation/runs/qualifier-verbose-source-checkpoint-protocol-20260925/` 复测：上下文压缩 **7 次**，第二批连续 `read_file` 游标为 **14→110→206→302→398→494**，最后一次工具结果含第 502 行尾部标记，才继续编辑；全部 **16** 次工具调用零错误。SDK 两项 `IMPLEMENTED`、独立 Playwright **2/2**、容器退出码 0；固定响应假模型请求 **16** 次，生产轨迹 **90/90** 行封印有效，未发现未脱敏测试密钥。这说明第一次卡住的是夹具未识别检查点；不证明真实大模型一定会按检查点正确行动。
- 扩充测试后主机全套 **129 项：126 通过、3 项因主机浏览器环境跳过**；测试夹具与本节文档不进入上述 ZIP。Meter 使用本地假服务返回 HTTP 404，`score=null`、真实模型费用未知。上述结果仅证明**固定响应假模型 + 旧浏览器镜像**下的上下文恢复及跨批续读协议，不能外推到真实模型能完成 BookStack/Keep，也不是当前完整 amd64 Runner 或正式赛成绩。尚未登录 ARC-Bench、上传参赛包或正式提交。

## 2026-09-25 批量源码预算回收与新候选包

- 上节压缩轨迹显示原 `read_files` 对五个文件平均分配 9,000 字符内容额度：四个很短的脚手架文件没有用完额度，`backend/server.mjs` 却在第 42 行截断，遗漏最后的监听调用。源码提交 `cc058e42d2956842e021e2bb569b1261432be874` 将未用额度重新分配给较长文件，继续保持总额度和准确的逐行游标；增加实际通用脚手架及长短混合批量读取回归。现有 400 行单文件上限、超大 JSON 的只读摘要与逐文件回读策略不变。主机全套 **131 项：128 通过、3 项因本机浏览器环境跳过**，`git diff --check` 通过。
- 从上述干净源码提交构建新的**精确候选 ZIP** `dist/langqi-forge-qualifier.zip`，SHA-256 `b7da303dbc8d4bdcf9656c1f913e4d1e3c9e24d1dfa925369eb6a27b7749d69c`，17 个白名单文件，清单绑定 `cc058e42...`；`unzip -t` 通过。测试夹具和本证据文档不进包。旧包 `c65070b1...` 已被同路径新包替代，不得再把旧包的运行结果说成新包的验证。
- **旧版 arm64 Runner + 当前本地模拟器包装**：用新精确 ZIP 在 `../factory26-local-simulation/runs/qualifier-source-budget-handoff-protocol-20260925/` 重跑固定响应双批长文件夹具。首批 `read_files` 返回 `backend/server.mjs` **45/45 行、未截断**；随后两批 SDK 状态均为 `IMPLEMENTED`、`local-contract-passed`、模型协议请求 **15** 次、独立 Playwright **2/2**、容器退出码 0，生产轨迹 **86/86** 行封印有效，未发现未脱敏测试密钥，7 次上下文压缩、工具调用零错误。Meter 本地假服务返回 HTTP 404，`score=null`，真实成本未知。该 2/2 仍只针对自建协议题和假模型。
- **当前缓存 amd64 基础镜像直启**：从同一 ZIP 组装全新工作区 `../factory26-local-simulation/runs/qualifier-source-budget-current-direct-20260925/`，在 `arcbench-local-current:20260924` 中安装包声明依赖后直接运行入口。首批 `read_files` 同样返回 `server.mjs` 45/45 行，官方 SDK 正常、固定响应假模型请求 **4** 次、`local-contract-passed`、结构/政策/语法/构建/启动本地检查 **6/6**，轨迹 **28/28** 行封印有效且未发现未脱敏测试密钥。对生成物独立调用当前镜像的 `run_submission.py::run_web_template` 后，首页 HTTP 200、`/api/health` HTTP 200 且 `ready=true`。这绕开了本机 QEMU 的 Chromium 预检，**不是当前完整 Runner 的独立 GUI 试验**；该夹具不调用 `browser_probe`，报告如实为 `behavioral_probe_tested=false`。
- 只读取得[主办方当前网站](https://create.gosim.org/factory26/)加载的规则文案，仍显示初赛 9/24–9/30、GitHub + Spreadsheets 选定功能复刻及 Top 20 晋级；未登录正式赛详情。当前剪贴板为空，`DASHSCOPE_API_KEY` 与 `OPENAI_API_KEY` 环境变量均未设置，故仍没有真实百炼模型的 BookStack/Keep 公开练习、人民币成本或当前完整 x86 GUI 成绩。ARC-Bench 未登录、未上传、未正式提交；账号与提交继续留待队长指示。

## 2026-09-25 视觉参考缺失的提示与轨迹校正

- 静态核对本地公开练习：BookStack 的 **34** 条、Keep 的 **32** 条原子需求均能进入依赖有序计划；BookStack 文字引用的 **19** 张 `reference/` 图片本地均存在，Keep 文字引用 **22** 张但本地只有 **20** 张，`reference/label_filtered_list.png`、`reference/search_keyword.png` 缺失。这只核对素材库存，不代表真实模型能实现需求或视觉图像已送入模型。当前参赛运行若未配置 `VISUAL_MODEL`，`inspect_reference` 工具不会开放；先前 `implementation_batch_started.visual_references_unavailable=[]` 在此情形下会错误暗示没有缺失视觉能力。
- 源码提交 `756998df4bdb613cb71c97b73dec8b5b2c265461` 修正上述口径：当前批次提及却不可检查的截图会明确写进编码 Prompt，要求模型不能声称已看图或臆造画面；生产轨迹无论视觉网关是否启用，均记录 `visual_inspection_enabled`、`visual_references_available` 和 `visual_references_unavailable`。可查看的截图仍只通过安全白名单的 `inspect_reference` 使用，改动没有预置任何题目专用视觉描述。主机全套 **131 项：128 通过、3 项环境性浏览器跳过**，覆盖无视觉网关与一部分图片存在、一部分缺失两种情况。
- 从干净源码构建的**新精确候选 ZIP** `dist/langqi-forge-qualifier.zip` SHA-256 为 `bb9d7d21b7ccf971a0c622485f0b99403dfcadf9c4573bf103d32ad772b09428`，17 个白名单文件、`unzip -t` 通过，来源清单绑定 `756998d...`；上节的 `b7da303...` 包已被替换。新增测试需求文件与本记录不在参赛 ZIP 中。
- **旧版 arm64 Runner + 当前本地模拟器包装**：精确新 ZIP 在 `../factory26-local-simulation/runs/qualifier-visual-unavailable-protocol-20260925/` 用固定响应假模型运行含缺失截图的合成题，容器退出码 0、SDK 项 `IMPLEMENTED`、独立 Playwright **1/1**。模型协议请求的 Prompt 含 `reference/unavailable.png` 不可检查的告知；批次轨迹记 `visual_inspection_enabled=false`、可用 `[]`、不可用该路径，视觉请求 **0** 次。生产轨迹 **28/28** 行哈希封印有效，未发现未脱敏测试密钥；Meter 本地假服务 HTTP 404，`score=null`。
- **当前缓存 amd64 基础镜像直启**：同一 ZIP 在 `../factory26-local-simulation/runs/qualifier-visual-audit-current-direct-20260925/` 安装 `arcbench-runtime==0.1.0` 后使用主办方入口参数生成，官方 SDK 接入正常、固定响应假模型请求 **4** 次、`local-contract-passed`、本地检查 **6/6**，视觉缺失轨迹如上、生产轨迹 **28/28** 行封印有效。再独立调用该镜像的 `run_submission.py::run_web_template`，首页和 `/api/health` 都是 HTTP 200，健康正文 `ready=true`。此直启绕开本机 QEMU Chromium 预检，**不是**当前完整 amd64 Runner 的 GUI 评测。上面的 1/1 只证明假模型协议，不是 BookStack/Keep 真模型通过率、正式赛成绩或视觉质量。
- 当前剪贴板为空，本机 `DASHSCOPE_API_KEY` 与 `OPENAI_API_KEY` 均未设置；真实模型、费用及当前完整 x86 GUI 仍缺证据。没有登录 ARC-Bench、上传或正式提交；队长保留后续决定权。

## 2026-09-25 最终修复轮的隔离与新候选包

- 大需求分批与依赖审计未发现需要修改的拓扑排序：本地公开 BookStack/Keep 分别解析为 34/32 条原子需求，默认 9/8 批。发现另一处实际风险：原最终修复轮直接改写已晋升的 `frontend/` 和 `backend/`，修复未完成或候选构建仍失败时可能留下半成品。源码提交 `589dc00a7de6ea59781e3af030cedfcbf65a18e5` 将修复轮改为私有副本编辑、候选完整检查通过后才晋升，并在晋升后再检查正式输出；未晋升的修复不计入最终行为探针声明。回归分别注入“智能体未完成”和“候选检查失败”，两者均保持原已提交应用不变；成功修复仍留有明确的晋升及检查轨迹。
- 主机单测最终复跑 **132 项：129 通过、3 项因本机 Chromium 环境跳过**；`git diff --check` 通过。第一次全套运行中有一例通用脚手架启动检查瞬时失败，其单项复跑及第二次全套复跑都通过；这仍是本机端口/启动链路的偶发性证据，不能被复跑成功抹去。
- 从干净源码提交构建的新精确候选包为 `dist/langqi-forge-qualifier.zip`，SHA-256 `10c8f89d7dcbe8cc54274a4978d09de8d16f274280b3338998d465216bbc8482`，17 个白名单文件，`unzip -t` 全部通过，包内来源清单绑定上述 `589dc00...`。上一节 `bb9d7d...` 包已被同路径新包替代。
- **旧版 arm64 Runner + 当前本地模拟器包装**：使用这份精确 ZIP、自建固定响应协议模型和单条合成要求，在 `../factory26-local-simulation/runs/qualifier-repair-staged-protocol-20260925/` 完成官方 SDK 接入、4 次协议模型请求、6/6 本地结构/策略/构建/启动检查、独立 Playwright **1/1**，容器退出码 0。生产轨迹 **28/28** 条哈希封印有效，未发现测试假 Key 明文；Meter 本地端口拒绝连接，`score=null`、Token 与费用未知。此正常协议夹具未触发最终修复轮；修复分支只由上述故障注入回归覆盖。该 1/1 **不是** BookStack/Keep 的真实模型通过率、正式赛得分，也不是当前 amd64 Runner 的完整 GUI 验证。
- 按官方 [Codex 非交互模式文档](https://developers.openai.com/codex/non-interactive-mode)检查了本机命令行作为隔离诊断的可行性：本机旧版 Codex CLI `v0.137.0` 不能解析当前模型配置中的 `max` 档，运行时大量报模型元数据解析错误；即便使用忽略用户配置的临时只读运行得到一次 `OK`，它也不是参赛包的 OpenAI-compatible 模型网关，更不构成项目生成能力证据。没有将 Codex 登录态转成赛事 API Key，也没有借它冒充公开练习。当前没有可用的百炼/赛事模型 Key；ARC-Bench 未登录、未上传、未正式提交。
