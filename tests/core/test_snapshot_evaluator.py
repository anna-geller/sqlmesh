import typing as t
from unittest.mock import call

import pytest
from pytest_mock.plugin import MockerFixture
from sqlglot import expressions as exp
from sqlglot import parse_one

from sqlmesh.core.engine_adapter import EngineAdapter
from sqlmesh.core.model import Model
from sqlmesh.core.snapshot import Snapshot, SnapshotTableInfo
from sqlmesh.core.snapshot_evaluator import SnapshotEvaluator


@pytest.fixture
def snapshot(duck_conn, make_snapshot) -> Snapshot:
    duck_conn.execute("CREATE VIEW tbl AS SELECT 1 AS a")

    model = Model(
        name="db.model",
        kind="snapshot",
        query=parse_one("SELECT a::int FROM tbl"),
    )

    snapshot = make_snapshot(model)
    snapshot.version = snapshot.fingerprint
    return snapshot


@pytest.fixture
def date_kwargs() -> t.Dict[str, str]:
    return {
        "start": "2020-01-01",
        "end": "2020-01-01",
        "latest": "2020-01-01",
    }


def test_evaluate(mocker: MockerFixture, make_snapshot):
    adapter_mock = mocker.patch("sqlmesh.core.engine_adapter.EngineAdapter")

    evaluator = SnapshotEvaluator(adapter_mock)

    model = Model(
        name="test_schema.test_model",
        storage_format="parquet",
        partitioned_by=["a"],
        query=parse_one(
            "SELECT a::int FROM tbl WHERE ds BETWEEN @start_ds and @end_ds"
        ),
    )

    snapshot = make_snapshot(model, physical_schema="physical_schema", version="1")
    evaluator.create(snapshot, {})
    evaluator.evaluate(
        snapshot,
        "2020-01-01",
        "2020-01-02",
        "2020-01-02",
        snapshots={},
    )

    assert adapter_mock.create_schema.mock_calls == [
        call("physical_schema"),
    ]

    adapter_mock.create_table.assert_called_once_with(
        "physical_schema.test_schema__test_model__1",
        columns={"a": exp.DataType.build("int")},
        storage_format="parquet",
        partitioned_by=["a"],
    )


def test_promote(mocker: MockerFixture, make_snapshot):
    adapter_mock = mocker.patch("sqlmesh.core.engine_adapter.EngineAdapter")

    evaluator = SnapshotEvaluator(adapter_mock)

    model = Model(
        name="test_schema.test_model",
        storage_format="parquet",
        partitioned_by=["a"],
        query=parse_one("SELECT a FROM tbl WHERE ds BETWEEN @start_ds and @end_ds"),
    )

    evaluator.promote(
        make_snapshot(model, physical_schema="physical_schema", version="1"),
        "test_env",
    )

    adapter_mock.create_schema.assert_called_once_with("test_schema__test_env")
    adapter_mock.create_view.assert_called_once_with(
        "test_schema__test_env.test_model",
        parse_one("SELECT * FROM physical_schema.test_schema__test_model__1"),
    )


def test_promote_model_info(mocker: MockerFixture):
    adapter_mock = mocker.patch("sqlmesh.core.engine_adapter.EngineAdapter")

    evaluator = SnapshotEvaluator(adapter_mock)

    evaluator.promote(
        SnapshotTableInfo(
            physical_schema="physical_schema",
            name="test_schema.test_model",
            fingerprint="1",
            version="1",
        ),
        "test_env",
    )

    adapter_mock.create_schema.assert_called_once_with("test_schema__test_env")
    adapter_mock.create_view.assert_called_once_with(
        "test_schema__test_env.test_model",
        parse_one("SELECT * FROM physical_schema.test_schema__test_model__1"),
    )


def test_evaluate_creation_duckdb(
    snapshot: Snapshot,
    duck_conn,
    date_kwargs: t.Dict[str, str],
):
    evaluator = SnapshotEvaluator(EngineAdapter(duck_conn, "duckdb"))
    evaluator.create(snapshot, {})
    version = snapshot.version

    def assert_tables_exist() -> None:
        assert duck_conn.execute(
            "SELECT table_schema, table_name, table_type FROM information_schema.tables"
        ).fetchall() == [
            ("sqlmesh", f"db__model__{version}", "BASE TABLE"),
            ("main", "tbl", "VIEW"),
        ]

    # test that a clean run works
    evaluator.evaluate(
        snapshot,
        "2020-01-01",
        "2020-01-01",
        "2020-01-01",
        snapshots={},
    )
    assert_tables_exist()
    assert duck_conn.execute(
        f"SELECT * FROM sqlmesh.db__model__{version}"
    ).fetchall() == [(1,)]

    # test that existing tables work
    evaluator.evaluate(
        snapshot,
        "2020-01-01",
        "2020-01-01",
        "2020-01-01",
        snapshots={},
    )
    assert_tables_exist()
    assert duck_conn.execute(
        f"SELECT * FROM sqlmesh.db__model__{version}"
    ).fetchall() == [
        (1,),
        (1,),
    ]