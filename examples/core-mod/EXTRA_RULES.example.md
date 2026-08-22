复制本文件到仓库根目录并改名为 `EXTRA_RULES.md`,配合打过 `octos-core.diff` 的 core 生效(官方版 core 会忽略)。内容会追加到 agent 系统提示词末尾,超过 8000 字符截断。以下示例规则来自真实踩坑(判卷 Playwright 的 UI 期望):

- 输入框一律用纯文本型,不要 `type="date"` / `type="number"`。
- 每个表单字段配可见的 `<label>`。
- 校验用 JS 在页面上输出错误文字,不要依赖 HTML5 `required`。
- 按钮用真实 `<button>`,文案纯文本。
- 同一可见文案同屏只允许命中一个元素(strict mode)。
- 生成期间绝不在判卷端口(默认 3000)启动任何服务;冒烟测试用独立端口。
