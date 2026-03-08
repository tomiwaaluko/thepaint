"""Model drift monitoring DAG — compares predictions to actuals nightly."""
import asyncio
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "chalk",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

dag = DAG(
    dag_id="monitoring",
    default_args=default_args,
    description="Model drift monitoring — compare predictions to actuals",
    schedule="0 2 * * *",  # 2:00 AM ET daily
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["chalk", "monitoring"],
)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def compute_daily_mae_task(**context):
    """Compute MAE for yesterday's predictions vs actuals."""
    from chalk.db.session import async_session_factory
    from chalk.monitoring.drift import compute_daily_mae

    yesterday = (datetime.utcnow() - timedelta(days=1)).date()

    async def _run():
        async with async_session_factory() as session:
            maes = await compute_daily_mae(session, yesterday)
            print(f"Daily MAE for {yesterday}: {maes}")
            return maes

    maes = _run_async(_run())
    context["ti"].xcom_push(key="daily_maes", value=maes)
    return maes


def check_for_drift_task(**context):
    """Check rolling MAE vs baseline for each stat."""
    from chalk.db.session import async_session_factory
    from chalk.monitoring.drift import check_for_drift, BASELINE_MAES

    async def _run():
        reports = []
        async with async_session_factory() as session:
            for stat in BASELINE_MAES:
                report = await check_for_drift(session, stat)
                reports.append({
                    "stat": report.stat,
                    "rolling_mae": report.rolling_mae,
                    "baseline_mae": report.baseline_mae,
                    "drift_pct": report.drift_pct,
                    "is_drifting": report.is_drifting,
                    "n_predictions": report.n_predictions,
                })
                print(
                    f"{stat}: rolling={report.rolling_mae:.3f} "
                    f"baseline={report.baseline_mae:.3f} "
                    f"drift={report.drift_pct * 100:.1f}% "
                    f"{'DRIFTING' if report.is_drifting else 'OK'}"
                )
        return reports

    reports = _run_async(_run())
    context["ti"].xcom_push(key="drift_reports", value=reports)
    return reports


def alert_if_drifting_task(**context):
    """Send alerts for any drifting stats."""
    from chalk.monitoring.alerts import alert_drift
    from chalk.monitoring.drift import DriftReport

    reports = context["ti"].xcom_pull(task_ids="check_for_drift", key="drift_reports")
    if not reports:
        print("No drift reports to check")
        return

    async def _run():
        for r in reports:
            if r["is_drifting"]:
                report = DriftReport(**r)
                await alert_drift(report)
                print(f"Alert sent for {r['stat']}")

    _run_async(_run())


# Task definitions
t_mae = PythonOperator(task_id="compute_daily_mae", python_callable=compute_daily_mae_task, dag=dag)
t_drift = PythonOperator(task_id="check_for_drift", python_callable=check_for_drift_task, dag=dag)
t_alert = PythonOperator(task_id="alert_if_drifting", python_callable=alert_if_drifting_task, dag=dag)

# Dependencies
t_mae >> t_drift >> t_alert
