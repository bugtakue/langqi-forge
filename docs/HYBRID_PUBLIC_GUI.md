# 跨架构公开 GUI 诊断（非正式评测）

用途：当 macOS ARM 主机上的当前 amd64 Runner 因 QEMU Chromium 预检故障而不能跑完整 GUI 时，对**已经生成的应用**运行公开 Playwright 测试。生成阶段仍使用当前 amd64 基础镜像；浏览器阶段借用本机缓存的旧 arm64 镜像 `arcbench-local-legacy:20260924`。这两个阶段拼接，**不等于主办方当前完整 Runner**，也不能用于推断隐藏测试、正式得分或真实模型开销。

前提：已有独立的本地模拟器 `--prepare-only` 工作区，至少包含 `template/frontend/dist/index.html`、`template/backend/server.mjs` 和 `tests/*.spec.ts`；并已在该工作区通过当前基础镜像生成应用。本诊断脚本不会调用模型，不传入模型密钥。测试时容器使用 `--network none`、只读挂载本仓库的 `scripts/` 目录、仅给生成工作区写权限。不要在工作区存放个人密钥；生成应用仍是不可信程序。

在本仓库根目录运行，替换准备好的工作区绝对路径与唯一标签：

```bash
diagnostic_workspace='/absolute/path/to/prepared-workspace'
docker run --rm --platform linux/arm64 --network none \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=${diagnostic_workspace},target=/workspace" \
  --mount "type=bind,source=$(pwd)/scripts,target=/harness,readonly" \
  arcbench-local-legacy:20260924 \
  bash /harness/run_hybrid_public_gui.sh /workspace run-001
jq '.stats' "${diagnostic_workspace}/hybrid-playwright-run-001-report.json"
```

脚本启动生成后端并等 `/api/health`，在测试目录放置独立的 `hybrid.playwright.config.ts` 和指向镜像内 Playwright 的 `node_modules` 链接，再执行公开测试。它为 Chromium 设置可写的临时 HOME；否则以非 root 用户启动时，浏览器会在任何断言前因 crashpad 退出。每个标签生成独立的 JSON 报告和 stdout/stderr/后端日志；已有同名报告会拒绝覆盖。若同名配置文件内容不同，脚本也拒绝覆盖。报告 `expected/unexpected` 只是这些公开测试的数量，不是平台分数。

真实模型练习仍需要合法的练习 Key，并须另行记录模型费用、任务用例总数与 GUI 失败分布；固定响应协议夹具不能替代此验证。正式上传、队伍登录及提交不由这个脚本完成。
