# Baseline — 2026-08-31

## 环境

- Harness 分支：`codex/low-token-impact-harness`
- 上游适配器基线：`b0999c95f7875c8d4ff3e58e733fb2c5abc8caf7`
- ARC-Bench：`code-philia/arc-bench@d5044350c4e51e5fdcc00ccb35a5f3770fe10029`
- 公开任务：`keep`
- 原子需求：32
- Playwright 用例：32
- 模式：`--dry-run`，不调用模型

## 结果

| 闸门 | 结果 |
|---|---:|
| 需求树解析 | 32 / 32 |
| `frontend/` + `backend/` 结构 | 通过 |
| `npm run build` | 通过 |
| `PORT=... npm start` | 通过 |
| `/api/health` ready | 通过 |
| 平台事件与 traceability | 通过 |
| GUI Playwright | 0 / 32 |

首个共同失败是页面不存在可访问名称为 `Take a note` 的按钮。其余失败均来自 Keep 业务功能尚未生成，而不是启动、端口或打包故障。

## 解释

这是基础设施地板线，不是参赛成绩预测。它证明提交不会因为目录、构建、端口、健康检查或留痕问题得到“零条测试执行”；同时也证明确定性空骨架不会伪造功能分。

## 下一闸门

1. 用平台注入的兼容模型完成 `keep` 的第一批需求。
2. 记录模型 Token、墙钟时间、修改文件和 GUI 通过数。
3. 将 Playwright 失败按共同根因聚类，只把最小失败上下文交给修复 Agent。
4. 对比“逐条需求”“三条一批”“公共地基优先”三种策略。
