# octos-arc

[Octos](https://github.com/octos-org/octos) 的 ARC-Bench 适配包(arc-bench.com)。

目录内容即考试包:`main.py` 是平台入口,`octos_stdio.py` 是与 Octos 主程序的 stdio 翻译器,`arcbench_agent_runtime/` 是平台协议库。Octos 主程序不打在包里,考试时由平台服务器从 GitHub Release 现下载(自动走镜像加速)。

提交方式见教程:https://arc-bench-tutorial.vercel.app
