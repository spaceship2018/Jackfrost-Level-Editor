"""Resolves friendly ``sparkel_<n>`` names to the MD5-hashed filenames the
game actually reads from ``areas/``.

The hash is regenerated at runtime with the same logic as ``level_hashes.py``
(``md5("sparkel_<n>")``) instead of parsing ``level_names.txt``, so the
mapping can never drift out of sync with that script.

Note: the plain ``sparkel_<n>.xml`` files sometimes present in ``areas/``
are leftovers from an earlier, abandoned attempt to patch the hashing out
of the game. The game only ever loads the hashed filename, and this editor
never reads or writes the plain-named copies.
"""

import hashlib
import os
from dataclasses import dataclass
from typing import List

PREFIX = "sparkel_"
COUNT = 40


@dataclass
class LevelRef:
    number: int
    friendly_name: str
    file_hash: str
    hashed_path: str
    exists: bool


def hash_for(number: int) -> str:
    return hashlib.md5(f"{PREFIX}{number}".encode("utf-8")).hexdigest()


def list_levels(areas_dir: str, count: int = COUNT) -> List[LevelRef]:
    refs = []
    for i in range(1, count + 1):
        friendly = f"{PREFIX}{i}"
        file_hash = hash_for(i)
        hashed_path = os.path.join(areas_dir, f"{file_hash}.xml")
        refs.append(
            LevelRef(
                number=i,
                friendly_name=friendly,
                file_hash=file_hash,
                hashed_path=hashed_path,
                exists=os.path.isfile(hashed_path),
            )
        )
    return refs
