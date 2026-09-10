# Jack Frost Level Editor

A Tkinter GUI for viewing and editing the Jack Frost level XML files in
`areas/`. Renders using the game's own sprites (`level_editor/images/`) by
default; switch to the built-in vector icons any time from the Settings
button.

## Run

From the `jackfrost` folder:

```
py -3 level_editor/main.py
```

(or `python level_editor/main.py`, depending on how Python is set up on
your machine)

## Usage

- **Levels** panel (left): pick one of the 40 levels by its friendly name
  (`sparkel_1`..`sparkel_40`). The editor resolves this to the MD5-hashed
  filename in `areas/` that the game actually loads and opens that file.
  The plain `sparkel_<n>.xml` files in `areas/` are leftovers from an
  earlier attempt to patch the hashing out of the game and are never read
  or written by this tool.
- **Row/column ruler**: index numbers along the top and left of the grid,
  scrolling in sync with it. Right-click a ruler cell for a menu to insert
  a row/column before or after it, or delete it — an alternative to the
  toolbar's Insert/Delete buttons (which prompt for an index instead).
- **Canvas** (center): shows the level grid. Ground blocks fill the whole
  cell, with small decorations for ladders/metal/trampoline/conveyor. Bushes
  draw as a small glyph in the corner; trees and signs are multi-cell
  elements drawn at their true footprint (tree: 3x3, anchored bottom-center;
  sign: 5 wide x 4 tall, anchored bottom-center) rather than squeezed into
  one cell. Objects (enemies, spawns, snowflakes, hazards) draw as distinct
  shapes — a flag pin for spawns, a star for snowflakes, a zigzag for
  spikes, a dashed circle for living gaps, a triangle for the two
  horned/dangerous dragons, and a circle (with the id number) for everything
  else jumpable. Moving/levitating platforms (ids 5-10) draw as a bar
  spanning their real width (3 or 5 blocks) with a ^/v arrow for
  raising/sinking. Use the radio buttons above the canvas to choose which
  layer you're painting, and the checkboxes to show/hide each layer's
  overlay for context (hiding bg also hides trees/signs, since they're bg
  content). Draw order is always signs, then the rest of the background,
  then ground, then objects on top — so nothing gets hidden behind an
  oversized sign or background sprite, whether on a fresh load or mid-edit.
  Right-click any cell (when not in a placement/waypoint mode) for a menu
  listing every element actually present at that cell across all three
  layers as a clickable "Erase <name>" action — including elements anchored
  elsewhere whose multi-cell footprint (a platform, tree, or sign) merely
  covers the cell you clicked; erasing then correctly clears the real
  anchor cell, not the one you clicked. Layers with nothing there show as a
  disabled, non-clickable info line instead.
- **Palette** (right): lists the ids available for the active layer, each
  row tinted with its canvas color. In sprite mode, each row also shows a
  small thumbnail of the actual sprite (in vector mode, just the color).
  Select one, then left-click a cell to paint it. Click-drag paints a run
  of cells. Painting a `1`/`2` (player spawn) automatically removes any
  other spawn of that player elsewhere in the level, since each level
  should have exactly one per player.
- **Legend tab** (right): a reference list of every ground/object/bg id,
  name, color, and (in sprite mode) a thumbnail of its sprite — always
  available regardless of which layer is active.
- **Settings** (toolbar): switch between the built-in vector icons and the
  game's own sprite art. Sprites are read from `level_editor/images/`
  (`GO<id>.png` for ground, `O<id>.png` for objects, `BG<id>.png` for
  background — exactly the ids in `constants.py`). Any id without a
  matching file just falls back to its vector icon. Quality scaling needs
  Pillow (`pip install pillow`); without it, sprites still work but scale
  in blocky integer steps.
- **Open XML in Notepad** (toolbar): opens the current level's real XML
  file (the hashed one) in Notepad, for a quick look at the raw markup.
- **Signs tab** (right): a `<sign>` is really "a Sign tile in the bg grid
  plus a text entry", and the editor keeps both in sync automatically no
  matter which way you create one:
  - Select the **Background** layer, pick id `3: Sign` from the palette,
    and click the grid — this sets that bg cell *and* creates the matching
    `<signs>` entry (default text `" "`) in one step, shown immediately in
    the list.
  - Or click "Add sign (click grid)" in this tab, then click the grid —
    same result, and it also selects the new entry and focuses the text
    box for you.
  A sign's true in-game footprint is 5 blocks wide, centered on its `col`,
  and 4 blocks tall, bottom-aligned on its `row` (extending upward) — the
  canvas draws exactly that footprint (as the game sprite in sprite mode,
  or a dashed outline + flag glyph in vector mode), and it respects the
  "show bg" checkbox like any other bg content. Selecting a sign in the
  list highlights that same footprint in yellow. Sign text uses normal line
  breaks in the text box; they convert to/from the game's `|` separator
  automatically. "Apply edit" commits row/col/text changes — moving a
  sign's row/col also moves its bg tile to match. Deleting a sign clears
  its bg tile too. Erasing a bg=3 cell directly (paint or context menu)
  removes the matching sign entry, and vice versa.
- **Paths tab** (right): placing a `9`/`10` (levitating platform) on the
  grid automatically creates its `<paths>` entry; erasing or overwriting
  that cell removes it again. Selecting a path in the list highlights the
  platform and its current waypoint route on the canvas. "Start adding
  waypoints" puts the canvas into a mode where left-clicks append a
  waypoint to the selected path and right-clicks remove the last one; click
  the button again to stop. Manual Add/Apply/Delete are still available for
  editing paths directly.
- **Insert/Delete row(s)/col(s)** (toolbar or ruler right-click): resizes
  the grid, applied to ground/objects/bg together, as one undo step. The
  toolbar buttons accept either a single index (`5`) or a range (`17-20`,
  either order) to insert/delete several at once; the ruler's right-click
  menu is single-index only. Deleting a row/col that a sign or path now
  falls outside of is flagged (not silently dropped) in the Signs/Paths
  tabs.
- **Undo / Redo** (toolbar, or Ctrl+Z / Ctrl+Y): steps back/forward through
  edits made in the current session, including compound actions like a
  spawn move or an auto-created path (cleared when you load a different
  level or close the app).
- **Save**: writes back to the canonical hashed `.xml` file in `areas/`.
  Before the first save of a given file in this session, the previous
  contents are copied to `<hash>.xml.bak` in `areas/` as a safety net.
  `areas másolata` is never touched.
