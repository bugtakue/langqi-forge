# 2026-09-24 本地验证记录

## 已完成协议运行使用的源码与包

- 源码分支：`codex/factory26-compliant-20260924`。
- 已验证提交：`28a013f6e7d11100db3c7fffdb84ba298343c5bc`。
- ZIP：`dist/langqi-forge-qualifier.zip`，SHA-256 `c2bec559cc78682c4e458ae8c4bee0588138854f98798f7225989659e163eca6`。13 个文件（含哈希清单），不含任务专用模板或旧实现。
- 该 ZIP 是以下协议运行的精确输入。后续若提交新 commit，即使只更新文档，打包器的来源 revision 也会改变；新的 ZIP 应在交付时单独标明哈希并再做一次运行确认。

## 验证层级

1. Python 保留测试 45/45 通过；包含模型缺失时失败关闭、Runner 预填文件兼容、通用存储并发、包白名单、轨迹哈希。
2. 主办方本地模拟器 `--prepare-only` 解包成功，清单验证得到上述源码提交。
3. 使用**本机已有的旧版 ARC-Bench Runner 基础镜像**加主办方当前 `local_runner.py` 包装，在自建一条「Example heading」协议夹具上运行成功。源码位于 `tests/protocol_gateway.py` 与 `tests/protocol_requirements/requirements.yaml`；它不是大模型，也不是比赛题目。
4. 协议运行工作区：`../factory26-local-simulation/runs/qualifier-protocol-20260924/`。`local-result.json` 记录 `container_exit_code=0`、`evaluation_status=skipped`、`score=null`；未提供 Playwright 测试。
5. 该运行的 `.arc/harness-report.json` 记录 1 条需求已实现、4 次模型协议请求、结构/包策略/交互/前端构建/后端启动健康检查全通过；`.arc/production-trace.jsonl` 共 26 条，哈希链校验有效。

## 明确不能据此声称的内容

- 没有使用真实大模型完成 BookStack/Keep，**没有公开 GUI 通过率、成本或官方得分**。
- 假模型只用于证明 ZIP、接口、工具调用、源码修改、构建和 Runner 部署链路，不反映生成复杂产品的能力。
- 此次完整运行的基础镜像来自本机旧版，不能替代当前主办方镜像的最终兼容性验证。当前镜像下载/构建和正式平台验证仍待完成。
- 未登录 ARC-Bench 队长账号、未建立正式比赛队伍、未上传和提交项目。

下一步是取得本地练习可用的模型 API Key，用主办方当前模拟镜像在 BookStack 与 Keep 分别实跑；只有独立 GUI 结果出来，才能讨论竞争力与正式提交版本。
