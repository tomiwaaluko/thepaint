# Phase 7 — Automation & Monitoring

## Goal
Two Airflow DAGs running unattended daily. Model drift monitoring alerts when MAE degrades.
Predictions available by 6 PM ET on all game days without manual intervention.

## Depends On
Phase 5 complete — full prediction pipeline working end-to-end.

## Unlocks
Phase 8 (Ensemble & Tuning) — needs automated retraining pipeline.

---

## Step 1 — Airflow Setup in Docker Compose

Add Airflow to `docker-compose.yml`:

```yaml
airflow:
  image: apache/airflow:2.9.0
  environment:
    AIRFLOW__CORE__EXECUTOR: LocalExecutor
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://chalk:chalk@db:5432/airflow
    AIRFLOW__CORE__FERNET_KEY: ${AIRFLOW_FERNET_KEY}
    AIRFLOW__WEBSERVER__SECRET_KEY: ${AIRFLOW_SECRET_KEY}
    DATABASE_URL: postgresql+asyncpg://chalk:chalk@db:5432/chalk
    REDIS_URL: redis://redis:6379/0
    ODDS_API_KEY: ${ODDS_API_KEY}
  volumes:
    - ./airflow/dags:/opt/airflow/dags
    - ./chalk:/opt/airflow/chalk
  ports:
    - "8080:8080"
  depends_on:
    - db
```

---

## Step 2 — Daily Ingest DAG

### `airflow/dags/daily_ingest.py`

**Schedule:** `0 8 * * *` (8:00 AM ET daily)

**Tasks in order:**

```
ingest_yesterday_games
        ↓
ingest_injuries
        ↓
fetch_odds_lines
        ↓
validate_row_counts
        ↓
notify_slack (on success or failure)
```

**Task definitions:**

`ingest_yesterday_games`
- Calls `ingest_team_season()` for yesterday's games
- Calls `ingest_player_season()` for all players who played yesterday
- Logs count of rows inserted

`ingest_injuries`
- Calls `ingest_injuries()` from injury_fetcher
- Flags any new "Out" designations for high-usage players

`fetch_odds_lines`
- Calls `fetch_player_props()` and `fetch_game_totals()` for today's games
- Only runs if there are games today

`validate_row_counts`
- Query: count of player_game_logs for yesterday — must be > 0 if games were played
- Query: count of injuries updated today — must be recent
- Raises AirflowException if validation fails (triggers retry + alert)

---

## Step 3 — Daily Predict DAG

### `airflow/dags/daily_predict.py`

**Schedule:** `0 18 * * *` (6:00 PM ET daily, after typical lineup lock)

**Tasks in order:**

```
check_todays_games
        ↓
refresh_injuries          (re-pull injury updates from last 2 hours)
        ↓
invalidate_stale_cache    (clear Redis predictions that predate latest injury report)
        ↓
generate_todays_predictions
        ↓
warm_api_cache             (pre-populate Redis with today's predictions)
        ↓
validate_predictions       (spot-check a sample of predictions)
        ↓
notify_slack
```

**`generate_todays_predictions` task:**
- Get today's game IDs
- Get all players on both rosters for each game
- For each player: call `predict_player()` and store in `predictions` table
- Run concurrently with `asyncio.gather()` — do not run sequentially

**`validate_predictions` task:**
- Sample 10 random predictions from today
- Check: p10 < p50 < p90 for each stat
- Check: p50 for pts between 5 and 60 (sanity bounds)
- Check: p50 for reb between 0 and 25
- Raise AirflowException if any sanity check fails

---

## Step 4 — Model Drift Monitoring

### `chalk/monitoring/drift.py`

After each game day, compare predictions to actual results and track drift over time.

**Function: `compute_daily_mae(session, game_date) → dict[str, float]`**
- For each stat: compute MAE between predictions and actuals for all games on game_date
- Returns: `{"pts": 4.9, "reb": 2.3, ...}`
- Store result in a `model_performance` table

**Function: `check_for_drift(session, stat, window_days=30) → DriftReport`**

```python
@dataclass
class DriftReport:
    stat: str
    rolling_mae: float         # mean MAE over last window_days
    baseline_mae: float        # test MAE from model training
    drift_pct: float           # (rolling - baseline) / baseline
    is_drifting: bool          # True if drift_pct > 0.15 (15% degradation)
    n_predictions: int
```

**`drift_pct > 0.15` (15% worse than baseline) triggers an alert.**

---

## Step 5 — Alerting

### `chalk/monitoring/alerts.py`

Simple Slack webhook alerting. No Slack? Email via SMTP also acceptable.

```python
async def send_slack_alert(message: str, level: str = "info") -> None:
    """
    level: "info" | "warning" | "error"
    Only sends if SLACK_WEBHOOK_URL is set in environment.
    """

async def alert_drift(report: DriftReport) -> None:
    message = (
        f"🚨 Model drift detected for *{report.stat}*\n"
        f"Rolling MAE: {report.rolling_mae:.3f} "
        f"(baseline: {report.baseline_mae:.3f}, +{report.drift_pct*100:.1f}%)\n"
        f"Trigger: retraining recommended"
    )
    await send_slack_alert(message, level="warning")

async def alert_dag_failure(dag_id: str, task_id: str, error: str) -> None
async def alert_predictions_ready(game_count: int, player_count: int) -> None
```

---

## Step 6 — Drift Monitoring DAG

### `airflow/dags/monitoring.py`

**Schedule:** `0 2 * * *` (2:00 AM ET — after games finish and results are in)

**Tasks:**

```
ingest_final_scores    (pull official box scores for yesterday's games)
        ↓
compute_daily_mae      (compare predictions to actuals)
        ↓
check_for_drift        (compare rolling MAE to baseline)
        ↓
alert_if_drifting      (send Slack alert if drift > 15%)
        ↓
update_performance_table
```

---

## Step 7 — Tests

### `tests/test_monitoring/test_drift.py`

`test_drift_report_detects_15pct_degradation`
- Insert predictions with artificially high error
- Verify DriftReport.is_drifting = True

`test_compute_daily_mae_matches_manual_calculation`

### `tests/test_dags/test_daily_ingest.py`

Use Airflow's `DagBag` test utilities:
- `test_dag_loads_without_errors`
- `test_dag_task_order_correct`
- `test_validate_row_counts_raises_on_zero`

---

## Phase 7 Completion Checklist

- [ ] `docker compose up` — Airflow webserver accessible at localhost:8080
- [ ] Both DAGs visible in Airflow UI with correct schedules
- [ ] `daily_ingest` DAG runs end-to-end manually (trigger from UI)
- [ ] `daily_predict` DAG runs end-to-end — predictions in DB after run
- [ ] `monitoring` DAG computes MAE and stores in performance table
- [ ] Drift alert fires in test when MAE > 15% above baseline
- [ ] Slack alert sends (or SLACK_WEBHOOK_URL not set → no-op, no error)
- [ ] `pytest tests/test_dags/ tests/test_monitoring/` — all pass
- [ ] `TODO.md` updated — all Phase 7 checkboxes marked done
