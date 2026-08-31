# Reproducible Codex / Claude Code comparisons

这里分开回答两个不同问题，防止通过改变起跑线制造一个没有意义的“胜利”。

## A. Factory-system 比赛

Langqi Forge 可以使用自己的版本化能力内核和可证伪能力胶囊。这正是 Factory26 所评价的 Harness 工程能力：GUI 通过率、模型 Token、墙钟时间、可复现轨迹与失败处理。

这个赛制比较的是完整参赛系统，不是底层模型的纯编码能力。

## B. Blank-workspace Agent 比赛

`run_codex.py` 与 `run_claude_code.py` 用同一份 prompt 模板、同一份只读需求、空输出目录、零人工、固定墙钟和同一外部评分器，专门比较两个通用代码 Agent 从零构建的能力。

### 不可变协议

1. 输入只复制公开 `requirements/`，不把测试源码放进 Agent 工作目录。
2. 输出目录必须不存在或为空；runner 把只读输入放在 `control/`，Agent 从真正空白的 `workspace/` 起跑，只在其中生成 `frontend/` 和 `backend/`。
3. 记录 CLI 版本、可执行文件哈希、Harness 提交/清洁度、模型、effort、墙钟和完整调用参数。
4. 禁用个人规则、skills、MCP、Apps、插件、浏览器、多 Agent、网络搜索、会话续写和持久记忆。Codex 用显式配置移除工具，并实时审计 JSONL；一旦出现违禁事件就立即终止整场。Claude Code 用空 MCP 配置与六项本地工具白名单，并审计完整 stream-JSON。
5. 保留原始 JSON/stream-json、stderr 和最后消息；失败或超时不重跑挑最好结果。
6. 生成后使用与 Langqi Forge 相同的 `factory26_harness.public_eval`、4 workers、文件内完全并发和相同 fixture profile。
7. 报告 pass、unexpected、skipped、flaky、生成时间、GUI 时间、Token 与可得成本；无法取得的指标写 `unknown`，不推算。
8. 两边都不得读测试源码、人工修改生成物或在评分后追加修复。如需第二轮，必须作为“双方同时允许一次反馈修复”的独立赛制。

Claude Code 另有 `--max-budget-usd`；Codex CLI 当前没有等价的本地美元上限参数，因此共同硬上限是墙钟，Token 与成本分开如实报告。任何“固定美元完全对等”的说法都是不准确的。

## 运行命令

先确认两个 CLI 都已登录，并同步公开需求：

```bash
codex login status
claude auth status
.venv/bin/python -m factory26_harness.public_tasks github sheet
```

当前证据固定使用 Codex CLI `0.151.0`。`0.137.0` 已无法解析当前模型目录，runner 会 fail closed。隔离安装到已忽略的 `.cache/`，不改用户全局 Codex：

```bash
npm install --prefix .cache/benchmark-tools/codex-0.151.0 \
  --registry=https://registry.npmjs.org --no-audit --no-fund \
  @openai/codex@0.151.0
```

Codex：

```bash
.venv/bin/python benchmarks/run_codex.py github \
  --output-dir /tmp/codex-github-run \
  --codex .cache/benchmark-tools/codex-0.151.0/node_modules/.bin/codex \
  --model gpt-5.4 --effort high --timeout-seconds 1800

.venv/bin/python benchmarks/run_codex.py sheet \
  --output-dir /tmp/codex-sheet-run \
  --codex .cache/benchmark-tools/codex-0.151.0/node_modules/.bin/codex \
  --model gpt-5.4 --effort high --timeout-seconds 1800
```

Claude Code：

```bash
.venv/bin/python benchmarks/run_claude_code.py github \
  --output-dir /tmp/claude-github-run \
  --model sonnet --effort high --max-budget-usd 5 --timeout-seconds 1800

.venv/bin/python benchmarks/run_claude_code.py sheet \
  --output-dir /tmp/claude-sheet-run \
  --model sonnet --effort high --max-budget-usd 5 --timeout-seconds 1800
```

然后为每个成功生成的制品执行相同 GUI：

```bash
.venv/bin/python -m factory26_harness.public_eval github <run>/workspace \
  --port <unique-port> --workers 4 --strict-exit

.venv/bin/python -m factory26_harness.public_eval github <run>/workspace \
  --port <another-port> --workers 4 --fixture-profile adversarial --strict-exit

.venv/bin/python -m factory26_harness.public_eval sheet <run>/workspace \
  --port <unique-port> --workers 4 --strict-exit
```

## 声明边界

运行器只负责冻结输入、环境、调用和轨迹，不自动把任何结果包装成胜利。认证失败、超时、零成本、部分生成或未执行评测都不是可比成绩。单次对照也只说明该 CLI 版本、该模型、该预算与该任务，不外推为 Codex 或 Claude Code 的普遍强弱。
