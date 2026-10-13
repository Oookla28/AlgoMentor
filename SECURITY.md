# 安全与部署约束

学生代码不在 Django 主机上 exec、eval 或普通 subprocess 执行。唯一执行边界为配置的隔离 Piston / Judge0。禁止挂载应用目录、SQLite、`.env` 到执行容器；配置实例时要求禁网、CPU/内存/输出约束由服务实际落实。公共执行权限不足必须返回 JUDGE_ERROR，不提供危险本地回退。

开发 `.env` 权限 0600，生产 SECRET_KEY 与 APP_ENCRYPTION_KEY 强制配置；备份主密钥，勿写 Git 或日志。个人 Key 按认证用户查找、Fernet 加密，只回传掩码。轮换时设置新的 APP_ENCRYPTION_KEY 和旧 APP_ENCRYPTION_PREVIOUS_KEYS，运行 `manage.py rotate_api_keys`，确认全部数据能够解密后移除旧密钥。改动主密钥但不保留旧值会使已有 Key 不可恢复。

数据详情、工具查询、图谱、聊天、提交、错题与报告按 request.user 过滤。身份不能由浏览器或模型指定。管理员 / 教师审核采用 Django admin staff 权限；普通学生不能审核勘误或查看其他学生数据。数据库按课程规模单机 SQLite IMMEDIATE 事务串行化。

所有写请求启用 CSRF，无 csrf_exempt。Session HTTPOnly、SameSite=Lax，生产 Secure Cookie、HTTPS 重定向、HSTS、DEBUG=False。模板自动转义；Markdown 用 DOM textContent 构造，只允许 http/https 链接，不运行 AI 输出 HTML。隐藏测试用例的 stdout/stderr 可能回显秘密输入，因此不对学生显示。

AI、执行和外部百科 URL 仅由管理员配置，学生无法传入 Base URL，requests 不跟随重定向。工具资料 / PDF / 网络内容为不可信数据，不能覆盖系统规则、改变当前身份或直接修改掌握度。工具调用限制 schema、次数、签名重复与时间；API 预算和限流使用持久化事务。

日志只保存请求 ID、错误类型、状态和脱敏概要，不打印请求正文、Key、上游响应或推理内容。真实 usage 缺失时保守保留预算，避免并发请求绕过限额。请求超时不证明服务商没有扣费，前端不得冒充精确账单。

当前提供课程工程级保护与测试，未做正式渗透测试；本机独立 VM 执行探针的原始结果见 tests/evaluation/isolation_results.json；生产仍需进一步审计，并使用 HTTPS 反向代理限制请求体与连接。运行项目不应把 127.0.0.1 开发服务器直接暴露公网。

本机部署使用无应用目录挂载的 Lima VM，官方 Piston privileged 容器只存在于该 VM。服务与包缓存均绑定主机回环地址；禁网和资源限制由 Isolate 实施。启动脚本检查 VM/容器配置，不向 VM 传入 Django 或用户 DeepSeek 凭据。详见 deployment/LOCAL_EXECUTION.md。
