# DOM 挂载检查的最小误判复现

2026-09-25。只使用本地人工合成、无参赛业务的样例，不访问隐藏测试、他人提交、真实账号或模型。

## 旧检查与真实浏览器冲突

旧代码把挂载方法第一个右括号当成参数列表结束，无法识别：

```javascript
const details = document.createElement("p");
details.textContent = "Attached result";
document.body.append(document.createTextNode("Prefix: "), details);
```

同样问题影响 `prepend`、`replaceChildren` 的后续节点参数。新增回归先在旧版执行，三个子例均被误判为 `never attaches`。真实浏览器样例 `dom-attachment-fixture/frontend/src/` 的段落和已命名输入框也被旧检查误拒。

样例通过 Python HTTP 服务仅监听 `127.0.0.1:19434`。Chrome 正常 DOM/可访问树显示：段落 `Attached result`、textbox `Diagnostic value`、button `Echo value`。对 textbox 输入 `nested-sibling-ok` 并点击按钮后，真实 status 显示 `Value: nested-sibling-ok`。采集的 error/warn 日志为空；服务收到无关的 favicon 404，不作为应用交互失败或“网络零错误”声明。验证完成后停止服务并确认端口无监听。

## 最小修订与边界

保留旧挂载、包装调用、返回和激活识别，增加一层嵌套前置参数的识别。没有关闭 interaction_policy，没有改变安全隔离、构建/启动、语法、行为探针或晋升条件，也没有额外 LLM 调用。正则仍是有限语法启发式，不宣称能证明任意 JavaScript 的数据流或完整无障碍行为。

回归覆盖合法嵌套前置参数、没有挂载目标的反例、缺少可访问名称的输入框仍拒绝、旧包装节点识别保留及人工浏览器样例。37 项相关工具/检查回归通过。最终完整回归见主改进记录。

本次是在观察 f3 stdout 的挂载错误后主动构造的独立复现。平台当时显示工作区文件不可用，未取得对应 f3 源码，**不能据此认定 f3 第101行就是同一问题**。新检查仅进入下一本地候选，不热换或取消正在运行的 f3。
