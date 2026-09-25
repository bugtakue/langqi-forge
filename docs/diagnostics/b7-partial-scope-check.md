# b7 中途产物的异常注册错误与通用离线检查

日期：2026-09-25。正式运行：https://arc-bench.com/runs/e36c41c1ff7d 。
运行源码：b7fe418ea85a93293da8fcd4f4f6a288ec75815d。以下诊断不改写在途快照。

## 证据来源与边界

11:09 UTC通过该运行正常“文件→project.zip”下载本队Stage2中途产物：

- 本机下载：`/Users/zerongliu/Downloads/e36c41c1ff7d-template.zip`
- 私有归档：`dist/official-evidence/e36c41c1ff7d/project-partial-20260925T1109.zip`
- 3,307,208字节、41文件、未压缩3,990,342字节。
- SHA-256：`01392f93a1d65aa6f5251d77a635c4d7871b277e128be5cc800c5703cdbbdb81`

此包不是最终生成物，尚不含封印完整生产轨迹；后续模型可能改写相关代码。
只检查本队生成的前后端及公开需求，不读取隐藏测试，不从评分阶段数据变化反推用例。

## 独立浏览器复现

应用文件解到一次性目录`/tmp/factory26-api-check.8ukoUz/template`，审看启动脚本后，以无凭证环境构建并监听127.0.0.1:19436。
在真实Chrome依次点Sign in→Create an account，填写无效用户名、无效邮箱、过短且不匹配的测试密码，条款不选，点Create account。
表单没有出现预期字段错误，Chrome控制台在11:10:57.687Z记录：

```text
ReferenceError: passwordInput is not defined
at doRegister (http://127.0.0.1:19436/app.js:271:5)
```

该函数catch分支在输出服务器字段错误之前使用了词法作用域中不存在的`passwordInput`、`confirmInput`。
公开需求中的异常输入流程未正常完成；不能将早先一次成功探针扩张成全部注册场景验证。
测试没有成功创建账户，没有使用个人真实凭证。诊断结束后已停止本地PID56920并确认19436端口无监听。

## 候选修订

不修补这份正式产物，而改通用harness：所有快速/完整验证先做词法作用域检查。
Espree10.4.0、eslint-scope8.4.0、eslint-visitor-keys4.2.1、globals16.5.0，esbuild0.25.11只用于开发期打包。
使用公开AST/Scope API，不加载完整ESLint配置发现器，不导入生成源码或运行其中函数。
运行时不需要node_modules或新网络请求；八个实际捆绑依赖的完整许可证随检查器分发。

同一真实产物的独立离线检查结果：

```text
frontend/src/app.js:271:5: Undeclared variable: passwordInput
frontend/src/app.js:272:5: Undeclared variable: confirmInput
```

一次本机耗时0.0764秒；不代表官方Runner速度或已经节约的人民币成本。
预打包JS为352,830字节；重建两次SHA-256一致：
`8301f685d0639bc55b901465aec9db5abfbf891ed195eefad30406162b0c942c`。
构建锁文件SHA-256：`8e76e728406fa6a15dc3eab47f9d7a9edb5444567600eeb11a44112a9651a59e`。
已把锁文件下载来源固定到registry.npmjs.org，用npm ci --ignore-scripts重装后重建哈希仍相同。

聚焦夹具覆盖作用域/解构/import/闭包、浏览器与Node环境、CommonJS与ESM、typeof、禁止注释放行、配置和源码不执行、离线独立bundle、软链/超限/超时/坏返回关闭。
首次全套发现浏览器文件被误按构建包CommonJS解析，已改为浏览器ES模块；五个旧会话测试夹具用裸标识符填充源码，改成等长注释/有效字符串，原有压缩/审计断言不变，不放宽检查器。
最终全量回归239项、236通过、3浏览器环境跳过，63.008秒；32项模型会话回归也通过，既有压缩容量未放宽。git diff --check通过。

限制：只做词法名字检查，不证明对象属性存在、业务正确、导入路径有效或GUI测试通过；TS/JSX和传统多script隐式全局目前不在支持范围。
新增组件是b7之后的本地候选，不重启、不取消当前正式运行，也不追加模型调用来检验本地静态器。
