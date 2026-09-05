"""Airflow DAG for the NetSage AI pipeline.

Schedule: hourly. Each run re-reads the case intake folder, runs the
deterministic checks on anything new, asks the AI assistant for a proposal,
and refreshes the dashboard numbers.

The DAG contains no business logic of its own. Every task calls a function in
`app.pipeline`, which is the same code `scripts/run_pipeline.py` calls. That
way the scheduled run and the manual run can never drift apart.

Deliberately NOT in this DAG: any task that applies a fix, or that marks a
diagnosis as correct. Those require a human in the web app.

Install: copy or symlink this file into $AIRFLOW_HOME/dags/ and make sure the
project root is importable, e.g.

    export PYTHONPATH=/path/to/netsage:$PYTHONPATH
    export NETSAGE_DATABASE_URL=postgresql+psycopg2://netsage:netsage@localhost:5432/netsage
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

# Make the project importable when Airflow loads this file from its dags dir.
PROJECT_ROOT = os.environ.get(
    "NETSAGE_PROJECT_ROOT",
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.db import init_db          # noqa: E402
from app.pipeline import (          # noqa: E402
    build_metrics, ingest_cases, run_diagnoses, run_rule_checks,
)

default_args = {
    "owner": "netsage",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "depends_on_past": False,
}


def _t_init(**_):
    init_db()
    return "schema ready"


def _t_ingest(**_):
    result = ingest_cases()
    print(f"Ingest: {result}")
    return result


def _t_rules(**_):
    result = run_rule_checks()
    print(f"Rule checks: {result}")
    return result


def _t_diagnose(**_):
    result = run_diagnoses()
    print(f"Diagnoses: {result}")
    return result


def _t_metrics(**_):
    result = build_metrics()
    print(f"Metrics: {result}")
    if result["pending_review"]:
        print(
            f"{result['pending_review']} proposals are waiting on a human "
            f"decision. They are not counted as correct."
        )
    return result


with DAG(
    dag_id="netsage_pipeline",
    description="Ingest network cases, run rule checks and AI diagnosis",
    default_args=default_args,
    start_date=datetime(2025, 1, 1),
    schedule="@hourly",
    catchup=False,
    max_active_runs=1,
    tags=["netsage", "networking", "ai"],
) as dag:

    init = PythonOperator(task_id="init_schema", python_callable=_t_init)
    ingest = PythonOperator(task_id="ingest_cases", python_callable=_t_ingest)
    rules = PythonOperator(task_id="run_rule_checks", python_callable=_t_rules)
    diagnose = PythonOperator(task_id="run_ai_diagnoses", python_callable=_t_diagnose)
    metrics = PythonOperator(task_id="build_metrics", python_callable=_t_metrics)

    # Rule checks run before diagnosis on purpose: the deterministic findings
    # are fed into the AI prompt as established facts.
    init >> ingest >> rules >> diagnose >> metrics
