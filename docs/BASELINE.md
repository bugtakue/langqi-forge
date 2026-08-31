# Public baseline — 2026-08-31

## 结论

独立 Harness 已在 ARC-Bench 公开 Spreadsheet 题包上完成一次从空目录生成到浏览器验收的全链路运行：

| 闸门 | 结果 |
|---|---:|
| 需求树解析 | 24 / 24 模块 |
| 公开 Playwright | 102 / 102 |
| Unexpected / skipped / flaky | 0 / 0 / 0 |
| GUI 墙钟时间 | 19.841 秒 |
| Harness 本地构建与启动检查 | 全部通过 |
| 模型 Token | prompt 0 / completion 0 |
| 手工修改生成结果 | 0 |

这是公开题成绩，不是隐藏题成绩或获奖预测。

## 固定输入

- Harness 分支：`codex/low-token-impact-harness`
- 上游适配器基线：`b0999c95f7875c8d4ff3e58e733fb2c5abc8caf7`
- 题包：ARC-Bench playground catalog 的 `sheet`
- 模块数：24
- 测试数：102
- 需求 SHA-256：`9f2bfd7a9242474ac8e5b3ab9bc0e77e7b659b0ac72b5110bddf53a313c2b494`
- 浏览器并发：12 workers
- 测试 timeout / expect timeout：30,000 / 5,000 ms

同步器会把每个测试文件的 SHA-256 一并记录在 `.cache/public-tasks/sheet/manifest.json`；题库本身被 `.gitignore` 排除，不进入参赛包。

## 复现

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m factory26_harness.public_tasks sheet

FACTORY26_SHEET_RUN="$(mktemp -d /tmp/factory26-sheet.XXXXXX)"
.venv/bin/python main.py .cache/public-tasks/sheet/requirements \
  --output-dir "$FACTORY26_SHEET_RUN/app" \
  --web-port 3421 \
  --smoke-port 3422 \
  --dry-run \
  --strict-exit

.venv/bin/python -m factory26_harness.public_eval sheet "$FACTORY26_SHEET_RUN/app" \
  --cache .cache/public-tasks \
  --port 3421 \
  --workers 12 \
  --timeout 30000 \
  --expect-timeout 5000 \
  --install-browser \
  --strict-exit
```

浏览器已安装后可以去掉 `--install-browser`。最终生成结果中的报告位于：

- `.arc/harness-report.json`
- `.arc/compiled-plan.json`
- `.arc/public-eval/sheet.feedback.json`
- `.arc/public-eval/sheet.playwright.json`
- `.arc/runner-events.jsonl`

## 演进记录

| 版本 | 公开 Sheet 通过数 | 关键变化 |
|---|---:|---|
| 通用地基 | 0 / 102 | 只验证平台契约、构建和启动 |
| Sheet core | 31 / 102 | 工作簿、工作表、单元格与公式基础 |
| Clipboard / menu | 38 / 102 | 剪贴板与菜单交互 |
| Reversible state core | 78 / 102 | 可逆编辑、结构操作、验证与引用迁移 |
| Sorting / filter / pivot | 102 / 102 | 稳定排序、持久化筛选、数据透视与依赖规则 |

修复阶段允许用 `public_eval --grep` 跑相关用例组；102 / 102 结论来自去掉 `--grep` 后对全量题包的一次干净运行。

## 声明边界

- 当前只证明公开 `sheet` 题包 102 / 102；隐藏测试仍可能揭示未覆盖的语义、可访问性、性能或异常路径。
- `github` 公开题已能同步与运行，但目前没有专用领域模板，因此不报告 GUI 分数。
- `keep` 通用骨架仍为 0 / 32；保留这个结果用于说明“能启动”不等于“有业务功能”。
- Spreadsheet 使用确定性零 Token 路径；未知题目仍进入受限模型实现与失败聚类修复路径。
