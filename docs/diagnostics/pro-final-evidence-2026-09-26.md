# c3887cd Pro 正式结果与完整生成证据

核验时间：2026-09-25 16:35—16:41 UTC（北京时间9月26日00:35—00:41）。本队运行[359dd7e72ca7](https://arc-bench.com/runs/359dd7e72ca7)，保存快照 `Langqi Forge c3887cd - Pro comparison`，页面提交时间2026/9/25 14:38:41，编码deepseek-v4-pro、视觉deepseek-v4-flash-vision-exp。

## 官方结果，不是内部自测

[正式GitHub单项榜](https://arc-bench.com/competition?competition=hackathon&task=github)，筛选Official Hackathon / GitHub / 全部模型：bugtakue **第3名，8.54分、11.0%通过率、¥15.5977**，共29项。该任务为100个测试，即11/100；榜单提交模型、时间与此快照一致。

该时点[正式综合榜](https://arc-bench.com/competition?competition=hackathon)全部任务/全部模型仍是旧Flash双项快照：bugtakue第19/24、0.00分、0.0%、¥2.3829、提交时间05:22:11。第三名29.17分。**单项第三不构成综合前三目标完成。** 不混入其他提交的Sheet成绩，也不从模型名推断竞争对手用了什么编程产品。

正式赛详情页余额已核验为¥451.67，这是GitHub结算后、下方Sheet开始前的余额，不是未来最终余额。

## 下载与封印

之前生成结束后的打包请求长时间显示Packaging，后续按钮恢复且本机仍无新文件；工作区此时已从临时ZIP变成`factory26-evidence.zip`。在该状态下重新请求一次正常project.zip下载，得到：

- 本机原件：`/Users/zerongliu/Downloads/359dd7e72ca7-template (2).zip`。
- 归档：`dist/official-evidence/359dd7e72ca7/project-final-generation.zip`，44成员、6,190,876字节，SHA `d22d79bd0dec34241fb8abfc3c9919f09397c73480f9d37edac492a55dd1ca09`。
- 只读取/提取外层中的`template/factory26-evidence.zip`；**不读取评分期应用数据或隐藏测试**。外层是评分开始后的下载，不把整个项目包误称为纯生成期快照。
- 内层归档：同目录`factory26-evidence.zip`，2,908,536字节，SHA `af5845802b7856f600cba269cf2a7b4f2f9a547c6da5e3e4082a00a54e082f0b`。
- 内层精确三个成员：`production-trace.jsonl`、`harness-report.json`、`evidence-manifest.json`；ZIP CRC、连续sequence、完整v2哈希链、逐行及报告脱敏检查全部通过。
- 806行，12,136,348字节，轨迹SHA `69e1a573ab6f4489a2532cd581823fad605b4d160f68dd03ed8307aac898c062`，链头 `473c955b787a7c08d769a4fc55b4d510127924cb968f135fb1a4c35900f2ded4`。
- 报告SHA `2fde2bcc0a62d93b3c2be294297175eba84b30c1503f9c73dfb982d80361e8bc`；清单的行数、字节、轨迹/报告SHA和链头均逐项吻合。
- 生成run_id `3e4721f3-dc0e-4d66-9e5c-9b4ecd1e3e19`，源码`c3887cd34403666e9b3b6189b9487cbfeaf35e78`，合同SHA `db821686a7556fb75bb1fd33a24181ebe09912a0ab6ef09777302322b91e3cd1`。不是本地a31cfa9候选。

## 生成终态与限制

报告`local-contract-partial`，5655.012秒；内部已实现4/47：REQ-1-1-1、REQ-1-1-2、REQ-1-1-3、REQ-2-1-1。它与11/100官方测试不是同一个分母。

106个正常编码响应、116次HTTP尝试；报告编码输入2,363,938、输出248,053 Token，视觉7次、输入7,070、输出1,126 Token。不能把无法观察到的超时请求用量当零，也不能拿这些Token自行替代平台人民币账单。报告manual_interventions=0只针对上传智能体的生成执行；本机独立产物检查另有记录，不能据此说整个备赛没有人工分析。

停止原因已由封印轨迹确认，而非旧stdout猜测：request107第一次99.508秒后HTTP502；第二次240.119秒、第三次240.154秒均TimeoutError。seq799—802打开既有模型故障断路器、放弃未验证候选，未再执行其余需求；没有耗尽3.6M输入预算，也没有证明网络/模型哪一层是根因。seq803—805最后重放3个已存行为胶囊并完成结构、语法、构建、启动检查，seq806正常记录部分完成。不是全部需求成功。

独立组织检查所发现的“登录后Workspace无应用内导航入口”仍是已知具体缺口，见`pro-partial-org-review-2026-09-26.md`；不能因为单项排名上升而忽略它。此处未修改生成物、运行时或放宽验证。

## 同快照Sheet串行启动

GitHub已有结算后，在Sheet单任务页确认最新保存名、Pro模型、14:38:41时间完全一致且“当前没有正在进行的任务运行”，仅点击一次“运行最新提交”。没有创建新快照、重新上传、批量运行或注入个人Key。

新运行：[40f69fc30bd3](https://arc-bench.com/runs/40f69fc30bd3)。21秒现场显示42条需求、100个场景，环境预检通过、依赖安装完成、Stage2 Launching generation agent，Stage3 pending。该运行尚无成绩或成本。先取得同版本双项证据，再决定下一轮候选；本地a31cfa9包继续保持未上传，不把它与这一版成绩混算。

3m38s首次日志刷新核验：seq9首批工作簿浏览、创建、重命名、CSV导入已开始；request1在3.342秒正常返回（输入11,445/输出106），两张官方参考图的视觉读取成功，最新seq29为request3第一尝试。尚无功能晋升或官方评分，短工具响应不能代表完整代码已经成功生成。只保留该精确Sheet页继续跟踪，不再重复运行GitHub。
