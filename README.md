# Factory26 Low-Token Harness

Factory26 / ARC-Bench 的独立参赛工程。目标不是让更多 Agent 讨论，而是用确定性程序完成机械工作，只把无法定位的实现问题交给模型。

当前版本已经完成第一条可运行闭环：

1. 读取并按依赖顺序编译 `requirements.yaml`。
2. 识别题目领域：未知题生成零依赖通用地基，Spreadsheet 题生成完整、可持久化的数据工作区。
3. 通过 OpenAI-compatible 网关驱动带受限工具的代码 Agent。
4. 每批只提供少量需求和已观测相关文件，记录需求到文件的影响图。
5. 在独立 smoke port 上执行构建、启动和 `/api/health` 检查。
6. 把 prompts、模型回复、工具调用、事件、需求溯源和 Git 提交全部落盘。

## 平台契约

```bash
python main.py <requirement_path> \
  --output-dir <generated_project> \
  --type web \
  --web-port 3000
```

平台注入：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `MODEL`
- `ARCBENCH_TASK_DIR`
- `ARCBENCH_TEMPLATE_DIR`
- `ARCBENCH_WEB_PORT`

生成结果固定包含：

```text
generated_project/
├── frontend/                 # npm install && npm run build
├── backend/                  # PORT=... npm start
└── .arc/
    ├── runner-events.jsonl
    ├── production-trace.jsonl
    ├── compiled-plan.json
    ├── change-impact.json
    ├── harness-report.json
    └── traceability/
```

## 本地验证

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

不调用模型，只验证提交结构、构建、启动、健康检查和留痕：

```bash
.venv/bin/python main.py path/to/requirements \
  --output-dir /tmp/factory26-output \
  --web-port 3301 \
  --smoke-port 3302 \
  --dry-run \
  --strict-exit
```

同步官方公开的 GitHub 与 Spreadsheet 题包：

```bash
.venv/bin/python -m factory26_harness.public_tasks github sheet
```

需求、测试与 SHA-256 清单会写入被 Git 忽略的 `.cache/public-tasks/`，便于重复测量而不把公开题库复制进提交包。

对生成项目执行公开 GUI 测试并自动形成失败聚类：

```bash
.venv/bin/python -m factory26_harness.public_eval sheet /tmp/factory26-output \
  --port 3401 \
  --install-browser \
  --strict-exit
```

原始 Playwright JSON、后端日志和最小修复包写入生成项目的 `.arc/public-eval/`。
首次运行可保留 `--install-browser`；浏览器已安装后可省略。定点回归可加
`--grep 'REQ-3-1-2|REQ-4-1-1'`，但发布前必须去掉 `--grep` 再跑完整题包。

## 设计边界

- 开发期间永不启动评分端口；所有自检使用单独 smoke port。
- 模型只能写 `frontend/` 和 `backend/`，不能修改 `.arc/`、Git、评分器或仓库外文件。
- 影响图只记录真实观察到的“需求→修改文件”关系，不猜隐藏测试。
- 局部检查不能证明 GUI 功能通过；最终始终执行一次完整构建和启动检查。
- `harness-report.json` 明确区分“本地可运行”与“ARC GUI 已得分”，禁止把前者包装成后者。

## 当前真实基线

2026-08-31 的可复现公开基线：

- 通用骨架在 `keep`：0 / 32；这是未知领域的诚实地板线。
- Spreadsheet 专用模板在 `sheet`：102 / 102，unexpected / skipped / flaky 均为 0。
- 完整 GUI 运行：12 workers，19.841 秒。
- 生成阶段：本地构建、启动、健康检查全部通过；prompt / completion Token 均为 0。
- 固定输入：24 个模块、102 个测试，需求 SHA-256 为
  `9f2bfd7a9242474ac8e5b3ab9bc0e77e7b659b0ac72b5110bddf53a313c2b494`。

这只证明公开 Spreadsheet 题通过，不代表隐藏题、GitHub 题或最终排名。GitHub 题已可同步和执行，当前仍走通用/模型路径，尚无可报告的公开 GUI 成绩。详见 [docs/BASELINE.md](docs/BASELINE.md)。

公开题迭代时，可将 Playwright JSON 报告压缩成按根因归类的最小修复包：

```bash
.venv/bin/python -m factory26_harness.feedback playwright-report.json \
  --impact generated_project/.arc/change-impact.json \
  --output generated_project/.arc/public-feedback.json
```

同一定位器、同一断言或同一启动错误只交给模型一次，避免逐条失败重复消耗 Token。隐藏测试不可见时不会伪造这份反馈。

## 来源与兼容性

项目从 `octos-org/arc-adapter` 的平台契约出发，保留其 `arcbench_agent_runtime/` 协议层，代码 Agent 和编排层已独立实现。上游参考提交：`b0999c95f7875c8d4ff3e58e733fb2c5abc8caf7`。
