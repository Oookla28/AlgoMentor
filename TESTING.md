# 测试说明

所有结果以 `data/pytest-final.log`、`tests/evaluation/results.json` 和外部服务探测原始 JSON 为准。执行命令见 README。

自动化层：pytest + pytest-django 隔离数据库。测试替身只在 tests 中注入，用于可重复验证请求参数、判题分类、状态转换、工具规划控制及错误处理。真实 LangChain create_agent 执行时间和 ORM 工具；真实 CrewAI kickoff 依次运行研究员和写手。付费模型的替身不能被解释为真实 DeepSeek 线上验证。Worker 超时测试实际启动可信测试子进程并确认终止；不是学生代码运行测试。

学习闭环检查 Accepted / Wrong Answer / Syntax Error / Runtime Error / TLE / MLE / Judge Error、隐藏数据保密、事务幂等、错题保留与重做解决、掌握度增长及回退、单题上限、无证据灰色图谱、章加权聚合、先修环拒绝与拓扑路径、真实快照及多用户隔离。

检索实验使用本机真实中文 BGE 和 Chroma；9 个库内问题来自已读 PDF，2 个库外问题检查拒答。原始每题命中、引用元数据、耗时均落盘。小样本结果只反映本组测试，不能推广成生产准确率。A/B/C 在线生成及事实一致性实验需要真实 Key，并保留回答供人工对照；未执行的指标标为 NOT_VERIFIED / REQUIRES_HUMAN_REVIEW。

Piston 运行列表读取成功不等于执行成功。本机现已部署独立 Lima VM 中的官方 Piston / Isolate 与 Python 3.12.0：六类实际判题全部匹配预期，21 道参考程序的 89 个用例实际通过。证据为 judge_results.json 和 problem_bank_results.json。verify_execution_isolation 另验证固定恶意行为探针并保留原始响应；含糊结果为 UNVERIFIED。历史公共实例 401/403 探测仍保留，但不代表本机当前服务状态。

页面验证以浏览器实际状态和日志保存：注册 / 登录、真实空总览、图谱搜索聚焦及节点详情、知识检索与来源、Python 状态演示、代码服务授权错误、未配置 Key 提示、响应式布局。浏览器 QA 使用的初始临时账户已经清理；当前使用既有登录态只验证“运行代码”，输入 4 实际输出 10，未创建测试学生成绩。已有正式账户与学习记录保留。

本次完整自动测试：218 passed、1 skipped；跳过项显式执行 `ALGOMENTOR_LIVE_EXECUTION=1 .venv/bin/pytest -q tests/integration/test_live_execution.py` 后 1 passed。该实测只写 pytest 测试数据库，验证真实 API 运行/提交、错题重做、学习证据、幂等和用户隔离，不污染正式学生记录。隔离探针本次 8 PASS、0 FAIL、1 UNVERIFIED：内存分配被终止，返回峰值约128MiB，但API未给OOM标记，保留未验证；网络/文件/环境/进程/输出/墙钟/CPU/临时文件检查均有实际证据。

## Wikipedia 与离线增量验收

本轮基线218通过、1跳过；最终320通过、2默认跳过。两个真实集成分别单独执行通过：真实LangChain+官方Wikipedia（规划LLM明确为测试替身）与真实Piston提交闭环。用户要求的四个概念实际API全部通过，额外合计6项；18项预热词表实际核对通过。离线冷启动在新WSGI进程、一次性数据库副本、外部DNS/socket与主机代理阻断下通过，DEBUG=False静态、BGE/Chroma、课程/图谱/算法、真实百科缓存和本机执行均可用。既有学生行指纹未变。完整证据与命令见 WIKIPEDIA_OFFLINE_REPORT.md 和 tests/evaluation/wikipedia_incremental_tests.json。未调用用户付费DeepSeek。
