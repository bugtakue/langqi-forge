# Langqi Forge · Factory26 初赛候选

琅岐岛民的 ARC-Bench 软件生成智能体。本分支采用**通用、模型驱动**的正式参赛路径：读取比赛提供的需求，生成可部署的前后端，留下可核验的生产轨迹。它不是循济产品本体。

> 状态：目前是本地候选，**未上传、未产生官方成绩、未确认晋级**。此前 GitHub/Spreadsheet 公开样题的 304/304 属于旧版题目专用能力内核，不得作为本版成绩或合规证明。旧版源码与证据可从 Git 历史查阅，但不会进入本版参赛 ZIP。

## 与当前规则的对应

- ZIP 根目录有 `main.py` 和 `requirements.txt`，入口遵循 `python3 main.py <requirements_dir> --output-dir <output_dir>`。
- 运行后必须生成 `frontend/`、`backend/`，分别支持 `npm run build`、`npm start`；后端按 `PORT` 监听并提供 `/api/health`。不依赖只在本地模拟器支持的 `deploy.sh`。
- 打包采用明确文件白名单。提交包不含 GitHub、Spreadsheet、BookStack、Keep 的页面、API、种子或业务实现；`generic_scaffold.py` 仅提供空前端、静态资源服务、健康检查及通用 HTTP/原子 JSON 存储辅助函数。
- 正常生成路径必须调用平台注入的 OpenAI-compatible 模型网关。模型缺失、实现批次未完成或构建/启动失败均返回非零；不会把空 scaffold 冒充完成品。
- 旧成绩不是本版性能证据。任何真实通过率以主办方独立 GUI 评测为准。

主办方本地模拟器：[hackathon-local-simulation](https://github.com/code-philia/hackathon-local-simulation)。报名与项目提交由队长操作；此处的打包命令**不会上传**。

## 工作流

```text
requirements.yaml
  → 校验并按依赖排序原子需求，继承必要的父级产品上下文
  → 创建与题目无关的可运行前后端
  → 按小批次交给 CodingAgent，通过模型工具调用读取、改写、校验源码
  → 每批通过 quick 构建校验，并作一次模型验收审计
  → 全量构建、启动、健康检查；失败可限轮修复
  → .arc/production-trace.jsonl + harness-report.json
  → 外部独立 GUI 评测（本智能体不自称已通过）
```

工具仅允许读项目文件、查询文本、修改 `frontend/` / `backend/` 和运行安全校验。覆写文件需要已观察的 SHA-256，限制写入文件数和字节数；模型看不到环境密钥。生产轨迹记录 Prompt、模型请求与响应、工具参数与结果、批次、校验和人工干预点，并对敏感字段脱敏、逐行链接哈希。

具体 Prompt、工具、循环及证据位置见 [参赛运行说明](docs/QUALIFIER_OPERATIONS.md) 和 [本地验证记录](docs/QUALIFIER_EVIDENCE_2026-09-24.md)。

## 本地运行

需要 Python 3.10+、Node.js/npm、可用的 OpenAI-compatible 模型服务。**不要把密钥写入仓库或 ZIP。**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
export OPENAI_API_KEY='...'
export OPENAI_BASE_URL='https://your-gateway.example/v1'
export MODEL='your-model'
.venv/bin/python main.py /absolute/path/to/requirements \
  --output-dir /absolute/path/to/generated-project
```

模型服务也可以由比赛平台注入；本地没有密钥时只能跑单元/协议测试，不能宣称真实智能体成绩。

```bash
.venv/bin/python -m unittest tests.test_qualifier tests.test_submission_bundle
```

工作区会产生：

- `frontend/`、`backend/`：真实生成的应用源码与启动文件；
- `.arc/compiled-plan.json`：需求批次与来源哈希；
- `.arc/production-trace.jsonl`：Prompt、模型、工具和迭代的脱敏哈希链；
- `.arc/harness-report.json`：本地构建/启动结果、模型调用次数和失败原因。

## 打包（不上传）

在**干净且已提交的工作树**运行：

```bash
.venv/bin/python -m factory26_harness.submission_bundle \
  --output dist/langqi-forge-qualifier.zip
unzip -l dist/langqi-forge-qualifier.zip
```

打包器会拒绝脏树、软链接、越界路径和疑似密钥文件，并写入逐文件哈希清单。审核时必须检查 ZIP 中没有 `factory26_harness/templates/` 或旧 `cli.py`、`planner.py`、`capabilities.py`。

## 目前尚缺

1. 使用真实模型在官方 BookStack/Keep 公开练习上运行，记录通过率和真实开销；协议夹具测试不等于该结果。
2. 正式比赛平台账号的队长登录、队伍确认与上传；报名网站登录不等于 ARC-Bench 登录。
3. 3–5 分钟 Demo 视频与可访问链接。视频制作在功能和本地评测稳定后进行。

本仓库旧版能力内核及其历史证据不进入新的比赛包；任何对外演示必须如实区分旧版、当前候选、模拟器结果和官方成绩。
