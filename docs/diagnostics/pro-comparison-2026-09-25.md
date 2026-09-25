# 同源码的编码模型对照

2026-09-25，前一Goal回合完成c3887cd正式失败取证及f8a3e84本地修复，属于实际进展。本回合不再叠加运行时代码修改，先隔离一个可控变量继续正式验证。

## 检查与决定

重新读取平台[API页](https://arc-bench.com/api-doc)，其内容是运行时SDK，不包含模型代理400的诊断细节。[DeepSeek官方思考模式文档](https://api-docs.deepseek.com/guides/thinking_mode/)列有OpenAI格式的reasoning_effort=low，并要求带工具时回传历史reasoning_content；该事实不能证明比赛别名/代理正确透传全部参数。封印请求的工具ID配对与字段保留检查已通过，但没有保留的错误原文，不能确定前一400根因，也不靠删除必要字段或盲目重试修复。

正式综合榜当前已有deepseek-v4-pro的有效记录，因此选择它进行一次串行对照。**沿用完全相同的c3887cd ZIP，只改变编码模型名称**；视觉模型、源码、提示、工具、reasoning_effort请求策略及预算不变。运行时段和模型随机性仍不可控制，一次成功也不能反向证明上一次是平台故障。

本地f8a3e84的候选流程重验修订刻意不混入；本次运行不包含那项修补。没有追加个人Key、充值或并行任务。

## 精确身份与启动

- 实际ZIP：`dist/langqi-forge-read-page-memory.zip`，21成员、189,200字节，SHA `50bba49d0d939201803da71e01f9993a7e4fa7b96f20c7a16bc5b772b647027f`；本回合重算SHA及ZIP CRC均通过。
- 包内`factory26-source.json`确认源码`c3887cd34403666e9b3b6189b9487cbfeaf35e78`、合同`db821686a7556fb75bb1fd33a24181ebe09912a0ab6ef09777302322b91e3cd1`。未从当前f8a3e84工作树重打包。
- 保存名：`Langqi Forge c3887cd - Pro comparison`；页面时间2026/9/25 14:38:41（页面未标时区），History (13)。
- 编码：`deepseek-v4-pro`；视觉：`deepseek-v4-flash-vision-exp`；网关：`https://api.arc-bench.com/v1`；比赛额度已勾选，个人Key框随之隐藏。
- 正式运行：[359dd7e72ca7](https://arc-bench.com/runs/359dd7e72ca7)。在GitHub单题页核验新保存身份且“当前没有正在进行的任务运行”后，点击一次“运行最新提交”；没有点击双题批量运行。
- 已核验新运行ID、版本、环境预检/依赖安装通过、Stage2启动，Stage3 pending。Sheet未开始；无新成绩或结算费用，¥467.27仅为本次运行前余额。

## 同期榜单

14:37 UTC左右现场读取[正式综合榜](https://arc-bench.com/competition?competition=hackathon)，筛选为Agentic Software Factory Hackathon / 全部任务 / 全部模型：24条结果，本队bugtakue第19，0.00分、0.0%、¥2.3829、提交时间05:22:11。它仍是最早b958be3的双题快照，不是单题c388/f3的合并成绩。

前三：VOLO-AI / Flash / 55.27分 / 50.5% / ¥16.3888；Iris / Pro / 36.34分 / 40.5% / ¥55.7107；尻名山掌管排水渠过弯的神 / GLM-5.3-Flash / 29.17分 / 29.5% / ¥24.9800。这些是这一时点的公开结果，不保证后续名次。

下一步跟踪这一精确Pro运行。重点是能否越过第二请求、晋升更多需求及最终官方通过率/人民币成本；不能将请求成功或内部晋升当成前三完成，也不能用它掩盖前版3/100的覆盖缺口。

## 首段观察

14:39:27 UTC开始首批注册/登录；request1/2/3分别在3.394/5.100/2.994秒正常返回，使用量输入/输出分别11,269/111、13,924/204、14,221/63。工具依次read_files、list_files、read_files成功，14:39:38发出request4/seq28。1m44s现场仍Stage2，Stage3 pending。三个都是短工具选择响应，不构成长代码生成或需求完成的证据；没有据此断定Flash故障原因。

## 8m10s观察：超时后恢复，尚未实现功能

14:43:39 UTC，request4第一次尝试在240.075秒后TimeoutError，按既有策略等待1秒重试；第二次在14:44:13返回，耗时33.818秒、输入14,924/输出2,261 Token。随后对需求提供的注册和登录参考图执行inspect_reference，两次视觉返回分别报告1,038/184与912/164 Token，工具均成功。14:44:39发出request5/seq41；14:47 UTC现场8m10s仍Stage2，Stage3 pending。尚未观察到write_files、批次晋升或官方分数。

这次实测证明一次超时后可恢复，不证明Flash故障根因、Pro长代码产出或新功能可用。没有取消、重复启动或并行Sheet。本回合只核查当前运行并独立封包已完成的本地修订，不再增加运行时变量。

10m09s交接前更新：request5首尝试也在14:48:39 UTC以240.15秒TimeoutError结束；14:48:40启动第二次尝试/seq43，仍在途。现场Stage2 / Stage3 pending，没有新写入或晋升。不能把前一次恢复概括为通道已稳定，下一回合接续同一运行，不手动重复启动。

## 首批晋升（14:57 UTC）

request5第二尝试139.202秒后成功（输入17,697/输出10,484），seq46首次写入应用数据。request6在167.866秒后返回（17,098/14,486），一次完成后端、前端与样式三次写入；不要从此前一次只写数据推断模型不支持多工具写入。seq62快速检查通过；后续又检查源码、修订前端并重新验证，seq119/124两次浏览器自测通过。

14:57:00，seq138明确首批REQ-1-1-1/REQ-1-1-2 completed=true、staged_changes_committed=true、19回合、2次行为自测。当前内部2/47，不能当作官方测试2/100。seq141开始恢复账号/退出/改密码三项；最新request22/seq157于14:57:08发出，19m34s现场仍Stage2、Stage3 pending。没有官方新成绩/费用或新综合名次，未并行Sheet。

期间发现验收压缩会在有空间时无谓缩减源码，本地最小修订和离线对照见`audit-source-capacity-2026-09-25.md`；不属于当前Pro运行。公开检索未确认VOLO-AI的参赛源码，不对第一名架构作推测；只读到公开ARC基线的接口设计/测试先行说明（https://github.com/code-philia/agentic-requirement-compiler）及其React模板目录（https://github.com/Weiyu-Kong/arc-template），未复制、安装、运行或替换当前参赛栈。

23m08s交接现场：request22第一次在15:01:08 UTC以240.155秒TimeoutError结束，15:01:09开始第二次尝试/seq159。仍Stage2/Stage3 pending，内部晋升仍2/47，无新官方结果。页面已保留，不取消、不重开、不并行。

## 第二批继续生成及独立首批检查

request22第二尝试也在15:05:10 UTC超时（240.154秒），第三次于15:09:01正常返回（229.766秒、输入21,507/输出20,263）。seq164/166/168写入前端、后端和样式；seq179 quick通过，随后seq180滚动压缩25,836字节源码，seq181验收压缩后62,963字符，seq187—199再读7个源码文件。它为前轮验收源码容量问题提供另一条观察，但不证明所有重读都可省略；新修订尚未上传。

31m33s现场仍Stage2/Stage3 pending，request26/seq201于15:10:25发出，第二批尚未晋升。此前request22超时不构成终止，不手动重开。

本轮另完成本队中途注册/登录的独立Chrome检查及10项本地API检查，三组8并发都只有1次成功/1个落盘账号；只使用公开需求和人工合成输入，无隐藏测试、额外模型调用或远端修改，临时服务已停止。完整来源/范围/源码哈希见`pro-partial-identity-review-2026-09-25.md`。没有修改参赛runtime或重新封包，最新待测包仍b49aee2。
