"""Shared local media classification policy."""

from __future__ import annotations

import mimetypes
import os
import shutil
import subprocess
from pathlib import Path

from pymo.config import ClassificationConfig


class Classifier:
    """Classify local files from content signatures with extension fallback."""

    def __init__(self, policy: ClassificationConfig) -> None:
        self.policy = policy
        self.file_command = shutil.which("file")
        self.warning: str | None = None
        if not self.file_command:
            self.warning = (
                "The system 'file' utility was not found; classification will "
                "fall back to filenames and extensions."
            )

    def detect_mime(
        self, path: Path, descriptor: int | None = None
    ) -> tuple[str, bool]:
        """Return one file's MIME type and whether it was read from content.

        The filename guess used when the utility is unavailable or fails is not
        a content signature: it is derived from the very name that
        classification exists to check.
        """

        if self.file_command:
            try:
                command = [self.file_command, "--brief", "--mime-type"]
                stdin: int | None = None
                if descriptor is not None:
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    command.append("-")
                    stdin = descriptor
                else:
                    command.extend(("--", str(path)))
                result = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    stdin=stdin,
                )
                detected = result.stdout.strip().split(";", 1)[0].lower()
                if result.returncode == 0 and detected:
                    return detected, True
            except (OSError, subprocess.SubprocessError):
                pass

        guessed, _ = mimetypes.guess_type(path.name)
        return (guessed.lower() if guessed else "unknown"), False

    def classify(self, path: Path, descriptor: int | None = None) -> tuple[str, str]:
        mime_type, from_content = self.detect_mime(path, descriptor)
        extension = path.suffix.lower()
        if not from_content:
            # The type was guessed from the filename, so it cannot outrank the
            # configured extension policy it was derived from. Platform MIME
            # databases disagree about media extensions, and interpreting a
            # guess as a content signature would report configured media as a
            # naming mismatch without ever reading a byte of it.
            if extension in self.policy.image_extensions:
                return "picture", mime_type
            if extension in self.policy.video_extensions:
                return "video", mime_type
        if mime_type.startswith("image/"):
            return "picture", mime_type
        if (
            mime_type.startswith("video/")
            or mime_type in self.policy.video_application_mime_types
        ):
            return "video", mime_type

        if mime_type in self.policy.generic_mime_types or mime_type == "unknown":
            if extension in self.policy.image_extensions:
                return "picture", mime_type
            if extension in self.policy.video_extensions:
                return "video", mime_type

        # A meaningful non-media content signature takes precedence over a
        # misleading extension (for example, a text file named fake.jpg).
        return "other", mime_type


def desired_directory(kind: str, root: Path, pics: Path, vids: Path) -> Path:
    """Map one classified media kind to its canonical collection directory."""

    if kind == "picture":
        return pics
    if kind == "video":
        return vids
    return root
