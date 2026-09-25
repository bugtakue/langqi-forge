# fa7 生成终态与未分类 HTTP 400

2026-09-25；本队正式运行 https://arc-bench.com/runs/9cd0d7fea546 ，源码 `fa7cb15216bbab616f359cf3f19878393f2c5d6a`。

## 状态

29m35s 现场 Stage2 完成、Stage3 Evaluation in progress。未取得官方 GUI 成绩、结算人民币费用或本轮排名；不启动并行 Sheet，不把生成结束当官方评测结束。

12:42:26 UTC 生成封印报告：status=local-contract-partial，1648.176 秒。保留 **4/47** 原子需求：REQ-2-1-1、REQ-3-1、REQ-3-3、REQ-3-2-3；43 项未完成。四条已收集行为胶囊最终重放通过，不等于全任务可用。

成功编码返回/计数 133，HTTP 尝试 134；报告输入 2,654,930、输出 148,250 Token；视觉 3 次，输入 2,948、输出 519；已报告合计 **2,806,647 Token**。失败 HTTP 是否产生其他用量需平台账单确认，不能自行按Token给出人民币费用。manual_interventions=0仅指生成进程内无人工热改。

## 归档与核验

正常项目下载原件 `/Users/zerongliu/Downloads/9cd0d7fea546-template.zip`；保存为 `dist/official-evidence/9cd0d7fea546/project-final-generation.zip`：44文件、6,409,031字节，SHA-256 `342fefad3a3e4151f01ba3a029fd86b4ef301dff04e19a5600406375bf368b2f`。

仅提取生成阶段 `factory26-evidence.zip`（3,145,434字节，SHA-256 `cf76dcc518a7e8cf54b002c9ab2dc1cb315dcb66a97dbc0162416fd315316f52`），不读取评分期业务状态。

- 轨迹830行全部封印，12,462,256字节；SHA-256 `226ffcdd928aeee7f4d650f722f6e240a4386eef50d70f685b3e7b76a011c7e3`。
- 链头 `734778826b9ce9837a64e1b5ce771ace262678d1e08bef79538de838d31a17a3`。
- 报告SHA-256 `24761daa467d9f9299ae1e8d18f04e8c9ca6f719bb3cbb40aad058ff09449645`。
- 需求合同SHA-256 `bdc17d23265a6b1948aec150e69d0b2accfa37db4c569305c97be7ff7f3b0b8f`。
- 证据包CRC、精确文件成员、清单字节数/哈希、require_fully_sealed链与源身份核验通过。未向外部上传完整轨迹。

## HTTP 400 能与不能说明什么

seq820 为第134次请求；seq822 在12:42:17 UTC记录 HTTP 400，elapsed=36.952，error_category=unclassified，retryable=false。seq825安全停止模型调用，保留此前已验收应用。

网关错误正文按既有隐私规则不入日志，只作有限分类。这次分类器未识别原因，因此**不能断言额度不足、上下文超限或供应商故障**，也不能声称本地 scope/完整流程改动修复了此错误。

离线检查最后两个封存请求：seq814 9消息/85,183脱敏JSON字符，seq820 5消息/93,892字符；assistant工具调用与tool结果配对完整，没有待响应调用或孤立tool结果，assistant均携带reasoning_content字段。这只是结构检查，不证明提供商一定接受；脱敏后的长度也不等于线上Token或原文长度。

后续先取官方结果；在再次花费额度前审查安全错误分类的可观测性，不通过不断重试400或打印原始响应正文解决。注册失败造成依赖阻断与大量反复读取仍是独立质量问题，不能归咎于最后一个网关错误。
