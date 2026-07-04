# Chalk Dev Flow

Agentic, self-correcting Git workflows for the **Tha Paint / Chalk** repo — modeled on
the Compound Engineering loop (brainstorm → plan → work → review → ship → compound) and
adapted for this project.

You run **one slash command per branch type** (e.g. `/chalk-feature`, `/chalk-bugfix`)
and it drives the whole loop end to end: it cuts a correctly-named branch off
`railway`, produces five spec documents, writes and tests the code, ships a PR into
`railway`, and **loops back to an earlier phase whenever a later one fails**.

---

## The Golden Branch Rule

> **All work branches off `railway`. `main` is never touched directly** — except by the
> one deliberate `railway → main` promotion inside `/chalk-release`.

---

## Two layers (like Windsurf's `workflows/` + `skills/`)

```
.claude/
├── commands/      ← WORKFLOWS you type: one per branch type (/chalk-feature, …)
├── skills/        ← PHASE building blocks the workflows invoke (chalk-brainstorm, …)
└── templates/     ← the five spec templates each run stamps out
```

- **Commands** (`.claude/commands/chalk-*.md`) are the orchestrators. Each is
  self-contained: `## MCP Integration`, `## Resuming`, and `## Steps` with loop-backs.
- **Skills** (`.claude/skills/chalk-*/SKILL.md`) are the reusable phases the
  orchestrators delegate to (invoked via the Skill tool). You can also run a phase
  standalone.

---

## Branch-type workflows (the commands you run)

| Command | Prefix | For | Tier |
|---|---|---|---|
| `/chalk-feature` | `feature/` | New capability | full loop |
| `/chalk-bugfix` | `bugfix/` | Normal bug fix (reproduce-first) | full loop |
| `/chalk-hotfix` | `hotfix/` | Urgent production fix | fast track |
| `/chalk-refactor` | `refactor/` | Restructure, no behavior change | full loop |
| `/chalk-perf` | `perf/` | Measured performance win | full loop |
| `/chalk-experiment` | `experiment/` | Spike → decide (may not ship) | explore |
| `/chalk-chore` | `chore/` | Deps / config / cleanup | light |
| `/chalk-docs` | `docs/` | Documentation only | light |
| `/chalk-test` | `test/` | Add/fix tests for existing code | light |
| `/chalk-style` | `style/` | Formatting / UI styling | light |
| `/chalk-ci` | `ci/` | CI/CD pipeline changes | light |
| `/chalk-build` | `build/` | Build system / deps tooling | light |
| `/chalk-release` | `release/` | Release prep **+ `railway → main`** | release |

Every workflow cuts its branch from `railway` and opens its PR into `railway`
(only `/chalk-release` promotes to `main`, with explicit confirmation).

## Phase skills (invoked by the workflows)

| Skill | Does | Produces |
|---|---|---|
| `chalk-brainstorm` | Requirements (what/why, no code) | `planning-spec.md` |
| `chalk-plan` | Design + buildable plan | `design-spec.md` + `implementation-spec.md` |
| `chalk-work` | TDD: RED → GREEN → simplify | `testing-spec.md` + passing code |
| `chalk-review` | Simplify + review vs specs/rules | reviewed diff |
| `chalk-ship` | Deploy spec, green gate, PR, CI | `deployment-spec.md` + PR into `railway` |
| `chalk-compound` | Capture learnings | `docs/solutions/` entry |

---

## The five specs

Every branch carries `specs/<branch-slug>/` (branch name with `/` → `-`):

| File | Written by | Contains |
|---|---|---|
| `planning-spec.md` | brainstorm | problem, scope, success criteria, constraints |
| `design-spec.md` | plan | approach, components, data flow, interfaces |
| `implementation-spec.md` | plan | tasks + **API spec + DB spec + security rules** |
| `testing-spec.md` | work | test plan, RED baseline, GREEN result |
| `deployment-spec.md` | ship | migrations, services, env, rollback |

Templates live in `.claude/templates/`. The specs are living documents — keep them in
sync with the code; a merged PR whose specs don't match the code is a bug in the specs.

---

## Loop engineering (self-correction)

Later phases loop back to earlier ones on failure, with caps so it never spins forever:

- **Tests fail after implementing** → stay in `chalk-work`; if the *plan* is wrong →
  back to `chalk-plan`.
- **Review finds a blocking issue** → code-level → `chalk-work`; design-level →
  `chalk-plan`.
- **CI/pipeline fails after push** → read the job log via MCP, then: test/lint/build →
  `chalk-work`; design flaw → `chalk-plan`.
- **Loop cap:** any fix loop that runs **3 times** with no progress stops and asks you
  instead of looping again.

## MCP usage

The workflows use whatever MCP servers are connected to your session — they check
what's available and prefer MCP tools over manual steps (issue trackers for ticket
context/status, Git hosting for PRs + pipeline polling + job logs, code-quality gates,
etc.). No specific server is assumed; this session always has the **GitHub MCP** and
**CodeRabbit**. If nothing fits a step, it falls back to `git` + the GitHub MCP.

---

## Quick start

```
/chalk-feature "opponent-adjusted usage rate"
/chalk-bugfix  "null usage rate for rookies"
/chalk-hotfix  "prediction endpoint 500 on playoff game ids"
/chalk-release v1.3.0
```
