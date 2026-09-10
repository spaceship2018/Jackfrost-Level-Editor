"""Id -> (name, color) tables transcribed from the ``Level-Tutorial`` file.

Colors are only used for the editor's canvas rendering; they have no
relationship to in-game art. ``None`` as a color means "draw nothing"
(id 0 / empty cell).
"""

GROUND_IDS = {
    0: ("No block", None),
    1: ("Red block", "#e05a4e"),
    2: ("Pink block", "#f2a6c9"),
    3: ("Orange block", "#f2994a"),
    4: ("Ladder top part", "#a9743a"),
    5: ("Ladder middle", "#c79256"),
    6: ("Ladder lower part", "#a9743a"),
    7: ("Metal block", "#8d99a6"),
    8: ("Trampoline", "#2ecc71"),
    9: ("Conveyor block right", "#4a90d9"),
    10: ("Conveyor block left", "#7fb2ea"),
}

OBJECT_IDS = {
    0: ("No object", None),
    1: ("Spawn point - Player 1", "#27ae60"),
    2: ("Spawn point - Player 2", "#16a085"),
    3: ("Snowflake", "#5bc8f5"),
    4: ("Green Dragon", "#2ecc71"),
    5: ("Raising platform (w3)", "#9b59b6"),
    6: ("Sinking platform (w3)", "#8e44ad"),
    7: ("Raising platform (w5)", "#bb8fce"),
    8: ("Sinking platform (w5)", "#6c3483"),
    9: ("Levitating platform (w3)", "#5dade2"),
    10: ("Levitating platform (w5)", "#2e86c1"),
    11: ("Orange nose enemy", "#e67e22"),
    12: ("Purple nose enemy", "#8e44ad"),
    13: ("Green Lizard", "#27ae60"),
    14: ("Yellow Lizard", "#f1c40f"),
    15: ("Red dragon (one horn)", "#c0392b"),
    16: ("Ice skater", "#85c1e9"),
    17: ("BathBird (black bird)", "#34495e"),
    18: ("Living gap", "#7f8c8d"),
    19: ("Spikes", "#e74c3c"),
    20: ("Pink dragon (two horn)", "#e91e8c"),
}

BG_IDS = {
    0: ("No object", None),
    1: ("Bush", "#58d68d"),
    2: ("Tree", "#1e8449"),
    3: ("Sign", "#d35400"),
}

LAYER_TABLES = {
    "ground": GROUND_IDS,
    "objects": OBJECT_IDS,
    "bg": BG_IDS,
}

LAYER_LABELS = {
    "ground": "Ground",
    "objects": "Objects",
    "bg": "Background",
}

# Object ids that are single-instance-per-level spawn points.
SPAWN_IDS = {1, 2}

# Object ids that are moving/levitating platforms and the number of blocks
# they occupy, extending to the right from their (row, col) anchor.
PLATFORM_WIDTHS = {5: 3, 6: 3, 7: 5, 8: 5, 9: 3, 10: 5}

# Of those, only levitating platforms use <paths> entries.
LEVITATING_IDS = {9, 10}

# A <sign> visually occupies this many blocks, extending to the right from
# its (row, col). The bg id below is the "Sign" background tile that a real
# sign's anchor cell always carries (confirmed 1:1 against real level data).
SIGN_WIDTH = 5
SIGN_BG_ID = 3

# A tree is a 3x3 background element anchored at its bottom-center cell:
#   x x x
#   x x x
#   x c x   <- (row, col) is 'c'
TREE_BG_ID = 2

# Footprint of every multi-cell element as (up, down, left, right): how many
# extra cells it occupies in each direction from its (row, col) anchor.
# Anything not listed here is a plain single-cell element.
FOOTPRINTS = {
    ("bg", TREE_BG_ID): (2, 0, 1, 1),
    ("bg", SIGN_BG_ID): (3, 0, 2, 2),
}
FOOTPRINTS.update({("objects", pid): (0, 0, 0, w - 1) for pid, w in PLATFORM_WIDTHS.items()})


def name_for(layer: str, value: int) -> str:
    table = LAYER_TABLES[layer]
    entry = table.get(value)
    return entry[0] if entry else f"Unknown ({value})"


def color_for(layer: str, value: int):
    table = LAYER_TABLES[layer]
    entry = table.get(value)
    return entry[1] if entry else "#000000"
