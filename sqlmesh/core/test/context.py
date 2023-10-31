from __future__ import annotations

import typing as t

from sqlmesh.core.context import ExecutionContext
from sqlmesh.core.engine_adapter import EngineAdapter
from sqlmesh.core.model.registry import ModelRegistry
from sqlmesh.core.test.definition import _fully_qualified_test_fixture_name


class TestExecutionContext(ExecutionContext):
    """The context needed to execute a Python model test.

    Args:
        engine_adapter: The engine adapter to execute queries against.
        model_registry: All upstream models to use for expansion and mapping of physical locations.
    """

    def __init__(
        self,
        engine_adapter: EngineAdapter,
        model_registry: ModelRegistry,
    ):
        self.is_dev = True
        self._engine_adapter = engine_adapter
        self.__model_tables = {
            name: _fully_qualified_test_fixture_name(name, model_registry)
            for name in model_registry.all_names
        }

    @property
    def _model_tables(self) -> t.Dict[str, str]:
        """Returns a mapping of model names to tables."""
        return self.__model_tables
