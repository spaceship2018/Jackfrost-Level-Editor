"""Reads/writes Jack Frost level XML files.

Parsing uses ``xml.etree.ElementTree``. Serialization is done by hand
(rather than ``ElementTree.write``) so the output matches the game's own
files byte-for-byte in structure: no XML declaration, one tag per line,
single-quoted attributes, CRLF line endings, no trailing blank line.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import List

from .model import Level, PathEntry, SignEntry

LAYER_TAGS = ("ground", "objects", "bg")


def _parse_row(text: str) -> List[int]:
    text = (text or "").strip()
    if not text:
        return []
    return [int(v) for v in text.split(",")]


def load_level(path: str) -> Level:
    tree = ET.parse(path)
    root = tree.getroot()

    def grid(tag: str) -> List[List[int]]:
        el = root.find(tag)
        if el is None:
            raise ValueError(f"Missing <{tag}> section in {path}")
        return [_parse_row(row.text) for row in el.findall("row")]

    ground = grid("ground")
    objects = grid("objects")
    bg = grid("bg")

    rows = len(ground)
    cols = len(ground[0]) if rows else 0
    for name, g in (("objects", objects), ("bg", bg)):
        if len(g) != rows or any(len(r) != cols for r in g):
            raise ValueError(
                f"Level {path}: '{name}' grid does not match 'ground' dimensions "
                f"({rows}x{cols})"
            )

    paths: List[PathEntry] = []
    paths_el = root.find("paths")
    if paths_el is not None:
        for pp in paths_el.findall("platformpath"):
            row = int(pp.get("row", "0"))
            col = int(pp.get("col", "0"))
            raw = pp.get("path", "") or ""
            waypoints = []
            for chunk in raw.split(","):
                chunk = chunk.strip()
                if not chunk:
                    continue
                r, c = chunk.split(":")
                waypoints.append((int(r), int(c)))
            paths.append(PathEntry(row=row, col=col, waypoints=waypoints))

    signs: List[SignEntry] = []
    signs_el = root.find("signs")
    if signs_el is not None:
        for sg in signs_el.findall("sign"):
            signs.append(
                SignEntry(
                    row=int(sg.get("row", "0")),
                    col=int(sg.get("col", "0")),
                    text=sg.get("text", "") or "",
                )
            )

    return Level(rows=rows, cols=cols, ground=ground, objects=objects, bg=bg, paths=paths, signs=signs)


def _escape_attr(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("'", "&apos;")
    )


def dump_level(level: Level) -> str:
    lines = ["<level>"]

    def emit_grid(tag: str, grid: List[List[int]]) -> None:
        lines.append(f"<{tag}>")
        for row in grid:
            lines.append(f"<row>{','.join(str(v) for v in row)}</row>")
        lines.append(f"</{tag}>")

    emit_grid("ground", level.ground)
    emit_grid("objects", level.objects)
    emit_grid("bg", level.bg)

    lines.append("<paths>")
    for p in level.paths:
        lines.append(f"<platformpath row='{p.row}' col='{p.col}' path='{_escape_attr(p.path_str())}'/>")
    lines.append("</paths>")

    lines.append("<signs>")
    for s in level.signs:
        lines.append(f"<sign row='{s.row}' col='{s.col}' text='{_escape_attr(s.text)}'/>")
    lines.append("</signs>")

    lines.append("</level>")
    return "\r\n".join(lines)


def save_level(level: Level, path: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(dump_level(level))
