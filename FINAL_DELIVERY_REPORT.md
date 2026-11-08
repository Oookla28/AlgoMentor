# FINAL DELIVERY REPORT · EvidenceRAG Studio / Evidence-Grounded Platform

日期：2026-11-08  
源目录：`/Volumes/半岛铁盒/实验室/AlgoMentor`  
部署目录：`/Volumes/半岛铁盒/实验室考核部署`  
本地分支：`main`  
代码提交：`c2a9c71`（平台增量；部署产物在最终提交中）  
远端：`feat/evidence-rag-studio` 已存在；本轮遵守“不 push”约束，未更新远端 `main`。

## 1. 已完成

### 1.1 冻结与兼容

- P0 基线：`docs/evidence_rag/baseline_before_next_stage.md`；
- legacy API/schema golden snapshot：
  `docs/evidence_rag/golden/legacy_api_snapshot.json`；
- legacy 搜索 JSON 严格保留原 11 个 Citation 字段；高级字段只进入
  advanced/platform payload；
- `.deployment-manifest.json` 记录源/目标、commit、config hash、能力状态、
  HTTP 验证与运行信息。

### 1.2 平台化

- `apps/platform/contracts`：DomainPack、TaskPack、ToolSpec、EvidenceUnit、ClaimUnit；
- 领域包：`data_structures`、`general_documents`；
- 模型：AgentRun/Step、Evidence、Claim、ConflictSet、EvaluationCase/Run、
  Domain/Task/Tool 记录；迁移 `platform.0001`；
- 显式 Agent 状态机 + 预算 + 工具权限/超时/幂等/证据策略；
- 自适应证据路由：keyword/semantic/read child/parent/siblings/source page/
  conflicting versions；最多 2 次 retrieve-more；
- capability health 与 `/platform/` 管理员控制台；
- 平台 API：capabilities、domains、agent/run、runs、run detail、sync domains；
- 平台评测协议、19 例数据集、三组指标与 B0–B5 矩阵。

### 1.3 文档与部署

- README 首屏：定位、三分钟 Demo、架构图、代码索引、状态表、H1/H2/H3、
  实际结果、复现、兼容性、限制、研究路线；
- ARCHITECTURE、IMPLEMENTATION_PLAN、TESTING、DELIVERY_REPORT、CHANGELOG；
- `docs/evidence_rag/evaluation_protocol.md`、`docs/research/RESEARCH_CARD.md`、
  `docs/deployment/LOCAL_DEPLOYMENT.md`；
- 部署脚本：`local_deploy.sh`、`run_local.sh`、`healthcheck.sh`、
  `evaluate_local.sh`、`snapshot_legacy_api.py`、`evaluate_platform.py`。

## 2. 已实际验证

| 项目 | 结果 |
| --- | --- |
| `manage.py check` | 无问题 |
| `makemigrations --check` | No changes detected |
| 完整回归 | **398 passed / 2 skipped**（15.24s） |
| 基线 legacy 评测 | 9 个库内命中 6/9；库外拒答 2/2 |
| advanced（TF-IDF） | 库内 **9/9**；库外 **2/2**；parent recovery 100% |
| 平台 19 例 | advanced 100%；legacy 75%；拒答 precision/recall **1.0/1.0** |
| claim support | coverage 0.976；unsupported claim rate **0** |
| 冲突识别 | **5/5** |
| 工具探针 | 权限拒绝、超时、无效调用均按预期 |
| Agent 质量 | avg 11.14 steps / 2.0 tools；p50/p95 226/246 ms |
| 部署 healthcheck | login 200、static 200、未登录 302/401，全部 PASS |
| 部署 HTTP 流程 | staff 登录 200；advanced 200（6 证据）；console 200；agent 200（11 steps/13 evidence）；student console 403；student 页面无管理入口 |

原始结果：`tests/evaluation/evidence_rag_results.json`、
`tests/evaluation/platform_results.json`、`DEPLOYMENT_REPORT.md`。

## 3. 需要本机环境才能验证

| 项目 | 状态 | 原因 |
| --- | --- | --- |
| BGE 高级索引 | Unverified | 本机无本地 BGE 权重 |
| Cross-Encoder 重排 | Optional / Unverified | 依赖未安装/未探测的模型 |
| LLM 查询改写 / 在线生成 | Optional / Unverified | 默认关闭；无个人 DeepSeek Key |
| OCR | Disabled | pytesseract/tesseract 缺失 |
| ASR | Disabled | faster-whisper/ffmpeg 缺失 |
| 关键帧 | Disabled | ffmpeg/opencv 缺失 |
| 本机 Piston | Environment-limited | `127.0.0.1:2000` 未开放 |
| 手机实机 / 生产安全审计 | Unverified | 未执行 |

## 4. 用户体验检查

- 学生：原搜索/聊天/来源/代码评测不变；高级检索显示来源卡片、拒答说明、
  冲突证据与可折叠上下文，不显示逐路轨迹、Token、模型调用；
- 管理员：`/knowledge/` 切片树、管理员维护；`/platform/` Capability Health、
  领域包、工具契约、Agent 运行、步骤、证据、Claim、冲突、评测运行；
- 学生访问 `/platform/` 403；写接口 staff + CSRF；API 限流；
- 页面加载态、空结果态、超时/错误提示、禁用按钮均已实现；
- 真实浏览器验证：高级检索、切片树、管理员维护、平台控制台，无 JS 错误。

## 5. 本地访问方式

当前已启动：

- URL：`http://127.0.0.1:8010/`
- 演示账号：`demo_student` / `demo_staff`
- 密码：`demo-pass-2026`（仅本机演示）
- PID：`36959`
- 日志：`/Volumes/半岛铁盒/实验室考核部署/data/run/server.log`

启动/检查/停止：

```bash
bash /Volumes/半岛铁盒/实验室考核部署/scripts/run_local.sh
bash /Volumes/半岛铁盒/实验室考核部署/scripts/healthcheck.sh
kill "$(cat /Volumes/半岛铁盒/实验室考核部署/data/run/server.pid)"
```

注意：服务只绑定 `127.0.0.1`，不得暴露公网；Chroma 默认在
`/tmp/algomentor-deploy-chroma`，重启机器后需重新执行 ingest。

## 6. 回滚方式

本次部署前目标目录已存在，已生成备份：

`/Volumes/半岛铁盒/实验室考核部署.backup.20261108_203155`

```bash
kill "$(cat /Volumes/半岛铁盒/实验室考核部署/data/run/server.pid)" || true
mv "/Volumes/半岛铁盒/实验室考核部署" "/Volumes/半岛铁盒/实验室考核部署.failed"
mv "/Volumes/半岛铁盒/实验室考核部署.backup.20261108_203155" "/Volumes/半岛铁盒/实验室考核部署"
```

不删除失败目录，便于排查；不覆盖用户数据库。

## 7. 未解决问题

1. B2–B5 研究矩阵未执行：缺 BGE/Cross-Encoder；
2. 评测规模小（19 例、单一课程 PDF），不能外推；
3. 冲突规则不是完整 NLI；`U(action)` 与 gate 阈值未校准；
4. OCR/ASR/关键帧、Piston、在线生成、手机实机、生产安全审计未验证；
5. 外接卷 Chroma 文件锁限制，部署使用 `/tmp`；长期运行需稳定磁盘与重建策略；
6. 本轮遵守“禁止 git push”，远端 `main` 尚未包含平台增量；需用户确认后再推送。

## 8. 后续建议

1. 在具备 BGE/Cross-Encoder 的环境跑 B2–B5，保存 config/dataset hash 与原始 trace；
2. 扩充课程/领域与 hard negatives，做验证集校准；
3. 接入真实 OCR/ASR，验证图片/视频时间戳引用；
4. 将 Chroma 放到受支持磁盘并做备份/重建演练；
5. 生产化前完成权限、限流、上传扫描、审计与安全评审。
