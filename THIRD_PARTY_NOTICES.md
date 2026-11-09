# Third-party Skill notices

This repository contains two separate Skill layers:

1. **Native runtime Skills** under `agent_skills/runtime/`, written for AlgoMentor.
   They are loaded by `apps/platform/skills/runtime.py` for user tasks and never
   grant permissions.
2. **Vendored development-agent references** under `agent_skills/vendor/`.
   These are pinned copies of upstream `SKILL.md` and license files. They are
   for maintainers/development agents only and are **not executable** in the
   product runtime.

## Vendored upstream sources

Vendored on 2026-11-09. The exact upstream commit, file SHA-256, byte count and
license path for every file are recorded in `skills.lock.json`,
`agent_skills/development/index.json` and each `agent_skills/vendor/*/UPSTREAM.json`.

| Skill | Repository | Commit | License | Vendored path |
| --- | --- | --- | --- | --- |
| frontend-design | anthropics/skills | `2c5958ecac7cee2b583967a2c4981d0f4a75c579` | Apache-2.0 (skill-local `LICENSE.txt`) | `agent_skills/vendor/anthropics-skills/frontend-design/` |
| webapp-testing | anthropics/skills | `2c5958ecac7cee2b583967a2c4981d0f4a75c579` | Apache-2.0 (skill-local `LICENSE.txt`) | `agent_skills/vendor/anthropics-skills/webapp-testing/` |
| systematic-debugging | obra/superpowers | `22f0b463e7a5e579904dd6211a520321035526f7` | MIT (`LICENSE`) | `agent_skills/vendor/obra-superpowers/systematic-debugging/` |
| test-driven-development | obra/superpowers | `22f0b463e7a5e579904dd6211a520321035526f7` | MIT (`LICENSE`) | `agent_skills/vendor/obra-superpowers/test-driven-development/` |
| verification-before-completion | obra/superpowers | `22f0b463e7a5e579904dd6211a520321035526f7` | MIT (`LICENSE`) | `agent_skills/vendor/obra-superpowers/verification-before-completion/` |
| skill-creator | openai/skills | `49f948faa9258a0c61caceaf225e179651397431` | Apache-2.0 (skill-local `LICENSE.txt`) | `agent_skills/vendor/openai-skills/skill-creator/` |
| literature-review | K-Dense-AI/scientific-agent-skills | `a25cf9ec00e2745d03f8704acf6f6919694ccd9a` | MIT (`LICENSE.md`) | `agent_skills/vendor/k-dense-scientific-agent-skills/literature-review/` |
| scientific-critical-thinking | K-Dense-AI/scientific-agent-skills | `a25cf9ec00e2745d03f8704acf6f6919694ccd9a` | MIT (`LICENSE.md`) | `agent_skills/vendor/k-dense-scientific-agent-skills/scientific-critical-thinking/` |

## What was not imported

- No upstream scripts, installers, package dependencies, MCP clients, network
  clients or cloud-service credentials.
- No global host configuration, shell profile changes or system Skill overrides.
- No upstream code is executed by the Django process.
- The product runtime still uses the six native Skills under `agent_skills/runtime/`;
  the vendored `literature-review` and `scientific-critical-thinking` files are
  references for the reviewed native `evidence-paper-comparison` and
  `experiment-review` workflows.

## Network note

The local machine's configured DNS resolver was not usable during vendoring.
Files were fetched from `raw.githubusercontent.com` by resolving that host to a
known GitHub IP and verifying TLS, without changing system DNS or proxy settings.
This affects only the vendoring procedure; the recorded commit and SHA-256 are
real values from the fetched bytes.

## Audit

```bash
python manage.py skills_audit
python manage.py skills_audit --json
```

The audit verifies every vendored body and license SHA-256, rejects symlinks and
path traversal, and reports the independent runtime Skill health.
