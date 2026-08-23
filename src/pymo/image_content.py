"""Shared exact displayed-image normalization.

This module owns the content definition used by both duplicate analysis and
migration evidence.  It deliberately does not own discovery, cache policy, or
mutation planning.
"""

from __future__ import annotations

import hashlib
import os
import warnings

from PIL import Image, ImageOps

DISPLAYED_PIXEL_ALGORITHM = "displayed-pixels-rgba-v1"


def displayed_pixel_hash(descriptor: int) -> str:
    """Hash one still image exactly as displayed after EXIF orientation.

    RGBA conversion makes equivalent RGB, palette, and grayscale images
    comparable.  Animated and multi-page inputs are rejected because hashing
    only one frame would weaken the exact-content contract.
    """

    os.lseek(descriptor, 0, os.SEEK_SET)
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            with Image.open(stream) as opened:
                if getattr(opened, "n_frames", 1) != 1:
                    raise ValueError("animated or multi-page image")

                image = ImageOps.exif_transpose(opened)
                rgba = image.convert("RGBA")

                digest = hashlib.sha256()
                digest.update(rgba.width.to_bytes(8, "big"))
                digest.update(rgba.height.to_bytes(8, "big"))
                digest.update(rgba.tobytes())
                return digest.hexdigest()
