# Adversarial hardening — 2026-09-01

本页记录正式百炼基线之后的最新代码强化。它证明当前工作树的确定性内核、故障语义和 GUI 兼容性；它不是新的模型生产轨迹。最终参赛证据仍需在实现冻结后用阿里云百炼重新生成并通过资格门。

## 最新回归

| 验收 | 结果 | unexpected / skipped / flaky | 备注 |
|---|---:|---:|---|
| GitHub 最新 dry-run 制品基准 | 101 / 101 | 0 / 0 / 0 | 4 workers，完全并发 |
| 同一制品改名对抗 | 101 / 101 | 0 / 0 / 0 | 4 workers，完全并发 |
| Spreadsheet 最新 dry-run 制品基准 | 102 / 102 | 0 / 0 / 0 | 4 workers，完全并发 |
| Python 全仓测试 | 114 / 114 | — | 含证据篡改、统计型伪报告、运行时替换、环境注入、轨迹密钥夹带、路径逃逸、胶囊、第三域盲测输入锁定、Planner 时间预算与并行预构建、原始 tool-call 规范化绑定、最小比赛包、评委报告、竞品 runner 和实时违规终止合同 |
| Node 内核与认证合同 | 22 / 22 | — | 含确定性随机总账/BOM 性质测试 |

2026-09-01 在干净提交 `ae293d7` 上完成了新的顺序离线冻结：GitHub baseline 11.113s、GitHub adversarial 10.843s、Spreadsheet baseline 19.327s，全部 4 workers、无 unexpected / skipped / flaky。这些是本地候选证据，不是模型生产证据。最终数字必须在实现冻结后从干净 commit 通过百炼顺序重跑，并由 v2 资格门与独立验证器一起验收。企业 GUI 另通过 GitHub 8 个页面与 Spreadsheet 5 个工作区的端到端操作。

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
- Planner 时间预算：已知域强制单次 HTTP attempt 和默认 60 秒上限；超时显式降级并关闭资格门，不用内部重试吞掉赛时。
- 计分路径预算：每次只发送候选域合同与候选域标签 schema，不把另一域合同和标签重复塞入上下文；当前两套公开题的序列化请求体合计较上一版缩小约 18%（这是相同模型字段下的 UTF-8 字节口径，不冒充网关 Token）。模型请求与可回滚基座的构建/健康预检并行，事件同步测试证明预检结束时被阻塞的 Planner 仍在运行，且并发轨迹哈希链完整。
- 模型参数证据：原始 tool call 留在 provider response，实际应用参数经确定性限长后另存并绑定原始参数哈希；资格门从原始回复重演规范化，不要求生成者自述二者一致。
- 提交包：只含 45 个运行文件（具体数量随源码冻结版本重算），拒绝脏树、symlink、凭据样路径、篡改及未登记夹带文件；旧 `arc.sh` 的明文登录与上传能力已经移除。
- 解压边界：比赛包要求生成 workspace 位于源码包外；若误把 `--output-dir` 放进解压目录，会在任何写入前以明确错误拒绝，不通过忽略任意子树来削弱源码清单。
- 工作区：路径穿越、大小写凭据名、symlink 逃逸、控制字符、无 SHA 覆盖和写入预算均拒绝。
- 执行：依赖 lifecycle script、本地依赖源、模型密钥继承、越界写入和中断事务均有 fail-closed 或恢复测试。
- 持久化：坏 JSON 原文件保持不变并拒绝启动；不会静默初始化为空状态。
- 证据：生产 trace、GitHub audit 和 Spreadsheet compute events 均验连续序列、哈希链接与内容哈希；后两者额外绑定完整业务状态根。
- 证据封口：源码文件树、Prompt/tool call、report、原始 Playwright JSON、测试包、反例和能力胶囊逐层交叉绑定。
- 评测器防伪造：不信任 Playwright `stats`自报；必须枚举每个 spec/project/result，匹配锁定 inventory SHA、单次无重试结果、4 workers/完全并行和 Playwright 1.62.1 完整运行时树。运行前后均验运行时，应用进程不获得评测目录与评测控制变量。
- 环境与轨迹防泄露：生成应用、npm 和 Playwright 只获得明示白名单变量；宿主的 OpenAI/百炼密钥、`NODE_OPTIONS` 和旧 E2E 覆盖不会继承。轨迹写盘会处理 password/cookie/session/header/连接串/JWT 等密钥形态，证据导出和独立验证再扫一次，即使重新封链也不会放行。
- Prompt 原文绑定：资格门直接重算 trace 内 user message SHA，必须命中由锁定公开需求编译出的双域 Prompt，不再只核对生成者自报的 requirement SHA。
- 证据反重跑：公开评测 label 不可覆盖；同名结果已存在时直接拒绝。
- 证据独立复核：导出前重算资格门；导出后再重算核心检查、胶囊语义与脱敏轨迹转换。
- 变异测试：20 个针对平衡、公式、BOM、日期化到货、幂等、关账、工作流、职责分离、审计、状态根和合并门禁的关键变异体全部被现有测试杀死。
- 竞品盲测：只给公开需求、不提供测试源码或现有内核；Codex 与 Claude Code 都从空目录开始，固定模型、effort、墙钟、原始轨迹和零人工，并由同一外部评分器验收。这与“参赛 Factory 是否能复用自有经验”分开报告。
- 自身泛化盲测：新增与两个公开域无关的 Change Control 任务，模型只能读到两个原子需求，无法通过 workspace tools 读取仓库外的 5 个 Playwright 测试。运行器要求 `generic → bounded coding agent`、至少一次真实编码迭代、零人工、锁定输入/测试/运行时 SHA、源码不变和封链结果。它不计入官方 304 分，在真实模型轨迹完成前也不宣称已通过。

## 尚未冒充完成的事项

- 最新代码尚未用百炼密钥重新生成最终双域生产轨迹；仓库现有 `evidence/final/` 仍是上一份真实 `qwen-plus` 运行。
- 第三域 Change Control 盲测的需求、隐藏测试和 fail-closed runner 已冻结；当前只能声明“通道可运行”，尚不声明泛化通过，直到真实百炼模型产生编码工具轨迹并通过 5/5 黑盒。
- 2026-09-01 的 `unbounded-v2` 隔离盲测不构成成对成绩：Codex CLI `0.151.0` + `gpt-5.4/high` 在 GitHub 上 1200.063 秒 timeout，未产生可评分文件；在 Spreadsheet 上 1200.062 秒 timeout，已生成前后端 10 个文件，但未执行 install/build/start，因此仍不评分。两次均无违规工具事件。Claude Code `2.1.161` 在 5.792 秒返回 OAuth token revoked 的 401，属认证失败而非参赛成绩。
- 独立的 `checkpointed-v3` 对双方同时要求早期可运行骨架与最多两文件的增量编辑，不覆盖 v2 超时。Codex 的 Spreadsheet v3 运行在约 1 分钟内生成了前后端可安装骨架，随后逐层生成事务持久化、公式、结构变更、CSV、排序/筛选/校验/透视和真实 SPA；但在 1200.044 秒时仍未做完最终 build/start 收尾，所以状态仍是 timeout、不评分。它证明检查点策略改善了可恢复性，也暴露出单文件仍可膨胀到 1,584 行的剩余问题。在 Claude 重新认证并完成同题运行前，不宣称任一通用 Agent 获胜。
- 3–5 分钟视频按用户要求后置；官网项目未提交，也未保存不可撤回的提交动作。
