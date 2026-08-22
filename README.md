# arc-adapter — ARC-Bench 标准适配包(参考实现)

这是 [Octos](https://github.com/octos-org/octos) 在 [ARC-Bench](https://arc-bench.com) 上的适配包,同时作为**标准参考实现**:想让自己的 agent 上 ARC-Bench,照这个仓库的结构写即可。配套提交脚本与教程:https://arc-bench-tutorial.vercel.app

## 适配包契约

以下内容提炼自平台 runner 源码(code-philia/arc-bench-website)和 19 轮真实提交。

### 平台怎么调用你

```
python main.py <requirement_path> [--output-dir DIR] [--type web] [--web-port N]
```

| 输入 | 来源 | 说明 |
|---|---|---|
| `requirement_path` | argv 或 `ARCBENCH_TASK_DIR`(默认 `/workspace/task`) | 需求树目录,里面是每个需求节点的描述文件 |
| 交付目录 | `--output-dir` 或 `ARCBENCH_TEMPLATE_DIR` | 你生成的代码必须写到这里 |
| 端口 | `--web-port` 或 `ARCBENCH_WEB_PORT`(默认 3000) | 判卷时访问你网站的端口 |
| 模型通道 | 环境变量 `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `MODEL` | 平台注入的 OpenAI 兼容端点,你的 agent 用它调 LLM |

### 你必须产出什么

判卷器在 agent 退出后检查交付目录,缺了直接判 `template is incomplete`:

```
<交付目录>/
├── frontend/    # npm install && npm run build 必须能通过
└── backend/     # npm run start 启动,读 PORT 环境变量
```

之后平台启动 backend(`PORT` 注入)、跑 Playwright 测试(每条 10 秒超时)打分。

### 事件协议

平台通过文件观察进度,位于交付目录的 `.arc/` 下:`runner-events.jsonl`(run 与每个需求节点的 started/done/failed)、`traceability/*.json`,外加 git commit 记录。本仓库的 `arcbench_agent_runtime/` 已经封装好这些,直接调用即可,不要自己拼文件。

## 目录结构

| 文件 | 职责 | 写自己的 agent 时 |
|---|---|---|
| `main.py` | 总控:解析参数、探活模型端点、逐需求节点驱动 agent、收尾检查 | 保留骨架,替换驱动调用 |
| `octos_stdio.py` | 驱动层:与 Octos 二进制对话 | **换成你的 agent 的调用方式** |
| `arcbench_agent_runtime/` | 平台协议库(事件 / git / 溯源) | 原样保留 |
| `requirements.txt` | Python 依赖 | 按需增删 |

## 照这个包写自己的 agent:三步

1. Fork 本仓库;
2. 把 `octos_stdio.py` 换成驱动你的 agent 的代码(CLI、SDK、HTTP 均可),让 `main.py` 里的每个需求节点轮到它去实现;
3. 用提交脚本验证打包结果:`sh arc.sh pack https://github.com/你的org/你的repo`,确认 zip 内容后 `sh arc.sh submit … 你的仓库链接` 开考。

## 魔改 Octos core 参赛:完整示例

fork 了 octos、改了 core 逻辑,想让改过的版本上场?见 [`examples/core-mod/`](examples/core-mod/):一个能真实 `git apply` 的示例 diff、配套胶水改动,以及"构建 → 换下载来源 → 提交 → 在成绩日志里验证魔改真的上场"的全流程。

一句话记住核心事实:适配包**不内置** Octos,runner 考试时按 `main.py` 顶部 `OCTOS_RELEASE_URL` 现场下载——不把这个地址指向你自己的构建,上场的仍是官方版,且不报错。

## 工程要点(真实踩坑)

- **日志双写**:平台的 stdout 截断会丢长日志;关键日志同时写 stderr(平台单独存)。
- **上传上限约 50MB**:大二进制不要打进 zip,运行时从 Release 现下载;平台服务器访问 GitHub 慢,要走镜像(ghfast.top / gh-proxy.com)。
- **端口清理**:判卷固定用 3000;你的 agent 若起过冒烟测试服务,退出前必须杀掉,否则 EADDRINUSE。
- **UI 契约**(判卷 Playwright 的期望):输入框用纯文本型(不要 `type="date"/"number"`);每个字段配可见 `<label>`;校验用 JS 在页面上输出错误文字,不要用 HTML5 `required`;按钮用真实 `<button>` 带纯文本。
- **共享机状态**:判卷机是多提交共用的,历史残留(端口占用、profile 冲突)要按「必然存在」来防御。
