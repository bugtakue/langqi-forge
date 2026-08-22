# 修改 Octos core:完整示例

场景:fork 了 [octos](https://github.com/octos-org/octos),修改了 core 逻辑,要让修改后的版本参与评测。本目录给出一条最短路径,附一个可以 `git apply` 的示例 diff。

## 什么时候需要改胶水层

| 改动范围 | 胶水层(本仓库)操作 |
|---|---|
| core 内部逻辑(提示词、策略、工具行为),对外接口不变 | 代码不动,只换二进制来源(见下) |
| 新增 env 开关等软接口 | 胶水加注入/透传(本示例的做法) |
| 改 `serve --stdio` 协议、CLI 参数、事件格式 | 同步改 `octos_stdio.py` |
| 平台契约(`main.py` 骨架、`arcbench_agent_runtime/`) | 不动 |

**关键**: 适配包不包含 Octos 二进制。评测时平台按 `main.py` 中 `OCTOS_RELEASE_URL` 的值现场下载。改了 core 但没改这个地址,平台下载的是官方版——不报错,但改动不生效。

## 示例 diff 内容(`octos-core.diff`)

两处,共 42 行,基于 octos 主干(`3134173f`):

1. **`prompt_segments.rs`** — 系统提示词渲染末尾追加环境变量 `OCTOS_ARC_EXTRA_RULES` 的内容(未设置时行为与官方版完全一致)。
2. **`serve.rs`** — `serve --stdio` 启动时向 stderr 输出 `[arc-mod] custom core active, extra_rules_chars=N`,用于确认修改版生效。

配套的胶水改动已在本仓库主干:

- `main.py`:检测到包根有 `EXTRA_RULES.md` 时注入 `OCTOS_ARC_EXTRA_RULES`(官方版 core 忽略该变量,带着文件无影响);
- `octos_stdio.py` + `main.py`:捕获 stderr 中的 `[arc-mod]` 标记,写入评测日志。

## 流程

1. **打补丁**:
   ```sh
   git clone https://github.com/你的账号/octos && cd octos
   git apply /path/to/octos-core.diff   # 冲突时先 git apply --check
   ```
2. **构建**: 产出 Linux x86_64 的 `octos` 与 `octos-sandbox`,tarball 结构与官方一致:
   ```sh
   tar -czf octos-bundle-x86_64-unknown-linux-gnu.tar.gz octos octos-sandbox
   ```
3. **换下载来源**: 把 tarball 传到你 fork 的 GitHub Release,改 `main.py` 中 `OCTOS_RELEASE_URL` 为你的 Release 地址。runner 上无法设环境变量,改常量是唯一方式;镜像加速对任意 github.com 地址生效。
4. **(可选)启用规则注入**: 把 `EXTRA_RULES.example.md` 复制为仓库根目录 `EXTRA_RULES.md`,写入评测规则。
5. **提交**: `sh arc.sh pack …` 验证打包,`sh arc.sh submit …` 提交。
6. **确认生效**: 评测日志里 grep `arc-mod`:
   ```
   [core-mod] [arc-mod] custom core active, extra_rules_chars=1234
   ```
   没有这行说明跑的是官方版,检查第 3 步的下载地址。
