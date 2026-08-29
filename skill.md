# ARC-Bench 提交技能(给 AI agent 执行)

你正在帮用户把一个 coding agent 提交到 ARC-Bench (https://arc-bench.com) 评测平台。按下面的步骤执行,遇到缺失信息先问用户。

## 需要向用户确认的信息

1. **ARC-Bench 账号**:邮箱和密码。没有账号的话,让用户先到 https://arc-bench.com 注册(约 1 分钟),再回来继续。
2. **agent 来源**:三选一——GitHub 链接、本地目录(需含 main.py)、或已打包的 zip。用户还没有自己的 agent 时,可以用参考实现 `https://github.com/octos-org/arc-adapter`(Octos 适配包)先跑通流程。
3. **题目**:默认 `ticketbooking`(复刻 12306 购票网站)。
4. **模型**:默认 `gpt-5.5`(当前最稳定)。备选 deepseek-v4-flash / gpt-5.6 / kimi-k3,详见教程。

## 执行步骤

```sh
# 1. 工作目录 + 下载提交脚本
mkdir -p ~/arc && cd ~/arc
curl -fsSLO https://raw.githubusercontent.com/octos-org/arc-adapter/main/arc.sh

# 2. 写入账号(两行:邮箱、密码)
printf '<邮箱>\n<密码>\n' > account.txt

# 3. 提交
sh arc.sh submit <题目> <模型> <agent来源>
```

输出出现 `started: <run-id>` 即提交成功。

## 提交后

```sh
sh arc.sh check
```

- 评测需要 40 分钟到 3 小时。`status` 从 `RUNNING` 变为 `COMPLETED` 或 `FAILED` 即结束。
- 不要高频轮询;告诉用户过段时间再查,或到 arc-bench.com 网页上看。
- 出结果后向用户解释:`score` 是测试通过率(如 9/36 = 25.0);**FAILED 不等于零分**,只要有测试执行过就有分,具体原因在 `failure_reason` 字段。

## 注意

- account.txt 里的密码只被 arc.sh 读取、只发往 arc-bench.com,没有其他网络请求。脚本源码: https://github.com/octos-org/arc-adapter/blob/main/arc.sh
- 常见报错(端口占用、"template is incomplete"、401/403)的处理方式见教程: https://arc-bench-tutorial.vercel.app
- 用户想写自己的适配包时,指引他看教程的「自定义 agent 提交」一节。
