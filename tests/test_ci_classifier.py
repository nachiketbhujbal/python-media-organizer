from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _classifier() -> ModuleType:
    path = Path(__file__).parents[1] / ".github" / "scripts" / "classify_ci.py"
    spec = importlib.util.spec_from_file_location("classify_ci", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_documentation_scope_is_explicit_and_narrow() -> None:
    classifier = _classifier()

    assert (
        classifier.classify_paths(
            (
                "README.md",
                "SECURITY.md",
                "LICENSE",
                "docs/ROADMAP.md",
                ".github/ISSUE_TEMPLATE/bug.yml",
            )
        )
        == "docs"
    )


def test_executable_or_workflow_changes_require_full_scope() -> None:
    classifier = _classifier()

    assert classifier.classify_paths(("src/pymo/cli.py",)) == "full"
    assert classifier.classify_paths((".github/workflows/ci.yml",)) == "full"
    assert classifier.classify_paths(("docs/ROADMAP.md", "pyproject.toml")) == "full"


def test_empty_or_unsafe_classification_fails_closed() -> None:
    classifier = _classifier()

    assert classifier.classify_paths(()) == "full"
    assert not classifier.is_documentation_path("../README.md")
    assert not classifier.is_documentation_path("nested/README.md")


def test_failed_commit_comparison_writes_full_scope(tmp_path: Path) -> None:
    classifier = _classifier()
    output = tmp_path / "github-output"

    status = classifier.main(
        [
            "--repository",
            str(tmp_path),
            "--base",
            "missing-base",
            "--head",
            "missing-head",
            "--output",
            str(output),
        ]
    )

    assert status == 0
    assert output.read_text(encoding="utf-8") == "scope=full\n"


def test_workflow_keeps_one_unconditional_fail_closed_gate() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    release = (root / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "paths-ignore" not in workflow
    assert "name: quality-gate" in workflow
    assert "if: always()" in workflow
    assert 'git show "${TRUSTED_SHA}:.github/scripts/classify_ci.py"' in workflow
    assert "trusted classifier unavailable; requiring full scope" in workflow
    assert "quality (macos-latest)" in workflow
    assert 'git cat-file -t "$GITHUB_REF_NAME"' in release
    assert "git merge-base --is-ancestor" in release
