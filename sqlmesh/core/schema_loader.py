from __future__ import annotations

import logging
import typing as t
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlglot import exp
from sqlglot.dialects.dialect import DialectType

from sqlmesh.core.engine_adapter import EngineAdapter
from sqlmesh.core.model.definition import Model
from sqlmesh.core.state_sync import StateReader
from sqlmesh.utils import UniqueKeyDict, yaml

logger = logging.getLogger(__name__)


def create_schema_file(
    path: Path,
    models: UniqueKeyDict[str, Model],
    adapter: EngineAdapter,
    state_reader: StateReader,
    dialect: DialectType,
    max_workers: int = 1,
) -> None:
    """Create or replace a YAML file with model schemas.

    Args:
        path: The path to store the YAML file.
        models: FQN to model
        adapter: The engine adapter.
        state_reader: The state reader.
        dialect: The dialect to serialize the schema as.
        max_workers: The max concurrent workers to fetch columns.
    """
    external_table_names = set()

    possible_fqn_to_name_mapping = {}
    for model in models.values():
        if model.kind.is_external:
            external_table_names.add(model.name)
        for dep in model.depends_on:
            if dep not in models:
                dep_table = exp.to_table(dep, dialect=dialect)
                external_table_names.add(dep)
                if dep_table.catalog:
                    dep_table.set("catalog", None)
                    dep_table_name = dep_table.sql(dialect=dialect)
                    possible_fqn_to_name_mapping[dep] = dep_table_name
                    external_table_names.add(dep_table_name)

    # Make sure we don't convert internal models into external ones.
    possible_existing_snapshots = state_reader.get_snapshots_by_name(
        external_table_names, exclude_external=True
    )
    existing_models = set()
    for possible_existing_snapshot in possible_existing_snapshots:
        model_name = possible_fqn_to_name_mapping.get(possible_existing_snapshot.fqn)
        if (
            model_name
            and (
                possible_existing_snapshot.fqn != possible_existing_snapshot.name
                and possible_existing_snapshot.name == model_name
            )
            or (possible_existing_snapshot.fqn == possible_existing_snapshot.name)
        ):
            existing_models.add(possible_existing_snapshot.fqn)

    if existing_models:
        logger.warning(
            "The following models already exist and can't be converted to external: %s."
            "Perhaps these models have been removed, while downstream models that reference them weren't updated accordingly",
            ", ".join(existing_models),
        )
        external_table_names -= existing_models

    with ThreadPoolExecutor(max_workers=max_workers) as pool:

        def _get_columns(table: str) -> t.Optional[t.Dict[str, t.Any]]:
            try:
                return adapter.columns(table, include_pseudo_columns=True)
            except Exception as e:
                logger.warning(f"Unable to get schema for '{table}': '{e}'.")
                return None

        schemas = [
            {
                "name": exp.to_table(table).sql(dialect=dialect),
                "columns": {c: dtype.sql(dialect=dialect) for c, dtype in columns.items()},
            }
            for table, columns in sorted(
                pool.map(
                    lambda table: (table, _get_columns(table)),
                    external_table_names,
                )
            )
            if columns
        ]

        with open(path, "w", encoding="utf-8") as file:
            yaml.dump(schemas, file)
