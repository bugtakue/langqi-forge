# 魔改 Octos core 参赛:完整示例

场景:你 fork 了 [octos](https://github.com/octos-org/octos),改了一点 core 逻辑,想让**改过的版本**上场考试。本目录给出一条最短可行路径,附一个能真实 `git apply` 的示例 diff。

## 先分清:什么时候要动胶水层

| 你改的东西 | 胶水层(本仓库)要动吗 |
|---|---|
| core 内部逻辑(提示词、策略、工具行为),对外用法不变 | 代码不动,只需换二进制来源(见下) |
| 新增 env 开关这类"软接口" | 胶水加注入/透传(本示例干的事) |
| 改 `serve --stdio` 协议、CLI 参数、事件格式 | 同步改 `octos_stdio.py` |
| 平台契约(`main.py` 骨架、`arcbench_agent_runtime/`) | 永远不动 |

**最容易踩的坑**:适配包**不内置** Octos。考试时 runner 按 `main.py` 顶部的 `OCTOS_RELEASE_URL` 现场下载官方 Release——你改完 core 却不改这个地址,上场的仍是官方原版,**不报错、分数照出**,改动静默失效。

## 示例 diff 改了什么(`octos-core.diff`)

两处,共 42 行,基于 octos 主干(`3134173f`):

1. **`prompt_segments.rs`** — 系统提示词渲染末尾追加环境变量 `OCTOS_ARC_EXTRA_RULES` 的内容(没设置时行为与官方版逐字节一致)。这是"魔改"本体:给 agent 注入考场规则。
2. **`serve.rs`** — `serve --stdio` 启动时向 stderr 打一行 `[arc-mod] custom core active, extra_rules_chars=N`。这是"上场证明"标记。

配套的胶水改动**已在本仓库主干**,无需再改:

- `main.py`:发现包根有 `EXTRA_RULES.md` 就注入 `OCTOS_ARC_EXTRA_RULES`(官方版 core 会忽略该变量,所以带着文件也无害);
- `octos_stdio.py` + `main.py`:抓到 stderr 里的 `[arc-mod]` 标记,`log()` 双写进成绩单可见的日志。

## 全流程

1. **打补丁**:
   ```sh
   git clone https://github.com/你的账号/octos && cd octos
   git apply /path/to/octos-core.diff   # 冲突时先 git apply --check 看原因
   ```
2. **构建 + 打包**:照 octos 仓库自己的构建方式产出 Linux x86_64 的 `octos` 与 `octos-sandbox`,tarball 结构必须和官方一致(runner 只解这两个成员):
   ```sh
   tar -czf octos-bundle-x86_64-unknown-linux-gnu.tar.gz octos octos-sandbox
   ```
3. **换下载来源**:把 tarball 传到你 fork 的 GitHub Release,然后把 `main.py` 顶部 `OCTOS_RELEASE_URL` 常量改成你的 Release 地址。runner 上你设不了环境变量,**改常量是唯一可靠的方式**;镜像加速对任意 github.com 地址同样生效。
4. **(可选)启用规则注入**:把 `EXTRA_RULES.example.md` 复制为仓库根目录 `EXTRA_RULES.md`,写你的考场规则。
5. **提交考试**:`sh arc.sh pack …` 验证打包,`sh arc.sh submit …` 开考。
6. **验证魔改真的上场了**:成绩单日志里 grep `arc-mod`,应看到:
   ```
   [core-mod] [arc-mod] custom core active, extra_rules_chars=1234
   ```
   没有这行 = 跑的还是官方版,回查第 3 步的下载地址。
