"""Loads the game's own sprite art (exported from the SWF as PNGs) as an
alternative to the built-in vector icons.

Expected location: ``level_editor/images/``, files named ``GO<id>.png``
(ground), ``O<id>.png`` (objects), ``BG<id>.png`` (background) — matching
the ids in ``constants.py``. Missing files simply mean no sprite for that
id; callers fall back to the vector icon.

Uses Pillow for quality resizing when available, otherwise falls back to
Tkinter's integer-only ``PhotoImage.subsample``.
"""

from __future__ import annotations

import os
import re
import tkinter as tk
from typing import Dict, Optional, Tuple

try:
    from PIL import Image, ImageTk
    _HAVE_PIL = True
except ImportError:  # Pillow not installed - degrade gracefully
    _HAVE_PIL = False

IMAGES_DIR ="images"

# Native pixel size of one ground block in the exported art. Used to scale
# everything else (objects, bg art) to the editor's cell size consistently,
# so relative proportions match how they actually look in the game.
NATIVE_BLOCK_PX = 26.0

_PREFIX = {"ground": "GO", "objects": "O", "bg": "BG"}

_files: Dict[str, Dict[int, str]] = {}
_dims: Dict[str, Tuple[int, int]] = {}  # path -> (w, h)
_image_cache: Dict[Tuple[str, int, int, int], "tk.PhotoImage"] = {}
_scanned = False


def _scan() -> None:
    global _scanned
    if _scanned:
        return
    _scanned = True
    for layer in _PREFIX:
        _files[layer] = {}
    if not os.path.isdir(IMAGES_DIR):
        return
    for layer, prefix in _PREFIX.items():
        pattern = re.compile(rf"^{re.escape(prefix)}(\d+)\.png$", re.IGNORECASE)
        for fname in os.listdir(IMAGES_DIR):
            m = pattern.match(fname)
            if m:
                _files[layer][int(m.group(1))] = os.path.join(IMAGES_DIR, fname)


def has_any_images() -> bool:
    _scan()
    return any(_files[layer] for layer in _files)


def has_image(layer: str, value: int) -> bool:
    _scan()
    return value in _files.get(layer, {})


def _native_dims(path: str) -> Tuple[int, int]:
    dims = _dims.get(path)
    if dims:
        return dims
    if _HAVE_PIL:
        with Image.open(path) as im:
            dims = im.size
    else:
        tmp = tk.PhotoImage(file=path)
        dims = (tmp.width(), tmp.height())
    _dims[path] = dims
    return dims


def native_size(layer: str, value: int) -> Optional[Tuple[int, int]]:
    _scan()
    path = _files.get(layer, {}).get(value)
    if not path:
        return None
    return _native_dims(path)


def scaled_size(layer: str, value: int, cell_size: int) -> Optional[Tuple[int, int]]:
    """Size (w, h) this sprite should render at, scaled so the shared
    reference block size maps to one editor cell."""
    dims = native_size(layer, value)
    if not dims:
        return None
    scale = cell_size / NATIVE_BLOCK_PX
    w, h = dims
    return max(1, round(w * scale)), max(1, round(h * scale))


def thumbnail(layer: str, value: int, max_size: int = 24):
    """A small, consistently-sized preview image for lists (palette/legend)
    - unlike scaled_size(), this always fits the longest side to max_size,
    regardless of the sprite's real in-game proportions, so a snowflake and
    a dragon read as similarly-sized icons in a reference list."""
    dims = native_size(layer, value)
    if not dims:
        return None
    w, h = dims
    scale = max_size / max(w, h)
    return get_image(layer, value, max(1, round(w * scale)), max(1, round(h * scale)))


def get_pil_image(layer: str, value: int, target_w: int, target_h: int):
    """Returns a raw PIL Image (RGBA) resized to (target_w, target_h), or
    None if Pillow isn't available or there's no sprite for this id. For
    compositing into another PIL image (e.g. exporting a level to PNG),
    not for on-screen Tkinter display - use get_image() for that."""
    if not _HAVE_PIL:
        return None
    _scan()
    path = _files.get(layer, {}).get(value)
    if not path:
        return None
    target_w, target_h = max(1, int(target_w)), max(1, int(target_h))
    with Image.open(path) as pil_img:
        return pil_img.convert("RGBA").resize((target_w, target_h), Image.LANCZOS)


def get_image(layer: str, value: int, target_w: int, target_h: int):
    """Returns a PhotoImage resized to (target_w, target_h), or None if no
    sprite is available for this id. Cached per (layer, id, size)."""
    _scan()
    path = _files.get(layer, {}).get(value)
    if not path:
        return None
    target_w, target_h = max(1, int(target_w)), max(1, int(target_h))
    key = (layer, value, target_w, target_h)
    img = _image_cache.get(key)
    if img is not None:
        return img
    if _HAVE_PIL:
        pil_img = get_pil_image(layer, value, target_w, target_h)
        img = ImageTk.PhotoImage(pil_img)
    else:
        img = tk.PhotoImage(file=path)
        orig_w, orig_h = img.width(), img.height()
        factor = max(1, min(orig_w // target_w or 1, orig_h // target_h or 1))
        if factor > 1:
            img = img.subsample(factor, factor)
    _image_cache[key] = img
    return img
