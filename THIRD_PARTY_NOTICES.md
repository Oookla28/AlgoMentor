# Third-party Skill notices

This repository contains **project-native runtime Skills** under `agent_skills/runtime/`.
They were written for AlgoMentor and are covered by this repository's license.

The following upstream Skill repositories were reviewed as **references only**.
They are not copied, installed, or loaded at runtime. Because this machine could
not resolve external DNS during the build, no upstream commit or SHA-256 could be
verified. Those values are deliberately left `null` in `skills.lock.json`; do not
treat them as pinned artifacts.

| Candidate | Repository | Observed license | State |
| --- | --- | --- | --- |
| frontend-design | anthropics/skills | Apache-2.0 (skill-local LICENSE.txt) | SOURCE_NOT_FETCHED / REFERENCE_ONLY |
| webapp-testing | anthropics/skills | Apache-2.0 (skill-local LICENSE.txt) | SOURCE_NOT_FETCHED / REFERENCE_ONLY |
| systematic-debugging | obra/superpowers | MIT (repository LICENSE) | SOURCE_NOT_FETCHED / REFERENCE_ONLY |
| test-driven-development | obra/superpowers | MIT (repository LICENSE) | SOURCE_NOT_FETCHED / REFERENCE_ONLY |
| verification-before-completion | obra/superpowers | MIT (repository LICENSE) | SOURCE_NOT_FETCHED / REFERENCE_ONLY |
| skill-creator | openai/skills | not re-verified | SOURCE_NOT_FETCHED / REFERENCE_ONLY |
| literature-review | K-Dense-AI/scientific-agent-skills | MIT (skill frontmatter) | SOURCE_NOT_FETCHED / REFERENCE_ONLY |
| scientific-critical-thinking | K-Dense-AI/scientific-agent-skills | MIT (skill frontmatter) | SOURCE_NOT_FETCHED / REFERENCE_ONLY |

Before any future import:

1. Read the actual upstream file at a fixed commit.
2. Re-verify the license from the repository and skill-local files.
3. Compute the SHA-256 of the exact file to be imported.
4. Review scripts and dependencies; never execute upstream scripts automatically.
5. Record the commit and hash in `skills.lock.json` and change the state to
   `PINNED_AND_REVIEWED`.

Runtime Skills grant no permissions. The server computes the effective tool
scope as the intersection of TaskPack, DomainPack, reviewed ToolSpec, current
capability and workspace/user authorization. A Skill's `allowed-tools` list can
only narrow that scope.
