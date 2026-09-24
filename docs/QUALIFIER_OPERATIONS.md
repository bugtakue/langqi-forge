# 初赛运行、生产轨迹与人工干预说明

适用对象：`main.py → factory26_harness.qualifier` 这一版比赛包。旧 `cli.py`、`planner.py` 和题目专用模板只在历史源码中存在，不进入本版 ZIP，也不属于本版得分声明。

## 输入与产出

入口接受主办方 `requirements/requirements.yaml` 路径及 `--output-dir`。输出根目录有 `frontend/` 与 `backend/`，后端由 `npm start` 按 `PORT` 监听，前端由 `npm run build` 产出 `frontend/dist/`。默认静态服务和 `/api/health` 是通用运行底座，不包含题目专用行为。

`requirements.py` 校验树、按依赖排序原子需求；`qualifier.py` 把父级模块描述并入各原子需求 Prompt，避免遗漏父级背景。空页面、空样式、健康端点及通用 HTTP/原子 JSON 存储辅助函数由 `generic_scaffold.py` 创建，业务代码只能由模型工具调用写入。

`arc_runtime.py` 只调用主办方公开 `arcbench-runtime==0.1.0` SDK 的高层方法：`AgentRuntime.from_env(project_dir=...)`、运行状态、`traceability.store_requirement_tree`、需求实现状态及 `git.ensure_repo/commit`。平台事件格式和 `.arc/traceability/` 表由 SDK 生成，本参赛包不构造事件载荷。在 Runner 环境中 SDK 缺失会失败关闭。每批代码与对应需求状态一并提交，提交失败会使运行失败；通用构建/启动检查不宣称逐需求 GUI 测试通过，也不会发送 `mark_test_passed`。本地 `.arc/production-trace.jsonl` 是额外的独立审计链，不代替平台事件。

报告里的 `behavioral_probe_tested` 仅表示每批至少完成一次带可见文本断言的本地浏览器探针；`behavioral_gui_tested=false` 继续表示尚未取得平台独立 GUI 评测。两者不能相互替代。Runner 自带与其 Chromium 匹配的 Python Playwright，参赛包的 `requirements.txt` 不安装或覆盖该版本。

## Prompts 与 Agent 迭代

1. `agent.py:SYSTEM_PROMPT` 规定实现职责、不可信需求边界、前后端可运行、持久化、交互与后端状态校验；模型必须实际编辑文件并执行校验。
2. `CodingAgent.implement` 为每一小批依赖有序需求构造用户 Prompt，包含需求 ID、描述、场景、父级上下文和相关文件。需求正文明确包裹为不可信数据。若同时提供三项 `VISUAL_*` 配置，Prompt 会列出本批实际存在的参考截图，模型可按需调用 `inspect_reference`；视觉描述仍是不可信线索，不得覆盖文字需求。
3. 模型调用由 `model.py:OpenAIChatClient` 发往环境注入的 OpenAI-compatible `/chat/completions`。没有 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`MODEL` 就失败，不切换到预制业务实现。
4. 每次模型响应可提出多个工具调用。批次必须有实际源码修改且最后一次修改通过 quick 校验（含不执行生成源码的 JavaScript 语法检查，以及清空旧 `dist` 后必须重新产出非空 `index.html`），随后进入 `ACCEPTANCE_AUDIT_PROMPT` 逐条审查；审计若再改动，必须重新校验。通过 quick 后可用 `browser_probe` 启动本地生成应用，按语义控件执行最多八步点击、填写、刷新等动作并断言可见文本；探针仅访问本地应用，不读取隐藏测试。若已使用探针但只做了无动作检查、断言失败或之后改了代码，必须在当前版本重新通过带断言的交互探针才能完成该批。探针是生成物自检，不是正式 GUI 得分。
5. 全部批次结束后独立执行结构、包策略、交互策略、前端构建、后端启动/健康检查。失败时最多运行配置的修复轮次。局部检查通过不等于 GUI 行为通过。

默认每批 4 条原子需求、最多 20 个模型回合、最多 2 个最终修复轮。总模型请求上限按实际批次数与允许回合数计算（默认上限 600 次），累计输入/输出 Token 安全上限随之放大；`FACTORY26_MAX_MODEL_REQUESTS`、`FACTORY26_MAX_TOTAL_PROMPT_TOKENS`、`FACTORY26_MAX_TOTAL_COMPLETION_TOKENS` 可显式覆盖并会写入运行报告。这些是上限，不是预算目标或成绩承诺；真实 Token/成本由模型服务和主办方计量为准。每批会在轨迹中保留 `agent_session_started`、`model_request`、`model_response`、`tool_call`、`tool_result`、`agent_acceptance_audit_requested`、`implementation_batch_finished` 等事件。

## 工具调用与安全

`workspace_tools.py` 暴露：`list_files`、`read_file`、`read_files`、`search_text`、`write_file`、`replace_text`、`run_validation`、`browser_probe`；完整视觉配置时再按批次开放 `inspect_reference`。后者只接受需求正文明确引用且文件实际存在的 `reference/` 图片，默认最多 8 次视觉请求，缓存重复图片；只记录图片 SHA、模型响应与用量，不记录图片字节或密钥。浏览器探针默认每批最多 3 次，仅在当前源码已通过 quick/full 时开放；只允许语义定位及本地路径导航，阻断外部 HTTP 请求，以不含模型密钥的环境启动后端。写入只允许 `frontend/`、`backend/`，禁止访问 `.env`、密钥、控制目录和越界路径；覆写文件要求当前 SHA-256；有文件数、字节数及模型回合/Token 上限。模型生成的代码经 `checks.py` 在剥离密钥的环境中构建和启动。生产轨迹由 `trace.py` 脱敏并逐行哈希链接。

## 人工干预点

- 运行前：队长决定参赛包版本、模型环境与公开练习任务；账号登录、正式上传仍由队长确认。
- 运行中：默认**零人工干预**；失败会停并写明原因，不由人工在评分容器内补改业务代码。
- 运行后：队长可以审看 `.arc/harness-report.json`、`.arc/production-trace.jsonl`、SDK 写入的 `.arc/runner-events.jsonl`、`.arc/traceability/`、Git 历史和主办方 GUI 报告，再决定是否继续改版或提交。任何改版都必须重新打包和评测。

报告中的 `manual_interventions: 0` 仅描述一次自动运行；不意味着本仓库开发过程没有人工决策。

## 提交前验收表

1. `python -m unittest tests.test_qualifier tests.test_submission_bundle` 通过，打包源工作树干净。
2. ZIP 清单仅为允许的通用 Python 模块、`main.py`、`requirements.txt`、哈希清单；不得包含 `templates/`、任务名、硬编码目标站点页面或测试答案。
3. 用主办方本地模拟器在至少两道公开练习上跑真实模型，记录通过数、测试总数、失败分布、模型调用与成本；不能拿协议夹具冒充这一项。
4. 确认正式 Runner 需要的 `frontend/`、`backend/`、构建与启动合同；不依赖只在本地模拟器实现的 `deploy.sh`。
5. 正式赛须账号、队伍和预算可用；不要把准备好的 ZIP 或本地报告写成已提交/官方成绩。
