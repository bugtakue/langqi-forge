# 琅岐岛民 Factory26 提交交接卡（未提交）

本卡用于队长后来核对填写项，**不是提交许可，也不是官方成绩**。以登录后当时的 ARC-Bench 表单和规则为最终依据；任何新代码都须重跑验收、重新打包并更新本卡。

## 当前精确候选

- 本地源码分支：`codex/factory26-compliant-20260924`；参赛包的代码/文档来源提交：`4aa256c87fa6c0196ae8c851fd8c2acebeac0d89`。后续 `b580fc3` 与本卡的提交只追加不入包的证据文档，不改变上述 ZIP 的清单身份。
- 参赛 ZIP：`dist/langqi-forge-qualifier.zip`；SHA-256：`421d56210348a600ce97e95177cc4d49c3d0c41792468a8c33eee00080a0e398`。17 个白名单文件、解压检查及逐文件清单验证通过；不含 Key、题目专用实现或测试答案。
- 启动合同：`python3 main.py <requirements_dir> --output-dir <output_dir>`；生成的 `frontend/` 与 `backend/` 分别支持 `npm run build`、按 `PORT` 执行 `npm start`，并提供 `/api/health`。依赖与本地启动步骤见仓库 `README.md`、`docs/QUALIFIER_OPERATIONS.md`。
- 实现说明：通用需求树解析、依赖排序、小批次模型工具调用、私有副本生成及晋升、构建/启动检查、可选本地浏览器探针、官方 `arcbench-runtime` 状态/追溯/Git 提交，以及独立哈希链。实际 Prompt、工具、迭代和人工干预点由 `factory26_harness/agent.py`、`factory26_harness/workspace_tools.py`、`factory26_harness/qualifier.py` 及运行轨迹核查；`manual_interventions: 0` 只描述单次自动运行。

## 本地证据边界

- 主机单元测试 132 项：129 通过、3 项因主机 Chromium 环境跳过。
- 该**精确 ZIP** 在旧版 arm64 Runner 的固定响应合成协议题完成 1/1 独立 Playwright；当前缓存的 amd64 基础镜像中直启生成、官方 SDK、6/6 本地检查及镜像自身部署流程通过，首页与 `/api/health` 返回 HTTP 200。完整运行目录和限制见 `docs/QUALIFIER_EVIDENCE_2026-09-24.md` 最后两节。
- 上述 1/1 是**假模型 + 自建合成题**。尚无真实模型的 BookStack/Keep 公开练习通过率、人民币模型成本、当前完整 x86 Runner GUI 结果或正式赛分数。不能用 `score=null` 推断 0 元或 0 分。

## 提交页字段状态

| 字段 | 可用材料 | 尚缺/不能填成什么 |
|---|---|---|
| GitHub 仓库（源码与启动方式） | 本地分支、`README.md`、上述 ZIP | `https://github.com/bugtakue/langqi-forge` 的公开 `main` 在本卡核对时仍为 `d0474d789c583b3c0d0dfbd133c4af8df270cfed`，**不是**当前候选 `4aa256c...`。队长决定公开后需先推送并核对远端提交，再填写可访问链接。 |
| 生产轨迹（Prompts、工具、迭代、人工干预） | 本地 `.arc/production-trace.jsonl`、SDK 事件、追溯表、生成项目 Git 历史；仓库说明列出字段 | 当前可展示轨迹只来自合成协议。需用真实模型完成至少一次合规本地练习并脱敏核验后，才能作为真实能力证据公开；不得把假模型轨迹表述为实战生成。 |
| 3–5 分钟 Demo | 结构与证据素材已有 | 视频制作与可访问链接按队长要求暂缓；不得填占位网址。登录后还要复核当前表单是否仍要求该字段。 |
| 账号与正式提交 | 官网报名账号与队名由队长掌握 | ARC-Bench 原密码未知，当前登录/注册页没有可见的找回密码入口；队长需通过主办方确认恢复方式。**未登录、未上传、未正式提交。** |

## 提交前停线

1. 真实模型在公开练习至少跑完一次，记录独立 GUI、费用和失败分布；据此决定是否改代码。百炼个人 Key 只用于本地练习，不写进仓库/ZIP；正式评测用平台注入 Key。
2. 在可运行当前 amd64 Runner Chromium 的 x86 环境复核最终 ZIP；本机 arm64→amd64 QEMU 浏览器预检失败，不得用直启或旧 arm64 浏览器替代该结论。
3. 队长恢复 ARC-Bench 访问后核对正式任务、当前表单字段、比赛券及规则；源码、轨迹、Demo 如需公开，先由队长确认发布范围。
4. 队长明确同意正式提交之前，不推送当前分支、不上传 ZIP、不点击提交。
