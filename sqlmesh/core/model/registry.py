from __future__ import annotations

import typing as t

from sqlmesh.core.model.definition import Model
from sqlmesh.utils.pydantic import PydanticModel

if t.TYPE_CHECKING:
    from sqlmesh.core.snapshot import Snapshot


class ModelRegistry(PydanticModel):
    """
    Contains registered models that can be accessed by both their name and fully qualified name.
    Ensures that a model is not added twice.
    Ensures that duplicate models are not returned if accessing all models
    """

    # Contains all models by their model name
    name_to_model: t.Dict[str, Model] = {}

    # Contains fully qualified models by their fqn only if that is different from their name
    fqn_to_model: t.Dict[str, Model] = {}

    @classmethod
    def from_snapshots(cls, snapshots: t.Iterable[Snapshot]) -> ModelRegistry:
        model_registry = cls()
        for snapshot in snapshots:
            if snapshot.is_model:
                model_registry.add(snapshot.model)
        return model_registry

    @property
    def models(self) -> t.ValuesView[Model]:
        return self.name_to_model.values()

    @property
    def all_names(self) -> t.Set[str]:
        return set(self.name_to_model).union(set(self.fqn_to_model))

    def __getitem__(self, item: str) -> Model:
        return self.get_or_raise(item)

    def __contains__(self, item: str) -> bool:
        return item in self.all_names

    def __len__(self) -> int:
        return len(self.name_to_model) + len(self.fqn_to_model)

    def add(self, model: Model) -> None:
        if model.name in self.name_to_model or model.name in self.fqn_to_model:
            raise ValueError(f"Duplicate model name found in registry. Name: {model.name}")
        self.name_to_model[model.name] = model
        if model.name_and_fqn_are_different:
            if model.fqn in self.fqn_to_model or model.fqn in self.name_to_model:
                raise ValueError(f"Duplicate model fqn found in registry. FQN: {model.fqn}")
            self.fqn_to_model[model.fqn] = model

    def upsert(self, model: Model) -> None:
        self.name_to_model.update({model.name: model})
        if model.name_and_fqn_are_different:
            self.fqn_to_model.update({model.fqn: model})

    def get(self, name: str) -> t.Optional[Model]:
        return self.name_to_model.get(name) or self.fqn_to_model.get(name)

    def get_or_raise(self, name: str) -> Model:
        try:
            return self.name_to_model.get(name) or self.fqn_to_model[name]
        except KeyError:
            raise ValueError(f"Model not found in registry but was expected. Name: {name}")

    def merge(self, model_registry: ModelRegistry) -> None:
        for model in model_registry.models:
            self.add(model)

    def filter(self, func: t.Callable) -> ModelRegistry:
        new_model_registry = ModelRegistry()
        for model in self.models:
            if func(model):
                new_model_registry.add(model)
        return new_model_registry

    def get_both_names(self, name: str) -> t.Set[str]:
        model = self.get(name)
        if model is None:
            return set()
        return {model.name, model.fqn}

    def get_model_name(self, name: str) -> t.Optional[str]:
        model = self.get(name)
        if model is None:
            return None
        return model.name
