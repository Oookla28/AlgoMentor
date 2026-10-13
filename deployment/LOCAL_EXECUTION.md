# 本机 Python 隔离执行

本机已部署 Python 3.12.0。网页的“运行代码”、完整题目评测和 Agent 执行工具共用这一服务，无需公共 Piston 白名单或个人 DeepSeek Key。DeepSeek Key 只用于模型请求。

执行链路为 `Django → 本机 HTTP → 独立 Lima Linux VM → 官方 Piston / Isolate → Python`。Django 不运行学生程序。VM 不挂载主机 home、项目、数据库或 `.env`，不转发 SSH agent；Piston API 只绑定主机 `127.0.0.1:2000`。Piston 需要 privileged 容器才能管理 Isolate，因此容器位于独立 VM 内。

## 已安装配置

|组件|本机配置|
|---|---|
|主机|Apple Silicon macOS；Rosetta 已安装|
|Lima|2.2.1；用户目录内安装，无 Homebrew 依赖|
|VM|`algomentor-exec`，Ubuntu 24.04，2 CPU、3 GiB 内存、12 GiB 稀疏磁盘|
|Docker|29.1.3；位于 VM 内，cgroup v2|
|Piston|官方 AMD64 镜像，固定 SHA-256 摘要；通过 Rosetta 运行|
|Python|官方 Piston 3.12.0 包，安装前与安装时均校验 SHA-256|
|容器外层上限|1536 MiB 内存、128 个进程|
|学生程序上限|按请求限制时间和内存，服务最大 3 秒、256 MiB、16 个进程、8192 字节输出；禁网|

版本、摘要及完整 VM 配置保存在 `scripts/install_lima_runtime.py`、`scripts/local_piston.py` 和 `deployment/lima-piston.yaml`。本机运行数据在 `~/.local/share/algomentor-execution/`，下载缓存在 `~/.cache/algomentor-execution/`，不会放入源码压缩包。

## 启动、检查与停止

在项目目录执行：

```bash
.venv/bin/python scripts/local_piston.py start
.venv/bin/python scripts/local_piston.py status
.venv/bin/python scripts/local_piston.py smoke
.venv/bin/python manage.py check_execution_service
```

`smoke` 与 `check_execution_service` 都真实运行固定 Python 程序，不能只靠运行时列表判断可用。当前 `.env` 中使用以下配置；修改后重启 Django 与报告 worker：

```dotenv
EXECUTION_PROVIDER=piston
PISTON_BASE_URL=http://127.0.0.1:2000/api/v2
PISTON_PYTHON_VERSION=3.12.0
```

关闭执行 VM 释放资源：

```bash
.venv/bin/python scripts/local_piston.py stop
```

网站仍可浏览课程。关闭执行服务后，运行/评测会明确报服务不可用；本次不计入成绩。重新执行 `start` 即可恢复，Python 包保存在 VM 命名卷中。

## 在另一台 Apple Silicon Mac 安装

要求 Python 3.12 项目虚拟环境和 Rosetta。先安装项目依赖，然后：

```bash
.venv/bin/python scripts/install_lima_runtime.py
.venv/bin/python scripts/local_piston.py start
.venv/bin/python scripts/local_piston.py install-python
.venv/bin/python scripts/local_piston.py smoke
```

首次下载 Lima、Ubuntu 镜像、Piston 镜像和 Python 包需要网络、磁盘空间与几分钟时间。脚本验证固定摘要，拒绝不匹配的缓存。它不会删除已有 VM；已有同名容器须具有 AlgoMentor 标签、指定镜像与规定限制，否则停止操作。

本机 macOS 下载代理无法被 Piston 的 Node 下载器直接使用，所以提供固定包缓存 `scripts/piston_package_mirror.py`。它仅在 `127.0.0.1:2099` 提供两条固定路由：索引和已校验的 Python 官方包；不提供任意文件或目录。Lima 通过内部网关访问缓存。缓存由管理脚本在后台启动，日志和 PID 写入运行目录。安装完成后的学生执行不需要下载网络。Docker/apt 可使用系统配置的无凭据 HTTP 下载代理；应用密钥和环境变量不会传入 VM。

## 实际验收

```bash
.venv/bin/python manage.py verify_judge
.venv/bin/python manage.py verify_problem_bank
.venv/bin/python manage.py verify_execution_isolation
```

结果分别保存在 `tests/evaluation/judge_results.json`、`problem_bank_results.json` 和 `isolation_results.json`。题库验收使用仓库参考解，不创建学生提交或掌握证据；隔离探针仅发送固定程序并保存实际返回值。本次结果为 8 PASS、0 FAIL、1 UNVERIFIED：内存分配被终止，但API缺少OOM元数据，无法独立证明终止原因。其余八项通过；输出限制明确返回OL，进程探针14个子进程后EAGAIN，CPU探针在独立墙钟3秒预算内约1秒CPU终止。含糊结果保留为 `UNVERIFIED`，不能据此宣称安全审计已通过。

历史 `JUDGE_ERROR` 保留为“评测未完成/无有效成绩”；服务恢复后需要学生重新提交，不能将历史错误自动改为通过。

官方实现说明：[Piston](https://github.com/engineer-man/piston)、[Lima](https://lima-vm.io/docs/)、[Docker daemon 代理配置](https://docs.docker.com/engine/daemon/proxy/)。该部署面向本机课程开发，未完成生产渗透测试。
