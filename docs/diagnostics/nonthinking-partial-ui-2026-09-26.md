# fb84f4e 生成期副本：独立入口与会话检查

## 来源与隔离

正式运行465e25b12c29在18m11s仍明确Stage2 Running agent、Stage3 Evaluation pending时，文件页正常请求一次project.zip。下载原件`/Users/zerongliu/Downloads/465e25b12c29-template.zip`；归档`dist/official-evidence/465e25b12c29/project-partial-repositories.zip`，3310399字节，SHA `0b90e79f1f2dc54a73436c497cb76adc657d75838011f13c436b455f610f960a`。

这是生成期中途应用副本，不是最终包，不保证与后续晋升内容相同。只白名单提取11个frontend/backend文件，未提取或读取隐藏测试、平台评分数据或他队内容。先检查脚本/源码：无外部依赖，npm build仅复制本地src到该副本dist，网络请求为相对本地API。克隆地址仅为页面字符串，未访问GitHub。

本地目录`/private/tmp/factory26-nonthinking-qa.YACB84/template`；独立构建成功，HOST=127.0.0.1/PORT=19441启动node（PID32655），Chrome页741295086通过正常用户操作检查。使用副本中已有合成账号，不是参赛平台或用户真实凭证。未修改生成代码；仅本地登录产生一条合成session。

## 已观察行为

1. 首页 → Acme Demo → Repositories正常可达，不需要浏览器后退或手工改URL；列表有公开仓库，名字筛选到不存在值显示No repositories found，清空恢复。
2. 匿名Private筛选无仓库，Public显示acme-docs；不据单一匿名用例声称完整权限体系通过。
3. 公共仓库详情显示名称、可见性、说明、默认分支及文件入口。README.md能从页面打开，刷新后内容/路径/分支/提交信息保留。
4. Code按钮弹出Clone，点击SSH后克隆值确实变化；但HTTPS依旧aria-selected=true、SSH=false。这是已实测的可访问选中态与实际协议不一致，不推测其官方得分影响。本轮没有执行复制或读取系统剪贴板。
5. 明确缺陷：合成alice-dev登录后页头显示用户名和Sign out；刷新同一页立即变成Sign in。源码及本地状态证据显示session持久保存userId=u-alice（对应记录真实存在），恢复会话却调用按username查找的findUser(state, session.userId)，因此找不到用户。

会话问题不是“刷新前后session丢失”：副本刷新后仍有1条session，其userId按id查找为true、按username查找为false。没有把session令牌或合成密码写入本文。该副本不实现注册，初批注册失败已被harness丢弃；此处查的是后续需求为自身场景生成的登录支撑路径。

筛选测试中首次自动化fill("")未清空控件，已从DOM value确认仍有旧值，再用正常全选/Backspace清空后重验；不将工具未清空误报为应用筛选缺陷。

## 源码不变与清理

后端server.mjs SHA `93fa24439183bf3936c2d39c8b2ad2424ebf895bd2ef75d8c5b2cb1cfa86deec`；前端app.js SHA `98ee65ca3416118bb7808c873d021978e9acd746cce10fcc625e6f93f7941ebd`。10个非数据源文件与原ZIP逐字节相同。只在本地创建构建产物和合成会话，未修补远端/本地业务代码以冒充agent结果。

检查完成后关闭Chrome本地页，对确认监听19441的PID32655发送SIGTERM，执行会话确认退出143。远端正式运行未取消、重启或改写。

## 对下一轮的意义

内部探针只验证所选流程，不自动覆盖全部身份/角色变体；即使局部浏览通过，跨页面会话主键错配仍会破坏后续场景。后续应从最终封印轨迹核对需求/模型探针覆盖，优先检验共享状态契约的稳定ID关联与刷新后身份连续性。不要针对这个题目预置账号、路由或修复业务代码，也不要据此放宽验收。新失败现场回传候选可能改善定位错误，但不会自动修复本次会话问题。
