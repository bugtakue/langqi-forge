# Factory26 Low-Token Harness

Factory26 / ARC-Bench 的独立参赛工程。目标不是让更多 Agent 讨论，而是用确定性程序完成机械工作，只把无法定位的实现问题交给模型。

当前版本已经完成第一条可运行闭环：

1. 读取并按依赖顺序编译 `requirements.yaml`。
2. 生成零依赖、可持久化的 `frontend/` 与 `backend/` 地基。
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

## 设计边界

- 开发期间永不启动评分端口；所有自检使用单独 smoke port。
- 模型只能写 `frontend/` 和 `backend/`，不能修改 `.arc/`、Git、评分器或仓库外文件。
- 影响图只记录真实观察到的“需求→修改文件”关系，不猜隐藏测试。
- 局部检查不能证明 GUI 功能通过；最终始终执行一次完整构建和启动检查。
- `harness-report.json` 明确区分“本地可运行”与“ARC GUI 已得分”，禁止把前者包装成后者。

## 当前真实基线

2026-08-31 在 ARC-Bench `keep` 公开任务上：

- 需求解析：32 / 32 个原子节点成功
- 提交结构、构建、启动、健康检查：通过
- 零模型 GUI 测试：0 / 32

这个零分是预期的地板线，说明可启动骨架不会冒充功能成绩。下一里程碑是注入比赛模型后取得首个真实 GUI 通过率。详见 [docs/BASELINE.md](docs/BASELINE.md)。

公开题迭代时，可将 Playwright JSON 报告压缩成按根因归类的最小修复包：

```bash
.venv/bin/python -m factory26_harness.feedback playwright-report.json \
  --impact generated_project/.arc/change-impact.json \
  --output generated_project/.arc/public-feedback.json
```

同一定位器、同一断言或同一启动错误只交给模型一次，避免逐条失败重复消耗 Token。隐藏测试不可见时不会伪造这份反馈。

## 来源与兼容性

项目从 `octos-org/arc-adapter` 的平台契约出发，保留其 `arcbench_agent_runtime/` 协议层，代码 Agent 和编排层已独立实现。上游参考提交：`b0999c95f7875c8d4ff3e58e733fb2c5abc8caf7`。
