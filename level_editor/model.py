from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

LAYERS = ("ground", "objects", "bg")


@dataclass
class SignEntry:
    row: int
    col: int
    text: str  # raw text as stored in the file; '|' is a line break


@dataclass
class PathEntry:
    row: int
    col: int
    waypoints: List[Tuple[int, int]] = field(default_factory=list)

    def path_str(self) -> str:
        return ",".join(f"{r}:{c}" for r, c in self.waypoints)


@dataclass
class Level:
    rows: int
    cols: int
    ground: List[List[int]]
    objects: List[List[int]]
    bg: List[List[int]]
    paths: List[PathEntry] = field(default_factory=list)
    signs: List[SignEntry] = field(default_factory=list)

    def grid_for(self, layer: str) -> List[List[int]]:
        return getattr(self, layer)

    def set_cell(self, layer: str, row: int, col: int, value: int) -> int:
        grid = self.grid_for(layer)
        old = grid[row][col]
        grid[row][col] = value
        return old

    def insert_row(self, index: int) -> None:
        for layer in LAYERS:
            self.grid_for(layer).insert(index, [0] * self.cols)
        self.rows += 1

    def delete_row(self, index: int) -> dict:
        removed = {layer: self.grid_for(layer).pop(index) for layer in LAYERS}
        self.rows -= 1
        return removed

    def insert_col(self, index: int) -> None:
        for layer in LAYERS:
            for row in self.grid_for(layer):
                row.insert(index, 0)
        self.cols += 1

    def delete_col(self, index: int) -> dict:
        removed = {layer: [row.pop(index) for row in self.grid_for(layer)] for layer in LAYERS}
        self.cols -= 1
        return removed

    def in_bounds(self, row: int, col: int) -> bool:
        return 0 <= row < self.rows and 0 <= col < self.cols

    def out_of_bounds_signs(self) -> List[SignEntry]:
        return [s for s in self.signs if not self.in_bounds(s.row, s.col)]

    def out_of_bounds_paths(self) -> List[PathEntry]:
        bad = []
        for p in self.paths:
            points = [(p.row, p.col)] + list(p.waypoints)
            if any(not self.in_bounds(r, c) for r, c in points):
                bad.append(p)
        return bad

    def missing_spawns(self) -> List[int]:
        found = {1: False, 2: False}
        for row in self.objects:
            for v in row:
                if v in found:
                    found[v] = True
        return [pid for pid, ok in found.items() if not ok]
