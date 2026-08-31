# Adversarial hardening — 2026-09-01

本页记录正式百炼基线之后的最新代码强化。它证明当前工作树的确定性内核、故障语义和 GUI 兼容性；它不是新的模型生产轨迹。最终参赛证据仍需在实现冻结后用阿里云百炼重新生成并通过资格门。

## 最新回归

| 验收 | 结果 | unexpected / skipped / flaky | 备注 |
|---|---:|---:|---|
| GitHub 最新 dry-run 制品基准 | 101 / 101 | 0 / 0 / 0 | 4 workers，完全并发 |
| 同一制品改名对抗 | 101 / 101 | 0 / 0 / 0 | 4 workers，完全并发 |
| Spreadsheet 最新 dry-run 制品基准 | 102 / 102 | 0 / 0 / 0 | 4 workers，完全并发 |
| Python 全仓测试 | 85 / 85 | — | 含证据篡改、路径逃逸、胶囊和竞品 runner 合同 |
| Node 内核与认证合同 | 22 / 22 | — | 含确定性随机总账/BOM 性质测试 |

三套最新 GUI 曾有两套并行运行，因此未把当时墙钟写成正式性能证据。最终数字必须在实现冻结后从干净 commit 顺序重跑，并由 v2 资格门与独立验证器一起验收。企业 GUI 另通过 GitHub 8 个页面与 Spreadsheet 5 个工作区的端到端操作。

## 被验证的闭环

### GitHub

`workflow run → job status/provenance → PR check → active Ruleset → CODEOWNERS/approval → atomic merge → audit state root`

- 工作流 DAG、必填 dispatch input、环境审批和禁止发起人自审均在后端执行。
- 活跃 Ruleset 才阻断；`evaluate` 模式只观察，便于安全上线。
- 合并同时检查 Maintain 权限、草稿/状态、最新评审、非作者批准、Request changes、CODEOWNERS 和所有必需 checks。
- 合法合并更新目标分支文件、生成 merge commit，并保存合并人、时间与提交 ID。
- 通用状态更新不能伪造 `merged`；分支保护或 active Ruleset 命中的分支不能被通用写接口绕过。
- 登录成功签发随机、限时且绑定浏览器 world 的服务端会话；客户端用户名头部不再构成身份，伪造头部写请求返回 401。
- 新凭据使用 PBKDF2-SHA256 派生存储；匿名状态不返回账户，认证状态也永不返回明文或派生密码。
- 账户恢复先取得不泄露账户存在性的短期上下文；修改密码后撤销该 world 下该账户的既有会话。
- 通用 `create/patch/list` 使用服务端权限矩阵与字段白名单，作者、资源编号和所有者由服务端约束；未声明字段、原型污染和跨资源改写在事务提交前拒绝。
- 所有 GitHub 命令在候选副本执行；失败只追加拒绝审计，不保留任何半成品业务修改。

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
- 证据封口：源码文件树、Prompt/tool call、report、原始 Playwright JSON、测试包、反例和能力胶囊逐层交叉绑定。
- 证据反重跑：公开评测 label 不可覆盖；同名结果已存在时直接拒绝。
- 证据独立复核：导出前重算资格门；导出后再重算核心检查、胶囊语义与脱敏轨迹转换。
- 变异测试：20 个针对平衡、公式、BOM、日期化到货、幂等、关账、工作流、职责分离、审计、状态根和合并门禁的关键变异体全部被现有测试杀死。
- 竞品盲测：只给公开需求、不提供测试源码或现有内核；Codex 与 Claude Code 都从空目录开始，固定模型、effort、墙钟、原始轨迹和零人工，并由同一外部评分器验收。这与“参赛 Factory 是否能复用自有经验”分开报告。

## 尚未冒充完成的事项

- 最新代码尚未用百炼密钥重新生成最终双域生产轨迹；仓库现有 `evidence/final/` 仍是上一份真实 `qwen-plus` 运行。
- Claude Code 本机当前已恢复登录，Codex / Claude Code 同题 runner 均已准备；尚未完成的实际对照不作为已有胜负宣称。
- 3–5 分钟视频按用户要求后置；官网项目未提交，也未保存不可撤回的提交动作。
