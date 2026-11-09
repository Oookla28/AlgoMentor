# Development-agent skills（内置参考）

本目录存放**开发辅助 Skill** 的固定版本副本，供本项目的开发 Agent / 维护者阅读。
它们不是产品运行时 Skill，不会参与用户任务选择，也不会授予任何工具、数据或网络权限。

- 运行时 Skill：`agent_skills/runtime/`，由 `apps/platform/skills/runtime.py` 按任务懒加载。
- 开发参考：`agent_skills/vendor/`，由 `agent_skills/development/index.json` 登记。
- 审计：`python manage.py skills_audit` 校验每个文件的 SHA-256 与许可证文件。

## 来源与许可

| Skill | 上游 | 许可 |
| --- | --- | --- |
| frontend-design | anthropics/skills | Apache-2.0（skill-local LICENSE.txt） |
| webapp-testing | anthropics/skills | Apache-2.0（skill-local LICENSE.txt） |
| systematic-debugging | obra/superpowers | MIT |
| test-driven-development | obra/superpowers | MIT |
| verification-before-completion | obra/superpowers | MIT |
| skill-creator | openai/skills | Apache-2.0（skill-local LICENSE.txt） |
| literature-review | K-Dense-AI/scientific-agent-skills | MIT |
| scientific-critical-thinking | K-Dense-AI/scientific-agent-skills | MIT |

每个 Skill 的固定 commit、SHA-256、许可证路径与实际字节数见 `index.json` 和仓库根目录
`skills.lock.json`。上游脚本、依赖、网络客户端和云服务均未安装或执行。

## 使用边界

- frontend-design 只用于新增界面的信息层级与可读性审查，不能覆盖本项目的主题、宋体字体与布局骨架。
- webapp-testing 只作为浏览器验收方法参考；本项目实际使用独立浏览器工具，不安装其 Playwright 依赖。
- systematic-debugging / TDD / verification 只作为开发流程参考，不能替代本轮真实命令与回归结果。
- skill-creator 的 Codex 专有工具依赖不得照搬到产品运行时。
- literature-review / scientific-critical-thinking 已由本项目原生 Skill
  `evidence-paper-comparison` / `experiment-review` 吸收为受控运行时流程；上游全文仅作参考。
