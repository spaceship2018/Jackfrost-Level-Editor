from __future__ import annotations

import copy
import os
import shutil
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import List, Optional, Tuple

from . import constants, export_image, level_names, sprites, xml_io
from .model import Level, PathEntry, SignEntry

CELL_SIZE = 22
RULER_SIZE = 24
AREAS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "areas")


# ---------------------------------------------------------------------------
# Undo/redo command records
# ---------------------------------------------------------------------------

class Command:
    """Base class for undoable actions. Subclasses implement undo()/redo()."""

    def undo(self, app: "App") -> None:
        raise NotImplementedError

    def redo(self, app: "App") -> None:
        raise NotImplementedError


class CompositeCommand(Command):
    """Bundles several commands into a single undo/redo step."""

    def __init__(self, commands: List[Command]):
        self.commands = commands

    def undo(self, app: "App") -> None:
        for cmd in reversed(self.commands):
            cmd.undo(app)

    def redo(self, app: "App") -> None:
        for cmd in self.commands:
            cmd.redo(app)


class PaintCommand(Command):
    def __init__(self, layer: str, row: int, col: int, old: int, new: int):
        self.layer, self.row, self.col, self.old, self.new = layer, row, col, old, new

    def undo(self, app: "App") -> None:
        app.level.set_cell(self.layer, self.row, self.col, self.old)
        app.redraw_cell(self.row, self.col)

    def redo(self, app: "App") -> None:
        app.level.set_cell(self.layer, self.row, self.col, self.new)
        app.redraw_cell(self.row, self.col)


class ResizeCommand(Command):
    def __init__(self, kind: str, axis: str, index: int, removed=None):
        # kind: 'insert' | 'delete'; axis: 'row' | 'col'
        self.kind, self.axis, self.index, self.removed = kind, axis, index, removed

    def _do(self, app: "App", insert: bool) -> None:
        lvl = app.level
        if insert:
            (lvl.insert_row if self.axis == "row" else lvl.insert_col)(self.index)
        else:
            self.removed = (lvl.delete_row if self.axis == "row" else lvl.delete_col)(self.index)
        app.rebuild_canvas()

    def redo(self, app: "App") -> None:
        self._do(app, insert=(self.kind == "insert"))

    def undo(self, app: "App") -> None:
        lvl = app.level
        if self.kind == "insert":
            (lvl.delete_row if self.axis == "row" else lvl.delete_col)(self.index)
        else:
            if self.axis == "row":
                lvl.insert_row(self.index)
                for layer, values in self.removed.items():
                    lvl.grid_for(layer)[self.index] = values
            else:
                lvl.insert_col(self.index)
                for layer, values in self.removed.items():
                    for r, row in enumerate(lvl.grid_for(layer)):
                        row[self.index] = values[r]
        app.rebuild_canvas()


class SignCommand(Command):
    def __init__(self, kind: str, index: int, before: Optional[SignEntry], after: Optional[SignEntry]):
        self.kind, self.index, self.before, self.after = kind, index, before, after

    def undo(self, app: "App") -> None:
        signs = app.level.signs
        if self.kind == "add":
            signs.pop(self.index)
        elif self.kind == "delete":
            signs.insert(self.index, self.before)
        elif self.kind == "edit":
            signs[self.index] = self.before
        app.refresh_signs()

    def redo(self, app: "App") -> None:
        signs = app.level.signs
        if self.kind == "add":
            signs.insert(self.index, self.after)
        elif self.kind == "delete":
            signs.pop(self.index)
        elif self.kind == "edit":
            signs[self.index] = self.after
        app.refresh_signs()


class PathCommand(Command):
    def __init__(self, kind: str, index: int, before: Optional[PathEntry], after: Optional[PathEntry]):
        self.kind, self.index, self.before, self.after = kind, index, before, after

    def undo(self, app: "App") -> None:
        paths = app.level.paths
        if self.kind == "add":
            paths.pop(self.index)
        elif self.kind == "delete":
            paths.insert(self.index, self.before)
        elif self.kind == "edit":
            paths[self.index] = self.before
        app.refresh_paths()

    def redo(self, app: "App") -> None:
        paths = app.level.paths
        if self.kind == "add":
            paths.insert(self.index, self.after)
        elif self.kind == "delete":
            paths.pop(self.index)
        elif self.kind == "edit":
            paths[self.index] = self.after
        app.refresh_paths()


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Jack Frost Level Editor")
        self.geometry("1500x800")

        self.level: Optional[Level] = None
        self.current_ref: Optional[level_names.LevelRef] = None
        self.active_layer = "ground"
        self.selected_id = 1
        self.layer_visible = {"ground": True, "objects": True, "bg": True}
        self.cell_ids: List[List[Optional[int]]] = []  # canvas rect ids per row/col
        self.marker_ids: List[List[List[int]]] = []  # extra canvas item ids per cell to clear on redraw
        self.dirty = False
        self.backed_up_paths = set()

        self.sign_placement_mode = False
        self.waypoint_mode = False
        self.selected_path_index: Optional[int] = None
        self.icon_style = "sprite"  # or "vector"
        self.show_gridlines = True
        self._bulk_redraw = False

        self.undo_stack: List[Command] = []
        self.redo_stack: List[Command] = []

        self._build_layout()
        self._populate_level_list()

        self.bind_all("<Control-z>", lambda e: self.undo())
        self.bind_all("<Control-y>", lambda e: self.redo())

    # -- layout -----------------------------------------------------------

    def _build_layout(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(side="top", fill="x")
        ttk.Button(toolbar, text="Save", command=self.save_level).pack(side="left", padx=2, pady=2)
        ttk.Button(toolbar, text="Undo", command=self.undo).pack(side="left", padx=2, pady=2)
        ttk.Button(toolbar, text="Redo", command=self.redo).pack(side="left", padx=2, pady=2)
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(toolbar, text="Insert row(s)", command=lambda: self._ask_range("row", "insert")).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Delete row(s)", command=lambda: self._ask_range("row", "delete")).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Insert col(s)", command=lambda: self._ask_range("col", "insert")).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Delete col(s)", command=lambda: self._ask_range("col", "delete")).pack(side="left", padx=2)
        ttk.Label(toolbar, text="  (or right-click the row/col ruler)").pack(side="left")
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(toolbar, text="Open XML in Notepad", command=self._open_in_notepad).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Export level image", command=self._export_level_image).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Settings", command=self._open_settings).pack(side="left", padx=2)
        self.status_var = tk.StringVar(value="No level loaded")
        ttk.Label(toolbar, textvariable=self.status_var).pack(side="right", padx=8)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(side="top", fill="both", expand=True)

        # -- left: level picker
        left = ttk.Frame(body, width=180)
        body.add(left, weight=0)
        ttk.Label(left, text="Levels").pack(anchor="w")
        self.level_list = tk.Listbox(left)
        self.level_list.pack(fill="both", expand=True)
        self.level_list.bind("<<ListboxSelect>>", self._on_level_selected)

        # -- center: canvas + rulers
        center = ttk.Frame(body)
        body.add(center, weight=1)

        layer_bar = ttk.Frame(center)
        layer_bar.pack(side="top", fill="x")
        self.layer_var = tk.StringVar(value=self.active_layer)
        for layer in ("ground", "objects", "bg"):
            ttk.Radiobutton(
                layer_bar, text=constants.LAYER_LABELS[layer], value=layer,
                variable=self.layer_var, command=self._on_layer_change,
            ).pack(side="left", padx=4)
            var = tk.BooleanVar(value=True)
            setattr(self, f"_vis_{layer}", var)
            ttk.Checkbutton(
                layer_bar, text=f"show {layer}", variable=var,
                command=lambda l=layer: self._on_visibility_change(l),
            ).pack(side="left", padx=(0, 10))

        self._gridlines_var = tk.BooleanVar(value=self.show_gridlines)
        ttk.Checkbutton(
            layer_bar, text="show gridlines", variable=self._gridlines_var,
            command=self._on_gridlines_change,
        ).pack(side="left", padx=(0, 10))

        canvas_frame = ttk.Frame(center)
        canvas_frame.pack(side="top", fill="both", expand=True)

        corner = tk.Canvas(canvas_frame, width=RULER_SIZE + 16, height=RULER_SIZE, bg="#e0e0e0", highlightthickness=0)
        self.col_ruler = tk.Canvas(canvas_frame, height=RULER_SIZE, bg="#e0e0e0", highlightthickness=0)
        self.row_ruler = tk.Canvas(canvas_frame, width=RULER_SIZE + 16, bg="#e0e0e0", highlightthickness=0)
        xscroll = ttk.Scrollbar(canvas_frame, orient="horizontal")
        yscroll = ttk.Scrollbar(canvas_frame, orient="vertical")
        self.canvas = tk.Canvas(canvas_frame, bg="#f5f5f5", highlightthickness=0)

        corner.grid(row=0, column=0, sticky="nsew")
        self.col_ruler.grid(row=0, column=1, sticky="ew")
        self.row_ruler.grid(row=1, column=0, sticky="ns")
        self.canvas.grid(row=1, column=1, sticky="nsew")
        yscroll.grid(row=1, column=2, sticky="ns")
        xscroll.grid(row=2, column=1, sticky="ew")
        canvas_frame.rowconfigure(1, weight=1)
        canvas_frame.columnconfigure(1, weight=1)

        def _on_xscroll(*args):
            xscroll.set(*args)
            self.col_ruler.xview_moveto(args[0])

        def _on_yscroll(*args):
            yscroll.set(*args)
            self.row_ruler.yview_moveto(args[0])

        self.canvas.config(xscrollcommand=_on_xscroll, yscrollcommand=_on_yscroll)

        def _xview(*args):
            self.canvas.xview(*args)
            self.col_ruler.xview(*args)

        def _yview(*args):
            self.canvas.yview(*args)
            self.row_ruler.yview(*args)

        xscroll.config(command=_xview)
        yscroll.config(command=_yview)

        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        self.canvas.bind("<MouseWheel>", _on_mousewheel)

        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<Button-3>", self._on_canvas_right_click)
        self.row_ruler.bind("<Button-3>", self._on_row_ruler_right_click)
        self.col_ruler.bind("<Button-3>", self._on_col_ruler_right_click)

        # -- right: palette + legend/signs/paths
        right = ttk.Frame(body, width=320)
        body.add(right, weight=0)

        style = ttk.Style(self)
        style.configure("Treeview", rowheight=28)

        ttk.Label(right, text="Palette (click canvas to paint, right-click for options)").pack(anchor="w")
        self.palette_tree = ttk.Treeview(right, show="tree", height=12, selectmode="browse")
        self.palette_tree.pack(fill="x")
        self.palette_tree.bind("<<TreeviewSelect>>", self._on_palette_select)
        self._palette_thumb_refs: List = []

        notebook = ttk.Notebook(right)
        notebook.pack(fill="both", expand=True, pady=(8, 0))
        self._build_legend_tab(notebook)
        self._build_signs_tab(notebook)
        self._build_paths_tab(notebook)

        self._refresh_palette()

    def _build_legend_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Legend")
        self.legend_tree = ttk.Treeview(tab, show="tree", selectmode="none")
        scroll = ttk.Scrollbar(tab, orient="vertical", command=self.legend_tree.yview)
        self.legend_tree.config(yscrollcommand=scroll.set)
        self.legend_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._legend_thumb_refs: List = []
        self._populate_legend()

    def _populate_legend(self) -> None:
        tree = self.legend_tree
        tree.delete(*tree.get_children())
        self._legend_thumb_refs = []
        for layer in ("ground", "objects", "bg"):
            tree.insert("", "end", iid=f"hdr_{layer}", text=f"--- {constants.LAYER_LABELS[layer]} ---", tags=("header",))
            for pid, (name, color) in sorted(constants.LAYER_TABLES[layer].items()):
                extra = ""
                if layer == "objects" and pid in constants.PLATFORM_WIDTHS:
                    extra = f" (width {constants.PLATFORM_WIDTHS[pid]})"
                kwargs = {}
                if self.icon_style == "sprite":
                    img = sprites.thumbnail(layer, pid)
                    if img:
                        kwargs["image"] = img
                        self._legend_thumb_refs.append(img)
                tag = f"leg_{layer}_{pid}"
                tree.insert("", "end", iid=f"row_{layer}_{pid}", text=f"  {pid}: {name}{extra}", tags=(tag,), **kwargs)
                if color:
                    tree.tag_configure(tag, background=color)
        tree.tag_configure("header", background="#dddddd")

    def _build_signs_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Signs")
        self.signs_list = tk.Listbox(tab, height=8, exportselection=False)
        self.signs_list.pack(fill="both", expand=True)
        self.signs_list.bind("<<ListboxSelect>>", self._on_sign_select)

        form = ttk.Frame(tab)
        form.pack(fill="x", pady=4)
        ttk.Label(form, text="Row").grid(row=0, column=0)
        ttk.Label(form, text="Col").grid(row=0, column=1)
        self.sign_row_var = tk.StringVar()
        self.sign_col_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.sign_row_var, width=6).grid(row=1, column=0)
        ttk.Entry(form, textvariable=self.sign_col_var, width=6).grid(row=1, column=1)
        self.sign_text = tk.Text(tab, height=4)
        self.sign_text.pack(fill="x")

        btns = ttk.Frame(tab)
        btns.pack(fill="x")
        self.sign_add_btn = ttk.Button(btns, text="Add sign (click grid)", command=self._toggle_sign_placement)
        self.sign_add_btn.pack(side="left")
        ttk.Button(btns, text="Apply edit", command=self._sign_apply).pack(side="left")
        ttk.Button(btns, text="Delete", command=self._sign_delete).pack(side="left")

    def _build_paths_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Paths")
        ttk.Label(tab, text="(paths for id 9/10 platforms are added automatically)").pack(anchor="w")
        self.paths_list = tk.Listbox(tab, height=8, exportselection=False)
        self.paths_list.pack(fill="both", expand=True)
        self.paths_list.bind("<<ListboxSelect>>", self._on_path_select)

        form = ttk.Frame(tab)
        form.pack(fill="x", pady=4)
        ttk.Label(form, text="Row").grid(row=0, column=0)
        ttk.Label(form, text="Col").grid(row=0, column=1)
        self.path_row_var = tk.StringVar()
        self.path_col_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.path_row_var, width=6).grid(row=1, column=0)
        ttk.Entry(form, textvariable=self.path_col_var, width=6).grid(row=1, column=1)
        ttk.Label(tab, text="Waypoints (row:col,row:col,...)").pack(anchor="w")
        self.path_waypoints_var = tk.StringVar()
        ttk.Entry(tab, textvariable=self.path_waypoints_var).pack(fill="x")

        btns = ttk.Frame(tab)
        btns.pack(fill="x")
        ttk.Button(btns, text="Add", command=self._path_add).pack(side="left")
        ttk.Button(btns, text="Apply edit", command=self._path_apply).pack(side="left")
        ttk.Button(btns, text="Delete", command=self._path_delete).pack(side="left")

        self.waypoint_btn = ttk.Button(
            tab, text="Start adding waypoints (click grid)", command=self._toggle_waypoint_mode, state="disabled",
        )
        self.waypoint_btn.pack(fill="x", pady=(6, 0))
        ttk.Label(tab, text="While active: click grid to append a waypoint,\nright-click to remove the last one.").pack(anchor="w")

    # -- settings / external tools -----------------------------------------

    def _open_settings(self) -> None:
        win = tk.Toplevel(self)
        win.title("Settings")
        win.transient(self)
        win.resizable(False, False)

        ttk.Label(win, text="Icon style", font=("TkDefaultFont", 9, "bold")).pack(anchor="w", padx=10, pady=(10, 2))
        var = tk.StringVar(value=self.icon_style)

        def apply(*_args) -> None:
            self.icon_style = var.get()
            self.rebuild_canvas()
            self._populate_legend()
            self._refresh_palette()

        ttk.Radiobutton(
            win, text="Vector icons (drawn shapes)", value="vector", variable=var, command=apply
        ).pack(anchor="w", padx=16)
        ttk.Radiobutton(
            win, text="Game sprites (from level_editor/images)", value="sprite", variable=var, command=apply
        ).pack(anchor="w", padx=16)
        if not sprites.has_any_images():
            ttk.Label(
                win, text="No sprite images found in level_editor/images/.",
                foreground="#aa3333",
            ).pack(anchor="w", padx=16, pady=(2, 0))
        elif not sprites._HAVE_PIL:  # noqa: SLF001 - informational only
            ttk.Label(
                win, text="Pillow not installed - sprites will look blocky when scaled.",
                foreground="#aa7700",
            ).pack(anchor="w", padx=16, pady=(2, 0))

        ttk.Button(win, text="Close", command=win.destroy).pack(pady=10)

    def _open_in_notepad(self) -> None:
        if not self.current_ref:
            messagebox.showinfo("No level loaded", "Load a level first.")
            return
        try:
            subprocess.Popen(["notepad.exe", self.current_ref.hashed_path])
        except OSError as exc:
            messagebox.showerror("Could not open Notepad", str(exc))

    def _export_level_image(self) -> None:
        if not self.level or not self.current_ref:
            messagebox.showinfo("No level loaded", "Load a level first.")
            return
        if not export_image._HAVE_PIL:  # noqa: SLF001
            messagebox.showerror(
                "Pillow required",
                "Exporting a level image needs Pillow.\n\nInstall it with:\n    pip install pillow",
            )
            return

        path = filedialog.asksaveasfilename(
            title="Export level image",
            initialfile=f"{self.current_ref.friendly_name}.png",
            defaultextension=".png",
            filetypes=[("PNG image", "*.png"), ("JPEG image", "*.jpg *.jpeg"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            img = export_image.render_level_image(
                self.level, self.icon_style, self.layer_visible, self.show_gridlines,
            )
            if path.lower().endswith((".jpg", ".jpeg")):
                flat = export_image.Image.new("RGB", img.size, export_image.BACKGROUND)
                flat.paste(img, mask=img.split()[3])
                flat.save(path, quality=95)
            else:
                img.save(path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Export failed", str(exc))
            return

        self.status_var.set(f"Exported image to {path}")

    # -- level list ---------------------------------------------------------

    def _populate_level_list(self) -> None:
        self.refs = level_names.list_levels(AREAS_DIR)
        self.level_list.delete(0, "end")
        for ref in self.refs:
            label = ref.friendly_name if ref.exists else f"{ref.friendly_name} (missing)"
            self.level_list.insert("end", label)

    def _on_level_selected(self, event=None) -> None:
        sel = self.level_list.curselection()
        if not sel:
            return
        ref = self.refs[sel[0]]
        if not ref.exists:
            messagebox.showerror("Missing file", f"{ref.hashed_path} does not exist.")
            return
        if self.dirty:
            if not messagebox.askyesno("Unsaved changes", "Discard unsaved changes and load this level?"):
                return
        self._load_level(ref)

    def _load_level(self, ref: level_names.LevelRef) -> None:
        try:
            self.level = xml_io.load_level(ref.hashed_path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Failed to load level", str(exc))
            return
        self.current_ref = ref
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.dirty = False
        self._cancel_modes()
        self.status_var.set(f"{ref.friendly_name} ({ref.file_hash}.xml) - {self.level.rows}x{self.level.cols}")
        self.refresh_signs()
        self.refresh_paths()
        self.rebuild_canvas()

    def _cancel_modes(self) -> None:
        self.sign_placement_mode = False
        self.waypoint_mode = False
        self.selected_path_index = None
        if hasattr(self, "sign_add_btn"):
            self.sign_add_btn.config(text="Add sign (click grid)")
        if hasattr(self, "waypoint_btn"):
            self.waypoint_btn.config(text="Start adding waypoints (click grid)", state="disabled")
        self.canvas.delete("sign_highlight")
        self.canvas.delete("path_highlight")

    # -- canvas / grid --------------------------------------------------

    def _gridline_color(self) -> str:
        return "#cccccc" if self.show_gridlines else ""

    def _on_gridlines_change(self) -> None:
        self.show_gridlines = self._gridlines_var.get()
        outline = self._gridline_color()
        for row in self.cell_ids:
            for rect in row:
                self.canvas.itemconfig(rect, outline=outline)

    def rebuild_canvas(self) -> None:
        self.canvas.delete("all")
        self.cell_ids = []
        self.marker_ids = []
        if not self.level:
            self._draw_rulers()
            return
        for r in range(self.level.rows):
            row_ids = []
            row_markers = []
            for c in range(self.level.cols):
                x0, y0 = c * CELL_SIZE, r * CELL_SIZE
                x1, y1 = x0 + CELL_SIZE, y0 + CELL_SIZE
                rect = self.canvas.create_rectangle(
                    x0, y0, x1, y1, outline=self._gridline_color(), fill="", tags="ground_layer"
                )
                row_ids.append(rect)
                row_markers.append([])
            self.cell_ids.append(row_ids)
            self.marker_ids.append(row_markers)
        self.canvas.config(scrollregion=(0, 0, self.level.cols * CELL_SIZE + 2, self.level.rows * CELL_SIZE + 2))
        self._bulk_redraw = True
        for r in range(self.level.rows):
            for c in range(self.level.cols):
                self.redraw_cell(r, c)
        self._bulk_redraw = False
        self._draw_rulers()
        self._draw_sign_overlays()
        self._draw_tree_overlays()
        self._draw_platform_overlays()
        self._restack_layers()

    def _restack_layers(self) -> None:
        """Enforces draw order back-to-front: signs, bg, ground, objects -
        regardless of the order individual items were actually created in."""
        self.canvas.tag_lower("sign_overlay")
        self.canvas.tag_raise("bg_layer")
        self.canvas.tag_raise("ground_layer")
        self.canvas.tag_raise("object_layer")

    def _draw_rulers(self) -> None:
        self.col_ruler.delete("all")
        self.row_ruler.delete("all")
        if not self.level:
            return
        width = self.level.cols * CELL_SIZE
        height = self.level.rows * CELL_SIZE
        self.col_ruler.config(scrollregion=(0, 0, width, RULER_SIZE))
        self.row_ruler.config(scrollregion=(0, 0, RULER_SIZE + 16, height))
        for c in range(self.level.cols):
            x = c * CELL_SIZE
            self.col_ruler.create_rectangle(x, 0, x + CELL_SIZE, RULER_SIZE, outline="#bbbbbb")
            self.col_ruler.create_text(x + CELL_SIZE / 2, RULER_SIZE / 2, text=str(c), font=("TkDefaultFont", 7))
        for r in range(self.level.rows):
            y = r * CELL_SIZE
            self.row_ruler.create_rectangle(0, y, RULER_SIZE + 16, y + CELL_SIZE, outline="#bbbbbb")
            self.row_ruler.create_text(
                (RULER_SIZE + 16) / 2, y + CELL_SIZE / 2, text=str(r), font=("TkDefaultFont", 7)
            )

    def _draw_platform_overlays(self) -> None:
        self.canvas.delete("platform_overlay")
        if not self.level or not self.layer_visible["objects"]:
            return
        for r in range(self.level.rows):
            for c in range(self.level.cols):
                val = self.level.objects[r][c]
                width = constants.PLATFORM_WIDTHS.get(val)
                if not width:
                    continue
                end_col = min(c + width, self.level.cols)
                span_w = (end_col - c) * CELL_SIZE
                x0_full = c * CELL_SIZE
                y0_full = r * CELL_SIZE

                tags = ("platform_overlay", "object_layer")
                if self.icon_style == "sprite":
                    img = sprites.get_image("objects", val, span_w, CELL_SIZE)
                    if img:
                        self.canvas.create_image(x0_full, y0_full, image=img, anchor="nw", tags=tags)
                        continue

                x0, x1 = x0_full + 3, x0_full + span_w - 3
                y0 = y0_full + CELL_SIZE // 2 - 5
                y1 = y0_full + CELL_SIZE // 2 + 5
                color = constants.color_for("objects", val)
                kwargs = {"fill": color, "outline": "#222222", "tags": tags}
                if val in constants.LEVITATING_IDS:
                    kwargs["dash"] = (4, 2)
                self.canvas.create_rectangle(x0, y0, x1, y1, **kwargs)
                mid_x, mid_y = (x0 + x1) / 2, (y0 + y1) / 2
                if val in (5, 7):  # raising
                    glyph = "^"
                elif val in (6, 8):  # sinking
                    glyph = "v"
                else:  # levitating - follows a path
                    glyph = str(val)
                self.canvas.create_text(
                    mid_x, mid_y, text=glyph, font=("TkDefaultFont", 8, "bold"), tags=tags
                )

    def _sign_span(self, row: int, col: int) -> Tuple[int, int, int, int]:
        """Pixel bounds of a sign's true footprint: SIGN_WIDTH blocks wide,
        centered on col; 4 blocks tall, bottom-aligned on row (row is where
        the sign 'stands', extending upward)."""
        half = constants.SIGN_WIDTH // 2
        x0 = (col - half) * CELL_SIZE
        x1 = (col + half + 1) * CELL_SIZE
        y0 = (row - 3) * CELL_SIZE
        y1 = (row + 1) * CELL_SIZE
        return x0, y0, x1, y1

    def _draw_sign_overlays(self) -> None:
        self.canvas.delete("sign_overlay")
        if not self.level or not self.layer_visible["bg"]:
            return
        for s in self.level.signs:
            if not self.level.in_bounds(s.row, s.col):
                continue
            x0, y0, x1, y1 = self._sign_span(s.row, s.col)
            span_w, span_h = x1 - x0, y1 - y0

            if self.icon_style == "sprite":
                img = sprites.get_image("bg", constants.SIGN_BG_ID, span_w, span_h)
                if img:
                    self.canvas.create_image(x0, y0, image=img, anchor="nw", tags="sign_overlay")
                    continue

            self.canvas.create_rectangle(
                x0 + 1, y0 + 1, x1 - 1, y1 - 1, outline="#cc8800", dash=(3, 2), tags="sign_overlay",
            )
            cx = (x0 + x1) / 2
            self.canvas.create_line(cx, y1 - 6, cx, y0 + 10, fill="#8a5a00", width=2, tags="sign_overlay")
            self.canvas.create_rectangle(
                cx - 10, y0 + 6, cx + 10, y0 + 18, fill="#d35400", outline="#5a3400", tags="sign_overlay"
            )
        self.canvas.tag_lower("sign_overlay")

    def _tree_span(self, row: int, col: int) -> Tuple[int, int, int, int]:
        """Pixel bounds of a tree's true footprint: 3 blocks wide, centered
        on col; 3 blocks tall, bottom-aligned on row (row/col is the 'c' in
        the ASCII diagram: x x x / x x x / x c x)."""
        x0 = (col - 1) * CELL_SIZE
        x1 = (col + 2) * CELL_SIZE
        y0 = (row - 2) * CELL_SIZE
        y1 = (row + 1) * CELL_SIZE
        return x0, y0, x1, y1

    def _draw_tree_overlays(self) -> None:
        self.canvas.delete("tree_overlay")
        if not self.level or not self.layer_visible["bg"]:
            return
        for r in range(self.level.rows):
            for c in range(self.level.cols):
                if self.level.bg[r][c] != constants.TREE_BG_ID:
                    continue
                x0, y0, x1, y1 = self._tree_span(r, c)
                span_w, span_h = x1 - x0, y1 - y0
                tags = ("tree_overlay", "bg_layer")

                if self.icon_style == "sprite":
                    img = sprites.get_image("bg", constants.TREE_BG_ID, span_w, span_h)
                    if img:
                        self.canvas.create_image(x0, y0, image=img, anchor="nw", tags=tags)
                        continue

                # vector fallback: a simple layered pine-tree shape filling
                # the true 3x3 footprint, trunk anchored at the bottom cell.
                cx = (x0 + x1) / 2
                color = constants.color_for("bg", constants.TREE_BG_ID)
                self.canvas.create_line(
                    cx, y1 - 2, cx, y1 - span_h * 0.18, fill="#6b3e1a", width=3, tags=tags
                )
                self.canvas.create_polygon(
                    cx, y0 + span_h * 0.22, x0 + 3, y1 - span_h * 0.22, x1 - 3, y1 - span_h * 0.22,
                    fill=color, outline="#12451f", tags=tags,
                )
                self.canvas.create_polygon(
                    cx, y0 + 2, x0 + 8, y0 + span_h * 0.5, x1 - 8, y0 + span_h * 0.5,
                    fill=color, outline="#12451f", tags=tags,
                )
        # New items always land on top of the whole canvas when created, so
        # without this, trees redrawn outside a full rebuild (e.g. from a
        # single paint, or undo/redo) would end up above ground/objects.
        self._restack_layers()

    def _add_marker_items(self, row: int, col: int, layer_tag: str, items: List[int]) -> None:
        for item in items:
            self.canvas.addtag_withtag(layer_tag, item)
        self.marker_ids[row][col].extend(items)

    def redraw_cell(self, row: int, col: int) -> None:
        if not self.level:
            return
        for item in self.marker_ids[row][col]:
            self.canvas.delete(item)
        self.marker_ids[row][col] = []

        x0, y0 = col * CELL_SIZE, row * CELL_SIZE
        x1, y1 = x0 + CELL_SIZE, y0 + CELL_SIZE

        ground_val = self.level.ground[row][col]
        sprite_ground = self.icon_style == "sprite" and self.layer_visible["ground"] and sprites.has_image("ground", ground_val)
        if sprite_ground:
            self.canvas.itemconfig(self.cell_ids[row][col], fill="")
            img = sprites.get_image("ground", ground_val, CELL_SIZE, CELL_SIZE)
            item = self.canvas.create_image(x0, y0, image=img, anchor="nw", tags="ground_layer")
            self.marker_ids[row][col].append(item)
        else:
            ground_color = constants.color_for("ground", ground_val) if self.layer_visible["ground"] else None
            self.canvas.itemconfig(self.cell_ids[row][col], fill=ground_color or "")
            if self.layer_visible["ground"] and ground_val:
                self._add_marker_items(row, col, "ground_layer", self._ground_overlay_items(ground_val, x0, y0, x1, y1))

        if self.layer_visible["bg"]:
            bg_val = self.level.bg[row][col]
            if bg_val:
                self._add_marker_items(row, col, "bg_layer", self._bg_marker_items(bg_val, x0, y0, x1, y1))

        if self.layer_visible["objects"]:
            obj_val = self.level.objects[row][col]
            if obj_val and obj_val not in constants.PLATFORM_WIDTHS:
                self._add_marker_items(row, col, "object_layer", self._object_marker_items(obj_val, x0, y0, x1, y1))

        if not self._bulk_redraw:
            self._restack_layers()

    # -- per-id icon drawing (no external art: plain canvas shapes) -------

    def _ground_overlay_items(self, val: int, x0, y0, x1, y1) -> List[int]:
        items = []
        if val in (4, 5, 6):  # ladder top/middle/bottom -> rungs + rails
            for frac in (0.3, 0.7):
                y = y0 + (y1 - y0) * frac
                items.append(self.canvas.create_line(x0 + 3, y, x1 - 3, y, fill="#5a3a1a", width=2))
            items.append(self.canvas.create_line(x0 + 3, y0, x0 + 3, y1, fill="#5a3a1a", width=2))
            items.append(self.canvas.create_line(x1 - 3, y0, x1 - 3, y1, fill="#5a3a1a", width=2))
        elif val == 7:  # metal block -> hatch marks
            midx, midy = (x0 + x1) / 2, (y0 + y1) / 2
            items.append(self.canvas.create_line(x0 + 3, y1 - 3, x1 - 3, y0 + 3, fill="#4a4a4a"))
            items.append(self.canvas.create_line(x0 + 3, midy, midx, y0 + 3, fill="#4a4a4a"))
            items.append(self.canvas.create_line(midx, y1 - 3, x1 - 3, midy, fill="#4a4a4a"))
        elif val == 8:  # trampoline -> bounce arc
            items.append(self.canvas.create_arc(
                x0 + 2, y0 + (y1 - y0) * 0.35, x1 - 2, y1 + (y1 - y0) * 0.55,
                start=0, extent=180, style="arc", outline="#0a5c2e", width=2,
            ))
        elif val in (9, 10):  # conveyor -> direction arrow (9=left, 10=right)
            arrow = "→" if val == 10 else "←"
            items.append(self.canvas.create_text(
                (x0 + x1) / 2, (y0 + y1) / 2, text=arrow, font=("TkDefaultFont", 10, "bold")
            ))
        return items

    def _bg_marker_items(self, val: int, x0, y0, x1, y1) -> List[int]:
        if val in (constants.SIGN_BG_ID, constants.TREE_BG_ID):
            # Multi-cell footprint elements are drawn separately, at their
            # true size/position, by _draw_sign_overlays()/_draw_tree_overlays().
            return []

        if self.icon_style == "sprite":
            size = sprites.scaled_size("bg", val, CELL_SIZE)
            if size:
                img = sprites.get_image("bg", val, *size)
                if img:
                    cx = (x0 + x1) / 2
                    return [self.canvas.create_image(cx, y1, image=img, anchor="s")]

        color = constants.color_for("bg", val)
        items = []
        if val == 1:  # bush
            items.append(self.canvas.create_oval(x0 + 1, y0 + 6, x0 + 11, y0 + 14, fill=color, outline=""))
        else:
            items.append(self.canvas.create_rectangle(x0 + 2, y0 + 2, x0 + 8, y0 + 8, fill=color, outline=""))
        return items

    def _object_marker_items(self, val: int, x0, y0, x1, y1) -> List[int]:
        if self.icon_style == "sprite":
            size = sprites.scaled_size("objects", val, CELL_SIZE)
            if size:
                img = sprites.get_image("objects", val, *size)
                if img:
                    cx = (x0 + x1) / 2
                    return [self.canvas.create_image(cx, y1, image=img, anchor="s")]

        color = constants.color_for("objects", val)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        r = (x1 - x0) / 2 - 3
        items = []

        if val in constants.SPAWN_IDS:  # flag pin + P1/P2 label
            label = "P1" if val == 1 else "P2"
            items.append(self.canvas.create_line(cx, y1 - 2, cx, y0 + 3, fill="#333333", width=2))
            items.append(self.canvas.create_polygon(
                cx, y0 + 2, cx + r, y0 + r * 0.6, cx, y0 + r * 1.1, fill=color, outline="#222222"
            ))
            items.append(self.canvas.create_text(cx, y1 - 5, text=label, font=("TkDefaultFont", 6, "bold")))
            return items

        if val == 3:  # snowflake -> 6-spoke star
            for dx, dy in ((r, 0), (r * 0.5, r * 0.866), (-r * 0.5, r * 0.866)):
                items.append(self.canvas.create_line(cx - dx, cy - dy, cx + dx, cy + dy, fill=color, width=2))
            return items

        if val == 19:  # spikes -> hazard zigzag
            n = 3
            step = (x1 - x0) / n
            for i in range(n):
                sx0 = x0 + i * step
                items.append(self.canvas.create_polygon(
                    sx0 + 1, y1 - 2, sx0 + step / 2, y0 + 4, sx0 + step - 1, y1 - 2,
                    fill=color, outline="#661111",
                ))
            return items

        if val == 18:  # living gap -> hollow dashed circle (harmless, pass-through)
            items.append(self.canvas.create_oval(
                x0 + 4, y0 + 4, x1 - 4, y1 - 4, outline=color, width=2, dash=(3, 2)
            ))
            items.append(self.canvas.create_text(cx, cy, text=str(val), font=("TkDefaultFont", 7)))
            return items

        if val in (15, 20):  # horned dragons -> triangle (cannot be jumped on, dangerous)
            items.append(self.canvas.create_polygon(
                cx, y0 + 3, x1 - 3, y1 - 3, x0 + 3, y1 - 3, fill=color, outline="#000000"
            ))
            items.append(self.canvas.create_text(cx, cy + 3, text=str(val), font=("TkDefaultFont", 7)))
            return items

        # everything else jumpable (regular enemies, green dragon, etc.) -> circle
        items.append(self.canvas.create_oval(x0 + 4, y0 + 4, x1 - 4, y1 - 4, fill=color, outline="#333333"))
        items.append(self.canvas.create_text(cx, cy, text=str(val), font=("TkDefaultFont", 7)))
        return items

    def _cell_from_event(self, event, widget=None):
        widget = widget or self.canvas
        x = widget.canvasx(event.x)
        y = widget.canvasy(event.y)
        col = int(x // CELL_SIZE)
        row = int(y // CELL_SIZE)
        if self.level and 0 <= row < self.level.rows and 0 <= col < self.level.cols:
            return row, col
        return None

    def _on_canvas_click(self, event) -> None:
        if not self.level:
            return
        cell = self._cell_from_event(event)
        if not cell:
            return
        row, col = cell
        if self.waypoint_mode and self.selected_path_index is not None:
            self._add_waypoint(row, col)
            return
        if self.sign_placement_mode:
            self._place_sign(row, col)
            return
        self._paint(row, col, self.selected_id)

    def _on_canvas_drag(self, event) -> None:
        if self.waypoint_mode or self.sign_placement_mode:
            return
        self._on_canvas_click(event)

    def _on_canvas_right_click(self, event) -> None:
        if not self.level:
            return
        cell = self._cell_from_event(event)
        if not cell:
            return
        row, col = cell
        if self.waypoint_mode and self.selected_path_index is not None:
            self._remove_last_waypoint()
            return
        self._show_cell_context_menu(event, row, col)

    def _find_anchor_covering(self, layer: str, row: int, col: int) -> Optional[Tuple[int, int, int]]:
        """If (row, col) holds a value, or is visually covered by some
        multi-cell element's footprint (a platform, tree, or sign) anchored
        elsewhere, returns (anchor_row, anchor_col, value). Otherwise None."""
        grid = self.level.grid_for(layer)
        val_here = grid[row][col]
        if val_here:
            return row, col, val_here
        for (flayer, fval), (up, down, left, right) in constants.FOOTPRINTS.items():
            if flayer != layer:
                continue
            for ar in range(row - down, row + up + 1):
                if not (0 <= ar < self.level.rows):
                    continue
                for ac in range(col - right, col + left + 1):
                    if not (0 <= ac < self.level.cols):
                        continue
                    if grid[ar][ac] == fval:
                        return ar, ac, fval
        return None

    def _show_cell_context_menu(self, event, row: int, col: int) -> None:
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label=f"Cell ({row}, {col})", state="disabled")
        menu.add_separator()
        for layer in ("ground", "objects", "bg"):
            found = self._find_anchor_covering(layer, row, col)
            if found:
                ar, ac, val = found
                name = constants.name_for(layer, val)
                label = f"Erase {name} ({constants.LAYER_LABELS[layer]})"
                if (ar, ac) != (row, col):
                    label += f" [at {ar},{ac}]"
                menu.add_command(
                    label=label,
                    command=lambda l=layer, r=ar, c=ac: self._paint(r, c, 0, layer=l),
                )
            else:
                menu.add_command(
                    label=f"{constants.LAYER_LABELS[layer]}: {constants.name_for(layer, 0)}", state="disabled"
                )
        self._popup_menu(menu, event)

    def _on_layer_change(self) -> None:
        self.active_layer = self.layer_var.get()
        self._refresh_palette()

    def _on_visibility_change(self, layer: str) -> None:
        self.layer_visible[layer] = getattr(self, f"_vis_{layer}").get()
        if self.level:
            self._bulk_redraw = True
            for r in range(self.level.rows):
                for c in range(self.level.cols):
                    self.redraw_cell(r, c)
            self._bulk_redraw = False
            self._draw_sign_overlays()
            self._draw_tree_overlays()
            self._draw_platform_overlays()
            self._restack_layers()

    # -- palette ----------------------------------------------------------

    def _refresh_palette(self) -> None:
        table = constants.LAYER_TABLES[self.active_layer]
        tree = self.palette_tree
        tree.delete(*tree.get_children())
        self._palette_thumb_refs = []
        for pid, (name, color) in sorted(table.items()):
            kwargs = {}
            if self.icon_style == "sprite":
                img = sprites.thumbnail(self.active_layer, pid)
                if img:
                    kwargs["image"] = img
                    self._palette_thumb_refs.append(img)
            tag = f"pal_{pid}"
            tree.insert("", "end", iid=str(pid), text=f" {pid}: {name}", tags=(tag,), **kwargs)
            if color:
                tree.tag_configure(tag, background=color)
        if self.selected_id not in table:
            self.selected_id = sorted(table.keys())[0]
        tree.selection_set(str(self.selected_id))
        tree.see(str(self.selected_id))

    def _on_palette_select(self, event=None) -> None:
        sel = self.palette_tree.selection()
        if not sel:
            return
        self.selected_id = int(sel[0])

    # -- painting (with spawn-uniqueness / auto-path side effects) --------

    def _paint(self, row: int, col: int, value: int, layer: Optional[str] = None) -> None:
        if not self.level:
            return
        layer = layer or self.active_layer
        old = self.level.grid_for(layer)[row][col]
        if old == value:
            return

        sub_commands: List[Command] = []

        self.level.set_cell(layer, row, col, value)
        self.redraw_cell(row, col)
        sub_commands.append(PaintCommand(layer, row, col, old, value))

        paths_touched = False
        signs_touched = False

        if layer == "objects":
            if value in constants.SPAWN_IDS:
                for r in range(self.level.rows):
                    for c in range(self.level.cols):
                        if (r, c) == (row, col):
                            continue
                        if self.level.objects[r][c] == value:
                            prev = self.level.objects[r][c]
                            self.level.set_cell("objects", r, c, 0)
                            self.redraw_cell(r, c)
                            sub_commands.append(PaintCommand("objects", r, c, prev, 0))

            if old in constants.LEVITATING_IDS:
                idx = self._find_path_index(row, col)
                if idx is not None:
                    removed = self.level.paths[idx]
                    self.level.paths.pop(idx)
                    sub_commands.append(PathCommand("delete", idx, removed, None))
                    paths_touched = True

            if value in constants.LEVITATING_IDS and self._find_path_index(row, col) is None:
                entry = PathEntry(row=row, col=col, waypoints=[(row, col)])
                index = len(self.level.paths)
                self.level.paths.append(entry)
                sub_commands.append(PathCommand("add", index, None, entry))
                paths_touched = True

        if layer == "bg":
            if old == constants.SIGN_BG_ID:
                idx = self._find_sign_index(row, col)
                if idx is not None:
                    removed = self.level.signs[idx]
                    self.level.signs.pop(idx)
                    sub_commands.append(SignCommand("delete", idx, removed, None))
                    signs_touched = True

            if value == constants.SIGN_BG_ID and self._find_sign_index(row, col) is None:
                entry = SignEntry(row=row, col=col, text=" ")
                index = len(self.level.signs)
                self.level.signs.append(entry)
                sub_commands.append(SignCommand("add", index, None, entry))
                signs_touched = True

        if layer == "objects":
            self._draw_platform_overlays()
        if layer == "bg":
            self._draw_tree_overlays()
        if paths_touched:
            self._cancel_modes()
            self.refresh_paths()
        if signs_touched:
            self.refresh_signs()

        cmd = sub_commands[0] if len(sub_commands) == 1 else CompositeCommand(sub_commands)
        self._push_command(cmd)

    def _find_path_index(self, row: int, col: int) -> Optional[int]:
        for i, p in enumerate(self.level.paths):
            if p.row == row and p.col == col:
                return i
        return None

    # -- resize -------------------------------------------------------------

    @staticmethod
    def _parse_index_or_range(text: str) -> Optional[Tuple[int, int]]:
        """Parses '5' -> (5, 5) or '17-20' -> (17, 20). Returns None if invalid."""
        text = text.strip()
        if not text:
            return None
        if "-" in text[1:]:  # allow a leading '-' to not be mistaken for a range
            head, _, tail = text.partition("-")
            try:
                a, b = int(head), int(tail)
            except ValueError:
                return None
            return (a, b) if a <= b else (b, a)
        try:
            v = int(text)
        except ValueError:
            return None
        return v, v

    def _ask_range(self, axis: str, kind: str) -> None:
        if not self.level:
            return
        limit = self.level.rows if axis == "row" else self.level.cols
        hi = limit if kind == "insert" else max(limit - 1, 0)
        prompt = simpledialog.askstring(
            f"{kind.title()} {axis}(s)",
            f"{kind.title()} {axis}(s) at index (0-{hi}), or a range like 17-20:",
        )
        if not prompt:
            return
        parsed = self._parse_index_or_range(prompt)
        if parsed is None:
            messagebox.showerror("Invalid input", "Enter a number (e.g. 5) or a range (e.g. 17-20).")
            return
        start, end = parsed
        self._resize_range(axis, kind, start, end - start + 1)

    def _resize_at(self, axis: str, kind: str, index: int) -> None:
        self._resize_range(axis, kind, index, 1)

    def _resize_range(self, axis: str, kind: str, start: int, count: int) -> None:
        if not self.level or count <= 0:
            return
        limit = self.level.rows if axis == "row" else self.level.cols
        if kind == "delete":
            if start < 0 or start + count > limit:
                messagebox.showerror("Out of range", f"That range doesn't fit within the current {axis} count ({limit}).")
                return
            if limit - count < 1:
                messagebox.showerror("Cannot delete", f"Level must keep at least one {axis}.")
                return
        else:
            if start < 0 or start > limit:
                messagebox.showerror("Out of range", f"Index must be between 0 and {limit}.")
                return

        sub_commands: List[Command] = []
        for _ in range(count):
            cmd = ResizeCommand(kind, axis, start)
            cmd.redo(self)
            sub_commands.append(cmd)
        cmd = sub_commands[0] if len(sub_commands) == 1 else CompositeCommand(sub_commands)
        self._push_command(cmd)
        self._cancel_modes()
        self._check_bounds_warnings()

    def _popup_menu(self, menu: tk.Menu, event) -> None:
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _on_col_ruler_right_click(self, event) -> None:
        if not self.level:
            return
        x = self.col_ruler.canvasx(event.x)
        c = int(x // CELL_SIZE)
        if not (0 <= c < self.level.cols):
            return
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label=f"Insert column before {c}", command=lambda: self._resize_at("col", "insert", c))
        menu.add_command(label=f"Insert column after {c}", command=lambda: self._resize_at("col", "insert", c + 1))
        state = "normal" if self.level.cols > 1 else "disabled"
        menu.add_command(label=f"Delete column {c}", command=lambda: self._resize_at("col", "delete", c), state=state)
        self._popup_menu(menu, event)

    def _on_row_ruler_right_click(self, event) -> None:
        if not self.level:
            return
        y = self.row_ruler.canvasy(event.y)
        r = int(y // CELL_SIZE)
        if not (0 <= r < self.level.rows):
            return
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label=f"Insert row before {r}", command=lambda: self._resize_at("row", "insert", r))
        menu.add_command(label=f"Insert row after {r}", command=lambda: self._resize_at("row", "insert", r + 1))
        state = "normal" if self.level.rows > 1 else "disabled"
        menu.add_command(label=f"Delete row {r}", command=lambda: self._resize_at("row", "delete", r), state=state)
        self._popup_menu(menu, event)

    def _check_bounds_warnings(self) -> None:
        if not self.level:
            return
        bad_signs = self.level.out_of_bounds_signs()
        bad_paths = self.level.out_of_bounds_paths()
        if bad_signs or bad_paths:
            messagebox.showwarning(
                "Out of bounds",
                f"{len(bad_signs)} sign(s) and {len(bad_paths)} path(s) now fall outside "
                f"the grid. Check the Signs/Paths tabs.",
            )
        self.refresh_signs()
        self.refresh_paths()

    # -- scroll / highlight helpers ---------------------------------------

    def _scroll_into_view(self, row: int, col: int) -> None:
        if not self.level:
            return
        total_w = self.level.cols * CELL_SIZE
        total_h = self.level.rows * CELL_SIZE
        if total_w > 0:
            self.canvas.xview_moveto(max(0, (col * CELL_SIZE - 100) / total_w))
        if total_h > 0:
            self.canvas.yview_moveto(max(0, (row * CELL_SIZE - 100) / total_h))

    def _highlight_sign(self, sign: SignEntry) -> None:
        self.canvas.delete("sign_highlight")
        if not self.level or not self.level.in_bounds(sign.row, sign.col):
            return
        x0, y0, x1, y1 = self._sign_span(sign.row, sign.col)
        self.canvas.create_rectangle(x0, y0, x1, y1, outline="#ffcc00", width=3, tags="sign_highlight")

    def _highlight_path(self, index: Optional[int]) -> None:
        self.canvas.delete("path_highlight")
        if not self.level or index is None or index >= len(self.level.paths):
            return
        p = self.level.paths[index]
        if not self.level.in_bounds(p.row, p.col):
            return
        obj_val = self.level.objects[p.row][p.col]
        width = constants.PLATFORM_WIDTHS.get(obj_val, 1)
        x0 = p.col * CELL_SIZE
        y0 = p.row * CELL_SIZE
        x1 = min(p.col + width, self.level.cols) * CELL_SIZE
        y1 = y0 + CELL_SIZE
        self.canvas.create_rectangle(x0, y0, x1, y1, outline="#ff9900", width=3, tags="path_highlight")
        pts = p.waypoints
        if len(pts) >= 2:
            coords = []
            for (r, c) in pts:
                coords.extend([c * CELL_SIZE + CELL_SIZE / 2, r * CELL_SIZE + CELL_SIZE / 2])
            self.canvas.create_line(*coords, fill="#ff9900", width=2, dash=(4, 2), tags="path_highlight")
        for (r, c) in pts:
            cx, cy = c * CELL_SIZE + CELL_SIZE / 2, r * CELL_SIZE + CELL_SIZE / 2
            self.canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill="#ff9900", outline="", tags="path_highlight")

    # -- signs ----------------------------------------------------------

    def refresh_signs(self) -> None:
        self.signs_list.delete(0, "end")
        if not self.level:
            return
        for s in self.level.signs:
            flag = "" if self.level.in_bounds(s.row, s.col) else " [out of bounds]"
            preview = s.text.replace("|", " / ")[:30] or "(empty)"
            self.signs_list.insert("end", f"({s.row},{s.col}) {preview}{flag}")
        self._draw_sign_overlays()

    def _toggle_sign_placement(self) -> None:
        self.sign_placement_mode = not self.sign_placement_mode
        self.sign_add_btn.config(
            text="Click grid to place sign..." if self.sign_placement_mode else "Add sign (click grid)"
        )

    def _find_sign_index(self, row: int, col: int) -> Optional[int]:
        for i, s in enumerate(self.level.signs):
            if s.row == row and s.col == col:
                return i
        return None

    def _place_sign(self, row: int, col: int) -> None:
        # Placing a sign always means "there's a Sign tile in the bg grid
        # here" - route through _paint so the bg cell and the <signs> entry
        # stay in sync exactly like painting id=3 from the bg palette does.
        idx = self._find_sign_index(row, col)
        if idx is None:
            self._paint(row, col, constants.SIGN_BG_ID, layer="bg")
            idx = self._find_sign_index(row, col)

        self.sign_placement_mode = False
        self.sign_add_btn.config(text="Add sign (click grid)")
        if idx is None:
            return
        self.signs_list.selection_clear(0, "end")
        self.signs_list.selection_set(idx)
        self._on_sign_select()
        self.sign_text.focus_set()

    def _on_sign_select(self, event=None) -> None:
        sel = self.signs_list.curselection()
        if not sel or not self.level:
            return
        s = self.level.signs[sel[0]]
        self.sign_row_var.set(str(s.row))
        self.sign_col_var.set(str(s.col))
        self.sign_text.delete("1.0", "end")
        self.sign_text.insert("1.0", s.text.replace("|", "\n"))
        self._highlight_sign(s)
        self._scroll_into_view(s.row, s.col)

    def _sign_from_form(self) -> Optional[SignEntry]:
        try:
            row = int(self.sign_row_var.get())
            col = int(self.sign_col_var.get())
        except ValueError:
            messagebox.showerror("Invalid input", "Row/col must be integers.")
            return None
        text = self.sign_text.get("1.0", "end-1c").replace("\n", "|")
        return SignEntry(row=row, col=col, text=text)

    def _sign_apply(self) -> None:
        sel = self.signs_list.curselection()
        if not sel or not self.level:
            return
        entry = self._sign_from_form()
        if entry is None:
            return
        index = sel[0]
        before = self.level.signs[index]
        sub_commands: List[Command] = [SignCommand("edit", index, before, entry)]

        if (before.row, before.col) != (entry.row, entry.col):
            # Moving a sign: keep the bg "Sign" tile in sync with it - clear
            # the old spot (if it was ours) and mark the new one.
            if self.level.in_bounds(before.row, before.col) and self.level.bg[before.row][before.col] == constants.SIGN_BG_ID:
                sub_commands.append(PaintCommand("bg", before.row, before.col, constants.SIGN_BG_ID, 0))
            if self.level.in_bounds(entry.row, entry.col):
                old_bg = self.level.bg[entry.row][entry.col]
                if old_bg != constants.SIGN_BG_ID:
                    sub_commands.append(PaintCommand("bg", entry.row, entry.col, old_bg, constants.SIGN_BG_ID))

        cmd = sub_commands[0] if len(sub_commands) == 1 else CompositeCommand(sub_commands)
        cmd.redo(self)
        self._push_command(cmd)
        self.signs_list.selection_set(index)
        self._highlight_sign(entry)

    def _sign_delete(self) -> None:
        sel = self.signs_list.curselection()
        if not sel or not self.level:
            return
        index = sel[0]
        before = self.level.signs[index]
        sub_commands: List[Command] = [SignCommand("delete", index, before, None)]
        if self.level.in_bounds(before.row, before.col) and self.level.bg[before.row][before.col] == constants.SIGN_BG_ID:
            sub_commands.append(PaintCommand("bg", before.row, before.col, constants.SIGN_BG_ID, 0))

        cmd = sub_commands[0] if len(sub_commands) == 1 else CompositeCommand(sub_commands)
        cmd.redo(self)
        self._push_command(cmd)
        self.canvas.delete("sign_highlight")

    # -- paths ------------------------------------------------------------

    def refresh_paths(self) -> None:
        self.paths_list.delete(0, "end")
        if not self.level:
            return
        bad = self.level.out_of_bounds_paths()
        for p in self.level.paths:
            flag = " [out of bounds]" if p in bad else ""
            self.paths_list.insert("end", f"({p.row},{p.col}) -> {p.path_str()}{flag}")

    def _on_path_select(self, event=None) -> None:
        sel = self.paths_list.curselection()
        if not sel or not self.level:
            return
        index = sel[0]
        p = self.level.paths[index]
        self.path_row_var.set(str(p.row))
        self.path_col_var.set(str(p.col))
        self.path_waypoints_var.set(p.path_str())
        self.selected_path_index = index
        self.waypoint_mode = False
        self.waypoint_btn.config(text="Start adding waypoints (click grid)", state="normal")
        self._highlight_path(index)
        self._scroll_into_view(p.row, p.col)

    def _path_from_form(self) -> Optional[PathEntry]:
        try:
            row = int(self.path_row_var.get())
            col = int(self.path_col_var.get())
        except ValueError:
            messagebox.showerror("Invalid input", "Row/col must be integers.")
            return None
        raw = self.path_waypoints_var.get().strip()
        waypoints = []
        try:
            for chunk in raw.split(","):
                chunk = chunk.strip()
                if not chunk:
                    continue
                r, c = chunk.split(":")
                waypoints.append((int(r), int(c)))
        except ValueError:
            messagebox.showerror("Invalid input", "Waypoints must look like row:col,row:col,...")
            return None
        return PathEntry(row=row, col=col, waypoints=waypoints)

    def _path_add(self) -> None:
        if not self.level:
            return
        entry = self._path_from_form()
        if entry is None:
            return
        index = len(self.level.paths)
        cmd = PathCommand("add", index, None, entry)
        cmd.redo(self)
        self._push_command(cmd)

    def _path_apply(self) -> None:
        sel = self.paths_list.curselection()
        if not sel or not self.level:
            return
        entry = self._path_from_form()
        if entry is None:
            return
        index = sel[0]
        before = self.level.paths[index]
        cmd = PathCommand("edit", index, before, entry)
        cmd.redo(self)
        self._push_command(cmd)
        self.paths_list.selection_set(index)
        self._highlight_path(index)

    def _path_delete(self) -> None:
        sel = self.paths_list.curselection()
        if not sel or not self.level:
            return
        index = sel[0]
        before = self.level.paths[index]
        cmd = PathCommand("delete", index, before, None)
        cmd.redo(self)
        self._push_command(cmd)
        self.selected_path_index = None
        self.waypoint_mode = False
        self.waypoint_btn.config(text="Start adding waypoints (click grid)", state="disabled")
        self.canvas.delete("path_highlight")

    def _toggle_waypoint_mode(self) -> None:
        if self.selected_path_index is None:
            return
        self.waypoint_mode = not self.waypoint_mode
        self.waypoint_btn.config(
            text="Stop adding waypoints" if self.waypoint_mode else "Start adding waypoints (click grid)"
        )

    def _add_waypoint(self, row: int, col: int) -> None:
        idx = self.selected_path_index
        if idx is None or idx >= len(self.level.paths):
            return
        entry = self.level.paths[idx]
        before = copy.deepcopy(entry)
        entry.waypoints.append((row, col))
        after = copy.deepcopy(entry)
        cmd = PathCommand("edit", idx, before, after)
        self._push_command(cmd)
        self.refresh_paths()
        self.paths_list.selection_set(idx)
        self.path_waypoints_var.set(entry.path_str())
        self._highlight_path(idx)

    def _remove_last_waypoint(self) -> None:
        idx = self.selected_path_index
        if idx is None or idx >= len(self.level.paths):
            return
        entry = self.level.paths[idx]
        if not entry.waypoints:
            return
        before = copy.deepcopy(entry)
        entry.waypoints.pop()
        after = copy.deepcopy(entry)
        cmd = PathCommand("edit", idx, before, after)
        self._push_command(cmd)
        self.refresh_paths()
        self.paths_list.selection_set(idx)
        self.path_waypoints_var.set(entry.path_str())
        self._highlight_path(idx)

    # -- undo/redo --------------------------------------------------------

    def _push_command(self, cmd: Command) -> None:
        self.undo_stack.append(cmd)
        self.redo_stack.clear()
        self.dirty = True

    def undo(self) -> None:
        if not self.undo_stack:
            return
        cmd = self.undo_stack.pop()
        cmd.undo(self)
        self._draw_platform_overlays()
        self._draw_tree_overlays()
        self.redo_stack.append(cmd)
        self.dirty = True

    def redo(self) -> None:
        if not self.redo_stack:
            return
        cmd = self.redo_stack.pop()
        cmd.redo(self)
        self._draw_platform_overlays()
        self._draw_tree_overlays()
        self.undo_stack.append(cmd)
        self.dirty = True

    # -- save -------------------------------------------------------------

    def save_level(self) -> None:
        if not self.level or not self.current_ref:
            return
        missing = self.level.missing_spawns()
        bad_signs = self.level.out_of_bounds_signs()
        bad_paths = self.level.out_of_bounds_paths()
        warnings = []
        if missing:
            warnings.append(f"Missing spawn point(s) for player {missing}")
        if bad_signs:
            warnings.append(f"{len(bad_signs)} sign(s) out of bounds")
        if bad_paths:
            warnings.append(f"{len(bad_paths)} path(s) out of bounds")
        if warnings:
            if not messagebox.askyesno("Save with warnings?", "\n".join(warnings) + "\n\nSave anyway?"):
                return

        path = self.current_ref.hashed_path
        if path not in self.backed_up_paths and os.path.isfile(path):
            shutil.copy2(path, path + ".bak")
            self.backed_up_paths.add(path)

        xml_io.save_level(self.level, path)
        self.dirty = False
        self.status_var.set(f"Saved {self.current_ref.friendly_name} ({self.current_ref.file_hash}.xml)")
