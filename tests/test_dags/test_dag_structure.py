"""Tests for DAG structure — validates DAGs load and have correct task order."""
import importlib
import sys
from unittest.mock import MagicMock

import pytest


# Mock airflow imports so tests run without airflow installed
@pytest.fixture(autouse=True)
def mock_airflow(monkeypatch):
    """Mock airflow modules for DAG structure tests."""
    airflow_mock = MagicMock()
    airflow_mock.DAG = MagicMock()
    airflow_mock.operators = MagicMock()
    airflow_mock.operators.python = MagicMock()
    airflow_mock.exceptions = MagicMock()

    # Create a real PythonOperator mock that tracks task_id
    class FakePythonOperator:
        def __init__(self, task_id, python_callable, dag=None, **kwargs):
            self.task_id = task_id
            self.python_callable = python_callable
            self.downstream_list = []
            self.upstream_list = []

        def __rshift__(self, other):
            if isinstance(other, FakePythonOperator):
                self.downstream_list.append(other)
                other.upstream_list.append(self)
            return other

    airflow_mock.operators.python.PythonOperator = FakePythonOperator

    # AirflowException
    class FakeAirflowException(Exception):
        pass

    airflow_mock.exceptions.AirflowException = FakeAirflowException

    modules_to_mock = {
        "airflow": airflow_mock,
        "airflow.operators": airflow_mock.operators,
        "airflow.operators.python": airflow_mock.operators.python,
        "airflow.exceptions": airflow_mock.exceptions,
    }
    for name, mock in modules_to_mock.items():
        monkeypatch.setitem(sys.modules, name, mock)


class TestDailyIngestDag:
    def test_dag_loads_without_errors(self):
        # Force reimport to use mocked airflow
        if "airflow.dags.daily_ingest" in sys.modules:
            del sys.modules["airflow.dags.daily_ingest"]
        spec = importlib.util.spec_from_file_location(
            "daily_ingest",
            "airflow/dags/daily_ingest.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

    def test_has_correct_tasks(self):
        if "airflow.dags.daily_ingest" in sys.modules:
            del sys.modules["airflow.dags.daily_ingest"]
        spec = importlib.util.spec_from_file_location(
            "daily_ingest",
            "airflow/dags/daily_ingest.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        task_ids = {
            module.t_ingest_games.task_id,
            module.t_ingest_injuries.task_id,
            module.t_fetch_odds.task_id,
            module.t_validate.task_id,
        }
        assert task_ids == {
            "ingest_yesterday_games",
            "ingest_injuries",
            "fetch_odds_lines",
            "validate_row_counts",
        }

    def test_task_order_correct(self):
        if "airflow.dags.daily_ingest" in sys.modules:
            del sys.modules["airflow.dags.daily_ingest"]
        spec = importlib.util.spec_from_file_location(
            "daily_ingest",
            "airflow/dags/daily_ingest.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # ingest_games >> ingest_injuries >> fetch_odds >> validate
        assert module.t_ingest_injuries in module.t_ingest_games.downstream_list
        assert module.t_fetch_odds in module.t_ingest_injuries.downstream_list
        assert module.t_validate in module.t_fetch_odds.downstream_list


class TestDailyPredictDag:
    def test_dag_loads_without_errors(self):
        if "airflow.dags.daily_predict" in sys.modules:
            del sys.modules["airflow.dags.daily_predict"]
        spec = importlib.util.spec_from_file_location(
            "daily_predict",
            "airflow/dags/daily_predict.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

    def test_has_six_tasks(self):
        if "airflow.dags.daily_predict" in sys.modules:
            del sys.modules["airflow.dags.daily_predict"]
        spec = importlib.util.spec_from_file_location(
            "daily_predict",
            "airflow/dags/daily_predict.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        task_ids = {
            module.t_check.task_id,
            module.t_injuries.task_id,
            module.t_invalidate.task_id,
            module.t_predict.task_id,
            module.t_warm.task_id,
            module.t_validate.task_id,
        }
        assert len(task_ids) == 6

    def test_predict_depends_on_invalidate(self):
        if "airflow.dags.daily_predict" in sys.modules:
            del sys.modules["airflow.dags.daily_predict"]
        spec = importlib.util.spec_from_file_location(
            "daily_predict",
            "airflow/dags/daily_predict.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert module.t_predict in module.t_invalidate.downstream_list


class TestMonitoringDag:
    def test_dag_loads_without_errors(self):
        if "airflow.dags.monitoring" in sys.modules:
            del sys.modules["airflow.dags.monitoring"]
        spec = importlib.util.spec_from_file_location(
            "monitoring",
            "airflow/dags/monitoring.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

    def test_has_three_tasks(self):
        if "airflow.dags.monitoring" in sys.modules:
            del sys.modules["airflow.dags.monitoring"]
        spec = importlib.util.spec_from_file_location(
            "monitoring",
            "airflow/dags/monitoring.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        task_ids = {
            module.t_mae.task_id,
            module.t_drift.task_id,
            module.t_alert.task_id,
        }
        assert task_ids == {"compute_daily_mae", "check_for_drift", "alert_if_drifting"}

    def test_drift_check_after_mae(self):
        if "airflow.dags.monitoring" in sys.modules:
            del sys.modules["airflow.dags.monitoring"]
        spec = importlib.util.spec_from_file_location(
            "monitoring",
            "airflow/dags/monitoring.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert module.t_drift in module.t_mae.downstream_list
        assert module.t_alert in module.t_drift.downstream_list
