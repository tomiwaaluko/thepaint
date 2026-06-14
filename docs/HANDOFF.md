# Chalk Handoff

Use this file when switching Codex accounts or starting a fresh session. It keeps the important project context in the repo so the next session can pick up from the same state without relying on account-local memory.

## How To Continue

1. Read `AGENTS.md` and this file.
2. Run `git status --short --branch`.
3. Review the modified files listed in the generated snapshot below.
4. Continue the current goal, then run the relevant tests before committing.

## Current Goal

Implement the pre-flight and Wave 1 accuracy fixes on branch `fix/injury-odds-preflight`.

Current scope:
- Fix roster injury feature lookup to use a 7-day, latest-report-wins window.
- Fix `betting_lines` uniqueness/upsert targeting so player props do not overwrite each other.
- Merge duplicate physical games and prevent future duplicate matchup rows.
- Activate Odds API cron ingestion with internal game/player resolution.
- Add sparse Vegas-line features to `generate_features()`.
- Add baseline MAE evaluation tooling before retraining.
- Record production verification items before deployment or retraining.

## Working Notes

- Do not revert existing local edits unless explicitly requested.
- Existing local edits to `AGENTS.md`, `CLAUDE.md`, and `.claude/settings.local.json` are unrelated to this branch and should remain unstaged unless explicitly requested.
- Keep secrets out of this file. Use `.env.example` as the public config reference.
- For FastAPI changes under `chalk/api/`, follow the repo `api-patterns` skill/instructions.
- For ingestion changes under `chalk/ingestion/` or ingestion scripts, follow the repo `data-ingestion` skill/instructions.
- For feature changes under `chalk/features/`, follow the repo `feature-engineering` skill/instructions and preserve the `as_of_date` leakage rule.
- Do not retrain models until migrations/data repair are deployed and a full 2024-25 baseline run is recorded.
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
- `pytest tests/test_features/ -v`: 44 passed after Vegas features.
- `pytest tests/test_ingestion/ -v`: 58 passed after Odds API activation.
- `pytest tests/ -v`: 251 passed, 4 warnings.
- Baseline evaluator smoke run: `python scripts/evaluate_baseline.py --season 2024-25 --stats pts reb ast fg3m --max-rows 50 --output .cache/baseline_smoke.json`.
  - `pts`: MAE 5.002, RMSE 6.478, bias -0.402.
  - `reb`: MAE 2.129, RMSE 2.711, bias -0.208.
  - `ast`: MAE 1.395, RMSE 2.033, bias 0.118.
  - `fg3m`: MAE 1.080, RMSE 1.558, bias -0.112.
- CodeRabbit cleanup focused tests: `pytest tests/test_ingestion/test_odds_fetcher.py tests/test_features/test_vegas.py tests/test_scaffold.py::TestORMModels::test_game_matchup_unique_constraint -v`: 12 passed.
- CodeRabbit cleanup full suite: `pytest tests/ -v`: 252 passed, 4 warnings.
- Baseline evaluator smoke after cleanup: `python scripts/evaluate_baseline.py --season 2024-25 --stats pts --max-rows 5 --output .cache/baseline_smoke_review_fix.json`.
  - `pts`: MAE 8.147, RMSE 8.625, bias -1.381.
- Gemini model fix compile check: `python -m py_compile chalk/config.py chalk/ingestion/injury_fetcher.py tests/test_ingestion/test_injury_fetcher.py`: passed.
- Gemini model fix tests: `pytest tests/test_ingestion/test_injury_fetcher.py tests/test_scaffold.py::TestConfig -v`: 23 passed.
- Gemini model fix ingestion tests: `pytest tests/test_ingestion/ -v`: 59 passed, 4 warnings.

## Production Audit

- Supabase read-only audit confirmed `max(injuries.report_date) = 2026-05-20` and 0 injury rows after 2026-05-20.
- Game `401873342` is final on 2026-05-21 with 0 player logs, but duplicate game `0042500302` has 26 player logs.
- There are 18 duplicate matchup groups; many duplicate pairs have logs on both IDs, so the migration now merges child rows before adding `uq_game_matchup`.
- Production Alembic version was `c3d4e5f6a7b8` at audit time; branch migrations are not yet applied.
- Railway project `chalk` is available with `production` and `staging` environments.
- `ODDS_API_KEY` is set on `web`, `ingest`, and `prediction` in both production and staging.
- Railway ingest/prediction logs show injury extraction failed because deprecated Gemini model IDs (`gemini-2.0-flash` / `gemini-2.0-flash-001`) return `404 NOT_FOUND`; this branch now defaults `GEMINI_MODEL` to `gemini-2.5-flash`.
- Staging `prediction` service config reports `python scripts/railway_prediction.py`, but the repo script is `scripts/railway_predict.py`; production uses the correct command.

## Open Items

- After deploy, verify injury ingestion inserts rows instead of logging Gemini `404 NOT_FOUND`.
- Fix staging `prediction` service start command to `python scripts/railway_predict.py` if Railway does not pick up `railway.predict.json`.
- Apply migrations only as part of the deploy flow after this code is merged/deployed, because `uq_game_matchup` requires the updated `upsert_games()` duplicate guard.
- Run full baseline: `python scripts/evaluate_baseline.py --season 2024-25 --stats pts reb ast fg3m stl blk to_committed`.
- Retraining remains pending until the full baseline is recorded and data repair is deployed.

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







