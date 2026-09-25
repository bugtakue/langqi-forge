# 8f30652 正式串行运行

## 精确制品与保存身份

- 源码：`8f306526796b95ad5b9233c98c02b05338a1c642`，运行时冻结不热改。
- ZIP：`dist/langqi-forge-completion-control.zip`，21成员、194348字节，SHA256 `645f9935a02cd872dfa582bcd5bcfbf33e0a9e581e4c0f47b561c48539a28e39`。
- 合同：`7fc744f0a1a2108b96a36f9f415818f5d440dacfee501e0a97232333c05a2510`。
- 上传前重算SHA、核对干净工作树；既有全量355项/352通过/3环境跳过与独立解包50项通过，详见completion-entry-policy-2026-09-26.md。不是官方分数。
- 正式赛保存名：`Langqi Forge 8f30652 - verified completion`，History16，页面保存时间2026/9/25 19:38:38（页面未标时区）。
- Python，`https://api.arc-bench.com/v1`，勾选比赛额度，未输入个人Key。编码`deepseek-v4-pro`、视觉`deepseek-v4-flash-vision-exp`。
- 前置余额￥422.68，不代表在途费用已扣除。

## 启动与早期证据

仅在fb84f4e Sheet正式结束、双项5/200结算后上传。GitHub单题页确认最新保存身份、Pro和没有正在运行任务，只点一次运行最新提交；没有点双题批量运行。

新运行：[a2b7ba164c06](https://arc-bench.com/runs/a2b7ba164c06)。3m36s现场Stage1预检完成、依赖安装成功、Stage2 Running agent、Stage3 Evaluation pending。

- 19:39:17 UTC：run_started，seq2。
- 19:39:18 UTC：第一批注册/登录开始，seq9；implementation会话seq11。
- 第一模型请求seq13正常返回seq14，3.182秒，prompt11640/completion111 Token、finish_reason tool_calls。
- seq16 read_files成功；19:39:22 UTC seq18第二请求在途，单次请求超时配置240秒、原最多3尝试。

以上证明新包已实际启动并调用模型，不证明完成了注册/登录、控件状态检查生效、收尾窗口已救回功能或任何官方GUI通过率。stdout是精简事件，开关的精确取值待封印轨迹核验。仍未启动Sheet；等待同一运行，不因观察超时取消、重开或并行。

### 6m04s接续

北京时间03:45:18刷新同一stdout，第二请求已于19:42:59 UTC正常返回，217.534秒、prompt14295/completion17054 Token；seq21/23两次list_files成功。seq24按原软限压缩上下文122431→47384字符，保留8/8完整源码文件共4369字节，soft_limit_exceeded=false；seq26第三请求在途。该长请求没有超时，不手动重启；没有已观察到的源码写入、功能晋升或官方分数。Token及耗时是真实开销证据，不以正常返回声称效率改善。

## 比较边界与当前排名

本候选合并完整源码保留、失败现场回传、控件状态断言及入口显式启用的冻结收尾，并使用bounded编码策略。不是相对fb84f4e的单变量实验，不能把未来变化全部归因于某一个机制。

2026-09-25 19:43 UTC附近刷新正式Hackathon/全部任务/全部模型：旧c3887cd仍第10/26、17/200（8.5%）、6.55分、￥25.0273。前三分别55.27、36.34、29.17分；第三名29.5%、￥24.9800。新8f运行暂无官方分数/费用，不把单任务名次或本地回归当目标完成。Goal保持active。

## 8m31s活任务核验

北京时间03:47:25刷新同一stdout：19:46:59 UTC seq27为request3首尝试240.122秒TimeoutError；19:47:00 seq28为原策略第二尝试，最多3次不变。该任务仍Stage2、Stage3 pending，不因一次请求失败判整任务终止；无手工重开/取消/并行，也没有已观察到的代码写入、需求晋升或新成绩。

只读核查agent.py：压缩保留messages[:2]，初始预装完整需求不会再列入retained_specification_ids，故seq24空列表本身不是丢需求证据。重新执行test_prefilled_specifications、test_retained_specifications、test_compaction_protocol共18项，0.100秒全通过；这是协议核查，不是实际生成质量或控件浏览器测试。未修改运行时。本轮按confirmed-live句柄核验等待，非阻塞；下一步仍读取同一a2b7ba164c06。
