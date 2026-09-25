# Pro组织浏览产物的独立检查

本队正式运行`359dd7e72ca7`，参赛源码c3887cd、编码deepseek-v4-pro。组织浏览REQ-2-1-1内部晋升后，从正常“文件 → project.zip”界面取得中途副本，未修改在途应用，未读取隐藏测试。本页不是官方GUI得分或最终生成产物验收。

## 制品与隔离

- 下载：`/Users/zerongliu/Downloads/359dd7e72ca7-template (1).zip`。
- 归档：`dist/official-evidence/359dd7e72ca7/project-partial-org.zip`，41成员、3,309,600字节，SHA `5de0c9d83461aca8c685688e816ebc35dce4ac0c1174f43faea559cd04a7c977`，CRC通过。
- 只解包11个frontend/backend应用文件到`/private/tmp/factory26-pro-org.youcwn/template`；公开REQ-2-1-1从相同任务的requirements.yaml读取，无评分期数据或其他队伍内容。
- 两次中途下载的公开requirements.yaml SHA一致：`bdc17d23265a6b1948aec150e69d0b2accfa37db4c569305c97be7ff7f3b0b8f`。
- 后端SHA `9c22bc37924a880c2b12e748880cc0a54b093a0b0e1faba943fe96704e936322`；前端app.js SHA `ecc249786912a43f90c6598b2f8f8db60b2b4c8fc179768a28e6a3e9900a66e1`。检查前后源码与下载件哈希不变。
- 先审查全部后端、前端与构建/辅助模块，无安装或外部模型调用；空继承环境构建，本机仅`127.0.0.1:19438`监听。只使用公开任务的虚构账号与本地会话，不输入真实身份或平台密钥。

下载曾长时间显示Packaging，新打开的同一运行页也等待加载；后来下载与读取恢复。未依据观察超时取消、重复下载或重新运行评测。

## Chrome实际操作

1. 新访客从首页可见Acme Demo链接进入组织页；Repositories是真实链接，Find a repository标签与Visibility选择器存在。
2. 输入acme-docs并选择Public后即时显示公开结果及描述、可见性和更新时间；点击后标题为acme-demo/acme-docs。
3. 浏览器Back返回后公开结果仍可见；输入私有名acme-secrets并选择Private，没有仓库链接，显示No repositories found。
4. 刷新后仍只有公开仓库链接（public=1，private=0）。直接打开该本地私有仓库地址，显示Repository not found or access denied。
5. 按公开Scenario 2，从首页Sign in，以任务给定的alice-dev合成身份登录。**发现入口缺口：登录落到Workspace，只有Sign out按钮，没有任何链接；刷新后links仍为0。** 无首页/组织入口可继续应用内导航。用浏览器Back两次可回首页，再点组织后正常显示公开仓库，因此不能写成组织功能完全不可用。
6. 浏览器error/warn采集为空；它不代表全部交互或权限矩阵通过。

第5点是公开流程的具体可用性问题，也是“访客探针通过不能覆盖登录后场景”的反例；不能凭它单独预测官方失败数。尚未验证拥有私有授权的账号、团队权限变更、组织/团队创建或后续模块。

## 独立接口检查

`pro_org_visibility.py`限制为已审查哈希的临时副本和固定本地端口，禁用代理/重定向，不接任何远端平台。实际10项检查全部通过：健康检查；访客及无私有授权的已登录账号各自的公开列表、公开详情、私有直达404、所有读取后状态SHA不变；公开合成账号登录成功。该登录只新增本地合成会话，没有修改应用源码。

现有代码仍是比赛合成数据实现，不是生产认证系统。没有因接口检查通过就声称完整权限安全或满足所有官方场景。

## 收尾与正式运行

本地浏览器标签741295077已关闭；核对PID90120的cwd正是临时backend后TERM，会话76182以143退出，19438无监听。临时副本与原件保留以便复核，无文件删除。

官方页面已恢复：101m43s及103m26s明确Stage2完成、Generation agent finished successfully，Stage3 Evaluation in progress。尚无官方分数/人民币结算；下一步只读取生成阶段封印证据，不能继续从评分期数据反推隐藏用例。独立复核页741295076已关闭，原任务页保留。

109m28s交接现场仍Stage3评分，第二次下载请求（生成结束后的一次）仍Packaging，本机尚无`359dd7e72ca7-template (2).zip`。文件树只观察到临时`.factory26-evidence-i977c7i9.zip`，不是已核验的最终`factory26-evidence.zip`。源码显示SDK完成标记先于finally中的证据导出；因此界面阶段完成不能代替ZIP三成员、清单、封印哈希链和脱敏核验。不得把中途org包当最终轨迹，也不重复点击尚在打包的下载。
