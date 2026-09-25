# Langqi Forge · Factory26 初赛候选

> 当前目标（2026-09-25）：以同一参赛快照完成两题并进入正式综合榜前三，尚未达到。队长确认终止反复撞到已知缺陷的旧版后，已启动 `b53d9a9` 的 [GitHub 正式运行](https://arc-bench.com/runs/de30d58e3116)，仍在生成阶段，Sheet 未开始。此版包含需求保留、工具提示修订与脱敏证据导出。旧版 `1b3419d` 终态 cancelled，不能当作完整 GUI 评测；取消费用须以平台计量为准。实时接续依据见[前三持续台账](docs/TOP3_CAMPAIGN_2026-09-25.md)，历史成本与失败记录见[改进记录](docs/IMPROVEMENT_REVIEW_2026-09-25.md)。本地测试不代表官方通过率。

琅岐岛民的 ARC-Bench 软件生成智能体。本分支采用**通用、模型驱动**的正式参赛路径：读取比赛提供的需求，生成可部署的前后端，留下可核验的生产轨迹。它不是循济产品本体。

本地强化候选新增“行为回归胶囊”：将当前版本成功执行的操作流程固化，后续批次抽查、修复后及最终验收全量重放已存流程，保护旧功能免于被新改动破坏。正常回放不增加大模型调用；未覆盖的流程仍明确未知。此强化**尚未上传或取得官方成绩**，详见[运行合同](docs/QUALIFIER_OPERATIONS.md)。

另已修复源码快照分配浪费：在原有总上下文上限内优先保留完整小文件，将剩余容量分给大文件；滚动源码快照可保留至多 36,000 字节，验收审计仍为 12,000 字节。真实在途产物的八文件已用于只读复现，完整回归 201 项 / 198 通过 / 3 浏览器环境跳过。是否降低实际成本、提高得分仍未验证，当前在途版本不含此修订。

最新本地协议修订还关闭了两项独立复现的问题：旧审计失效后压缩造成孤立工具结果，以及验收压缩丢弃尚未交付模型的读取正文。新增调用配对/原样投递回归后，完整合跑 205 项 / 202 通过 / 3 浏览器环境跳过。仍未上传或取得官方新分数，旧 a21ec28 本地包不再用于下一轮，候选身份以持续台账为准。

> 状态：2026-09-25 经队长授权，当前候选已上传 ARC-Bench 并结束首次两题运行。**两题均在生成阶段失败，官方得分 0.00，榜单当时为第 14 名，费用 ¥2.3829；未确认晋级。**精确版本、运行链接和证据边界见[首次正式赛记录](docs/OFFICIAL_FIRST_RUN_2026-09-25.md)。此前 GitHub/Spreadsheet 公开样题的 304/304 属于旧版题目专用能力内核，不得作为本版成绩或合规证明。旧版源码与证据可从 Git 历史查阅，但不会进入本版参赛 ZIP。

> 账号与榜单提示（2026-09-25 核对）：ARC-Bench 队长账号及平台技术队名为 `bugtakue`，参赛确认已完成；GOSIM 报名队名为“琅岐岛民”。首次提交 `Langqi Forge b958be3 - first evaluation` 使用比赛额度运行 GitHub 与在线表格两题。ARC-Bench-Lite 榜单是**公开赛**，本次应查看 [hackathon 正式赛榜](https://arc-bench.com/competition?competition=hackathon)。运行中的快照不能计作已有官方排名。

## 与当前规则的对应

- ZIP 根目录有 `main.py` 和 `requirements.txt`，入口遵循 `python3 main.py <requirements_dir> --output-dir <output_dir>`。
- 运行后必须生成 `frontend/`、`backend/`，分别支持 `npm run build`、`npm start`；后端按 `PORT` 监听并提供 `/api/health`。不依赖只在本地模拟器支持的 `deploy.sh`。
- 打包采用明确文件白名单。提交包不含 GitHub、Spreadsheet、BookStack、Keep 的页面、API、种子或业务实现；`generic_scaffold.py` 仅提供空前端、静态资源服务、健康检查及通用 HTTP/原子 JSON 存储辅助函数。
- 正常生成路径必须调用平台注入的 OpenAI-compatible 模型网关。模型缺失、没有任何有效实现或最终构建/启动失败均返回非零；不会把空 scaffold 冒充完成品。多需求批次失败时先丢弃未验证改动，默认最多再按前后两半各尝试一次；每半批仍须自行通过校验才晋升，依赖最终失败项的需求不继续尝试。若仍有失败，已验证的独立实现可标为 `local-contract-partial` 交给独立 GUI 评测，而不伪称全部完成。拆批会增加模型调用，真实得分收益仍待评测。
- 通过官方 `arcbench-runtime` SDK 上报运行状态、需求实现状态、需求树追溯表及每批 Git 提交；不手写平台事件。独立哈希链仍保留 Prompt、工具调用与模型迭代。通用构建通过不等于需求的 GUI 测试通过，因此不会虚报逐需求 `test_passed`。
- 旧成绩不是本版性能证据。任何真实通过率以主办方独立 GUI 评测为准。
- 截至 2026-09-25，[ARC-Bench 正式赛公开列表](https://arc-bench.com/competition)显示两项任务、200 个测试；队伍已确认，已读取正式任务正文并进行首轮运行。BookStack/Keep 的 66 条公开基准用例是练习材料，不能等同正式赛题或 200 个测试。此前读取的平台「排行榜计分方式」以**同一份提交**完成两个任务后的综合 GUI 通过率和人民币模型开销计算：合理开销为 `0.4 × 测试总数 × 通过率百分数 ÷ 100`，最低开销按 ¥0.10、开销比率限制在 0.01–100；低于或等于合理开销时奖励指数为 0.1，高于时惩罚指数为 0.2。若正式赛仍为 200 项测试，合理开销相当于每 1 个百分点 ¥0.8，**不同于**队长收到的 2026-09-20《参赛须知》所列 ¥1.2。平台按得分、通过率、较低开销、较早提交时间排序；旧 PDF 的单任务最长 48 小时仍待正式赛内复核。规则版本与差异见[参赛运行说明](docs/QUALIFIER_OPERATIONS.md)及[本地验证记录](docs/QUALIFIER_EVIDENCE_2026-09-24.md)，以评测时平台规则为准。
- 设置 `VISUAL_MODEL` 后，智能体可按需读取需求明确引用的 `reference/` 截图，通过视觉模型提取布局线索；默认复用已配置的 `OPENAI_API_KEY` / `OPENAI_BASE_URL`，若同时提供完整的 `VISUAL_API_KEY` / `VISUAL_BASE_URL` 则优先走独立视觉网关。图片只发往选定的模型网关，不写入生产轨迹或生成应用；未指定视觉模型、显式视觉凭证只填一半或共享网关不完整时不启用此工具。视觉模型是否可调用及其费用仍须以真实网关验证。

主办方本地模拟器：[hackathon-local-simulation](https://github.com/code-philia/hackathon-local-simulation)。报名与项目提交由队长操作；此处的打包命令**不会上传**。

## 工作流

```text
requirements.yaml
  → 校验并按依赖排序原子需求，继承必要的父级产品上下文
  → 从当次需求编译有界的全局架构目录（名称与依赖），每批仅把当前需求当作实现任务
  → 创建与题目无关的可运行前后端
  → 按小批次在私有副本交给 CodingAgent，通过模型工具调用读取、改写、校验源码；成功才晋升
  → 将已编辑源码路径作为有界、非可信交接索引传给下一批，供其按需读取已有模块
  → 每批通过 quick 交互策略、JavaScript 语法和新鲜构建产物校验，并作一次模型验收审计
  → 可对本地生成应用执行有界浏览器交互与可见文本断言；失败后改码须重验
  → 多需求批次失败先丢弃未验证代码，可有界拆成两个半批重试；最终失败项阻断其依赖项，保留独立已验证功能
  → 全量构建、启动、健康检查；失败时在私有副本限轮修复，通过后才晋升
  → 官方 SDK 记录节点状态、追溯表和 Git 提交历史
  → .arc/production-trace.jsonl + harness-report.json
  → 外部独立 GUI 评测（本智能体不自称已通过）
```

工具仅允许读项目文件、查询文本、修改 `frontend/` / `backend/`、运行安全校验，以及在本地生成应用上做有界浏览器探测。浏览器探测不能读取隐藏测试或访问外部网站；覆写文件需要已观察的 SHA-256，限制写入文件数和字节数；模型看不到环境密钥。生产轨迹记录 Prompt、模型请求与响应、工具参数与结果、批次、校验和人工干预点，并对敏感字段脱敏、逐行链接哈希。

具体 Prompt、工具、循环及证据位置见 [参赛运行说明](docs/QUALIFIER_OPERATIONS.md) 和 [本地验证记录](docs/QUALIFIER_EVIDENCE_2026-09-24.md)。

队长准备填写表单前先看[提交交接卡](docs/SUBMISSION_HANDOFF_2026-09-25.md)：它区分当前本地候选与仍在旧提交的公开 GitHub `main`，并列出真实模型成绩、账号和 Demo 等尚缺项；该卡本身不执行上传或提交。

## 本地运行

需要 Python 3.10+、Node.js/npm、Chromium 与可用的 OpenAI-compatible 模型服务；主办方 Runner 自带与浏览器二进制匹配的 Playwright，参赛包不覆盖其版本。本机独立运行时才单独安装 Playwright 与对应浏览器。**不要把密钥写入仓库或 ZIP。**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install playwright==1.57.0  # 仅本机独立运行；Runner 不执行本行
.venv/bin/python -m playwright install chromium
export OPENAI_API_KEY='...'
export OPENAI_BASE_URL='https://your-gateway.example/v1'
export MODEL='your-model'
# 可选：指定视觉模型后复用上面的 Key 与网关
export VISUAL_MODEL='your-vision-model'
# 如需不同视觉网关，以下两项必须同时提供
export VISUAL_API_KEY='...'
export VISUAL_BASE_URL='https://your-vision-gateway.example/v1'
.venv/bin/python main.py /absolute/path/to/requirements \
  --output-dir /absolute/path/to/generated-project
```

正式评测由平台注入模型 API Key，无需随 ZIP 上传个人 Key；本地公开练习仍需可用的练习 Key。本地没有密钥时只能跑单元/协议测试，不能宣称真实智能体成绩。失败拆批可用 `--salvage-splits 0` 或 `FACTORY26_SALVAGE_SPLITS=0` 关闭；默认至多增加两次模型会话/原始失败批次，不在成功批次上额外花费。模型网关持续不可用、认证失败或总预算耗尽会停止后续请求并保留此前已验证的独立实现；没有有效实现时仍失败退出。模型明确回复 `AUDIT BLOCKED:` 时直接结束当前尝试；连续三次无工具、无可接受进展也结束，避免白耗回合。固定响应夹具的浏览器结果只代表运行链路，不代表 BookStack/Keep 的通过率；详见本地验证记录。

本机为 ARM 架构，缓存的当前 amd64 Runner 在 QEMU 下仍无法完成 Chromium 预检。为排查生成物的公开 GUI 行为，可用[跨架构本地浏览器诊断](docs/HYBRID_PUBLIC_GUI.md)：在当前 amd64 基础镜像里生成应用，再用旧 arm64 浏览器镜像运行公开 Playwright 测试。此桥接只用于本地诊断，既不是当前完整 Runner，也没有正式/隐藏测试成绩。

```bash
.venv/bin/python -m unittest tests.test_qualifier tests.test_submission_bundle
```

工作区会产生：

- `frontend/`、`backend/`：真实生成的应用源码与启动文件；
- `.arc/compiled-plan.json`：需求批次与来源哈希；
- `.arc/production-trace.jsonl`：Prompt、模型、工具和迭代的脱敏哈希链；
- `.arc/harness-report.json`：本地构建/启动结果、模型调用次数和失败原因。
- `factory26-evidence.zip`：运行结束后导出的脱敏原轨迹、报告与哈希清单，位于输出根目录而非网页静态目录；成功/失败运行均导出。平台下载包含性仍须正式运行后核验，不能据本地合同测试宣称旧轨迹已取回。
- `local-contract-partial` 表示至少一批需求已实现、本地应用可构建启动，但报告列出的需求仍失败；它仅允许独立 GUI 测试获得可能的部分通过数，不是整题完成或官方分数。
- 报告中的 `model_requests` 是成功返回的模型请求数，`model_http_attempts` 包含重试；两者不能混作真实费用。HTTP 408/425/429/5xx 最多尝试 3 次；`Retry-After` 等待上限默认 60 秒，可用 `FACTORY26_MAX_RETRY_AFTER_SECONDS` 在 0–120 秒内调整。认证等非临时错误不重试。
- `.arc/runner-events.jsonl`、`.arc/traceability/`：由官方 SDK 写入的状态及追溯数据；工作区 Git 历史记录通用 scaffold 和生成批次。

## 打包（不上传）

在**干净且已提交的工作树**运行：

```bash
.venv/bin/python -m factory26_harness.submission_bundle \
  --output dist/langqi-forge-qualifier.zip
unzip -l dist/langqi-forge-qualifier.zip
```

打包器会拒绝脏树、软链接、越界路径和疑似密钥文件，并写入逐文件哈希清单。审核时必须检查 ZIP 中没有 `factory26_harness/templates/` 或旧 `cli.py`、`planner.py`、`capabilities.py`。

## 目前尚缺

1. 使用真实模型在官方 BookStack/Keep 公开练习上运行，记录通过率和真实开销；协议夹具测试不等于该结果。
2. 首轮两题均在生成阶段失败，未获得有效 GUI 通过结果；先补足平台可见的逐批失败诊断，定位根因，再修复并复验。该轮官方零分和费用已归档，不能用本地单测代替真实模型能力证据。
3. 3–5 分钟 Demo 视频与可访问链接暂缓。此前提交页截图出现该字段，而[赛事官网 FAQ](https://create.gosim.org/factory26/)称只需提交智能体；正式材料要求应以队长登录后当前提交页核对，不能据旧截图或 FAQ 单独认定。

本仓库旧版能力内核及其历史证据不进入新的比赛包；任何对外演示必须如实区分旧版、当前候选、模拟器结果和官方成绩。
