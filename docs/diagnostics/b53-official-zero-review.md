# b53 正式零分与需求语义诊断

核验日期：2026-09-25。只检查本队正常下载产物、平台可见结果和公开需求；没有访问隐藏测试或他人私有提交。

## 官方结果

- 运行：https://arc-bench.com/runs/de30d58e3116
- 快照：Langqi Forge b53d9a9 - prompt and evidence
- GitHub：0/100、0.0%、得分 0.00、￥9.7380。
- 平台显示 108m55s、4.180M Token（约数），余额 ￥487.18。
- Sheet 未运行，不能作为完整综合新成绩；目标仍未完成。
- Test Results 只显示 0/100，没有具体失败原因。不能据此推断平台故障，或把下述缺陷说成所有失败的唯一原因。

## 本地真实浏览器观察

来源 `dist/official-evidence/de30d58e3116/project.zip`（SHA-256 `abcb1928602921cc82f230e13f9dd0268a5c9e828921bcbf3916a096367a10ca`）。仅解压 frontend/backend 到 `/tmp/factory26-gui-check.PnigZ8/template`，审看自有代码后以清空继承环境、`HOST=127.0.0.1`、`PORT=19432` 构建并运行。通过受控 Chrome 界面操作，不执行隐藏评测或额外模型调用。

1. 首页正常渲染；Sign in 打开带 Username or email / Password 的表单。
2. 公开 REQ-1-1-1 指定唯一 **link** `Create an account`。实际 DOM 为 **button**，精确 link 数量 0、button 数量 1。
3. 公开合成种子账户登录成功，显示 Signed in as alice-dev；刷新后仍登录。
4. Organizations / Repositories / Work items 都只有空占位，没有已实现的对应业务流程。
5. 退出后回到首页。此次浏览器采集没有 error/warn；未完成注册或账号恢复流程，不宣称这些流程通过。
6. 临时服务 PID 28314 已正常终止，19432 不再监听；原始 ZIP 和正式平台产物未改。

## 已核验的自检盲区

封印轨迹 sequence 106 的注册自检按 `role=button` 点击 `Create an account`，迁就了生成页面而没有遵守公开需求的 link。seq 467 的恢复流程传入五条 expect_text，超过工具上限四条，未实际运行浏览器；旧逻辑却没有留下待补验义务，该需求之后被本地晋升。两项都不能用构建成功或接口成功替代。

## 任务无关的最小修订

- Prompt 和工具说明要求从公开规格选角色、名称和断言，修页面而不是放宽定位。没有嵌入上述项目名称、固定账号或业务答案。
- 未明确 index 时保留 Playwright 的严格唯一匹配；显式 index 仍支持重复条目。原来无条件 nth(0) 会掩盖重复控件。
- 首次无效探针参数不消耗浏览器启动额度，但标记待补验；同源码已有真实通过记录时继续保留，不因未执行的无效调用撤销它。
- 保持现有模型、回合、Token、视觉和三次浏览器启动上限。没有在包中放入下载的成品应用。

本地协议回归与真实 GUI 观察分开记录。需要新一轮官方运行才能判断提分，不能把本页当作修复后的官方成绩。

## 修订验收

完整 `.venv/bin/python -m unittest discover -s tests -q -b`：218 项 / 215 通过 / 3 浏览器环境跳过，56.631 秒；`git diff --check` 通过。五项新增离线检查覆盖严格角色/label/text 定位、显式重复项、首次无效计划补验与提示词合同。原有同版本已验证行为保留测试继续通过。初轮发现 Prompt 增长使 8,000 字符回归超限，已压缩文字而非放宽限制；最终该回归通过。
