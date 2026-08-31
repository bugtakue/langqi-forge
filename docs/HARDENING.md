# Adversarial hardening — 2026-08-31

本页记录正式百炼基线之后的最新代码强化。它证明当前工作树的确定性内核、故障语义和 GUI 兼容性；它不是新的模型生产轨迹。最终参赛证据仍需在实现冻结后用阿里云百炼重新生成并通过资格门。

## 最新回归

| 验收 | 结果 | unexpected / skipped | 墙钟时间 |
|---|---:|---:|---:|
| GitHub 公开基准 | 101 / 101 | 0 / 0 | 8.927 秒 |
| GitHub 对抗改名 | 101 / 101 | 0 / 0 | 9.397 秒 |
| Spreadsheet 公开基准 | 102 / 102 | 0 / 0 | 17.811 秒 |
| Python 全仓测试 | 61 / 61 | — | 15.237 秒 |
| Node 双内核合同 | 18 / 18 | — | 0.389 秒 |

三套公开 GUI 均为 4 workers、文件内完全并发。企业 GUI 另通过 GitHub 8 个页面与 Spreadsheet 5 个工作区的端到端操作。时间只描述本机该次运行，不作为跨机器性能承诺。

## 被验证的闭环

### GitHub

`workflow run → job status/provenance → PR check → active Ruleset → CODEOWNERS/approval → atomic merge → audit state root`

- 工作流 DAG、必填 dispatch input、环境审批和禁止发起人自审均在后端执行。
- 活跃 Ruleset 才阻断；`evaluate` 模式只观察，便于安全上线。
- 合并同时检查 Maintain 权限、草稿/状态、最新评审、非作者批准、Request changes、CODEOWNERS 和所有必需 checks。
- 合法合并更新目标分支文件、生成 merge commit，并保存合并人、时间与提交 ID。
- 通用状态更新不能伪造 `merged`；分支保护或 active Ruleset 命中的分支不能被通用写接口绕过。

### Spreadsheet

`runtime contract → validated mutation → optimistic revision → postcondition → state-root event`

- 安全算术解析器不使用 `eval`，并检测公式依赖环。
- 总账使用整数分，拒绝不平、跨币种和关闭账期；同 reference/幂等键的同输入重试返回原凭证，不增加 journal、event 或 revision，不同输入则冲突。
- 月结可显式复开，所有 close/reopen 都进入证据链；原凭证不改写，只能产生反向凭证。
- MRP 在无环多级 BOM 上计算净需求、批量、损耗、安全库存和提前期；日期化采购到货只在 available date 当日及以后进入可用量。
- 所有写请求要求 `expectedRevision`，命令后置条件失败则候选副本整体丢弃。

## 故障与攻击矩阵

- 需求 YAML：体积、节点数、深度、别名、重复 ID、未知依赖、自依赖和环均有上限或拒绝语义。
- Prompt injection：已知能力后拼接未知/恶意操作不会继承内核覆盖；只把未覆盖节点送入 delta Agent。
- Agent：工具调用洪泛、连续无进展、无最终验证、超 Token/字节预算均熔断。
- 工作区：路径穿越、大小写凭据名、symlink 逃逸、控制字符、无 SHA 覆盖和写入预算均拒绝。
- 执行：依赖 lifecycle script、本地依赖源、模型密钥继承、越界写入和中断事务均有 fail-closed 或恢复测试。
- 持久化：坏 JSON 原文件保持不变并拒绝启动；不会静默初始化为空状态。
- 证据：生产 trace、GitHub audit 和 Spreadsheet compute events 均验连续序列、哈希链接与内容哈希；后两者额外绑定完整业务状态根。
- 变异测试：20 个针对平衡、公式、BOM、日期化到货、幂等、关账、工作流、职责分离、审计、状态根和合并门禁的关键变异体全部被现有测试杀死。

## 尚未冒充完成的事项

- 最新代码尚未用百炼密钥重新生成最终双域生产轨迹；仓库现有 `evidence/final/` 仍是上一份真实 `qwen-plus` 运行。
- Claude Code 本机 OAuth 已被撤销，固定预算对照协议可准备，但在重新登录前不能产生诚实的对照结果。
- 3–5 分钟视频按用户要求后置；官网项目未提交，也未保存不可撤回的提交动作。
