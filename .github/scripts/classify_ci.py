#!/usr/bin/env python3
"""Classify a Git change for the contained GitHub Actions policy."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path, PurePosixPath


def is_documentation_path(path: str) -> bool:
    """Return whether *path* belongs to the deliberately lightweight scope."""
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or ".." in candidate.parts:
        return False
    if candidate.parts[:1] == ("docs",):
        return True
    if candidate.parts[:2] == (".github", "ISSUE_TEMPLATE"):
        return True
    if len(candidate.parts) == 1:
        return candidate.suffix.lower() == ".md" or candidate.name == "LICENSE"
    return False


def changed_paths(repository: Path, base: str, head: str) -> tuple[str, ...]:
    """Return repository paths changed between two exact commit identities."""
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "--no-renames",
            "--diff-filter=ACDMRTUXB",
            base,
            head,
            "--",
        ],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("Git could not compare the requested commits")
    return tuple(line for line in result.stdout.splitlines() if line)


def classify_paths(paths: tuple[str, ...]) -> str:
    """Return ``docs`` only when every changed path is lightweight."""
    if paths and all(is_documentation_path(path) for path in paths):
        return "docs"
    return "full"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    scope = "full"
    try:
        paths = changed_paths(args.repository, args.base, args.head)
        scope = classify_paths(paths)
    except (OSError, RuntimeError) as error:
        print(f"CI scope classification failed closed: {error}", file=sys.stderr)
    with args.output.open("a", encoding="utf-8") as output:
        output.write(f"scope={scope}\n")
    print(f"CI scope: {scope}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
