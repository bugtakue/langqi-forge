# 2026-09-24 本地验证记录

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
