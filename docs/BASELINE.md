# Public baseline — 2026-08-31

## 结论

Langqi Forge 已在 ARC-Bench 公开 GitHub 与 Spreadsheet 题包上完成从空目录生成到浏览器验收的双域闭环。GitHub 还通过了重命名夹具与文件内完全并发门禁。

| 运行 | 模块 | GUI | Unexpected / skipped / flaky | GUI 墙钟时间 | prompt / completion Token |
|---|---:|---:|---:|---:|---:|
| GitHub 基准 | 47 | 101 / 101 | 0 / 0 / 0 | 9.515 秒 | 0 / 0 |
| GitHub 对抗改名 | 47 | 101 / 101 | 0 / 0 / 0 | 9.536 秒 | 0 / 0 |
| Spreadsheet 基准 | 24 | 102 / 102 | 0 / 0 / 0 | 19.420 秒 | 0 / 0 |

三次运行均启用文件内完全并发。GitHub 另通过 12 workers 的连续 101 / 101 稳定性运行；本地结构、构建、启动与健康检查也全部通过。

这是公开题成绩，不是隐藏题成绩、Top 20 保证或获奖预测。

## 固定输入

- Harness 分支：`codex/low-token-impact-harness`
- 上游适配器基线：`b0999c95f7875c8d4ff3e58e733fb2c5abc8caf7`
- 题包：ARC-Bench playground catalog 的 `github` 与 `sheet`
- GitHub：47 模块 / 101 测试，需求 SHA-256 `a4ba2c2e1bd62091a46384e89a823819a485ab609780ce00ead1490edd881959`
- Spreadsheet：24 模块 / 102 测试，需求 SHA-256 `9f2bfd7a9242474ac8e5b3ab9bc0e77e7b659b0ac72b5110bddf53a313c2b494`
- 最终证据：4 workers、文件内完全并发；timeout / expect timeout 为 30,000 / 5,000 ms

同步器会把每个公开测试文件的 SHA-256 记录在 `.cache/public-tasks/<task>/manifest.json`。题库被 `.gitignore` 排除，不进入参赛源码包。

## 对抗与并发门禁

GitHub `adversarial` profile 会改写 31 个账号，以及仓库、Fork、分支、默认分支、Issue、标签、里程碑、草稿分支和评审者等夹具。它的目的不是增加公开题覆盖，而是发现名字硬编码与并发竞态。

这套门禁真实发现并促成两项修复：

1. 普通 PR 与草稿 PR 并发创建时曾竞争同一编号；现由后端原子分配。
2. Issue 标题保存后的异步整页重绘曾覆盖刚打开的描述表单；现改为局部字段更新。

独立资格门 `factory26-public-qualification-v1` 会拒绝：测试失败、跳过、flaky、非全并发运行、测试计数漂移、超时、非零 Token，以及本地生成检查失败。

## 复现

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m factory26_harness.public_tasks github sheet
```

生成并验收 GitHub：

```bash
GITHUB_RUN="$(mktemp -d /tmp/langqi-github.XXXXXX)"
.venv/bin/python main.py .cache/public-tasks/github/requirements \
  --output-dir "$GITHUB_RUN/app" \
  --web-port 3421 \
  --smoke-port 3422 \
  --dry-run \
  --strict-exit

.venv/bin/python -m factory26_harness.public_eval github "$GITHUB_RUN/app" \
  --port 3431 \
  --install-browser \
  --strict-exit

.venv/bin/python -m factory26_harness.public_eval github "$GITHUB_RUN/app" \
  --port 3441 \
  --fixture-profile adversarial \
  --strict-exit
```

生成并验收 Spreadsheet：

```bash
SHEET_RUN="$(mktemp -d /tmp/langqi-sheet.XXXXXX)"
.venv/bin/python main.py .cache/public-tasks/sheet/requirements \
  --output-dir "$SHEET_RUN/app" \
  --web-port 3451 \
  --smoke-port 3452 \
  --dry-run \
  --strict-exit

.venv/bin/python -m factory26_harness.public_eval sheet "$SHEET_RUN/app" \
  --port 3461 \
  --strict-exit
```

浏览器已安装后可去掉 `--install-browser`。最后运行 fail-closed 门禁：

```bash
.venv/bin/python -m factory26_harness.qualification \
  --github-project "$GITHUB_RUN/app" \
  --sheet-project "$SHEET_RUN/app" \
  --output qualification.json
```

生成制品中的关键证据：

- `.arc/harness-report.json`
- `.arc/compiled-plan.json`
- `.arc/public-eval/github.feedback.json`
- `.arc/public-eval/github.adversarial.feedback.json`
- `.arc/public-eval/sheet.feedback.json`
- `.arc/runner-events.jsonl`
- `.arc/production-trace.jsonl`

## 演进记录

Spreadsheet：

| 版本 | 公开通过数 | 关键变化 |
|---|---:|---|
| 通用地基 | 0 / 102 | 只验证平台契约、构建和启动 |
| Sheet core | 31 / 102 | 工作簿、工作表、单元格与公式基础 |
| Clipboard / menu | 38 / 102 | 剪贴板与菜单交互 |
| Reversible state core | 78 / 102 | 可逆编辑、结构操作、验证与引用迁移 |
| Sorting / filter / pivot | 102 / 102 | 稳定排序、持久化筛选、数据透视与依赖规则 |

GitHub：

| 阶段 | 公开通过数 | 关键变化 |
|---|---:|---|
| 通用地基 | 0 / 101 | 只验证平台契约、构建和启动 |
| Account / organization | 30 / 101 | 身份、团队、成员与仓库授权 |
| Repository lifecycle | 45 / 101 | 搜索、创建、Fork、克隆与可见性 |
| Code / branch | 60 / 101 | 文件树、提交、搜索、分支与 Web 编辑 |
| Issue workflow | 76 / 101 | 创建、编辑、评论、元数据、关闭与权限 |
| Protection / PR / review | 101 / 101 | 保护规则、比较、评审、合并与状态转换 |

局部修复可使用 `--grep`；表中的最终结论均来自去掉 `--grep` 后对全量题包的干净运行。

## 声明边界

- 只证明固定哈希的公开 `github` 101 / 101 与 `sheet` 102 / 102。
- 隐藏测试仍可能揭示未覆盖的语义、可访问性、性能、异常路径或环境差异。
- `keep` 通用骨架仍为 0 / 32；保留这个地板线，用于说明“能启动”不等于“有业务功能”。
- GitHub 与 Spreadsheet 使用确定性零 Token 路径；未知题目仍进入受限模型实现与失败聚类修复路径。
- 公开全绿、对抗全绿和门禁通过都不等于隐藏题全绿，更不等于最终排名、融资价值或获奖保证。
