# 安全与部署约束

## 2026-11-08 工作台增量

- **工作空间是硬门禁**：私有空间只有所有者/成员可读；共享空间所有登录用户可读、仅 staff/owner/editor 可写；staff 不自动获得私有空间访问权。API、任务、产物、原文页均按空间校验。
- **索引隔离**：同一文件上传到不同空间使用加盐 `document_hash`，切片 ID 使用目标文档哈希；检索通过 `document_ids` 与 Chroma `document_hash` 过滤，不依赖“检索后删除”。
- **上传边界**：文件名 sanitize、扩展名 allowlist、20 MB 限制、上传目录隔离；解析器不执行文件内容。私有上传默认不进入共享课程空间。
- **Skill 不授权**：Skill 的 `allowed-tools` 只能收窄服务端交集；YAML `safe_load`、路径穿越/符号链接/大小限制；上游脚本不执行；开发 Skill 仅参考，未安装。
- **代码分析不执行用户代码**：只读检索 + 静态模式 + 文本建议 diff；产品任务状态固定 `UNVERIFIED`。Piston/Judge0 仍为可选且未验证；禁止回退到宿主 subprocess。
- **任务运行**：SQLite 短事务领取 + lease/heartbeat；取消在步骤间检查；外部副作用不明时不盲目重试；不保存完整 chain-of-thought 与密钥。
- **产物下载**：需要任务所有者或空间读权限；`Content-Disposition: attachment` + `nosniff`；HTML 产物由转义渲染器生成。
- **本地部署**：仅监听 `127.0.0.1`；不暴露公网；既有 `.env`/加密主密钥/数据库不覆盖；停止脚本只结束本项目 PID 并校验命令与工作目录。

学生代码不在 Django 主机上 exec、eval 或普通 subprocess 执行。唯一执行边界为配置的隔离 Piston / Judge0。禁止挂载应用目录、SQLite、`.env` 到执行容器；配置实例时要求禁网、CPU/内存/输出约束由服务实际落实。公共执行权限不足必须返回 JUDGE_ERROR，不提供危险本地回退。

开发 `.env` 权限 0600，生产 SECRET_KEY 与 APP_ENCRYPTION_KEY 强制配置；备份主密钥，勿写 Git 或日志。个人 Key 按认证用户查找、Fernet 加密，只回传掩码。轮换时设置新的 APP_ENCRYPTION_KEY 和旧 APP_ENCRYPTION_PREVIOUS_KEYS，运行 `manage.py rotate_api_keys`，确认全部数据能够解密后移除旧密钥。改动主密钥但不保留旧值会使已有 Key 不可恢复。

数据详情、工具查询、图谱、聊天、提交、错题与报告按 request.user 过滤。身份不能由浏览器或模型指定。管理员 / 教师审核采用 Django admin staff 权限；普通学生不能审核勘误或查看其他学生数据。数据库按课程规模单机 SQLite IMMEDIATE 事务串行化。

所有写请求启用 CSRF，无 csrf_exempt。Session HTTPOnly、SameSite=Lax，生产 Secure Cookie、HTTPS 重定向、HSTS、DEBUG=False。模板自动转义；Markdown 用 DOM textContent 构造，只允许 http/https 链接，不运行 AI 输出 HTML。隐藏测试用例的 stdout/stderr 可能回显秘密输入，因此不对学生显示。

AI、执行和外部百科 URL 仅由管理员配置，学生无法传入 Base URL，requests 不跟随重定向。工具资料 / PDF / 网络内容为不可信数据，不能覆盖系统规则、改变当前身份或直接修改掌握度。工具调用限制 schema、次数、签名重复与时间；API 预算和限流使用持久化事务。

日志只保存请求 ID、错误类型、状态和脱敏概要，不打印请求正文、Key、上游响应或推理内容。真实 usage 缺失时保守保留预算，避免并发请求绕过限额。请求超时不证明服务商没有扣费，前端不得冒充精确账单。

当前提供课程工程级保护与测试，未做正式渗透测试；本机独立 VM 执行探针的原始结果见 tests/evaluation/isolation_results.json；生产仍需进一步审计，并使用 HTTPS 反向代理限制请求体与连接。运行项目不应把 127.0.0.1 开发服务器直接暴露公网。

本机部署使用无应用目录挂载的 Lima VM，官方 Piston privileged 容器只存在于该 VM。服务与包缓存均绑定主机回环地址；禁网和资源限制由 Isolate 实施。启动脚本检查 VM/容器配置，不向 VM 传入 Django 或用户 DeepSeek 凭据。详见 deployment/LOCAL_EXECUTION.md。
