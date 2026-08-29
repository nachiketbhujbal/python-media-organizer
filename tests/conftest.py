from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"

SCRIPT_COMMANDS = {
    "scan.py": "scan",
    "validate.py": "validate",
    "correct_extensions.py": "correct-extensions",
    "organize_media.py": "organize",
    "rename_media.py": "rename",
    "find_image_duplicates.py": "find-image-duplicates",
    "find_video_duplicates.py": "find-video-duplicates",
}


@pytest.fixture
def run_script():
    def run(name: str, *arguments: object) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONPATH"] = str(SOURCE_ROOT)
        command = SCRIPT_COMMANDS[name]
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "pymo",
                command,
                *(str(item) for item in arguments),
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )

    return run
