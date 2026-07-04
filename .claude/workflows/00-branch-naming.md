# Workflow 00 — Branch Naming & Setup

**Phase 0 of the Chalk Dev Flow.** Borrows from Superpowers `using-git-worktrees`.
Triggered by [`/chalk-branch`](../commands/chalk-branch.md).

The job of this phase: get onto a correctly-named, isolated branch cut from
`railway`, and scaffold the spec folder that the rest of the loop fills in.

---

## The Golden Rule

> **Always branch from `railway`. Never branch from `main`, and never commit to
> `main` directly.** `main` only changes through an explicit `railway → main`
> release merge (see the bottom of this file).

If you find yourself on `main` with changes to commit, stop — you have violated the
rule. Create the correct branch and move the changes onto it.

---

## Step 1 — Pick the prefix

Choose the single most accurate prefix for the change. If a change spans two
categories, pick the one a reviewer would look for first (a new feature that also
adds tests is still `feature/`, not `test/`).

| Prefix | Use for |
|---|---|
| `feature/` | New user-facing capability or model/feature-pipeline addition |
| `bugfix/` | Correcting wrong behavior in non-urgent code |
| `hotfix/` | Urgent production fix that must ship now |
| `chore/` | Maintenance, deps bumps, config, cleanup with no behavior change |
| `docs/` | Documentation only |
| `refactor/` | Restructuring without changing behavior |
| `test/` | Adding or repairing tests only |
| `style/` | Formatting / lint / UI styling only |
| `perf/` | Performance improvement |
| `ci/` | CI/CD pipeline changes |
| `build/` | Build system or dependency tooling |
| `release/` | Release preparation (version bumps, changelog, tags) |
| `experiment/` | Throwaway or exploratory work not meant to ship as-is |

## Step 2 — Build the slug

`<prefix>/<kebab-case-description>`

- lowercase, words joined by hyphens
- no spaces, no underscores, no uppercase
- concise but specific: `feature/opponent-usage-rate`, not `feature/stuff`
- for `release/`, use the version: `release/v1.2.0`

The **branch slug** (used for the spec folder) is the branch name with `/` replaced
by `-`, e.g. `feature/opponent-usage-rate` → `feature-opponent-usage-rate`.

## Step 3 — Cut the branch from `railway`

```bash
# Always start from the latest railway, never main.
git fetch origin railway
git switch --create <prefix>/<slug> origin/railway
# or, when isolating work from the current tree, use a worktree (Superpowers style):
#   git worktree add ../chalk-<slug> -b <prefix>/<slug> origin/railway
```

Verify the base:

```bash
git merge-base --is-ancestor origin/railway HEAD && echo "based on railway ✅"
```

If that prints nothing, the branch is **not** based on `railway` — recreate it.

## Step 4 — Scaffold the spec folder

```bash
mkdir -p specs/<branch-slug>
cp .claude/templates/planning-spec.md       specs/<branch-slug>/planning-spec.md
cp .claude/templates/design-spec.md         specs/<branch-slug>/design-spec.md
cp .claude/templates/implementation-spec.md specs/<branch-slug>/implementation-spec.md
cp .claude/templates/testing-spec.md        specs/<branch-slug>/testing-spec.md
cp .claude/templates/deployment-spec.md     specs/<branch-slug>/deployment-spec.md
```

Fill in the header of each spec (branch name, prefix, date, one-line intent). Leave
the bodies for their owning phases.

## Step 5 — Confirm a clean baseline

Before writing anything, prove the starting point is green (Superpowers rule — never
start work on a red baseline, or you can't tell what you broke):

```bash
pytest tests/ -v
cd dashboard && npm run lint && npm run build   # only if the change touches the frontend
```

Record the result in `planning-spec.md` under "Baseline". If the baseline is red,
stop and surface it — do not build on top of failing tests.

---

## Definition of done for phase 0

- [ ] On a branch named `<prefix>/<slug>`, based on `origin/railway`
- [ ] `main` untouched
- [ ] `specs/<branch-slug>/` exists with all five spec files stamped from templates
- [ ] Baseline test result recorded in `planning-spec.md`

Next: [`/chalk-brainstorm`](../commands/chalk-brainstorm.md) →
[`01-brainstorm.md`](01-brainstorm.md).

---

## Appendix — the `railway → main` release merge

`main` is the release line. Promote `railway` to `main` **only** when deliberately
cutting a release, and only from a `release/` branch or a maintainer-approved merge:

```bash
git fetch origin
git switch main
git pull origin main
git merge --no-ff origin/railway     # bring railway's tested state into main
git push origin main
```

Never do this as a side effect of feature work. If you are unsure whether a release
merge is wanted, ask before touching `main`.
