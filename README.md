# Langqi Forge — Factory26 Low-Token Harness

Factory26 / ARC-Bench 的独立参赛工程。它把规格编译成可运行软件：稳定能力走确定性领域内核，未知能力才进入受限代码 Agent 与定点修复环。目标不是堆更多 Agent，而是在 GUI 通过率、Token 与完成时间三项指标之间取得可复现的优势。

当前闭环：

1. 读取并按依赖顺序编译 `requirements.yaml`。
2. 识别题目领域：GitHub 与 Spreadsheet 走零 Token 可持久化内核，未知题生成通用地基。
3. 未被领域内核覆盖的需求才通过 OpenAI-compatible 网关交给带受限工具的代码 Agent。
4. 每批只提供少量需求和已观测相关文件，记录需求到文件的影响图并聚类 GUI 失败。
5. 在独立 smoke port 上执行构建、启动和 `/api/health` 检查，不占用评分端口。
6. 把 prompts、模型回复、工具调用、Agent 迭代、人工干预点、需求溯源和 Git 提交全部落盘。
7. 最后由 fail-closed 资格门同时检查双域 GUI、对抗夹具、并发、时间、跳过项与 Token。

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
.venv/bin/python -m factory26_harness.public_eval github /tmp/factory26-github \
  --port 3401 \
  --install-browser \
  --strict-exit

# 同一制品进入改名、换值、完全并发的对抗世界
.venv/bin/python -m factory26_harness.public_eval github /tmp/factory26-github \
  --port 3411 \
  --fixture-profile adversarial \
  --strict-exit
```

原始 Playwright JSON、后端日志和最小修复包写入生成项目的 `.arc/public-eval/`。
首次运行可保留 `--install-browser`；浏览器已安装后可省略。定点回归可加
`--grep 'REQ-3-1-2|REQ-4-1-1'`，但发布前必须去掉 `--grep` 再跑完整题包。

双域制品均跑完后执行独立资格门：

```bash
.venv/bin/python -m factory26_harness.qualification \
  --github-project /tmp/factory26-github \
  --sheet-project /tmp/factory26-sheet \
  --output qualification.json
```

门禁会拒绝任何 unexpected、skipped、flaky、非全并发运行、测试计数漂移、超时、非零 Token 或本地构建失败。

## 设计边界

- 开发期间永不启动评分端口；所有自检使用单独 smoke port。
- 模型只能写 `frontend/` 和 `backend/`，不能修改 `.arc/`、Git、评分器或仓库外文件。
- 影响图只记录真实观察到的“需求→修改文件”关系，不猜隐藏测试。
- 局部检查不能证明 GUI 功能通过；最终始终执行一次完整构建和启动检查。
- `harness-report.json` 明确区分“本地可运行”与“ARC GUI 已得分”，禁止把前者包装成后者。

## 当前真实基线

2026-08-31 的可复现公开基线：

| 赛题 / 世界 | 模块 | GUI | unexpected / skipped / flaky | GUI 时间 | 生成 Token |
|---|---:|---:|---:|---:|---:|
| GitHub 基准 | 47 | 101 / 101 | 0 / 0 / 0 | 9.515 秒 | 0 / 0 |
| GitHub 对抗改名 | 47 | 101 / 101 | 0 / 0 / 0 | 9.536 秒 | 0 / 0 |
| Spreadsheet 基准 | 24 | 102 / 102 | 0 / 0 / 0 | 19.420 秒 | 0 / 0 |

三次运行均启用文件内完全并发；GitHub 另有 12 workers 连续稳定性运行。生成阶段的构建、启动与健康检查全部通过。固定需求 SHA-256：

- GitHub：`a4ba2c2e1bd62091a46384e89a823819a485ab609780ce00ead1490edd881959`
- Spreadsheet：`9f2bfd7a9242474ac8e5b3ab9bc0e77e7b659b0ac72b5110bddf53a313c2b494`

这只证明同步到上述哈希的公开题通过，不代表隐藏测试、最终排名或获奖。耗时也会随机器负载变化。完整证据、演进和声明边界见 [docs/BASELINE.md](docs/BASELINE.md)。

公开题迭代时，可将 Playwright JSON 报告压缩成按根因归类的最小修复包：

```bash
.venv/bin/python -m factory26_harness.feedback playwright-report.json \
  --impact generated_project/.arc/change-impact.json \
  --output generated_project/.arc/public-feedback.json
```

同一定位器、同一断言或同一启动错误只交给模型一次，避免逐条失败重复消耗 Token。隐藏测试不可见时不会伪造这份反馈。

## 来源与兼容性

项目从 `octos-org/arc-adapter` 的平台契约出发，保留其 `arcbench_agent_runtime/` 协议层，代码 Agent 和编排层已独立实现。上游参考提交：`b0999c95f7875c8d4ff3e58e733fb2c5abc8caf7`。
