"""Airflow 리스너 플러그인 — DAG 실행 · 태스크 상태가 바뀔 때마다 관제 스냅샷을 갱신 (shi_status_sync)

DAG 실행 이벤트는 scheduler 에서, 태스크 이벤트는 태스크 프로세스에서 불린다.
이벤트 시점에는 바뀐 상태가 메타 DB 에 아직 커밋되기 전이라, 그 실행 · 태스크 상태만 덮어써서 보낸다.
"""
import sys

from airflow.listeners import hookimpl
from airflow.plugins_manager import AirflowPlugin

import shi_status_sync


def _ti_key(ti):
    return (ti.dag_id, ti.run_id, ti.task_id)


def _run_key(dag_run):
    return (dag_run.dag_id, dag_run.run_id)


@hookimpl
def on_dag_run_running(dag_run, msg):
    shi_status_sync.sync({_run_key(dag_run): "running"})


@hookimpl
def on_dag_run_success(dag_run, msg):
    shi_status_sync.sync({_run_key(dag_run): "success"})


@hookimpl
def on_dag_run_failed(dag_run, msg):
    shi_status_sync.sync({_run_key(dag_run): "failed"})


@hookimpl
def on_task_instance_running(previous_state, task_instance):
    shi_status_sync.sync({_ti_key(task_instance): "running"})


@hookimpl
def on_task_instance_success(previous_state, task_instance):
    shi_status_sync.sync({_ti_key(task_instance): "success"})


@hookimpl
def on_task_instance_failed(previous_state, task_instance, error):
    shi_status_sync.sync({_ti_key(task_instance): "failed"})


class ShiStatusPlugin(AirflowPlugin):
    name = "shi_status"
    listeners = [sys.modules[__name__]]
