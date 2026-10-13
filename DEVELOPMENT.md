# 开发说明

以 Python 3.12 虚拟环境运行。主系统只有 Django、SQLite、原生模板，禁止引入前端构建流程。所有依赖版本见 requirements.in（直接）和 requirements.txt（已验证完整冻结）。修改版本后重新安装、执行 pip check 和完整 pytest，更新真实记录。

新增业务放入所属 app/services，views 只处理 HTTP。跨模块写入通过公开服务完成；MasteryState 只能通过统一 mastery_service 更新。新增模型必须提交迁移。默认运行数据、用户密钥和 Chroma 不纳入源码；原始课程 PDF 可随交付保存，不能改写。

命令：migrate → seed_knowledge → seed_problems → ingest_knowledge → seed_knowledge。模型加载网络失败应明确报错；如主动选择 tfidf，必须同步修改检索阈值并重建索引，不作隐藏降级。

新增知识点保留可读 slug，新增关系先检查 NetworkX 先修无环。课程题目加入 apps/problems/services/seed_catalog.py（以实际文件为准），保持服务端隐藏用例；使用 verify_problem_bank 验证授权执行服务上的参考程序。语法检查与自动化测试替身不代表真实参考程序评测通过。

新增 Agent 工具必须使用明确的 Pydantic schema，当前用户身份从闭包上下文绑定，禁止模型提供身份。修改模型接口仅在 core/llm 中完成，记录官方文档与参数兼容性，验证 reasoning_content 多轮回传。不能通过替换官方模型来掩盖兼容性错误。

报告使用独立 Worker；后台状态必须持久化，测试停止、失败与超时恢复。统计由 Python 提供，生成文本不能决定成绩。更新功能状态必须同步 IMPLEMENTATION_PLAN.md 与 DELIVERY_REPORT.md。
