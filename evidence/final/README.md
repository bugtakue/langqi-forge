# Final public evidence

这是一组从干净 Harness commit `c93949ae525c47aa7be3eeb259a9b5550216020b` 产生的最终公开证据。两次生成都真实调用阿里云百炼 `qwen-plus`，不是本地协议模拟器；密钥未写入任何文件。

## 结果

| 制品 / 验收 | run_id | 模型 Token | GUI | workers / 过滤 | 时间 |
|---|---|---:|---:|---:|---:|
| GitHub 生成 + 基准 | `674576e0-0112-493b-8eed-4c6f998a9829` | 2776 / 280 | 101 / 101 | 4 / 无 | 9.123 秒 |
| GitHub 改名对抗 | 同一制品 | 同上 | 101 / 101 | 4 / 无 | 8.687 秒 |
| Spreadsheet 生成 + 基准 | `a6f4e025-2ecb-4e08-8103-c7a333c2fb65` | 1756 / 271 | 102 / 102 | 4 / 无 | 17.073 秒 |

所有 GUI 运行均为 `unexpected=0`、`skipped=0`、`flaky=0`。最终 [`qualification.json`](qualification.json) 为 `passed=true`。

## 完整生产轨迹

GitHub：

- [`production-trace.jsonl`](github/production-trace.jsonl)：21 个连续事件，含完整 system/user Prompt、工具 schema、Qwen 原始 tool call、provider response id、Token、路由、验证和人工点。
- [`planner-contract.json`](github/planner-contract.json)：模型选择的 7 类 GitHub 能力、风险与验证重点。
- [`harness-report.json`](github/harness-report.json)：源码 commit、run_id、调用次数、Token 与本地验证结果。
- [`github.feedback.json`](github/github.feedback.json) / [`github.adversarial.feedback.json`](github/github.adversarial.feedback.json)：两次完整 GUI compact 报告。

Spreadsheet：

- [`production-trace.jsonl`](sheet/production-trace.jsonl)：19 个连续事件，字段与 GitHub 轨迹相同。
- [`planner-contract.json`](sheet/planner-contract.json)：模型选择的 8 类 Spreadsheet 能力、风险与验证重点。
- [`harness-report.json`](sheet/harness-report.json)：源码 commit、run_id、调用次数、Token 与本地验证结果。
- [`sheet.feedback.json`](sheet/sheet.feedback.json)：完整 GUI compact 报告。

[`manifest.json`](manifest.json) 记录每个公开证据文件的 SHA-256 与字节数。公开导出只将本机绝对路径替换成 `<harness-repository>` / `<*-generated-project>`；Prompt、模型回复、工具参数和失败字段没有删改。公开任务测试源码故意不进入仓库。

## 人工干预

两个最终生产运行都是 Planner 1 次、Coding Agent 0 次、人工干预 0 次。轨迹中的 `human_intervention_checkpoint` 明确记录：异常时关闭资格门，不在评分运行中临时请人改代码。开发期真实发现的四类竞态和修复过程见 [`docs/BASELINE.md`](../../docs/BASELINE.md)。

## 声明边界

这些证据只支持固定哈希公开题的 304 / 304 与本仓库资格门通过，不支持“隐藏题必过”“必进 Top 20”或“必获奖”等结论。
