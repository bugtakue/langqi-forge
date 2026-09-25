# c3887cd Pro Sheet 完整生成证据

## 官方结算补充（2026-09-25 17:44—17:47 UTC现场）

刷新运行页后出现View leaderboard、运行控制消失，显示固定Duration 47m46s；此前页面在本地持续计时、旧Evaluation in progress未自动清除。**以后评分阶段须适时重载同一运行页核验，不把本地计时器当服务器仍在运行的证据。** 未因旧界面状态取消或重启。

- [Sheet正式单项榜](https://arc-bench.com/competition?competition=hackathon&task=sheet)：本队第13，4.56分、6.0%=6/100、￥9.4297、Pro、同一提交14:38:41。
- [正式综合榜](https://arc-bench.com/competition?competition=hackathon)，筛选Agentic Software Factory Hackathon/全部任务/全部模型：本队**第9/24，6.55分、8.5%=17/200、￥25.0273**，Pro、同一提交14:38:41。GitHub同快照11/100与Sheet6/100对应17/200。
- 前三仍55.27/36.34/29.17；综合前三目标未完成。不是把GitHub单项第三代作完成。
- 竞赛详情余额￥442.24，为下一轮启动前额度。平台显示的单项费15.5977+9.4297与综合25.0273有0.0001显示舍入差，本页保留各页面原值，不擅自修正账单。

下方“官方评分中”保留为取证时点，不再是当前等待事项；本次证据已归档、结果已结算。

正式运行[40f69fc30bd3](https://arc-bench.com/runs/40f69fc30bd3)，与GitHub359dd7e72ca7使用同一保存快照c3887cd / Pro。本文核验生成终态，不把内部7/24当成官方GUI通过率。53—55分钟现场Stage2完成、Stage3官方评分中，尚无本项最终账单或新综合名次。

## 制品及封印

正常文件页从临时ZIP变为factory26-evidence.zip后，只请求一次project.zip下载。

- 外层原件`/Users/zerongliu/Downloads/40f69fc30bd3-template (1).zip`；归档`dist/official-evidence/40f69fc30bd3/project-final-generation.zip`，26成员/2661296字节，SHA `a425c6a0a9bdd4070c2159dbca426f1f36a399a4904d37a5e4e529d05ec5576b`。
- 外层包含评分开始后的应用，**不能称整个包为纯生成期快照**。只读取/提取`template/factory26-evidence.zip`，未读取评分期业务数据、隐藏测试或他队内容。
- 内层同目录`factory26-evidence.zip`，2036960字节，SHA `b39f81252ad30fe7c43e752c3414e1fcfbf0c1106696dea835decc30c072c9e0`。
- 精确三成员production-trace.jsonl/harness-report.json/evidence-manifest.json，CRC通过；562行连续sequence、完整v2哈希链、逐行及报告脱敏检查通过。
- 轨迹8423114字节，SHA `e6155a72b5d2689f5c204f8965c5826f76a767def78081be28b96de616421ba8`；链头 `9085601c2c8b9359d7284381de4a00a0bd209daeca9993ce4f7a12afabe8693b`。
- 报告SHA `9b5e97328221b4c7cf1dcfaf387b8b71ec0b182e9eb02041190fd1ef2494dec4`；清单行数、大小、两项SHA、链头及source/run_id逐项一致。
- run_id `79b92cc7-1a3b-4089-ad92-ae812db813e5`；源码`c3887cd34403666e9b3b6189b9487cbfeaf35e78`，合同SHA `db821686a7556fb75bb1fd33a24181ebe09912a0ab6ef09777302322b91e3cd1`。不含后续本地d9c86b4候选修订。

## 最终报告

状态local-contract-partial，2864.742秒。内部实现7/24（工作簿浏览/新建/重命名、CSV导入/导出、工作表重命名/添加），其余17项未完成。

77个成功编码响应，82次HTTP尝试，报告输入1776519/输出118795 Token；视觉3次、输入2096/输出538。超时请求不可观测的用量不按零推算，人民币只取官方结算。manual_interventions=0只指上传智能体此次运行，不代表备赛无人分析。

request78连续240.151/240.135/240.090秒TimeoutError，seq555—558候选失败、熔断并跳过后续。全部失败尝试累计1200.636秒，约占生成时长41.91%；这不是可保证省下的成本或根因判断。没有耗尽3.6M输入/1.5M输出/600响应预算。seq559—560最终重放两条已存流程均通过，覆盖范围仍标not_assessed，不能称全需求测试通过。

## 第三批纯读取循环：从完整轨迹确认

seq248—392，20回合、0写入/探针、未晋升；read_file26/read_files1/read_requirement_spec3。前后端和CSS的全部read_file结果各自只有一个SHA，排除这段循环由文件持续变化引起。

重复完整同范围读取包括backend/server.mjs 180—385共3次、385—425共2次，frontend/src/app.js 385—492共2次，另有交叠范围。15次压缩频繁接近96K；seq295当前源码快照仅123字节（8文件各15—16字节），但已读页仍占10131字节；seq347快照16741+已读页14338字节，核心后端/前端仍分别截断至4692/4691字节，而文件真实为12208/13305字节。

seq295后模型请求的序列化组成：系统5914、初始任务32694、checkpoint5424、保留原始需求9937、已读页11170、assistant/provider上下文16309、两项工具结果5743/8608字符（单消息计数含独立列表外壳，不直接加总作总量）。不能删除provider字段来假装解决协议；该字段仅按长度分析，不公开其内容。

seq348/361/370/377/390收尾提醒被省略，其中390是最终回合；其余4次发生在还会继续调用同批模型时。与GitHub完整轨迹发现的提醒空间缺口一致，已本地修订d9c86b4，但这只保护控制提醒，不宣称消除了源码片段轮换/全部重复读取。

当前证据支持“同版本源码在紧张上下文中持续补读”这一具体诊断。尚未通过模型A/B证明原因占比，也不能把所有读取都记成浪费。后续应比较同快照双项正式结果和重复读取/完成率，而不是增加工具、增大上下文或预先宣称名次改善。
