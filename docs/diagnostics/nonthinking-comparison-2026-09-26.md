# d9基础的非思考请求对照候选

2026-09-26。本候选在独立worktree `/private/tmp/factory26-nonthinking.KaQecx`、分支`codex/factory26-nonthinking-20260926`，源码`fb84f4e6dcba99b9d858425b5d92a3d873d63825`。直接基于d9c86b4，不包含主分支b443324完整源码保留修订，两者不得混淆。

## 改动与边界

相对d9只有编码请求策略变化：根main.py默认`FACTORY26_DEEPSEEK_REASONING_POLICY=non-thinking`；已知DeepSeek编码模型发送`thinking:{type:disabled}`且不发reasoning_effort；视觉策略不变，其他供应商无新增字段。显式runner策略优先；预算、提示、重试、隔离、上下文与验收全部保持。原始请求写入封印轨迹，不删不透明的历史provider字段或工具配对。

[DeepSeek官方说明](https://api-docs.deepseek.com/guides/thinking_mode/)提供此开关，但ARC-Bench模型代理透传未获证实；本地验证不证明远端生效，不保证更快、更便宜或质量更好。背景d9首批2响应后req3三次超时，0写入失败；不是根据隐藏测试设计。

启动仍`python3 main.py <requirements_dir> --output-dir <output_dir>`；依赖/平台注入环境见README。显式`FACTORY26_DEEPSEEK_REASONING_POLICY=bounded`恢复原请求策略。源码分支内同名诊断文档包含完整对照预注册；不改变在途运行。

## 离线验证与封包

- 全量321项：318通过、3环境跳过，62.659秒；新增3项为策略白名单、入口覆盖、请求/轨迹/协议保真。无真实模型调用。
- 干净源码封包`dist/langqi-forge-nonthinking-d9.zip`，21成员/190501字节，SHA `e781889d49cb1165659debce898224ce7f42eee33a27ca1bd279180e68101082`。
- 合同SHA `ab5bfcb432ed522ae3dbd345f603742e2f80338e0ba6a6c4a9742b69279c7dfb`。独立解包`/private/tmp/factory26-nonthinking-package.pMow9a`核对清单全部文件/尺寸/哈希、AST、真实包入口默认及显式覆盖。
- 独立解包实际模块29项策略/压缩/源码记忆/网关协议检查通过（0.125秒）。首次检查误写不存在的test_agent_context，产生测试装载错误，未上传；修正为实际test_compaction_protocol后通过，非产品代码失败。

## 评测约束

先确认d9终态，再用同样GitHub/Pro/视觉模型和既有比赛额度串行测试。核验实际请求字段、延迟/usage/超时、首次写入/晋升、最终官方通过率和费用；不凭速度下结论。服务时变与随机性仍是混杂因素。若本候选有有效产出，再同快照Sheet，不拼接版本成绩。代理拒绝字段时保留错误，不盲目重复启动或偷偷回退。此记录目前仅候选封包，不表示已上传/得分。

## 后续上传（2026-09-25 18:15—18:18 UTC）

正常原生选择器上传上述ZIP，页面成功；Python、名称`Langqi Forge fb84f4e - nonthinking comparison`、Pro编码/Flash视觉、比赛额度勾选、https://api.arc-bench.com/v1，无个人Key。新历史卡保存时间18:15:38，两项均未运行；旧d9卡为失败0/0、￥0.6018，非在途。余额￥441.64为启动前值。

GitHub任务页确认精确新名称/时间/模型，且“当前没有正在进行的任务运行”。点击一次“play-circle 运行最新提交”，页面进入创建运行；不点击历史批量“Run 2 remaining tasks”，不同时启动Sheet。创建结果待后续补录，不能把点击当启动成功。

随后页面真实跳转[465e25b12c29](https://arc-bench.com/runs/465e25b12c29)，26—36秒核验精确名称、GitHub、预检通过、Stage2运行上传智能体/依赖已安装/启动生成、Stage3 pending。启动已确认；首次stdout为空，尚未确认真实模型响应、策略透传、任何功能晋升或分数。不重复点击、不改在途源码。

02:19:17北京时间刷新stdout完成，2m16s观察：前11次真实响应均成功，耗时依次2.822/8.569/6.706/25.830/15.523/2.911/3.090/5.875/21.217/7.020/3.544秒，无model_error。seq32/37/42/52/57/62/67/72共8次实际写入或替换，涉及状态、后端、app.js、api.js；req12/seq74在途。首批尚未晋升、无官方成绩/成本，最终原始请求轨迹尚未下载，不能仅凭速度声称代理执行了thinking策略。此为早期运行信号，不是因果效果或质量改善证明。
