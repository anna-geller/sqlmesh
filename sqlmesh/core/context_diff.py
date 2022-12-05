"""
# ContextDiff

ContextDiff encapsulate the differences between two environments. The two environments can be the local
environment and a remote environment or two remote environments. ContextDiff is an important part of
SQLMesh. SQLMesh plans use ContextDiff to determine what models were changed between two environments.
The SQLMesh CLI diff command uses ContextDiff to determine what to visualize.

When creating a ContextDiff object, SQLMesh will compare the snapshots from one environment with those of
another remote environment and determine if models have been added, removed, or modified.
"""
from __future__ import annotations

import typing as t

from sqlmesh.core.environment import Environment
from sqlmesh.core.snapshot import Snapshot, SnapshotDataVersion
from sqlmesh.utils.errors import SQLMeshError
from sqlmesh.utils.pydantic import PydanticModel

if t.TYPE_CHECKING:
    from sqlmesh.core.state_sync import StateReader


class ContextDiff(PydanticModel):
    """ContextDiff is an object representing the difference between two environments.

    The two environments can be the local environment and a remote environment or two remote
    environments.
    """

    environment: str
    """The environment to diff."""
    added: t.Set[str]
    """New models."""
    removed: t.Set[str]
    """Deleted models."""
    modified_snapshots: t.Dict[str, t.Tuple[Snapshot, Snapshot]]
    """Modified snapshots."""
    snapshots: t.Dict[str, Snapshot]
    """Merged snapshots."""
    new_snapshots: t.List[Snapshot]
    """New snapshots."""
    previous_plan_id: t.Optional[str]
    """Previous plan id."""

    @classmethod
    def create(
        cls,
        environment: str | Environment,
        snapshots: t.Dict[str, Snapshot],
        state_reader: StateReader,
    ) -> ContextDiff:
        """Create a ContextDiff object.

        Args:
            environment: The remote environment to diff.
            snapshots: The snapshots of the current environment.
            state_reader: StateReader to access the remote environment to diff.

        Returns:
            The ContextDiff object.
        """
        if isinstance(environment, str):
            env = state_reader.get_environment(environment)
        else:
            env = environment
            environment = env.name

        existing_info = {info.name: info for info in (env.snapshots if env else [])}
        existing_models = set(existing_info)
        current_models = set(snapshots)
        removed = existing_models - current_models
        added = current_models - existing_models
        modified_info = {
            name: existing_info[name]
            for name, snapshot in snapshots.items()
            if name not in added
            and snapshot.fingerprint != existing_info[name].fingerprint
        }

        stored = state_reader.get_snapshots(
            list(modified_info.values())
            + [snapshot.snapshot_id for snapshot in snapshots.values()]
        )

        merged_snapshots = {}
        modified_snapshots = {}
        new_snapshots = []
        snapshot_remote_versions: t.Dict[
            str, t.Tuple[t.Tuple[SnapshotDataVersion, ...], int]
        ] = {}

        for name, snapshot in snapshots.items():
            modified = modified_info.get(name)
            existing = stored.get(snapshot.snapshot_id)

            if existing:
                merged_snapshots[name] = existing.copy()
                if modified:
                    modified_snapshots[name] = (existing, stored[modified.snapshot_id])
                    for child, versions in existing.indirect_versions.items():
                        existing_versions = snapshot_remote_versions.get(child)
                        if (
                            not existing_versions
                            or existing_versions[1] < existing.created_ts
                        ):
                            snapshot_remote_versions[child] = (
                                versions,
                                existing.created_ts,
                            )
            else:
                snapshot = snapshot.copy()
                merged_snapshots[name] = snapshot
                new_snapshots.append(snapshot)
                if modified:
                    snapshot.previous_versions = modified.all_versions
                    modified_snapshots[name] = (snapshot, stored[modified.snapshot_id])

        for snapshot in new_snapshots:
            if (
                snapshot.name in snapshot_remote_versions
                and snapshot.previous_version
                and snapshot.data_hash_matches(snapshot.previous_version)
            ):
                remote_versions = snapshot_remote_versions[snapshot.name][0]
                remote_head = remote_versions[-1].version
                local_head = snapshot.previous_version.version

                if remote_head in (
                    local.version for local in snapshot.previous_versions
                ):
                    snapshot.set_version(local_head)
                elif local_head in (remote.version for remote in remote_versions):
                    snapshot.set_version(remote_head)
                else:
                    snapshot.set_version()

        return ContextDiff(
            environment=environment,
            added=added,
            removed=removed,
            modified_snapshots=modified_snapshots,
            snapshots=merged_snapshots,
            new_snapshots=new_snapshots,
            previous_plan_id=env.plan_id if env else None,
        )

    @property
    def has_differences(self) -> bool:
        return bool(self.added or self.removed or self.modified_snapshots)

    def directly_modified(self, model_name: str) -> bool:
        """Returns whether or not a model was directly modified in this context.

        Args:
            model_name: The model_name to check.

        Returns:
            Whether or not the model was directly modified.
        """

        if model_name not in self.modified_snapshots:
            return False

        current, previous = self.modified_snapshots[model_name]
        return not current.data_hash_matches(previous)

    def text_diff(self, model: str) -> str:
        """Finds the difference of a model between the current and remote environment.

        Args:
            model: The model name.

        Returns:
            A unified text diff of the model.
        """
        if model not in self.snapshots:
            raise SQLMeshError(f"`{model}` does not exist.")
        if model not in self.modified_snapshots:
            return ""

        new, old = self.modified_snapshots[model]
        return old.model.text_diff(new.model)