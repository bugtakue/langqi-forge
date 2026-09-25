# 参赛入口启用冻结代码收尾

## 决策依据

fb84f4e的GitHub完整生成轨迹中，有一批修复后已quick通过却耗尽回合；同快照Sheet的seq652—666提供更直接证据：revision10写入→quick通过→请求终审→行为探针通过→恰好20回合耗尽→丢弃整批。Sheet总输入仍2529646，未触发360万全局上限。详见nonthinking-sheet-final-evidence-2026-09-26.md。

不是所有失败都差一次审查；例如该Sheet矩形范围操作的探针没有实际拖选，补一次审查也可能正确拒绝。此改动不能当作将未晋升消耗74.82%全部救回的承诺。

## 本次窄改动

已有completion tail的门禁与实现不变，仅正式`python main.py ...`入口用setdefault显式开启FACTORY26_COMPLETION_TAIL=1。调用库默认仍关闭，Runner明确0/1保持优先，非法值仍被原校验拒绝，不静默覆盖。每次agent_session_started额外记录实际completion_tail_enabled，便于封印后追溯。

只对有代码修改、当前revision quick/full通过、已经请求同revision终审、仍有原资源额度的implementation候选生效。冻结代码后最多一次原预算内行为探针加一次无工具终审；已验证当前行为时只补终审。不得读取/写入源码、调用其他工具、重新开批或跳过完整验证/回归/晋升门。原全局请求/输入/输出上限、20回合常规实施和浏览器上限不变，实际总会话最多22次模型请求。模型拒审、证据不足、预算不足或revision变化均不能晋升。

候选整合主分支完整源码保留、失败现场回传、控件状态断言；编码策略回到此前有非零成绩的bounded，而非fb84f4e的nonthinking。因此后续若分数变化，只能归于这一整包候选与真实运行，不能宣称单独识别了某一改动的因果贡献。不新增agent席位，不读官方隐藏测试、不热改已生成应用。

## 验证

4项入口测试覆盖入口默认开启/库默认关闭、显式关闭、显式开启、非法覆盖失败关闭；原收尾边界夹具另外验证trace实际开关。与控件状态等28项聚焦回归通过。冻结完整回归355项，352通过/3既有环境跳过，63.973秒；git diff --check通过。未调用真实模型/浏览器，不能代替正式提分结果。

## 干净封包与独立解包

- 干净源码`8f306526796b95ad5b9233c98c02b05338a1c642`，包`dist/langqi-forge-completion-control.zip`，21成员/194348字节。
- ZIP SHA `645f9935a02cd872dfa582bcd5bcfbf33e0a9e581e4c0f47b561c48539a28e39`，合同SHA `7fc744f0a1a2108b96a36f9f415818f5d440dacfee501e0a97232333c05a2510`。
- 独立解包`/private/tmp/factory26-completion-control.Ivsvzl`，精确白名单/CRC/逐文件字节/哈希/整个manifest重算与所有Python AST通过。
- 实际从解包目录加载runtime，50项控件/失败现场/语义/收尾/上下文协议/入口测试通过（0.205秒）。没有用工作树runtime替代ZIP检验，没有个人Key/模型调用。
- 封包时未上传，后续保存及正式启动状态以下节为准。准备和封包不等于线上通过。

## 后续上传与正式启动

2026-09-25 19:38:38平台保存`Langqi Forge 8f30652 - verified completion`（History16，页面时间未标时区），精确沿用上述ZIP，上传前再次核对SHA与干净工作树。旧fb84f4e Sheet正式终态后，串行启动GitHub [a2b7ba164c06](https://arc-bench.com/runs/a2b7ba164c06)，没有并行Sheet、重复启动或取消其他任务。预检/依赖安装通过且首个模型调用与read_files成功；官方成绩仍未知。平台stdout是精简事件，不以未显示开关字段推断入口失效；实际会话开关仍待完整封印轨迹核验。详见completion-control-official-run-2026-09-26.md。
