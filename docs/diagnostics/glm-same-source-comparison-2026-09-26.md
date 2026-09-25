# 8f30652 同源码GLM通道对照

## 选择依据与固定变量

Pro运行a2b7ba164c06在第三请求超时后HTTP400失败，零业务写入，0/0、￥0.5966，完整封印见completion-control-official-run-2026-09-26.md。不能由此检验源码保留、控件断言或收尾的业务收益。不重复该失败运行，也不继续其Sheet。

下一正式快照保持同一个ZIP、提示词、预算、工具、门禁、视觉模型和赛事网关，仅将编码模型切换`glm-5.3-flash`。该模型在现场综合榜已有其他队伍完成记录，说明是有正式使用先例的候选，不证明适合本智能体或足以夺前三。源码内既有DeepSeek专属字段白名单不会给GLM注入reasoning_effort，未额外改代码或临时降级。

- 源码`8f306526796b95ad5b9233c98c02b05338a1c642`。
- ZIP `dist/langqi-forge-completion-control.zip`，21成员/194348字节；上传前重算SHA `645f9935a02cd872dfa582bcd5bcfbf33e0a9e581e4c0f47b561c48539a28e39`。
- 合同`7fc744f0a1a2108b96a36f9f415818f5d440dacfee501e0a97232333c05a2510`。
- 保存名`Langqi Forge 8f30652 - GLM comparison`，History17，页面时间2026/9/25 19:59:42（未标时区）。
- Python；编码GLM，视觉`deepseek-v4-flash-vision-exp`；`https://api.arc-bench.com/v1`；比赛额度明确勾选，无个人Key，前置余额￥422.09。

## 保存核验与串行边界

首次保存未确认成功，独立新页读取仍History16，无新记录；核对原表单/包/额度后只重试保存一次，随后明确History17、上述精确名称/GLM/时间、两题均未运行。不是反复创建运行。原生文件选择器最初受侧栏滚动位置影响未打开，滚动到可见区域后完成一次成功上传；没有改扩展权限或采用网页内部接口。

仅进入GitHub单题，不点Run 2 remaining tasks。单题页确认最新保存名称、GLM、19:59:42及当前没有正在进行任务，再只点击一次运行最新提交；先显示正在创建运行，随后真实跳转[2d8bb92545c0](https://arc-bench.com/runs/2d8bb92545c0)。22s现场预检/依赖完成、Stage2生成、Stage3 pending，精确名称/任务匹配；没有取消其他运行或并行Sheet。

目前尚未确认首个模型返回、源码写入、需求晋升或新GUI分数。后续继续观察同一任务；即便通道恢复，也不能倒推Pro的400已定因。保存、启动与提分分开记录。

## 首段真实模型与工具进展

北京时间04:03:11刷新stdout，2m31s再次读取同一页面：21次model_response、0次model_error、10次changed=true的写入/替换。20:02:49 UTC seq105 quick构建/语法/作用域等通过，证明当前代码已能构建，不证明业务完整。

随后三次browser_probe参数被安全拒绝：seq111和116提示steps必须为至多16个动作的数组，seq121提示第8步unsupported action。暂未取得完整调用参数，不能区分数组类型与长度错误或猜测第8步具体动作。原探针边界没有被放宽；seq124/125第21请求已返回工具调用，后续探针结果仍待观察，不宣称收尾成功或首批已晋升。未出现implementation_batch_finished，Stage2仍在途、Stage3 pending。

新通道已实际越过Pro失败前的两次响应，不能据单次运行确定Pro根因、模型普遍优劣或正式分数。下一步沿同一2d8bb92545c0读取收尾/批次结果，待完整封印后分析具体参数错误，避免根据精简stdout臆改接口。
