# Wikipedia 与离线学习增量开发报告

日期：2026-10-13。基于既有 AlgoMentor 增量实现；基线提交 `dc65434`。保持原 Django、个人 BYOK、DeepSeek 档位、掌握算法、学习统计、知识网络与代码隔离架构。

## 1. 本次新增功能

- Wikipedia 官方 Action API：搜索后进行标题相关性判断，再获取摘要、页面ID、修订、语言、链接和真实时间；处理重定向、歧义、空摘要、限流、超时、异常JSON及来源白名单。
- SQLite 公共缓存：缓存真实百科资料与公开概念别名，七天TTL集中配置；有效缓存、过期缓存和实时数据分别标记，刷新失败保留旧内容。公共缓存不包含学生原问题、聊天或Key。
- LangChain 原工具兼容与 `search_wikipedia`：课程证据优先，明确百科要求与安全扩展概念触发真实工具；外部来源持久化到本用户聊天引用。百科和学生查询可组合，无付费模型替换或虚构调用。
- 本地学习与独立百科入口：`/knowledge/local/` 不调用AI或Wikipedia外网；`/knowledge/wikipedia/` 无Key即可查询。已有知识网络、算法、学习记录、错题、推荐和报告保持可用。
- 外部服务独立状态与恢复：业务请求更新状态，普通状态读取不探测。网络、个人Key/额度、具体模型分别隔离；冷却后半开重试，真实成功恢复，无须重启。
- 私有代码草稿：SQLite按用户+题目/实验区隔离，手动保存/载入，不自动发往执行服务、不计成绩。
- 真正本地模型与静态资源：BGE默认local_files_only，首次下载由管理命令显式执行；模型/索引维度不变。WhiteNoise为DEBUG=False提供collectstatic后的本地资源。

## 2. 实际新增和修改文件

下列清单来自本次 Git 差异；未修改掌握度算法、推荐评分、原有迁移或既有实验结果。

| 文件 | 作用 |
| --- | --- |
| `.env.example` | 新增百科、缓存、冷却和离线配置示例 |
| `ARCHITECTURE.md` | 补充缓存、状态隔离与真实工具路由边界 |
| `README.md` | 保留原内容，新增两个功能章节与模型准备步骤 |
| `WIKIPEDIA_OFFLINE_REPORT.md` | 本次增量开发与验收报告 |
| `apps/accounts/services/credential_service.py` | 更换密钥时清理本用户旧服务错误状态，不改变加密 |
| `apps/agents/migrations/0002_service_availability.py` | 新增表或公开别名的非破坏性增量迁移 |
| `apps/agents/models.py` | 持久化独立服务可用性状态 |
| `apps/agents/services/agent_factory.py` | 在真实LangChain中调用注册百科工具，保留模型/思考档位 |
| `apps/agents/services/agent_service.py` | 百科路由、服务预检与结构化来源返回 |
| `apps/agents/services/tool_registry.py` | 新增search_wikipedia并保留旧工具名 |
| `apps/agents/services/trace_service.py` | 保留真实百科来源及失败状态 |
| `apps/agents/tests/test_agents.py` | 原百科传输测试适配官方ActionAPI，保留原断言目的 |
| `apps/agents/tests/test_wikipedia_routing.py` | 百科/离线/来源路由/权限/草稿或真实API集成测试 |
| `apps/agents/tools/external_search_tool.py` | 旧Provider委托唯一百科服务，兼容原返回键 |
| `apps/knowledge/management/commands/prepare_embedding_model.py` | 显式模型下载或离线缓存完整性检查 |
| `apps/knowledge/management/commands/warmup_wikipedia.py` | 管理员主动、可重跑、限速的缓存预热 |
| `apps/knowledge/migrations/0002_wikipedia_cache.py` | 新增表或公开别名的非破坏性增量迁移 |
| `apps/knowledge/migrations/0003_public_wikipedia_aliases.py` | 新增表或公开别名的非破坏性增量迁移 |
| `apps/knowledge/models.py` | 公共百科缓存、公开概念别名及时间/修订元数据 |
| `apps/knowledge/services/embedding_service.py` | 默认只加载已有本地BGE模型，索引标识不变 |
| `apps/knowledge/services/wikipedia_service.py` | 唯一官方搜索/摘要/缓存/白名单/降级实现 |
| `apps/knowledge/tests/test_local_pages.py` | 百科/离线/来源路由/权限/草稿或真实API集成测试 |
| `apps/knowledge/tests/test_offline_embedding.py` | 百科/离线/来源路由/权限/草稿或真实API集成测试 |
| `apps/knowledge/tests/test_wikipedia.py` | 百科/离线/来源路由/权限/草稿或真实API集成测试 |
| `apps/knowledge/urls.py` | 本地学习与独立百科页面路由 |
| `apps/knowledge/views.py` | 本地检索、缓存-only与非LLM百科接口 |
| `apps/problems/migrations/0002_code_draft.py` | 新增表或公开别名的非破坏性增量迁移 |
| `apps/problems/models.py` | 用户隔离的CodeDraft模型 |
| `apps/problems/tests/test_drafts.py` | 百科/离线/来源路由/权限/草稿或真实API集成测试 |
| `apps/problems/urls.py` | 私有草稿API路由 |
| `apps/problems/views.py` | 草稿字节校验、手动保存/载入，不创建评测证据 |
| `apps/reports/services/crew_service.py` | 已知模型不可用时快速拒绝新生成 |
| `apps/reports/services/report_service.py` | 队列前按当前模型检查，不影响历史报告/统计 |
| `apps/tutor/services/chat_service.py` | 课程优先与百科来源持久化，保留原引用结构 |
| `config/settings/base.py` | 可选配置默认值及参数校验 |
| `config/settings/production.py` | WhiteNoise本地生产静态资源 |
| `config/urls.py` | 新增状态、本地知识与百科JSON接口 |
| `core/execution/availability.py` | 统一记录真实执行可用性，学生代码错误不记服务故障 |
| `core/execution/judge0_client.py` | 接入执行服务状态，不改变判题接口 |
| `core/execution/piston_client.py` | 接入执行服务状态，不改变沙箱边界 |
| `core/execution/test_execution.py` | 原传输测试使用隔离测试数据库保存服务状态 |
| `core/llm/deepseek_client.py` | 网络/个人授权/具体模型故障隔离与冷却恢复 |
| `core/services/__init__.py` | 轻量服务模块包入口 |
| `core/services/availability.py` | 持久化状态、原子半开恢复、多用户/多模型隔离 |
| `core/services/test_availability.py` | 降级、恢复、预算和用户/模型状态测试 |
| `core/views.py` | 只读无付费探测的服务状态API |
| `knowledge/wikipedia_keywords.json` | 十八项真实核对的双语公共概念与说明 |
| `requirements.in` | 增加WhiteNoise 6.12.0直接依赖 |
| `requirements.txt` | 锁定WhiteNoise运行依赖 |
| `scripts/bootstrap.py` | 新克隆创建SQLite父目录，首次显式准备模型后再入库 |
| `scripts/offline_probe.py` | 新WSGI进程、外网阻断、数据库副本的实际离线验证 |
| `scripts/verify_offline.py` | 运行冷启动并保存实际证据 |
| `static/css/app.css` | 延续现有风格的状态/本地学习/草稿样式 |
| `static/js/app.js` | 共享来源卡片展示百科语言、时间、缓存与署名 |
| `static/js/chat.js` | 模型对应状态检查与本地学习引导 |
| `static/js/code.js` | 执行状态检查、手动草稿保存与载入 |
| `static/js/knowledge.js` | 本地学习入口，不影响原课程检索 |
| `static/js/offline-learning.js` | 非LLM本地/Wikipedia查询交互 |
| `static/js/reports.js` | 报告服务状态提示与冷却检查 |
| `static/js/services.js` | 只读取本地状态，不作外网/付费探测 |
| `templates/base.html` | 独立服务状态组件和本地学习导航 |
| `templates/knowledge/index.html` | 百科与本地学习入口 |
| `templates/knowledge/local.html` | 课程原文、百科历史缓存与本地功能汇总 |
| `templates/knowledge/wikipedia.html` | 公开概念搜索、实时/缓存切换与许可署名 |
| `templates/problems/detail.html` | 私有代码草稿与执行服务提示 |
| `templates/reports/index.html` | 服务不可用时保留历史报告与明确提示 |
| `templates/tutor/chat.html` | AI不可用提示及本地/独立百科入口 |
| `tests/evaluation/offline_cold_start.json` | 本次新增实际验证证据，保留原实验文件 |
| `tests/evaluation/student_data_preservation.json` | 本次新增实际验证证据，保留原实验文件 |
| `tests/evaluation/wikipedia_agent_live.json` | 本次新增实际验证证据，保留原实验文件 |
| `tests/evaluation/wikipedia_incremental_tests.json` | 本次新增实际验证证据，保留原实验文件 |
| `tests/evaluation/wikipedia_keyword_review.json` | 本次新增实际验证证据，保留原实验文件 |
| `tests/evaluation/wikipedia_live_results.json` | 本次新增实际验证证据，保留原实验文件 |
| `tests/integration/test_live_wikipedia_agent.py` | 百科/离线/来源路由/权限/草稿或真实API集成测试 |
| `DELIVERY_REPORT.md` | 保留原验收记录并链接增量报告 |
| `TESTING.md` | 新增本轮回归与冷启动说明 |
| `tests/integration/test_bootstrap.py` | 新克隆数据目录与既有配置保留验证 |
| `tests/evaluation/wikipedia_browser_qa.json` | 本轮实际浏览器查询及来源展示证据 |

## 3. 系统运行方式

发现并修复了新克隆缺少空 data 目录的初始化问题（Git不保留空目录）；bootstrap会创建SQLite父目录，既有数据不改写。现有环境只需更新依赖、应用增量迁移，然后启动。不要重新bootstrap现有学生库。

```bash
cd AlgoMentor
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py prepare_embedding_model --check-only
.venv/bin/python scripts/local_piston.py start
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

另开终端在相同目录执行 `.venv/bin/python manage.py report_worker`。本机Web与Worker已重启并实际运行。首次缺少模型时联网执行 `prepare_embedding_model`，正常查询不会自动下载。生产静态执行 `collectstatic --noinput --settings=config.settings.production`。

缓存预热（已实际执行四项，成功四项）：

```bash
.venv/bin/python manage.py warmup_wikipedia --query '红黑树' --query 'KMP算法' --query '二叉搜索树' --query 'Dijkstra算法' --interval 1
.venv/bin/python manage.py warmup_wikipedia --interval 1
```

第二条为可选的全审核词表预热，重复执行跳过有效缓存；支持`--language`、`--config`、`--limit`、`--force-refresh`，不在服务器启动时批量请求。

离线验收（不更改主机网络，不写真实学生数据库）：先确认本地模型/向量索引已准备、已有注册账户、预热红黑树缓存，并收集静态文件。

```bash
.venv/bin/python manage.py collectstatic --noinput --settings=config.settings.production
.venv/bin/python scripts/verify_offline.py
ALGOMENTOR_LIVE_WIKIPEDIA=1 .venv/bin/pytest -q tests/integration/test_live_wikipedia_agent.py
ALGOMENTOR_LIVE_EXECUTION=1 .venv/bin/pytest -q tests/integration/test_live_execution.py
```

配置示例见 `.env.example`。Wikipedia开关、默认/补充语言、请求超时、缓存天数、User-Agent、自动历史缓存回退、服务重试间隔和本地模型模式都具有默认值与校验；缺失可选配置不会阻止启动。

## 4. 测试结果

| 验证 | 实际结果 | 证据 |
| --- | --- | --- |
| 开发前原有回归 | 218 passed、1 skipped，8.67秒 | 本机data/pytest-before-wikipedia.log |
| 最终自动回归 | 320 passed、2 skipped（完整日志见证据） | wikipedia_incremental_tests.json；本机data/pytest-wikipedia-final.log |
| 指定百科联网四题 | 红黑树、KMP、二叉搜索树、Dijkstra全部成功；扩展合计6/6 | wikipedia_live_results.json |
| 人工预热词表核对 | 18/18：17中文、循环队列为English Circular buffer | wikipedia_keyword_review.json |
| LangChain +真实百科 | 1 passed，2.96秒；真实官方HTTP与工具调用，规划LLM明确使用测试替身 | wikipedia_agent_live.json |
| 真实评测闭环回归 | 1 passed，1.76秒；实际Piston，隔离pytest数据库 | wikipedia_incremental_tests.json |
| 离线冷启动 | PASSED：全新WSGI进程，外部DNS/socket与主机代理均阻断，DEBUG=False本地静态、BGE/Chroma、课程/图谱/算法、真实百科历史缓存、本机隔离Python、草稿与学习记录均通过 | offline_cold_start.json |
| 学生数据保留 | 原有账户、聊天、提交、掌握、错题与报告行的只读指纹核对未变 | student_data_preservation.json |
| Django/迁移/依赖 | 系统检查无问题；No changes detected；No broken requirements found | 实际命令输出 |
| 浏览器 | 实际查询Wikipedia缓存并显示原时间/来源/语言；本地检索返回四条课程证据 | 本机output/screenshots/wikipedia-cache.png、local-learning.png |

两个默认跳过项均已显式单独运行通过。Wikipedia真实测试不使用Mock；LangChain联网集成的模型规划是测试替身，不能当作DeepSeek端到端推理验收。降级、冷却恢复、权限和不同模型错误隔离以实际业务代码配合HTTP测试替身验证。未为本次验收调用用户付费DeepSeek。

原始实验JSON没有被本次覆盖。新增证据均保存在 `tests/evaluation/`，运行日志、数据库备份与未脱敏原始证据不进入公开仓库或源码压缩包。

## 5. 已知限制

- 完整离线学习要求本地或局域网Django可访问、依赖/模型/向量索引已准备。浏览器失去与云端Django的连接不在此支持范围，未实现完整PWA或跨数据库同步。
- DeepSeek新的生成和CrewAI报告仍需有效Key、额度及网络。维基实时数据仍需网络；离线仅能读取已经保存的百科内容。没有缓存时明确无资料。
- 本机Piston VM运行时可离线执行；远程执行服务不可达时不能评测。草稿不会自动执行或增加掌握度。
- 服务状态描述最近真实调用，UNKNOWN不等于失败；恢复通过限频后的实际请求验证，不做付费模型后台健康探测。
- Wikipedia采用保守标题相关性与人工公共概念别名，不保证任意复杂自然语言问题都能找到条目。英文原文会保留实际语言，无模型时不假装翻译。
- 未新增生产渗透测试、三个DeepSeek档位的专项线上推理或CrewAI付费生成验收；原有隔离内存探针的OOM原因未独立证明这一限制仍保留。

官方依据：[MediaWiki Action API](https://www.mediawiki.org/wiki/API:Main_page)、[Wikimedia User-Agent政策](https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy)、[Wikipedia内容使用与署名](https://en.wikipedia.org/wiki/Wikipedia:Reusing_Wikipedia_content)、[WhiteNoise Django部署](https://whitenoise.readthedocs.io/en/stable/django.html)。
