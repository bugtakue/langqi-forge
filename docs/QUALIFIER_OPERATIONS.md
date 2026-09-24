# 初赛运行、生产轨迹与人工干预说明

适用对象：`main.py → factory26_harness.qualifier` 这一版比赛包。旧 `cli.py`、`planner.py` 和题目专用模板只在历史源码中存在，不进入本版 ZIP，也不属于本版得分声明。

## 输入与产出

入口接受主办方 `requirements/requirements.yaml` 路径及 `--output-dir`。输出根目录有 `frontend/` 与 `backend/`，后端由 `npm start` 按 `PORT` 监听，前端由 `npm run build` 产出 `frontend/dist/`。默认静态服务和 `/api/health` 是通用运行底座，不包含题目专用行为。

`requirements.py` 校验树、按依赖排序原子需求；`qualifier.py` 把父级模块描述及父级显式 `visual_reference` 继承到各原子需求，避免遗漏父级背景。视觉图片清单同时读取描述中的 `reference/` 路径和显式 `visual_reference` 字段；是否可检查仍由图片路径、存在性、文件类型、大小和视觉网关配置共同决定。空页面、空样式、健康端点及通用 HTTP/原子 JSON 存储辅助函数由 `generic_scaffold.py` 创建，业务代码只能由模型工具调用写入。

`arc_runtime.py` 只调用主办方公开 `arcbench-runtime==0.1.0` SDK 的高层方法：`AgentRuntime.from_env(project_dir=...)`、运行状态、`traceability.store_requirement_tree`、需求实现状态及 `git.ensure_repo/commit`。平台事件格式和 `.arc/traceability/` 表由 SDK 生成，本参赛包不构造事件载荷。在 Runner 环境中 SDK 缺失会失败关闭。每批代码与对应需求状态由 SDK 一并提交；状态文件也在 Git 内，不能先提交代码、再写完成状态。提交失败会把当前需求标记为失败并使运行失败；即使某个需求级失败事件写入报错，也仍独立尝试写运行级失败事件，并在本地报告保留 SDK 报错。通用构建/启动检查不宣称逐需求 GUI 测试通过，也不会发送 `mark_test_passed`。本地 `.arc/production-trace.jsonl` 是额外的独立审计链，不代替平台事件。

报告里的 `behavioral_probe_tested` 仅表示每批**已晋升的实现**至少完成一次带可见文本断言的本地浏览器探针，没有被丢弃的批次冒充；若最终修复轮又改动应用文件，该修复版本也必须重新通过探针，否则该字段为 `false`。`browser_probe_batches[].committed` 标记批次是否进入最终应用。`browser_probe_repairs` 和 `repair_finished.browser_probe` 分别在报告与轨迹中记录修复轮的调用数、改动文件与验证状态。`behavioral_gui_tested=false` 继续表示尚未取得平台独立 GUI 评测。两者不能相互替代。Runner 自带与其 Chromium 匹配的 Python Playwright，参赛包的 `requirements.txt` 不安装或覆盖该版本。

以 [ARC-Bench 当前竞赛页的「排行榜计分方式」](https://arc-bench.com/competition) 为最新公开口径：设 `N` 为该榜涉及的测试总数、`p = 100 × (通过数 / N)`、`b` 为人民币模型开销；合理开销为 `0.4 × N × p / 100`。`p=0` 时不得推断正分；`p>0` 时，实际开销最低按 ¥0.10 计，`b/合理开销` 的比率限制在 `0.01–100`，得分为 `S = p / 比率^γ`；实际开销不高于合理开销时 `γ=0.1`，否则 `γ=0.2`。综合榜要求**同一份提交完成全部任务**，先汇总通过数、测试数与开销再计一次分；单任务榜取该任务的最高得分运行。当前正式赛公开卡片显示 **2 任务、200 测试**，若该数量保持不变，合理开销相当于 `0.8p`，与队长提供的 2026-09-20《参赛须知》所列 `1.2p` 不同；正式运行前仍须复核平台是否再次调整。当前页面依次按得分、通过率、较低开销、较早提交时间排位；[GOSIM 官网规则](https://create.gosim.org/factory26/rules)另把完成时间列为采集指标，但未公布权重，不应据旧材料断言完成时间只用于破同分。只有 Meter 报出的币种明确是人民币时，才能将本地开销代入；`score=null` 表示 Meter 未取得开销，不是 0 元成本或 0 分；`token_cost_usd` 在本地模拟器里只是 `token_cost` 的兼容别名，不能据字段名推断币种。比赛券暂定 ¥500、可重复提交但同队不可并行等来自较早的《参赛须知》，当前未登录状态无法在正式赛详情页复核。单任务 48 小时是旧资料中的运行上限，不能为抢时间牺牲主要的 GUI 正确率。

浏览器探针在读取首页和每步断言时最多等待 2 秒，让异步渲染与操作反馈有机会稳定；超过上限仍按失败报告，不把短时间空白页或尚未出现的反馈当作成功。前端构建、浏览器探针与后端启动健康检查都在临时复制的应用文件上运行，跳过 `node_modules` 等缓存，拒绝源文件软链及过大的复制范围。构建前后会核对应用源码与种子的内容哈希：若 `npm run build` 新增、删除或改写 `frontend/dist/` 之外的应用文件，自检失败，要求 Agent 修正；只有非空且安全的 `frontend/dist/` 会晋升回原项目。这样避免自检副本掩盖平台稍后在原项目重建时的同类副作用；启动初始化或浏览器探针的相对路径写入也不会污染原种子。这是应用状态隔离与事后校验，不是进程网络沙箱；绝对路径写入、网络副作用、`npm install` 生命周期脚本及平台独立构建的环境差异不在此保证范围内。此等待和隔离只影响本地自检，不读取或运行平台隐藏测试。

## Prompts 与 Agent 迭代

1. `agent.py:SYSTEM_PROMPT` 规定实现职责、不可信需求边界、前后端可运行、持久化、交互与后端状态校验；模型必须实际编辑文件并执行校验。
2. `CodingAgent.implement` 为每一小批依赖有序需求构造用户 Prompt，包含需求 ID、描述、场景、父级上下文和相关文件。需求正文明确包裹为不可信数据。若同时提供三项 `VISUAL_*` 配置，Prompt 会列出本批实际存在的参考截图，模型可按需调用 `inspect_reference`；视觉描述仍是不可信线索，不得覆盖文字需求。
3. 模型调用由 `model.py:OpenAIChatClient` 发往环境注入的 OpenAI-compatible `/chat/completions`。没有 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`MODEL` 就失败，不切换到预制业务实现。
4. 每次模型响应可提出多个工具调用。批次在系统临时目录的应用副本中运行，必须有实际源码修改且最后一次修改通过 quick 校验（含不执行生成源码的 JavaScript 语法检查，以及清空旧 `dist` 后必须重新产出非空 `index.html`），随后进入 `ACCEPTANCE_AUDIT_PROMPT` 逐条审查。单纯再次调用 `run_validation` 不算完成审计；模型须给出以 `AUDIT PASS:` 开头的无工具总结，明确未验证部分。这个标记是模型自述，不是逐需求独立测试通过；审计若再改动，必须重新校验。模型明确给出 `AUDIT BLOCKED:` 则当前尝试立即失败，未验证修改不会晋升；连续三次无工具、无可接受进展也结束尝试，而不是追问到 20 回合。通过 quick 后可用 `browser_probe` 启动本地生成应用，按语义控件执行最多八步点击、填写、刷新等动作并断言可见文本；探针仅访问本地应用，不读取隐藏测试。若已使用探针但只做了无动作检查、断言失败或之后改了代码，必须在当前版本重新通过带断言的交互探针才能完成该批。探针是生成物自检，不是正式 GUI 得分。
5. 完成的批次经文件类型/体积核查后才晋升到正式生成项目并由 SDK 提交；失败尝试的临时源码被丢弃。默认一个**多需求**批次若正常结束但未完成，按拓扑顺序拆为前后两半，各至多重试一次；前半仍失败时，后半依赖它的需求先标为 `FAILED`，其余独立项仍尝试。每个半批必须独立生成、校验与提交，不能用整批失败前的未验证改动冒充成果；重试半批仍失败则整半批记 `FAILED`，不推断其中哪个单项已实现。拆批深度上限为一层，每个原始批次最多两次额外会话；`--salvage-splits 0` 可禁用，模型调用抛出运行时错误或请求余量为零时也不再拆批，避免在认证/网关故障时加倍请求。依赖最终失败需求的后续节点不再尝试；独立批次继续。没有任何有效实现时返回非零；有有效实现且最终可构建启动时，部分失败以 `local-contract-partial` 和明确的失败需求列表交给 Runner 继续做独立 GUI 评测。这个状态**不是**全部需求完成，GUI 通过率与得分仍只能由平台测试确定。
6. 全部批次结束后独立执行结构、包策略、交互策略、前端构建、后端启动/健康检查。失败时最多运行配置的修复轮次。局部检查通过不等于 GUI 行为通过。

每批重新开启模型会话时，Harness 保留此前成功批次由工具实际编辑过的源码路径，按最近修改优先、最多 60 个路径且路径正文累计不超过 4,000 字符交给下一批，并在 `implementation_batch_started.prior_source_paths` 留痕。它只是文件索引，不是已实现或已验收的证明；模型须用 `read_files` 按需检查内容。这避免后续批次只看固定五个入口文件而漏掉此前新增的功能模块，同时对提示词体积设限。

默认每批 4 条原子需求、最多 20 个模型回合、最多 2 个最终修复轮。开启失败拆批时，请求容量按每个原始批次最多 3 次会话（原批 + 两半批）预留，但**成功批次不发生拆批开销**；总模型请求上限默认至多 600 次，累计输入/输出 Token 安全上限随之放大。`FACTORY26_SALVAGE_SPLITS=0`、`FACTORY26_MAX_MODEL_REQUESTS`、`FACTORY26_MAX_TOTAL_PROMPT_TOKENS`、`FACTORY26_MAX_TOTAL_COMPLETION_TOKENS` 可显式调整并会写入运行报告。容量是上限，不是预算目标或成绩承诺；拆批是否值得新增模型成本必须以真实公开练习的 GUI 通过率和人民币费用比较，不能只看固定响应夹具。真实 Token/成本由模型服务和主办方计量为准。每次尝试在轨迹中保留 `agent_session_started`、`model_request`、`model_response`、`tool_call`、`tool_result`、`agent_acceptance_audit_requested`、`implementation_batch_finished`；触发拆批另有 `implementation_batch_split`，报告中有 `salvage_attempts`。

模型 HTTP 请求遇到 408/425/429/5xx 或连接中断时，最多尝试 3 次；有 `Retry-After` 时遵守秒数或 HTTP 日期，默认最多等待 60 秒（`FACTORY26_MAX_RETRY_AFTER_SECONDS` 可设为 0–120）。超过本地等待上限就失败关闭，不提前重复请求；401 等非临时错误和格式错误的成功响应不重试。提供商错误正文可能包含敏感信息，因此轨迹只记状态码与重试决策，不保存错误正文。报告把成功的 `model_requests` 与实际 `model_http_attempts` 分开，仍不能由此推断费用：服务端可能在失败响应前已消耗 Token，须以平台计量为准。

超长会话触发上下文压缩时，检查点保留当前源码哈希、校验版本，以及浏览器探针已用次数、剩余额度、是否需要重验和最近一次断言/页面错误摘要；完整原始调用仍在独立生产轨迹中。压缩不把失败探针改写为通过。

## 工具调用与安全

`workspace_tools.py` 暴露：`list_files`、`read_file`、`read_files`、`search_text`、`write_file`、`replace_text`、`run_validation`、`browser_probe`；完整视觉配置时再按批次开放 `inspect_reference`。后者只接受需求正文明确引用且文件实际存在的 `reference/` 图片，默认最多 8 次视觉请求，缓存重复图片；只记录图片 SHA、模型响应与用量，不记录图片字节或密钥。浏览器探针默认每批最多 3 次，仅在当前源码已通过 quick/full 时开放；只允许语义定位及本地路径导航，阻断**浏览器**发起的外部 HTTP 请求，以不含模型密钥的环境启动后端。后端进程的网络边界仍由 Runner 容器负责，不能把浏览器路由限制说成后端网络隔离。写入只允许 `frontend/`、`backend/`，禁止访问 `.env`、密钥、控制目录和越界路径；覆写文件要求当前 SHA-256；有文件数、字节数及模型回合/Token 上限。模型生成的代码经 `checks.py` 在剥离密钥的环境中构建和启动。生产轨迹由 `trace.py` 脱敏并逐行哈希链接。

## 人工干预点

- 运行前：队长决定参赛包版本、模型环境与公开练习任务；账号登录、正式上传仍由队长确认。
- 运行中：默认**零人工干预**；单批失败会留下原因、丢弃未验证改动并尝试独立后续需求；无有效实现、SDK 异常或最终合同失败会停。不由人工在评分容器内补改业务代码。
- 运行后：队长可以审看 `.arc/harness-report.json`、`.arc/production-trace.jsonl`、SDK 写入的 `.arc/runner-events.jsonl`、`.arc/traceability/`、Git 历史和主办方 GUI 报告，再决定是否继续改版或提交。任何改版都必须重新打包和评测。

报告中的 `manual_interventions: 0` 仅描述一次自动运行；不意味着本仓库开发过程没有人工决策。

## 提交前验收表

1. `python -m unittest tests.test_qualifier tests.test_submission_bundle` 通过，打包源工作树干净。
2. ZIP 清单仅为允许的通用 Python 模块、`main.py`、`requirements.txt`、哈希清单；不得包含 `templates/`、任务名、硬编码目标站点页面或测试答案。
3. 用主办方本地模拟器在至少两道公开练习上跑真实模型，记录通过数、测试总数、失败分布、模型调用与成本；不能拿协议夹具冒充这一项。
4. 确认正式 Runner 需要的 `frontend/`、`backend/`、构建与启动合同；不依赖只在本地模拟器实现的 `deploy.sh`。
5. 正式赛须账号、队伍和预算可用；不要把准备好的 ZIP 或本地报告写成已提交/官方成绩。
