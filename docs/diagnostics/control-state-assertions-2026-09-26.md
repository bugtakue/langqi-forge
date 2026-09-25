# 本地控件状态断言候选

## 有证据的缺口

生成期副本QA已发现：SSH克隆值发生变化，但HTTPS/SSH的aria-selected没有同步。对应生成轨迹的终审文字曾自报“aria-selected toggled”，实际浏览器探针只断言页面文字，没有状态读取能力。原始副本/哈希/操作见nonthinking-partial-ui-2026-09-26.md；自报不等于实测，部分副本也不能代替最终全部应用。不能据此断言该缺陷就是官方1/100的全部原因。

本修订给通用探针补充这类证据能力，不预置题目、标签、角色组合、路由或业务修复。模型仍只能依据当次公开需求选择检查对象。

## 合同

每步可另带至多4个expect_controls，例：

```json
{"action":"click","role":"tab","name":"Details","expect_text":["Details"],
 "expect_controls":[{"role":"tab","name":"Details","property":"selected","equals":true}]}
```

- 每个断言只接受唯一精确role+name或label及可选独立scope；拒绝CSS、JavaScript、任意属性和额外字段。目标必须存在、唯一且可见。
- 属性白名单：value、selected、checked、disabled。value要求字符串（允许空，至多500字符）；其他必须是真正Boolean，不把字符串false或数字0强转。
- value读取控件实际值并全量精确比较，不以截断前缀通过；返回最多500字符。password输入（大小写type均适用）不读取值。checked兼容明确ARIA或原生checkbox/radio；selected缺失/非法值返回未知，不能当作false。
- 状态与文字共同等待现有至多2秒的观察窗口；状态不匹配也进入原assertion_failures，因此原成功门、工具压缩、修复、独立重放都不能忽略它。
- 原16步骤、3次默认浏览器调用/5次绝对上限、隔离种子、loopback网络限制和模型预算不变，没有新浏览器或LLM调用步骤。单步多了最多4个状态观察，存在额外本地读取成本。
- 已通过流程精确保存新字段，独立胶囊重放不剥除状态断言。原“真实交互+至少一条正向文字”胶囊门保持；状态断言是补充，不许可仅reload或仅状态的流程绕过原门槛。
- 普通无新字段流程维持原验证输出结构。普通模式仍可仅文字验证，因此这是能力补足，并非自动完整需求覆盖；模型不用它或只测一个角色仍有盲区。

## 验证与回归修复

新增13项离线页/进程fixture覆盖schema与执行白名单、错误类型/数量、文字成功但selected失败、未知ARIA不当false、精确/空输入值、原生/ARIA选中态、禁用态、密码不读取、超长值不前缀通过、隐藏/缺失/重复控件、独立scope、异步状态等待、跨origin先阻断、失败压缩/封印/验证资格、真实隔离runner分支的断言计数，以及带正向文字的状态配方实际进入RegressionMemory重放。

首次全量351项发现小上下文测试超原8000字符（8314），缩短重复提示后仍为8025，再压缩网络边界重复措辞恢复；没有扩大上限或削弱断言。第二次全量发现入口指导的三个字面合同回归，恢复原“actual landing page / visible controls / direct-entry / cannot replace”指导后21项针对性通过，未修改原测试。最终冻结全量 **351项，348通过、3环境跳过，63.468秒**；git diff --check通过。

本地没有Python Playwright/匹配Runner Chromium的完整环境，既有3项真实浏览器集成测试继续按原条件跳过；本次fixture没有调用真实模型/浏览器，不能宣称正式效果已验证。辅助AST决策代理显示既有runtime函数无增长、新增最大14；不作为正式复杂度CI替代品。

主分支仍bounded编码策略，包含完整源码保留、失败现场回传及默认关闭completion tail；正式fb84f4e是另一独立源码，尚不含以上后续改动。本候选不热改、取消或并行打断Sheet运行。下一次是否提分必须靠同一新快照双题正式成绩与费用证明。
