from __future__ import annotations

import logging
import typing as t

from airflow import DAG
from airflow.models import BaseOperator
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator
from airflow.utils.session import provide_session
from sqlalchemy.orm import Session

from sqlmesh.core._typing import NotificationTarget
from sqlmesh.core.environment import Environment
from sqlmesh.core.plan import PlanStatus
from sqlmesh.core.snapshot import Snapshot, SnapshotId, SnapshotTableInfo
from sqlmesh.integrations.github.notification_operator_provider import (
    GithubNotificationOperatorProvider,
)
from sqlmesh.integrations.github.notification_target import GithubNotificationTarget
from sqlmesh.schedulers.airflow import common, util
from sqlmesh.schedulers.airflow.operators import targets
from sqlmesh.schedulers.airflow.operators.hwm_sensor import HighWaterMarkSensor
from sqlmesh.schedulers.airflow.operators.hwm_signal import HighWaterMarkSignalOperator
from sqlmesh.schedulers.airflow.operators.notification import (
    BaseNotificationOperatorProvider,
)
from sqlmesh.schedulers.airflow.state_sync.xcom import XComStateSync
from sqlmesh.utils.date import TimeLike, now, to_datetime
from sqlmesh.utils.errors import SQLMeshError

logger = logging.getLogger(__name__)


TASK_ID_DATE_FORMAT = "%Y-%m-%d_%H-%M-%S"

NOTIFICATION_TARGET_TO_OPERATOR_PROVIDER: t.Dict[
    t.Type[NotificationTarget], BaseNotificationOperatorProvider
] = {
    GithubNotificationTarget: GithubNotificationOperatorProvider(),
}


class SnapshotDagGenerator:
    def __init__(
        self,
        engine_operator: t.Type[BaseOperator],
        engine_operator_args: t.Optional[t.Dict[str, t.Any]],
        ddl_engine_operator_args: t.Optional[t.Dict[str, t.Any]],
        snapshots: t.Dict[SnapshotId, Snapshot],
    ):
        self._engine_operator = engine_operator
        self._engine_operator_args = engine_operator_args or {}
        self._ddl_engine_operator_args = (
            ddl_engine_operator_args or self._engine_operator_args
        )
        self._snapshots = snapshots

    def generate_incremental(self) -> t.List[DAG]:
        return [
            self._create_incremental_dag_for_snapshot(s)
            for s in self._snapshots.values()
            if s.unpaused_ts
        ]

    def generate_apply(self, request: common.PlanApplicationRequest) -> DAG:
        return self._create_plan_application_dag(request)

    def _create_incremental_dag_for_snapshot(self, snapshot: Snapshot) -> DAG:
        dag_id = common.dag_id_for_snapshot_info(snapshot.table_info)
        logger.info(
            "Generating the incremental DAG '%s' for snapshot %s",
            dag_id,
            snapshot.snapshot_id,
        )

        if not snapshot.unpaused_ts:
            raise SQLMeshError(
                f"Can't create an incremental DAG for the paused snapshot {snapshot.snapshot_id}"
            )

        with DAG(
            dag_id=dag_id,
            schedule_interval=snapshot.model.cron,
            start_date=to_datetime(snapshot.unpaused_ts),
            catchup=True,
            is_paused_upon_creation=False,
            tags=[
                common.SQLMESH_AIRFLOW_TAG,
                common.SNAPSHOT_AIRFLOW_TAG,
                snapshot.name,
            ],
        ) as dag:

            hwm_sensor_tasks = self._create_hwm_sensors(snapshot=snapshot)

            evaluator_task = self._create_snapshot_evaluator_operator(
                snapshots=self._snapshots,
                snapshot=snapshot,
                task_id="snapshot_evaluator",
            )

            hwm_signal_task = HighWaterMarkSignalOperator(
                task_id="high_water_mark_signal"
            )

            hwm_sensor_tasks >> evaluator_task >> hwm_signal_task

            return dag

    def _create_plan_application_dag(
        self, request: common.PlanApplicationRequest
    ) -> DAG:
        dag_id = common.plan_application_dag_id(
            request.environment_name, request.request_id
        )
        logger.info(
            "Generating the plan application DAG '%s' for environment '%s'",
            dag_id,
            request.environment_name,
        )

        new_snapshots = {
            s for snapshots in request.new_snapshot_batches for s in snapshots
        }
        all_snapshots = {
            **{s.snapshot_id: s for s in new_snapshots},
            **self._snapshots,
        }

        with DAG(
            dag_id=dag_id,
            schedule_interval="@once",
            start_date=now(),
            catchup=False,
            is_paused_upon_creation=False,
            tags=[
                common.SQLMESH_AIRFLOW_TAG,
                common.PLAN_AIRFLOW_TAG,
                request.environment_name,
            ],
        ) as dag:
            start_task = EmptyOperator(task_id="plan_application_start")
            end_task = EmptyOperator(task_id="plan_application_end")

            (create_start_task, create_end_task) = self._create_creation_tasks(
                request.new_snapshot_batches
            )

            (backfill_start_task, backfill_end_task) = self._create_backfill_tasks(
                request.backfill_intervals_per_snapshot, all_snapshots
            )

            (
                promote_start_task,
                promote_end_task,
            ) = self._create_promotion_demotion_tasks(
                request.promotion_batches,
                request.demotion_batches,
                request.environment_name,
                request.start,
                request.end,
                request.no_gaps,
                request.plan_id,
                request.previous_plan_id,
            )

            start_task >> create_start_task
            create_end_task >> backfill_start_task
            backfill_end_task >> promote_start_task

            self._add_notification_target_tasks(
                request, start_task, end_task, promote_end_task
            )
            return dag

    def _add_notification_target_tasks(
        self,
        request: common.PlanApplicationRequest,
        start_task: BaseOperator,
        end_task: BaseOperator,
        promote_end_task: BaseOperator,
    ) -> None:
        has_success_or_failed_notification = False
        for notification_target in request.notification_targets:
            notification_operator_provider = (
                NOTIFICATION_TARGET_TO_OPERATOR_PROVIDER.get(type(notification_target))
            )
            if not notification_operator_provider:
                continue
            plan_start_notification_task = notification_operator_provider.operator(
                notification_target, PlanStatus.STARTED, request
            )
            plan_success_notification_task = notification_operator_provider.operator(
                notification_target, PlanStatus.FINISHED, request
            )
            plan_failed_notification_task = notification_operator_provider.operator(
                notification_target, PlanStatus.FAILED, request
            )
            if plan_start_notification_task:
                start_task >> plan_start_notification_task
            if plan_success_notification_task:
                has_success_or_failed_notification = True
                promote_end_task >> plan_success_notification_task
                plan_success_notification_task >> end_task
            if plan_failed_notification_task:
                has_success_or_failed_notification = True
                promote_end_task >> plan_failed_notification_task
                plan_failed_notification_task >> end_task
        if not has_success_or_failed_notification:
            promote_end_task >> end_task

    def _create_creation_tasks(
        self, new_snapshot_batches: t.List[t.List[Snapshot]]
    ) -> t.Tuple[BaseOperator, BaseOperator]:
        start_task = EmptyOperator(task_id="snapshot_creation_start")
        end_task = EmptyOperator(task_id="snapshot_creation_end")

        new_snapshot_batches = [b for b in new_snapshot_batches if b]

        if not new_snapshot_batches:
            start_task >> end_task
            return (start_task, end_task)

        new_snapshots = [s for snapshots in new_snapshot_batches for s in snapshots]
        update_state_task = PythonOperator(
            task_id="snapshot_creation__update_state",
            python_callable=creation_update_state_task,
            op_kwargs={"new_snapshots": new_snapshots},
        )

        update_state_task >> end_task

        for batch_id, batch in enumerate(new_snapshot_batches):
            task = self._create_snapshot_create_table_operator(
                batch, f"snapshot_creation__create_tables_batch_{batch_id}"
            )
            start_task >> task
            task >> update_state_task

        return (start_task, end_task)

    def _create_promotion_demotion_tasks(
        self,
        promotion_batches: t.List[t.List[SnapshotTableInfo]],
        demotion_batches: t.List[t.List[SnapshotTableInfo]],
        environment: str,
        start: TimeLike,
        end: t.Optional[TimeLike],
        no_gaps: bool,
        plan_id: str,
        previous_plan_id: t.Optional[str],
    ) -> t.Tuple[BaseOperator, BaseOperator]:
        start_task = EmptyOperator(task_id="snapshot_promotion_start")
        end_task = EmptyOperator(task_id="snapshot_promotion_end")

        snapshots = [s for snapshots in promotion_batches for s in snapshots]
        update_state_task = PythonOperator(
            task_id="snapshot_promotion__update_state",
            python_callable=promotion_update_state_task,
            op_kwargs={
                "snapshots": snapshots,
                "environment_name": environment,
                "start": start,
                "end": end,
                "no_gaps": no_gaps,
                "plan_id": plan_id,
                "previous_plan_id": previous_plan_id,
            },
        )

        start_task >> update_state_task

        promotion_batches = [b for b in promotion_batches if b]
        demotion_batches = [b for b in demotion_batches if b]

        for batch_id, batch in enumerate(promotion_batches):
            task = self._create_snapshot_promotion_operator(
                batch,
                environment,
                f"snapshot_promotion__create_views_batch_{batch_id}",
            )
            update_state_task >> task
            task >> end_task

        for batch_id, batch in enumerate(demotion_batches):
            task = self._create_snapshot_demotion_operator(
                batch,
                environment,
                f"snapshot_promotion__delete_views_batch_{batch_id}",
            )
            update_state_task >> task
            task >> end_task

        if not promotion_batches and not demotion_batches:
            update_state_task >> end_task

        return (start_task, end_task)

    def _create_backfill_tasks(
        self,
        backfill_intervals: t.List[common.BackfillIntervalsPerSnapshot],
        snapshots: t.Dict[SnapshotId, Snapshot],
    ) -> t.Tuple[BaseOperator, BaseOperator]:
        snapshot_to_tasks = {}
        for intervals_per_snapshot in backfill_intervals:
            sid = intervals_per_snapshot.snapshot_id

            if not intervals_per_snapshot.intervals:
                logger.info(f"Skipping backfill for snapshot %s", sid)
                continue

            snapshot = snapshots[sid]

            task_id_prefix = (
                f"snapshot_evaluator__{snapshot.name}__{snapshot.fingerprint}"
            )
            tasks = [
                self._create_snapshot_evaluator_operator(
                    snapshots=snapshots,
                    snapshot=snapshot,
                    task_id=f"{task_id_prefix}__{start.strftime(TASK_ID_DATE_FORMAT)}__{end.strftime(TASK_ID_DATE_FORMAT)}",
                    start=start,
                    end=end,
                )
                for (start, end) in intervals_per_snapshot.intervals
            ]
            snapshot_start_task = EmptyOperator(
                task_id=f"snapshot_backfill__{snapshot.name}__{snapshot.fingerprint}__start"
            )
            snapshot_end_task = EmptyOperator(
                task_id=f"snapshot_backfill__{snapshot.name}__{snapshot.fingerprint}__end"
            )
            snapshot_start_task >> tasks >> snapshot_end_task
            snapshot_to_tasks[snapshot.snapshot_id] = (
                snapshot_start_task,
                snapshot_end_task,
            )

        backfill_start_task = EmptyOperator(task_id="snapshot_backfill_start")
        backfill_end_task = EmptyOperator(task_id="snapshot_backfill_end")

        if not snapshot_to_tasks:
            backfill_start_task >> backfill_end_task
            return (backfill_start_task, backfill_end_task)

        entry_tasks = []
        parent_ids_to_backfill = set()
        for sid, (start_task, _) in snapshot_to_tasks.items():
            has_parents_to_backfill = False
            for p_sid in snapshots[sid].parents:
                if p_sid in snapshot_to_tasks:
                    snapshot_to_tasks[p_sid][1] >> start_task
                    parent_ids_to_backfill.add(p_sid)
                    has_parents_to_backfill = True

            if not has_parents_to_backfill:
                entry_tasks.append(start_task)

        backfill_start_task >> entry_tasks

        exit_tasks = [
            end_task
            for sid, (_, end_task) in snapshot_to_tasks.items()
            if sid not in parent_ids_to_backfill
        ]
        for task in exit_tasks:
            task >> backfill_end_task

        return (backfill_start_task, backfill_end_task)

    def _create_snapshot_promotion_operator(
        self,
        snapshots: t.List[SnapshotTableInfo],
        environment: str,
        task_id: str,
    ) -> BaseOperator:
        return self._engine_operator(
            **self._ddl_engine_operator_args,
            target=targets.SnapshotPromotionTarget(
                snapshots=snapshots,
                environment=environment,
            ),
            task_id=task_id,
        )

    def _create_snapshot_demotion_operator(
        self,
        snapshots: t.List[SnapshotTableInfo],
        environment: str,
        task_id: str,
    ) -> BaseOperator:
        return self._engine_operator(
            **self._ddl_engine_operator_args,
            target=targets.SnapshotDemotionTarget(
                snapshots=snapshots,
                environment=environment,
            ),
            task_id=task_id,
        )

    def _create_snapshot_create_table_operator(
        self,
        new_snapshots: t.List[Snapshot],
        task_id: str,
    ) -> BaseOperator:
        return self._engine_operator(
            **self._ddl_engine_operator_args,
            target=targets.SnapshotCreateTableTarget(new_snapshots=new_snapshots),
            task_id=task_id,
        )

    def _create_snapshot_evaluator_operator(
        self,
        snapshots: t.Dict[SnapshotId, Snapshot],
        snapshot: Snapshot,
        task_id: str,
        start: t.Optional[TimeLike] = None,
        end: t.Optional[TimeLike] = None,
    ) -> BaseOperator:
        table_mapping = {}
        for sid in [snapshot.snapshot_id, *snapshot.parents]:
            parent_snapshot = snapshots[sid]
            table_mapping[sid.name] = parent_snapshot.table_name

        return self._engine_operator(
            **self._engine_operator_args,
            target=targets.SnapshotEvaluationTarget(
                snapshot=snapshot,
                table_mapping=table_mapping,
                start=start,
                end=end,
            ),
            task_id=task_id,
        )

    def _create_hwm_sensors(self, snapshot: Snapshot) -> t.List[HighWaterMarkSensor]:
        output = []
        for upstream_snapshot_id in snapshot.parents:
            upstream_snapshot = self._snapshots[upstream_snapshot_id]
            upstream_dag_id = common.dag_id_for_snapshot_info(
                upstream_snapshot.table_info
            )
            output.append(
                HighWaterMarkSensor(
                    target_dag_id=upstream_dag_id,
                    target_cron=upstream_snapshot.model.cron,
                    this_cron=snapshot.model.cron,
                    task_id=f"{upstream_dag_id}_high_water_mark_sensor",
                )
            )
        return output


@provide_session
def creation_update_state_task(
    new_snapshots: t.List[Snapshot],
    session: Session = util.PROVIDED_SESSION,
) -> None:
    XComStateSync(session).push_snapshots(new_snapshots)


@provide_session
def promotion_update_state_task(
    snapshots: t.List[SnapshotTableInfo],
    environment_name: str,
    start: TimeLike,
    end: t.Optional[TimeLike],
    no_gaps: bool,
    plan_id: str,
    previous_plan_id: t.Optional[str],
    session: Session = util.PROVIDED_SESSION,
) -> None:
    environment = Environment(
        name=environment_name,
        snapshots=snapshots,
        start=start,
        end=end,
        plan_id=plan_id,
        previous_plan_id=previous_plan_id,
    )
    XComStateSync(session).promote(environment, no_gaps=no_gaps)