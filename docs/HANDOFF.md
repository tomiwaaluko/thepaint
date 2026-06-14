# Chalk Handoff

Use this file when switching Codex accounts or starting a fresh session. It keeps the important project context in the repo so the next session can pick up from the same state without relying on account-local memory.

## How To Continue

1. Read `AGENTS.md` and this file.
2. Run `git status --short --branch`.
3. Review the modified files listed in the generated snapshot below.
4. Continue the current goal, then run the relevant tests before committing.

## Current Goal

Implement the pre-flight accuracy fixes before Wave 1 on branch `fix/injury-odds-preflight`.

Current scope:
- Fix roster injury feature lookup to use a 7-day, latest-report-wins window.
- Fix `betting_lines` uniqueness/upsert targeting so player props do not overwrite each other.
- Record production verification items before data repair or retraining.

## Working Notes

- Do not revert existing local edits unless explicitly requested.
- Existing local edits to `AGENTS.md`, `CLAUDE.md`, and `.claude/settings.local.json` are unrelated to this branch and should remain unstaged unless explicitly requested.
- Keep secrets out of this file. Use `.env.example` as the public config reference.
- For FastAPI changes under `chalk/api/`, follow the repo `api-patterns` skill/instructions.
- For ingestion changes under `chalk/ingestion/` or ingestion scripts, follow the repo `data-ingestion` skill/instructions.
- For feature changes under `chalk/features/`, follow the repo `feature-engineering` skill/instructions and preserve the `as_of_date` leakage rule.
- Do not activate Odds API cron calls or retrain models until the production injury/log assumptions are verified.
- The generated snapshot can be refreshed manually with `powershell -ExecutionPolicy Bypass -File scripts/update_handoff.ps1`.
- For automatic refresh while working, keep this running in a PowerShell window: `powershell -ExecutionPolicy Bypass -File scripts/start_handoff_watcher.ps1`. Stop it with `powershell -ExecutionPolicy Bypass -File scripts/stop_handoff_watcher.ps1`.
- To try launching it in the background from a normal terminal, run `powershell -ExecutionPolicy Bypass -File scripts/launch_handoff_watcher.ps1`.

## Suggested Verification

- Backend tests: `pytest tests/ -v`
- Focused feature tests: `pytest tests/test_features/ -v`
- Focused ingestion tests: `pytest tests/test_ingestion/ -v`
- Focused API tests: `pytest tests/test_api/ -v`
- Frontend, if touched: `cd dashboard && npm run build`

## Latest Verification

- `pytest tests/test_features/ -v`: 39 passed.
- `pytest tests/test_features/test_roster.py -v`: 5 passed.
- `pytest tests/test_ingestion/test_odds_fetcher.py -v`: 2 passed.
- `python -m py_compile chalk/features/roster.py chalk/ingestion/odds_fetcher.py chalk/db/models.py alembic/versions/d4e5f6a7b8c9_fix_betting_line_player_uniqueness.py`: passed.
- `pytest tests/ -v`: 239 passed, 2 failed. Failures are outside this pre-flight change:
  - `tests/test_ingestion/test_injury_fetcher.py::TestGeminiParsing::test_extract_with_gemini_uses_raw_record_prompt` expects `gemini-2.0-flash`; current code uses `gemini-2.0-flash-001`.
  - `tests/test_scaffold.py::TestConfig::test_settings_requires_database_url` reads a local environment `DATABASE_URL` instead of the repo default.

## Open Items

- Verify Railway/Supabase claims before data repair: injury cron stopped after 2026-05-20, game `401873342` on 2026-05-21 has zero player logs, and `ODDS_API_KEY` is configured for the relevant Railway services.
- Decide separately whether to fix the unrelated Gemini model-name test/code mismatch.
- Rerun the full suite in a sanitized environment without local production-style env vars before PR handoff.

## Next Session Prompt

```text
I am continuing work in C:\Users\gokug\Documents\GitHub\chalk.

Please read AGENTS.md and docs/HANDOFF.md first, then inspect git status.
Do not revert existing changes. Continue from the handoff notes and verify with the listed test commands.
```

<!-- HANDOFF_AUTO_START -->
## Generated Snapshot

- Last refreshed: 2026-05-20 18:51:48 -04:00
- Repository: C:\Users\gokug\Documents\GitHub\chalk
- Branch: main

### Git Status

```text
## main...origin/main
 M chalk/api/routes/fantasy.py
 M chalk/api/routes/games.py
 M chalk/api/routes/players.py
 M chalk/api/routes/props.py
 M chalk/api/routes/teams.py
 M chalk/ingestion/nba_fetcher.py
 M chalk/ingestion/seed.py
 M scripts/railway_ingest.py
 M tests/test_api/test_games.py
?? docs/HANDOFF.md
?? scripts/install_handoff_hooks.ps1
?? scripts/launch_handoff_watcher.ps1
?? scripts/start_handoff_watcher.ps1
?? scripts/stop_handoff_watcher.ps1
?? scripts/update_handoff.ps1
```

### Changed Files

```text
chalk/api/routes/fantasy.py
chalk/api/routes/games.py
chalk/api/routes/players.py
chalk/api/routes/props.py
chalk/api/routes/teams.py
chalk/ingestion/nba_fetcher.py
chalk/ingestion/seed.py
scripts/railway_ingest.py
tests/test_api/test_games.py
```

### Staged Files

```text
(none)
```

### Diff Stat

```text
 chalk/api/routes/fantasy.py    |   5 +-
 chalk/api/routes/games.py      |  18 +---
 chalk/api/routes/players.py    |   3 +-
 chalk/api/routes/props.py      |   3 +-
 chalk/api/routes/teams.py      |   3 +-
 chalk/ingestion/nba_fetcher.py | 237 ++++++++++++++++++++++++++++++++++++++++-
 chalk/ingestion/seed.py        |   3 +
 scripts/railway_ingest.py      |  18 +++-
 tests/test_api/test_games.py   |  31 +-----
 9 files changed, 269 insertions(+), 52 deletions(-)
```

### Recent Commits

```text
a484ba9 Add .dockerignore and .mcp.json files; update .gitignore and Dockerfile
1a8bc73 Merge pull request #19 from tomiwaaluko/injury
f91c082 adding skills
eacd7d8 Update Gemini injury model
925a715 Migrate Gemini injury agent to google-genai
```
<!-- HANDOFF_AUTO_END -->







