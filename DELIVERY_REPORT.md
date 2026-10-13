# 数构智学开发与验收报告

> 本文保留初始发布版本的验收记录。Wikipedia 与离线学习增量的最新功能、320 项回归和冷启动证据见 [增量开发报告](WIKIPEDIA_OFFLINE_REPORT.md)。

记录日期：2026-10-13（Asia/Shanghai）。完整源代码位于 AlgoMentor/。本报告区分已实现、本机测试和真实服务验证。本机隔离执行已接通；线上 AI 全档位、CrewAI 与完整安全审计仍不能宣称全部验收通过。

## 第一部分：项目完成情况

已建立可运行 Django Web 系统、账户注册登录、个人配置与加密 BYOK、真实课程入库、五个 LangChain 工具、隔离评测适配、题库、提交 / 错题 / 学习活动、规则指数与 BKT、动态知识网络、学习路径、五个 Python 算法演示、真 CrewAI 报告队列、异常映射、个人预算与测试实验脚本。

本机可独立使用知识库检索、原文追溯、知识图谱、算法演示及学习分析。本机学生代码现由独立 Lima VM 内的官方 Piston / Isolate 与 Python 3.12.0 执行，无需公共执行授权。生成类功能仍使用网页个人 Key。历史执行失败保留为无有效成绩。

## 第二部分：模块实现说明

- accounts：Django 认证、学习目标、Fernet/MultiFernet 密钥、网页保存/删除/真实连接测试、按用户 usage 和事务预算。
- knowledge：保存完整原始课程 PDF，LangChain 切分、BGE 中文本地向量、Chroma 持久化、文档哈希、512维与索引版本、原文页码和片段详情、教师审核勘误。
- agents / tutor：create_agent、DeepSeek BaseChatModel 适配、思考字段正确回传、时钟 / ORM / Wiki / Chroma / 执行工具、真实调用 Trace、教学状态与分级提示。
- problems / learning：21道原创练习与89个服务端用例；真实远程执行适配，幂等提交与原子学习闭环、隐藏用例不泄漏、真实诊断接口、错题重做与复习、掌握度/快照/推荐。
- graph：45个知识点、4章及课程根节点，54条先修/关联关系，NetworkX DAG 校验、稳定布局、聚合进度、历史恢复、SVG 搜索/缩放/拖动/点击/原文/路径。
- visualization：单链表反转、KMP、BF、循环队列、顺序栈。所有帧由 Python 决定，播放和前后步由原生 JS 渲染。
- reports：Researcher 与 Writer、两个 Task、Process.sequential、crew.kickoff；客观数字使用 SQLite 快照生成并核验；后台 Worker 持久化任务和强制超时。

## 第三部分：真实测试结果

|验证|实际结果|证据|
|---|---|---|
|pytest完整测试|218 passed, 1 skipped in 7.83s（跳过项另作真实执行）|data/pytest-final.log|
|Django系统检查|无问题|实际 manage.py check|
|生产配置部署检查|无警告|实际 check --deploy --settings=config.settings.production|
|迁移一致性|No changes detected|实际 makemigrations --check --dry-run|
|依赖兼容|No broken requirements found|实际 pip check|
|课程入库|15页、35块、512维BGE向量|KnowledgeDocument / Chroma索引|
|BGE检索实验|9个库内问题全部Hit@4，2个库外返回无证据；所有来源元数据可核对|tests/evaluation/results.json|
|可信自编参考程序|89个本地课程测试通过|apps/problems/tests/test_catalog.py；不接受学生代码|
|本机Piston真实执行|Python3.12.0打印与网页输入4输出10通过|tests/evaluation/local_execution.json；output/screenshots/local-python-execution.png|
|题库真实执行|21题、89用例全部ACCEPTED，不创建学生证据|tests/evaluation/problem_bank_results.json|
|提交接口真实闭环|独立测试数据库内实际运行/错题/重做/掌握/幂等/用户隔离，1 passed in 1.75s|data/pytest-live-execution.log|
|本机隔离探针|8 PASS、0 FAIL、1 UNVERIFIED；内存终止原因未独立证明|tests/evaluation/isolation_results.json|
|历史公共Piston探测|HTTP401，需授权；当前本机执行不使用它|tests/evaluation/execution_probe.json|
|Judge0公开服务|HTTP403|同上|
|六类真实判题实验|6/6匹配预期，agreement=1.0|tests/evaluation/judge_results.json|
|DeepSeek未认证探测|/models返回401；未验证推理|tests/evaluation/ai_external_probe.json|
|外部百科|中文红黑树摘要真实HTTP200、有效JSON|同上|
|浏览器桌面交互|登录空总览、图谱详情/先修路径、KMP逐步与BF比较、真实执行授权失败提示|output/screenshots与browser_qa.json|

LangChain 与 CrewAI 框架确实在测试中运行；付费 LLM 使用明确测试替身。常规单元测试的执行响应使用测试替身；另列的本机服务实验、题库与提交闭环确实使用真实 Piston。Worker超时测试实际运行可信测试子进程并确认终止。样本量小，不能将检索9/9推广为平台准确率。

## 第四部分：系统架构说明

采用 Django 模块化单体与 SQLite。账户、课程、教学、Agent、题目、学习、图谱、报告、实验分别管理自己的模型与服务；core 提供统一异常、JSON接口、LLM、加密和执行基础设施。外部 HTTP 放在数据库事务外，最终提交与学习状态使用 IMMEDIATE 事务和幂等约束。页面使用服务器模板和原生 SVG，无前端构建。

课程结构共享，进度/密钥/聊天/提交/错题/报告按当前认证用户独立查询。掌握度仅由统一服务写入，主页、图谱和报告读取同一状态。架构细节、公式与模型关系见 ARCHITECTURE.md。

## 第五部分：创新点与技术实现

- 可追溯的知识网络闭环：真实评测 → 原子提交 → 去重学习证据 → 掌握指数/BKT → 图谱/路径/错题/报告。
- 单题反复通过不会直接变成充分掌握；近期错误能导致可解释退步，章节聚合包括无证据节点。
- 原文与勘误分离；保留老师 PDF，待审核纠错不能作为正式课程证据。
- DeepSeek 思考工具消息保真，工具身份由服务器锁定，Trace 只记录真实执行和脱敏概要。
- CrewAI 分析与 Python 客观数字分离，数字快照不一致拒绝发布；任务超时可强制终止并持久化恢复。
- Python 确定性算法状态可逐步回放和BF/KMP比较，避免LLM编造动画过程。

## 第六部分：仍未解决的问题

1. 用户已在网页配置个人 DeepSeek Key，服务器日志可见真实聊天请求成功。三个档位、多工具线上任务、AI诊断、CrewAI在线报告与完整A/B/C质量实验未作系统性验收，不能从单次聊天成功推广。
2. 本机独立执行已完成：六类判题和全题库实际通过，禁网、主机文件/环境隔离、进程/输出限制、墙钟/CPU超时、临时文件隔离通过。200MiB分配在128MiB请求下被终止，但公共API没有OOM元数据，因此内存探针仍标UNVERIFIED；未做正式渗透测试。
3. 响应式CSS已实现，但浏览器视口工具实际仍保持1280×720，不能把本次桌面截图当手机测试；手机/平板实机验证待完成。
4. 当前检索测试集、题库和BKT先验规模有限。检索需更多人工核验问题，BKT默认参数未经拟合；未做正式渗透测试或实际生产反向代理部署验收。

## 第七部分：完整运行命令

本机虚拟环境、数据库、课程索引和隔离Python已经建立。重启电脑后先启动执行VM：

```bash
cd AlgoMentor
.venv/bin/python scripts/local_piston.py start
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

另开终端启动报告队列：

```bash
cd AlgoMentor
.venv/bin/python manage.py report_worker
```

新环境：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/bootstrap.py
.venv/bin/pytest -q
.venv/bin/python manage.py evaluate_system
```

网页注册并配置个人Key；执行服务部署见 deployment/LOCAL_EXECUTION.md。实测命令：

```bash
.venv/bin/python manage.py verify_problem_bank
.venv/bin/python manage.py verify_judge
.venv/bin/python manage.py verify_execution_isolation
ALGOMENTOR_LIVE_EXECUTION=1 .venv/bin/pytest -q tests/integration/test_live_execution.py
.venv/bin/python manage.py evaluate_system --live --username YOUR_USER
```

## 第八部分：现场演示流程

1. 新注册账户，展示个人总览无伪造成绩、知识点无学习证据。
2. 在课程知识库搜索“循环队列判满条件”，展开实际PDF页码与完整原文片段。
3. 搜索KMP图谱节点，点击名称，查看先修顺序、真实掌握指数、原文和相关练习入口。
4. 算法实验室选择KMP，逐步查看失配与next数组，使用同输入BF比较；链表查看prev/curr/next，循环队列查看队满和绕回。
5. 设置页面保存自己的DeepSeekKey，逐档进行真实推理测试，检查真实usage和错误状态。
6. 询问“查询我最近链表掌握情况，再执行代码并安排下一步”，核对实际工具调用Trace。需要合法执行服务。
7. 提交错误和正确程序，展示用例真实结果、错题保留、掌握度更新及图谱变化；查看不同用户隔离。
8. 启动report_worker，生成本周报告，展示任务状态、CrewAI研究员与写手逻辑，逐项核对数据库数字。
9. 如凭据缺失，当场展示真实配置/授权错误，并说明该线上环节待验证，不能表演伪造结果。
