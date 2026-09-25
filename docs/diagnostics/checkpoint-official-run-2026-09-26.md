# 收尾空间候选正式运行

## 终态补充（2026-09-25 18:09 UTC核验）

18:16 UTC历史卡补充：本次官方显示0.00分、0.0%、test pass (0/0)、15m44s、42632 Token、费用￥0.6018；Sheet未运行。0/0是生成失败未执行GUI，不改写成0/100。启动下版前余额￥441.64。综合榜仍取此前同快照完成双项的c3887cd，第9、6.55分、8.5%、￥25.0273。

重载同一运行后出现View leaderboard、固定15m44s、生成命令exit1，已结束，不再等待或启动同版Sheet。req3第三次尝试240.113秒再次超时，seq29—34记录失败/熔断；首批changed_files为空、0探针、0晋升，最终failed。此前“GitHub后同版Sheet”计划被此次无产出失败撤销，避免复制已知失败继续耗费额度。既有c3887cd综合结果不变；本次没有有效的新GUI成绩。

正常下载原件`/Users/zerongliu/Downloads/b15311c6f690-template.zip`，归档`dist/official-evidence/b15311c6f690/project-final-generation.zip`，42成员/3377549字节，SHA `3d9212cfc0502d5030953cb8b844decfc82bc062fd67d06c872061e56ee88539`。只提取内层生成证据包，未读取外层应用数据或隐藏测试；外层不作为纯生成时刻证明。

内层`factory26-evidence.zip`75794字节，SHA `227a645c76cbc4c53a8b5ba3a3383e065781ec51b19cb6b82c6f467f8a177254`，精确三个证据成员。CRC、34行连续v2哈希链、逐行/报告脱敏、清单SHA/大小/行数/source/run_id全部核验通过。

- 轨迹308964字节，SHA `39031b8480e3f6d336604adf960d5d72d66443aa7fe3d468174db2ab5c3b7b38`，链头 `c39a4b653191893c5d8fad58f441605814dbeeb6c974674bbfc571db33768e53`。
- 报告SHA `fc7b10b2bdb9bd4d9315db5064c047e1b890c8e97725bfa82a761073a4fb95f0`，run_id `f96ee1e1-53e0-4ccd-98c5-3cb180fefbbf`。
- 源码/合同与下方d9上传身份一致；943.834秒，2成功响应/5 HTTP尝试，可观测输入25196/输出17436，视觉0，人工运行内干预0。超时不可观测用量不按0计算；人民币成本未在本页核验。
- 三个编码请求均真实发送reasoning_effort=low、max_tokens=8192。request2成功215.816秒，只调用list_files；随后三次超时。这不证明代理忽略参数或证明收尾优化无效：失败发生在该优化有机会发挥作用前。

下一候选在独立分支从d9单变量对照编码thinking=disabled；不合并b443源码保留优化，不自动重试失败远端任务，不放宽门禁。见`nonthinking-comparison-2026-09-26.md`。

2026-09-25 17:47—17:49 UTC现场。先确认c3887cd GitHub与Sheet均结算、综合第9/24（6.55分、17/200、￥25.0273），再保存下一版，不并行评测。

## 提交身份

- 源码`d9c86b4819e132dd8f37d4c859b837b6a1de149a`，不是后续仅文档提交169313e。
- ZIP `dist/langqi-forge-turn-checkpoint.zip`，21成员/190319字节，上传前重算SHA `de73d844501606960e9ab449dcf69fcfbd2a4165b549335e0f268b53172260cc`一致。
- 合同SHA `42f3b29b14ce799840765a3566f6f0a8b81b2d10108592c313b1c1b08172c965`；独立解包/28项检查以及源码全量318项（315通过/3环境跳过）见turn-checkpoint-reserve-2026-09-26.md。
- 正常原生文件选择器上传，页面确认上传成功；Python、名称`Langqi Forge d9c86b4 - completion checkpoint`，比赛额度勾选，编码deepseek-v4-pro、视觉deepseek-v4-flash-vision-exp，网关https://api.arc-bench.com/v1。没有个人Key。
- 保存后History(14)，最新提交时间17:47:29。额度￥442.24是启动前余额，不当最终成本。

本版包含此前候选的新流程修复后重验、压缩审计容量、write_file哈希前置条件、入口连续性，以及本次收尾控制空间修订。相对正式c3887cd不止一个变量，不把成绩变化单独归功于收尾提醒。

## 单项启动

GitHub任务页实际显示最新名称/Pro/17:47:29及“当前没有正在进行的任务运行”。第一次按不含图标的精确按钮名定位失败、0匹配，没有点击；重新读取可访问名称后，只点击一次`play-circle 运行最新提交`。

新正式运行[b15311c6f690](https://arc-bench.com/runs/b15311c6f690)。3秒现场已确认运行名、GitHub任务、容器创建/启动、Stage2 Running uploaded agent、Stage3 pending。未并行Sheet、未取消任何任务、未重复点击。尚无真实模型完成响应、需求晋升、官方分数或成本。

下一步跟踪同一运行；GitHub完成后用同一保存快照串行运行Sheet，不混用不同源码成绩。此时不改超时后的全局停止策略：当前逻辑还保护认证、额度和协议错误，若后续设计一次性新会话恢复，必须按明确错误类别、有界尝试、既有预算与隔离门测试，不能靠错误字符串把所有网关失败重试。

2m03s首段日志已确认首批注册/登录开始；request1在3.336秒成功返回（输入11273/输出106），read_files成功，seq18 request2发出。环境预检通过。这里只证明真实模型/工具链启动，不是业务功能通过或得分。
