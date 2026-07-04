---
description: Phase 0 — cut a correctly-named branch off railway (never main) and scaffold the five specs.
argument-hint: <prefix> "<short description>"   e.g. feature "opponent usage-rate feature"
---

Run **Phase 0 — Branch Naming & Setup** of the Chalk Dev Flow.

Arguments: `$ARGUMENTS` (first token = branch prefix from the convention table;
remainder = the work description used to build the kebab-case slug).

Follow this workflow exactly: @.claude/workflows/00-branch-naming.md

Key rules:
- **Branch from `origin/railway`. Never from `main`; never commit to `main`.**
- Pick the single most accurate prefix (`feature/ bugfix/ hotfix/ chore/ docs/
  refactor/ test/ style/ perf/ ci/ build/ release/ experiment/`).
- Scaffold `specs/<branch-slug>/` by copying all five templates from
  `.claude/templates/`.
- Prove a green baseline (`pytest tests/ -v`) and record it in `planning-spec.md`.

Stop at this phase's Definition of Done and report the branch name, the spec folder
path, and the baseline result.
