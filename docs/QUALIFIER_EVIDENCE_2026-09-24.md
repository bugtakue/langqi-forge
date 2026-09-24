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
