"""Strict identifiers for the retained-copy journal operation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class CopyBinding:
    destination: str
    parent_device: int
    parent_inode: int
    token: str
    content: str
    reserve_bytes: int
    source_scope: str
    artifact_name: str | None = None

    def encode(self) -> str:
        value = (
            f"external:copy:{self.destination}:{self.parent_device}:"
            f"{self.parent_inode}:{self.token}:{self.content}:{self.reserve_bytes}:{self.source_scope}"
        )
        return value if self.artifact_name is None else value + ":" + self.artifact_name

    def tree_binding(self) -> CopyBinding:
        return replace(self, artifact_name=None)

    @classmethod
    def decode(cls, value: str) -> CopyBinding:
        fields = value.split(":")
        if len(fields) not in {9, 10} or fields[:2] != ["external", "copy"]:
            raise ValueError("invalid retained-copy binding")
        for digest in (fields[2], fields[6], fields[8]):
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("invalid retained-copy digest")
        numbers = [int(fields[index]) for index in (3, 4, 7)]
        if any(value < 0 for value in numbers):
            raise ValueError("invalid retained-copy number")
        if any(
            str(value) != fields[index]
            for value, index in zip(numbers, (3, 4, 7), strict=True)
        ):
            raise ValueError("noncanonical retained-copy number")
        if str(uuid.UUID(fields[5])) != fields[5]:
            raise ValueError("invalid retained-copy token")
        artifact = fields[9] if len(fields) == 10 else None
        if artifact is not None and str(uuid.UUID(artifact)) != artifact:
            raise ValueError("invalid retained-copy artifact token")
        return cls(
            fields[2],
            numbers[0],
            numbers[1],
            fields[5],
            fields[6],
            numbers[2],
            fields[8],
            artifact,
        )

    @property
    def stage_name(self) -> str:
        return f".pymo-copy-{self.token}"

    @property
    def scratch_name(self) -> str:
        return f".pymo-copy-{self.token}-partial"


def copy_operations() -> tuple[str, str, str, str]:
    return (
        "COPY_QUARANTINE_TREE",
        "COPY_QUARANTINE_STAGE",
        "COPY_QUARANTINE_SCRATCH",
        "COPY_QUARANTINE_ARTIFACT",
    )
