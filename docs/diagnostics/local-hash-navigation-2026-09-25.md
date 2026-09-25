# 站内哈希导航兼容性

## 证据与因果边界

12cc147正式运行`1844901550a1`在恢复账号批次的seq539/545连续报告“browser navigation must use a local path beginning with /”。stdout不显示请求参数；完整生成轨迹尚未封印，所以不能确定这两次是否提交了带哈希的路径，也不能宣称此修订解释了全部线上失败。

独立确定的缺陷：本队已下载中途应用实际使用`#/signin`、`#/register`、`#/workspace`路由，旧`validate_steps`却把`/#/signin`拒绝，仅因为urlsplit结果含fragment。这个完整目标的scheme/netloc仍为`http`/`127.0.0.1:33563`，不是外部导航。旧错误还暗示缺少前导斜杠，实际已经有斜杠。

## 修订与不变边界

- 接受以`/`开头的本地路径所带query/fragment；仍拒绝完整URL、`//`、反斜杠、控制字符、无前导斜杠与超长输入。
- 导航仍采用固定loopback基址加路径，不使用可改变基址的urljoin。不新增JavaScript执行或CSS选择器。
- 同端口网络拦截、每步导航后hostname/port校验、页面错误失败、源隔离、预算和行为断言全部保持。
- 观察结果的`path`保留实际hash路由，不能把不同SPA页面都报告成`/`；不包含origin。原有轨迹脱敏仍适用。
- 工具schema提供`/path`和`/#/route`示例，错误文本明确禁止项。完整规格中的链接角色与页面入口仍应遵守；支持直接导航不允许绕过功能要求。

## 验证

四项新增单元测试覆盖：query/hash保留与固定origin、外部/协议相对/反斜杠/控制字符拒绝、精确goto参数及断言/scope回转、观察结果真实hash路径。既有外网请求阻断失败测试继续保留。原`/safe#fragment`拒绝用例变为有效本地路径用例，有意修正原错误合同，而非删除外网拒绝要求。

真实Chrome使用已审查的中途应用隔离副本，源码哈希与`12cc-partial-identity-review.md`一致：直接打开`http://127.0.0.1:33563/#/signin`得到登录页，按页面已显示的注册路由直接导航到`/#/register`得到注册表单，刷新仍停留正确注册页。未注册新账号或改源；检查后页面关闭、服务停止。该真实浏览器证据不是Python Runner整合测试，三项环境跳过仍如实保留。

初始聚焦64项/61通过/3跳过，6.839秒；加入观察路径修订后，全量288项/285通过/3浏览器环境跳过，63.687秒。上下文限额和原有安全/回归测试没有放宽。当前正式在途仍是12cc147，不含这些改动。既有1628eea ZIP也不含本轮路由修订，不可误作最新包。

## 候选制品

干净源码`af7d4ad3212bf747e540d1b3fce81b50c16f9209`，`dist/langqi-forge-local-navigation.zip`：20文件、186,994字节，SHA-256 `5ac3f718d2b66858a61f71d302132ec5b196e15f9de91f46c937d80b0b9b5e24`。独立解包`/private/tmp/factory26-local-navigation.Fdpa7l`核验19runtime文件与真实导入路径、合同SHA`028f9ae2f502868097dbc785ddfcdded2916a7eb0fe3fef79a9d07b2dadc174b`、CRC和路径参数回转/拒绝。未上传平台或推送源码，也没有额外模型调用。
