# Pro Sheet 首批产物的独立复核

本队正式运行`40f69fc30bd3`，c3887cd / deepseek-v4-pro。2026-09-26上海时间约01:08，Stage2期间通过正常“文件→project.zip”下载一次中途应用；不是最终产物或官方分数。未读隐藏测试、评分期数据或他队私有内容，未改在途应用。

## 制品

- 原件`/Users/zerongliu/Downloads/40f69fc30bd3-template.zip`，归档`dist/official-evidence/40f69fc30bd3/project-partial-workbooks.zip`。
- 23成员、643219字节，SHA256 `4a8a210aceeb889be3ff01b1a85c110e129e705d97c9549193f920b61cd69c40`，全部CRC通过。
- 只解包11个frontend/backend文件到`/private/tmp/factory26-pro-sheet.ptnDx8/template`，先审查完整源码/构建辅助模块再运行；未解包/执行requirements或评测代码。不安装依赖、不连模型或远端API，空继承环境构建，仅监听127.0.0.1:19439。
- server.mjs SHA `c16c17f047cf3f7111279272d1035b0135d5639b2b366f8df5362c89889087c8`；app.js SHA `508ccb22f4163cc6c77262c8597a703105fd2454b6e5ed95749efbd925a3f651`。源码/原件检查前后哈希不变。

## Chrome实际操作

1. 首页New blank workbook→Create，实际进入Untitled spreadsheet，仅Sheet1选中、Worksheet grid、A1选中、200个空单元格；刷新保持同一URL和标题/A1状态。
2. Rename workbook输入纯空格，Save显示`Workbook name cannot be empty`且旧标题不变。改为合成名“本地验收簿”后保存成功，刷新及Back to home仍保留。
3. 首页Import CSV通过原生选择器导入合成CSV，逐项核对A1:C4：中文、逗号、尾空字段、双引号与字段内换行完整。B2=`含,逗号`，C2为空，B3=`他说"你好"`，B4=`第一行\n第二行`。首行仍是数据，标题按文件名去.csv为“本地导入”；刷新后内容保留。
4. 未闭合引号CSV显示`Invalid CSV file format. Import failed.`；取消刷新仍只有Q3 Sales和两本合成工作簿。失败前后state.json SHA完全相同：`057f91e6e62749000e5ec14e303d92ac9f6365901f910745b96604308a83274b`，无半成品。
5. 浏览器error/warn为空。未注入网络/磁盘失败，未测新会话、并发/重复提交或全部场景；不能声称全面验收。第二批不在该副本内，不评价其导出/工作表操作。

## 正式日志新证据

36m39s现场、刷新01:16:38，Stage2生成、Stage3 pending，没有Sheet官方成绩/费用/新综合名次。

- request22第二次尝试seq159成功，197.549秒，输入26555/输出17681 token。
- seq245第二批REQ-1-3-2/REQ-2-1-3/REQ-2-1-1在20回合、1探针后completed/committed=true，连同首批内部累计7项，不等于7个官方测试通过。
- seq248—392第三批20回合、0探针、未提交、changed_files空；tool_result计数read_file26/read_files1/read_requirement_spec3，无写入。15次context_compacted，source_snapshot_bytes范围123—24236。
- seq393拆分。seq394—523单项REQ-2-2-1仍20回合、0探针、未提交，但有候选修改；工具计数read_file16/read_files1/replace_text9/run_validation1/search_text1/inspect_reference1。
- seq524开始剩余两项；latest seq549 request78在途。

这是重复读取/收尾不足的症状，不足以确定具体冗余、上下文丢失或模型内部根因。等最终封印轨迹核验参数/返回正文后再修复，不因等待额外调用模型或放宽验收。

## 收尾

本地标签741295081关闭；核对PID3622 cwd后TERM，会话11746以143结束，19439无监听。临时副本/合成CSV/归档保留，无删除；未编辑生成应用、未推送或上传。候选仍b5652fc，正式仍c3887cd。
