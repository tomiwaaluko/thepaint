---
description: Phase 3 — write the testing spec and failing tests (RED) before any implementation.
---

Run **Phase 3 — Test** of the Chalk Dev Flow.

Follow this workflow exactly: @.claude/workflows/03-test.md

Read `specs/<branch-slug>/implementation-spec.md`, then produce
`specs/<branch-slug>/testing-spec.md` from @.claude/templates/testing-spec.md and
write the tests as **failing** tests under `tests/`.

Mandatory: an `as_of_date` leakage test for every feature function, idempotency tests
for ingestion, `httpx.AsyncClient` API tests, walk-forward validation tests, and edge
cases. Never hit the real nba_api — mock everything. Do **not** write production logic
yet.

Run `pytest` and confirm the new tests fail for the right reason (RED); record it in
the testing spec. Stop at this phase's Definition of Done.
