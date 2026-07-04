# specs/

Per-branch specification folders produced by the [Chalk Dev Flow](../.claude/README.md).

Each branch gets `specs/<branch-slug>/` (the branch name with `/` → `-`, e.g.
`feature/opponent-usage-rate` → `feature-opponent-usage-rate/`) containing the five
living specs:

| File | Written in phase | Command |
|---|---|---|
| `planning-spec.md` | 1 · Brainstorm | `/chalk-brainstorm` |
| `design-spec.md` | 2 · Plan & Design | `/chalk-plan` |
| `implementation-spec.md` (API + DB + security) | 2 · Plan & Design | `/chalk-plan` |
| `testing-spec.md` | 3 · Test | `/chalk-test` |
| `deployment-spec.md` | 6 · Ship | `/chalk-ship` |

Templates live in [`.claude/templates/`](../.claude/templates). Start a new branch's
folder with `/chalk-branch`, which stamps all five from the templates.
