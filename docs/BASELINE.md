# Historical v1 public baseline — 2026-08-31

## 结论

Langqi Forge 已用真实阿里云百炼 `qwen-plus` 规划调用完成 GitHub 与 Spreadsheet 双域闭环。模型不是生成后的旁路说明器：它必须调用 `select_build_contract`，其领域与覆盖判断直接决定执行路线；错选或损坏返回会被发布门拒绝。

本页是 commit `c93949a` 的历史 v1 基线，用于保留真实模型证据与演进过程；它不代表当前 v2 强化实现已经完成生产资格运行。

| 运行 | 模块 | 模型请求 | prompt / completion Token | GUI | unexpected / skipped / flaky | GUI 墙钟时间 |
|---|---:|---:|---:|---:|---:|---:|
| GitHub 基准 | 47 | 1 | 2776 / 280 | 101 / 101 | 0 / 0 / 0 | 9.123 秒 |
| GitHub 对抗改名 | 47 | 同一制品 | 同上 | 101 / 101 | 0 / 0 / 0 | 8.687 秒 |
| Spreadsheet 基准 | 24 | 1 | 1756 / 271 | 102 / 102 | 0 / 0 / 0 | 17.073 秒 |

三次 GUI 验收均启用 4 workers 与文件内完全并发。双域生成阶段的构建、启动和健康检查通过；`factory26-public-qualification-v1` 最终为 `passed=true`。

这是公开题成绩，不是隐藏题成绩、Top 20 保证或获奖预测。墙钟时间受本机同时运行两套浏览器验收的资源争抢影响。

## 固定输入与模型证据

- 模型：阿里云百炼 `qwen-plus`
- 接口：`dashscope.aliyuncs.com` OpenAI-compatible Chat Completions
- 决策方式：函数工具 `select_build_contract`
- 每个领域：1 次成功模型请求、1 次 HTTP 尝试、1 次 Planner 迭代、0 次代码 Agent 迭代、0 次人工干预
- GitHub：47 模块 / 101 测试，需求 SHA-256 `a4ba2c2e1bd62091a46384e89a823819a485ab609780ce00ead1490edd881959`
- Spreadsheet：24 模块 / 102 测试，需求 SHA-256 `9f2bfd7a9242474ac8e5b3ab9bc0e77e7b659b0ac72b5110bddf53a313c2b494`
- 产生最终证据的 Harness 源码：`c93949ae525c47aa7be3eeb259a9b5550216020b`（运行时工作树干净）
- 上游适配器基线：`b0999c95f7875c8d4ff3e58e733fb2c5abc8caf7`

模型请求的 system/user Prompt、工具 schema、原始 tool call、响应 ID、Token 与契约均保留在 `evidence/final/*/production-trace.jsonl`。公开题源码被 `.gitignore` 排除，不进入证据包或提交包。

## 对抗与并发门禁

GitHub `adversarial` profile 会改写 31 个账号，以及仓库、Fork、分支、默认分支、Issue、标签、里程碑、草稿分支和评审者等夹具，用于发现名字硬编码与并发竞态。

开发过程真实发现并修复了四类问题：

1. 普通 PR 与草稿 PR 并发创建时竞争同一编号，改为后端原子分配。
2. Issue 标题保存后的异步整页重绘覆盖刚打开的描述表单，改为局部字段更新。
3. 两个评测进程共用临时 Playwright 配置文件，改为同目录唯一临时文件再原子替换。
4. Spreadsheet 的 Ctrl+V fallback 晚于下一次剪贴板写入，改为在 keydown 当下快照剪贴板 Promise。

资格门拒绝：模型未调用、非函数工具决策、Planner 错选或失败、轨迹断裂、缺少 provider response id、HTTP 重试、Token 为零或越界、需求哈希不符、本地检查失败、少于 4 workers、使用 grep、GUI 计数漂移、unexpected、skipped、flaky、非完全并发及超时。

## 演进记录

Spreadsheet：

| 阶段 | 公开通过数 | 关键变化 |
|---|---:|---|
| 通用地基 | 0 / 102 | 只验证平台合同、构建和启动 |
| Sheet core | 31 / 102 | 工作簿、工作表、单元格与公式基础 |
| Clipboard / menu | 38 / 102 | 剪贴板与菜单交互 |
| Reversible state core | 78 / 102 | 可逆编辑、结构操作、验证与引用迁移 |
| Sorting / filter / pivot | 102 / 102 | 稳定排序、持久化筛选、数据透视与依赖规则 |

GitHub：

| 阶段 | 公开通过数 | 关键变化 |
|---|---:|---|
| 通用地基 | 0 / 101 | 只验证平台合同、构建和启动 |
| Account / organization | 30 / 101 | 身份、团队、成员与仓库授权 |
| Repository lifecycle | 45 / 101 | 搜索、创建、Fork、克隆与可见性 |
| Code / branch | 60 / 101 | 文件树、提交、搜索、分支与 Web 编辑 |
| Issue workflow | 76 / 101 | 创建、编辑、评论、元数据、关闭与权限 |
| Protection / PR / review | 101 / 101 | 保护规则、比较、评审、合并与状态转换 |

随后由纯确定性内核进化为当前混合 Harness：一次模型规划 → 受约束工具契约 → 版本化内核或代码 Agent → 并发 GUI → 发布资格门。

## 复现

先配置比赛网关或百炼兼容接口：

```bash
export OPENAI_API_KEY='your-key'
export OPENAI_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1'
export MODEL='qwen-plus'
```

同步公开任务并生成两个制品：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m factory26_harness.public_tasks github sheet

GITHUB_RUN="$(mktemp -d /tmp/langqi-github.XXXXXX)"
SHEET_RUN="$(mktemp -d /tmp/langqi-sheet.XXXXXX)"

.venv/bin/python main.py .cache/public-tasks/github/requirements \
  --output-dir "$GITHUB_RUN/project" --web-port 3421 --smoke-port 3422 --strict-exit

.venv/bin/python main.py .cache/public-tasks/sheet/requirements \
  --output-dir "$SHEET_RUN/project" --web-port 3451 --smoke-port 3452 --strict-exit
```

再执行 GitHub 基准、GitHub 对抗、Spreadsheet 基准与资格门。完整命令见仓库首页。关键证据：

- `.arc/harness-report.json`
- `.arc/planner-contract.json`
- `.arc/compiled-plan.json`
- `.arc/production-trace.jsonl`
- `.arc/public-eval/*.feedback.json`
- `qualification.json`

## 声明边界

- 只证明固定哈希公开任务的 GitHub 101 / 101 与 Sheet 102 / 102。
- 未声称模型独立手写了所有界面；准确口径是“模型规划控制面 + 确定性能力数据面”。
- 未知任务仍可能进入受限代码 Agent，带来更多 Token、时间与失败风险。
- 公开全绿、对抗全绿和资格门通过都不等于隐藏题全绿、最终排名或获奖保证。
