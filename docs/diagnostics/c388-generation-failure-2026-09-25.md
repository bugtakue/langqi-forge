# c3887cd 首批网关失败

正式运行：https://arc-bench.com/runs/edf2cdd5b477 ，`Langqi Forge c3887cd - read page memory`。

## 官方终态

2026-09-25现场核验History (12)：得分0.00、test pass **0/0**、Features 0.0%、8m0s、11,375 Token、**¥0.0348**；余额¥467.27。运行页Stage2显示进程退出码1，未产生可评测应用。Sheet未运行，未核验新的综合排名。0/0表示没有进入正式测试，不得改写为0/100；只有一个正常模型响应，不能假设超时调用在上游是否完成。

第二请求首次尝试240.099秒超时，按既定策略重试一次；第二次235.296秒后返回HTTP400，不重试并安全停止。错误体256字节、JSON对象、已识别字段位置error.message/code/type，但安全分类仍unclassified，原文未持久化。不能据延迟断言是平台故障、限额、模型能力或协议错误。

## 封印证据

通过本队运行页正常下载 `/Users/zerongliu/Downloads/edf2cdd5b477-template.zip`；只打开内层`factory26-evidence.zip`的三项封印生成证据，不读隐藏测试。

- 原下载归档：`dist/official-evidence/edf2cdd5b477/project-final-generation.zip`，3,340,382字节、42成员；SHA `02685231c9ccafe583d8cb3ca16712ca1b399621e46de84b01b7746c0df03438`。
- 内层证据ZIP：38,596字节；SHA `c09400f33e9e3aaaaee255544dca364cac8b95bd854455f9e9d60b5a3d59a3de`。
- 轨迹：161,312字节、26行全部封印；SHA `0311228fedbda78227eb0a62149e555f8bf1fd78b7a0118fd99d8f4e29792bab`；链头`edcdbe24e69d32529cc3a70229ce76e9d5912b04f16fe2f8e5e3e88ddbc7a37e`。
- 报告SHA `3e1a1b267e0a2eca185281dffd6db0886bf1ac9f4fb2c2dadb690d86c63269c4`。
- 源码`c3887cd34403666e9b3b6189b9487cbfeaf35e78`，合同`db821686a7556fb75bb1fd33a24181ebe09912a0ab6ef09777302322b91e3cd1`。
- 三成员精确清单、ZIP CRC、完整哈希链、清单声明的内容哈希及字节数核验通过；现有脱敏扫描0命中，不将扫描当作绝对无敏感数据保证。

内部报告：1个正常模型响应、3次HTTP尝试、0项晋升、47项未完成。两份请求消息的tool_call与tool结果ID完整配对，带工具调用的assistant消息保留reasoning_content；此项检查不能证明整体协议或参数均被网关接受。

请求1/2序列化字符数48,294/56,915，max_tokens均8192；第二请求在read_files之后，尚无write_file/replace_text或上下文压缩事件。因此这次失败没有检验源码页缓存效果。不要盲目重跑或将其算作覆盖率改善；下一步先排查可核验网关合同与可观察诊断，再决定下一次串行比较。
