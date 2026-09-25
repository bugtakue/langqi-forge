# f3 首批晋升产物的独立浏览器检查

2026-09-25，检查对象为本队 `9eb571d8b5b6` / f3b0a9e 的中途下载产物，不是最终产物或官方GUI评测。仅访问本队正常文件下载与公开需求，没有隐藏测试或他人提交。

## 来源与隔离

- 10:19 UTC 正常“文件”页已经显示工作区，点击 `project.zip` 下载。
- 原下载：`/Users/zerongliu/Downloads/9eb571d8b5b6-template.zip`。
- 归档：`dist/official-evidence/9eb571d8b5b6/project-partial-20260925T1019.zip`。
- SHA-256：`56c7bc37e7f351a2004938b2e39d23b6d1ecb507b7ffa63008bf711cebc1a2eb`。
- 41个文件，解压总量3,990,533字节；包含公开需求、图片及已晋升应用，不包含最终证据ZIP。完整生产轨迹仍需终态导出。
- 审查源码/启动脚本后仅解压 frontend/backend 到 `/tmp/factory26-f3-gui.gX7Oa1/template`；清空继承环境后用 Node 构建并以 `HOST=127.0.0.1 PORT=19435` 启动。没有 npm install、个人密钥或比赛模型调用。

## 实际观察

1. Home 的 Sign in 链接可进入登录页；`Create an account` 是真实 anchor、有 href，不再是 b53 的 button 角色错误。
2. 注册页可见 Username、Email、Password、Confirm password、未勾选的 Agree to the terms 和可操作 Create account。
3. 不合规用户名/邮箱、空密码/确认、未勾选条款一起提交后，五个对应字段错误同时显示，按钮仍可操作，没有创建账户。
4. 截图确认失败后用户名 `-retry-local` 和邮箱 `invalid-retry` 仍在各自输入框。此处工具的 DOM snapshot/只读 value 读数为空，但屏幕实际保留了值，不能据读数误判应用清空输入。
5. 不存在的合成用户名登录显示 Invalid credentials，没有进入已登录工作区。
6. 使用公开需求的既有合成种子账号邮箱登录成功，显示 alice-dev；整页刷新后仍保持登录。
7. Sign out 后整页刷新返回未登录首页。状态文件计数为 accounts=1、sessions=1、activeSessions=0，未新增注册账户。
8. 采集到的浏览器 error/warn 日志为空。页面仍只有工作区占位说明，没有组织或仓库流程；数据中 organizations/repositories均为0。

未执行成功注册、账号恢复、改密或组织/仓库/权限流程；不把这些局部观察当成完整需求通过，更不是正式得分。该副本的用户均为公开合成测试数据，不使用真实账户凭证。

## 收尾

临时服务会话34569已停止，19435无监听；归档ZIP哈希未变。浏览器副本的登录/退出只修改临时副本，没有回写平台应用、正式参赛包或生产环境。

10:23 UTC 官方同一运行仍 Stage 2 / Stage 3 pending。请求26在10:20:58返回finish_reason=length、报告completion_tokens=24,477；sequence222标记一次输出截断，随后请求27继续。没有重复启动、并行评测或取消当前任务。
