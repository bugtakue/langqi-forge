# 2026-09-25 首次正式赛上传与评测

## 授权及精确提交

队长明确授权“可以啊，你可以先尝试着上传看看多少名”。本次上传当前候选并使用比赛额度启动两道正式赛任务；尚无最终分数时，不把排队或运行中状态记为成绩。

- 账号及平台技术队名：`bugtakue`；GOSIM 报名队名：琅岐岛民。
- 提交名称：`Langqi Forge b958be3 - first evaluation`。
- 页面保存时间：`2026/9/25 05:22:11`（页面显示值，未标时区）。
- ZIP：`dist/langqi-forge-qualifier.zip`，SHA-256 `6fbc9a7a5b8dec8513ee437bf93154b507afb8a84b403373b4f796e521bb4115`。
- 来源修订：`b958be3733b19df571422ec4d3496ca35c24fc54`；17 个白名单文件。上传前确认工作树干净；上一轮 141 项测试中 138 通过、3 项浏览器环境跳过，ZIP 解压校验通过。
- 编码模型：`deepseek-v4-flash`；视觉模型：`deepseek-v4-flash-vision-exp`；平台 Base URL `https://api.arc-bench.com/v1`。
- 已勾选“使用比赛额度评测”；使用平台临时 Key，上传前剩余额度 ¥500。未填入个人百炼 Key。
- 快照保存后 History 从 0 变为 1；随后点击 `Run 2 remaining tasks`，页面返回 `Started 2 runs.`。未重复启动。

## 官方运行链接

| 任务 | 运行 | 初始状态 |
|---|---|---|
| GitHub Collaboration Platform Core Requirements | [09725f3b57ae](https://arc-bench.com/runs/09725f3b57ae) | 环境预检通过、依赖安装通过、Running agent；65 个需求节点，100 个场景 |
| Core Requirements for an Online Spreadsheet Data Workspace | [3fbdb49ce00a](https://arc-bench.com/runs/3fbdb49ce00a) | 环境预检通过、依赖安装通过、Running agent；42 个需求节点，100 个场景 |

上表初始状态于 2026-09-25 05:23 UTC 左右从登录后页面核实；最终结果见下节。

## 已返回的表格任务结果

- 运行 `3fbdb49ce00a` 在生成阶段以退出码 1 结束，页面时长 `11m 29s`。
- 标准输出：`[factory26] failed: no requirement batch completed; refusing empty scaffold`，随后记录 `failed; model_requests=40`。
- 提交汇总显示该任务得分 `0.00`、测试通过率 `0.0%`、Features `0.0%`、`393,293` Tokens、成本 `0.9667 CNY`；剩余额度显示 `¥499.03`。这些是平台字段，不推算为 100 条 GUI 全部执行过。
- 失败发生在应用生成阶段；平台没有给出逐批工具/模型失败详情。本次下载的 GitHub 生成中项目快照不含 `.arc` 诊断目录，标准输出只打印总失败原因，目前不能据此确定具体根因。
- 同时刻 GitHub 任务 `09725f3b57ae` 仍为 `running`。汇总里的临时 `0.00` 不代表两题已全部完成或本队已有最终排名。

## 两题结束后的官方结果

2026-09-25 05:37 UTC 左右，两题都已结束；正式榜筛选 `hackathon`、全部任务、全部模型，搜索 `bugtakue` 返回 **第 14 名，0.00 分，0.0% 测试通过率，¥2.3829 模型开销**。这是当时的榜单快照，不能用这个零分位次推断晋级资格。

| 任务 | 平台结果 | 模型响应次数 | Tokens | 模型开销 | 页面时长 |
|---|---|---:|---:|---:|---|
| GitHub | 生成退出码 1；0.00 分；0.0% | 93 | 909,626 | ¥1.4162 | 14m 13s |
| 在线表格 | 生成退出码 1；0.00 分；0.0% | 40 | 393,293 | ¥0.9667 | 11m 29s |

两题标准输出均为 `no requirement batch completed; refusing empty scaffold`。这表明没有候选批次通过当前智能体的完成与校验流程；不能凭总失败消息断言是模型、提示词、工具合同还是校验规则的某一个具体问题。平台汇总为 `test pass (0/0)`，没有独立 GUI 有效执行证据；不能写成“200 项已全部执行且失败”。模型次数来自智能体 stdout，不等于平台 HTTP 请求计费次数。

提交汇总显示成本 **2.3829 CNY**、剩余额度 **¥497.62**、总运行时间 **25m 42s**（两个任务时长相加；本次两题同时启动）。本轮仅上传一个快照，各任务启动一次，没有重试或重复提交。

下一步应先补足平台可见的逐批失败诊断，定位真实模型首次执行失败的原因，再修复和复验。当前包的本地单测和合成协议成绩不能作为其真实生成能力的证明。

## 上传前的榜单参照

正式赛筛选为 `hackathon`；当时显示 17 条成绩，本队尚无记录。领先者 Iris 为 36.34 分、40.5% 通过率、¥55.7107 模型开销。该快照不是当前提交的成绩，也不代表最终晋级门槛。

官方榜单：[Agentic Software Factory Hackathon](https://arc-bench.com/competition?competition=hackathon)。
