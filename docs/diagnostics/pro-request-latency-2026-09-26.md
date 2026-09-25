# Pro请求耗时复核：先解决可观测瓶颈

## 数据范围

仅分析本队GitHub生成期已核验封印包`dist/official-evidence/359dd7e72ca7/factory26-evidence.zip`，SHA `af5845802b7856f600cba269cf2a7b4f2f9a547c6da5e3e4082a00a54e082f0b`。取806行中的model_request、model_response、model_error和tool_call；不读评分数据、隐藏测试或其他队伍实现。下面是日志字段的聚合，不是新模型调用，也不是官方费用拆分。

## 实际统计

- 106个正常编码响应，elapsed_seconds合计3291.517秒，单次中位数7.951秒。
- 10次失败尝试：9次TimeoutError、1次HTTP502；已记录耗时2260.695秒，即37.68分钟，约占报告生成时长5655.012秒的40.0%。不把这些失败的未知Token用量视作零。
- 64个响应最终只请求read_file/read_files/list_files，响应耗时合计862.128秒。这里包含模型决策时间，**不是文件I/O耗时**；只返回读取工具也不能证明此前推理完全无用。
- 其中4个读取响应超过60秒：request/response seq495/497为93.439秒、560/562为81.012秒、590/594为96.241秒、629/631为124.540秒。
- 工具调用数：read_file 87、read_files 10、list_files 1、write_file 10、replace_text 15、run_validation 10、browser_probe 9、inspect_reference 8、read_requirement_spec 3。调用不等于成功，也不能与需求覆盖混用。
- 107个编码请求均实际携带`max_tokens=8192`、`reasoning_effort=low`，未携带thinking开关；不是只检查本地默认配置。
- 其中11个正常响应报告completion_tokens大于8192，最高20,263。这里只能确认请求字段与报告值的差异；无法据此确定代理是否忽略参数、对推理Token另计、模型策略不同或使用量口径不同。

## 官方资料核验与判断边界

2026-09-26查阅[DeepSeek思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)及[Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)：官方提供low/high/max及显式关闭思考的控制；携带tools的后续请求须保留历史reasoning_content。已保留的推理字段不能为了缩短请求随意删除。官方文档不证明`api.arc-bench.com`比赛代理的参数透传和计量口径。

ARC公开仓库首页描述的是benchmark及复现流程，没有在该页发现模型代理的透传合同；没有继续读取任何测试或参考实现，也没有给主办方发送消息。当前不能声称已定位平台错误。

## 决策

下一轮改进优先关注失败请求与重复读取造成的成本，而不是先增加agent数量。可考虑“规划/复杂修复保留推理，明确的机械执行采用轻量策略”，但这只是待对照假设：必须验证实际请求生效、工具协议、需求通过率和人民币成本，不得在当前运行中热改，不因关闭推理就宣称更强。

本轮不改变runtime、超时、模型、额度、工具权限或验证门。a31cfa9已有候选（写入前置条件、新流程重验、源码容量）继续保留未上传；先完成当前c3887cd同快照Sheet，避免把不同版本或不同模型的成绩拼接。

## 当前Sheet恢复证据

正式运行[40f69fc30bd3](https://arc-bench.com/runs/40f69fc30bd3)，同c3887cd/Pro。第3个请求首次240.151秒超时，seq31第二次尝试在203.357秒正常返回（输入15,387/输出16,274）；seq34/36成功写入backend/server.mjs和backend/data/state.json。随后seq37上下文从120,630压缩至62,751字符，保留源码快照10,841字节/8个完整文件，seq39发出request4。9m06s现场Stage2仍生成、Stage3 pending，尚无已晋升需求、官方分数或最终费用。

这是已恢复的活运行，不因一次超时取消或重开。上一Goal回合完成正式结算和新任务启动，本轮取得新的请求耗时/参数差异证据与确切恢复进展；综合前三仍未完成。
