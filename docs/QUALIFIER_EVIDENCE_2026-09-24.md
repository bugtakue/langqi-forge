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

## 通用浏览器交互探针与最终候选包（本页最新）

- 为补上「能构建、能启动，但用户操作可能失效」的验收盲点，新增 `browser_probe`：只在当前源码通过 quick/full 后，使用 Runner 自带 Chromium 对**生成的本地应用**执行有界语义控件操作、刷新和可见文本断言；拦截浏览器外部 HTTP 请求，不提供任意脚本、远程网址或隐藏测试读取。每批最多 3 次，若已经使用探针但没有完成带断言的动作、探针失败或后来改动源码，则该批不得仅凭旧探针完成。报告分别记录 `behavioral_probe_tested`（本地探针）与 `behavioral_gui_tested=false`（没有独立平台 GUI 成绩）。
- 第一次包含探针的协议 ZIP 在旧版 arm64 Runner 中失败关闭：宽范围的 Playwright 依赖让 pip 安装新版 Python Playwright，却保留旧版 Chromium 二进制；浏览器无法启动，模拟智能体没有虚报完成。修复为不在参赛 `requirements.txt` 覆盖 Runner 预装 Playwright；本机独立环境才自行安装匹配的 Python 包和 Chromium。这个失败是依赖版本适配证据，**不是比赛任务失败**。
- 最终候选运行源码提交为 `d9d99e2c40723ac88d08d832104360e5cf4e9cd0`；ZIP `dist/langqi-forge-qualifier.zip` 的 SHA-256 是 `3d73edea56b787b3503edf183d438f258352b848e069389224de6c9e98768353`，16 个文件，`unzip -t` 通过。此后只追加本证据文档；ZIP 清单仍精确绑定该运行源码提交。主机单元测试 58/58 通过（其中需容器浏览器的 1 项在主机跳过），在 arm64 Runner 容器内浏览器探针相关 3/3 项全部运行并通过。
- **同一最终 ZIP** 在旧版 arm64 Runner + 当前本地模拟器包装的完整协议运行：`../factory26-local-simulation/runs/qualifier-browser-probe-final-20260924/`。自建模型协议夹具提出 5 次模型接口请求，其中一次 `browser_probe` 实际点击 `Try` 按钮，页面显示 `Clicked` 并命中显式断言；智能体报告 `local-contract-passed`、`arcbench_runtime=official-sdk`、`behavioral_probe_tested=true`、6/6 本地检查通过。后续独立 Playwright 协议测试为 1/1，容器退出码 0；`score=null`、Token/费用为 `null`，**不是公开练习或正式赛成绩**。生产轨迹 31/31 行哈希链有效，未发现未脱敏密钥。
- **同一最终 ZIP** 在当前主办方 amd64 基础镜像（上节所列摘要）直启：`../factory26-local-simulation/runs/qualifier-current-base-final-direct-20260924/`。官方 SDK 可安装且正常记录，4 次自建模型协议请求后 `local-contract-passed`，6/6 构建/启动检查通过；此直启夹具没有调用浏览器探针，报告明确为 `behavioral_probe_tested=false`。完整新版 Runner 在本机仍卡于 arm64→amd64 QEMU 的 Chromium 预检，不能由直启结果替代它的 GUI 验证。
- 当前仍未取得真实模型对 BookStack 和 Keep 的生成结果、两题综合 GUI 通过率、真实开销、官方得分或晋级资格；正式队长账号也未登录，项目未上传或正式提交。
