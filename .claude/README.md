# Chalk Dev Flow

A branch-first development workflow for the **Tha Paint / Chalk** repo. It combines
the [Compound Engineering](https://github.com/) outer loop (brainstorm → plan → work →
simplify → review → compound) with [Superpowers](https://github.com/) practices
(git worktrees, test-driven development, subagent-driven review, finishing a
development branch).

Every unit of work:

1. **starts on a correctly-named branch cut from `railway`** (never from `main`), and
2. **produces five specification documents** in `specs/<branch-slug>/` before and
   during implementation.

---

## The Golden Branch Rule

> **All work branches off `railway`. `main` is never touched directly.**
> `main` only ever changes through a deliberate `railway → main` release merge.

See [`workflows/00-branch-naming.md`](workflows/00-branch-naming.md) for the full
convention.

### Branch prefixes

| Prefix | Use for | Example |
|---|---|---|
| `feature/` | New features | `feature/add-dashboard` |
| `bugfix/` | Normal bug fixes | `bugfix/fix-login-validation` |
| `hotfix/` | Urgent production fixes | `hotfix/fix-checkout-crash` |
| `chore/` | Maintenance tasks | `chore/update-eslint-config` |
| `docs/` | Documentation changes | `docs/update-readme` |
| `refactor/` | Code cleanup without behavior change | `refactor/auth-service` |
| `test/` | Adding or fixing tests | `test/add-user-api-tests` |
| `style/` | Formatting / UI styling | `style/navbar-spacing` |
| `perf/` | Performance improvements | `perf/optimize-image-loading` |
| `ci/` | CI/CD pipeline changes | `ci/add-github-actions` |
| `build/` | Build system / dependency changes | `build/update-vite-config` |
| `release/` | Release prep | `release/v1.2.0` |
| `experiment/` | Experimental work | `experiment/ai-search-flow` |

---

## The Loop

The core loop is eight phases. Each has a workflow file (the instructions) and a
slash command (the trigger). Run `/chalk-flow` to drive the whole thing, or invoke
any phase on its own.

| # | Phase | Command | Workflow | Borrows from | Produces |
|---|---|---|---|---|---|
| 0 | Branch | `/chalk-branch` | [00-branch-naming](workflows/00-branch-naming.md) | SP · using-git-worktrees | branch off `railway` + `specs/` folder |
| 1 | Brainstorm | `/chalk-brainstorm` | [01-brainstorm](workflows/01-brainstorm.md) | CE · ce-brainstorm / SP · brainstorming | **planning-spec.md** |
| 2 | Plan & Design | `/chalk-plan` | [02-plan-and-design](workflows/02-plan-and-design.md) | CE · ce-plan / SP · writing-plans | **design-spec.md** + **implementation-spec.md** |
| 3 | Test | `/chalk-test` | [03-test](workflows/03-test.md) | SP · test-driven-development | **testing-spec.md** + failing tests |
| 4 | Implement | `/chalk-implement` | [04-implement](workflows/04-implement.md) | CE · ce-work / SP · subagent-driven-development | passing code |
| 5 | Simplify & Review | `/chalk-review` | [05-simplify-and-review](workflows/05-simplify-and-review.md) | CE · ce-simplify-code + ce-code-review / SP · requesting-code-review | reviewed diff |
| 6 | Ship | `/chalk-ship` | [06-ship](workflows/06-ship.md) | SP · finishing-a-development-branch | **deployment-spec.md** + PR |
| 7 | Compound | `/chalk-compound` | [07-compound](workflows/07-compound.md) | CE · ce-compound | `docs/solutions/` entry |

*CE = Compound Engineering, SP = Superpowers.*

```
        ┌─────────────────────────────────────────────────────────┐
        ▼                                                         │
0 Branch → 1 Brainstorm → 2 Plan&Design → 3 Test → 4 Implement    │
                                                        │         │
                                    5 Simplify&Review ◀─┘         │
                                          │                       │
                                     6 Ship → 7 Compound ─────────┘
                                                (feeds the next loop)
```

---

## The Five Specs

Every branch carries a spec folder at `specs/<branch-slug>/`:

| File | Written in phase | Template |
|---|---|---|
| `planning-spec.md` | 1 · Brainstorm | [templates/planning-spec.md](templates/planning-spec.md) |
| `design-spec.md` | 2 · Plan & Design | [templates/design-spec.md](templates/design-spec.md) |
| `implementation-spec.md` (API + DB + security) | 2 · Plan & Design | [templates/implementation-spec.md](templates/implementation-spec.md) |
| `testing-spec.md` | 3 · Test | [templates/testing-spec.md](templates/testing-spec.md) |
| `deployment-spec.md` | 6 · Ship | [templates/deployment-spec.md](templates/deployment-spec.md) |

The specs are living documents — update them as reality diverges from the plan. A
merged PR whose specs no longer match the code is a bug in the specs.

---

## Quick start

```
/chalk-flow feature "opponent-adjusted usage rate feature"
```

or step by step:

```
/chalk-branch feature "opponent-adjusted usage rate feature"
/chalk-brainstorm
/chalk-plan
/chalk-test
/chalk-implement
/chalk-review
/chalk-ship
/chalk-compound
```
