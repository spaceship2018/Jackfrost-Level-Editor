"""Renders a Level to a standalone PNG/JPEG image (e.g. for a wiki page),
independent of the on-screen Tkinter canvas.

This is a from-scratch renderer built on Pillow rather than a screenshot of
the Tkinter canvas: Tkinter's own canvas-to-image path (``Canvas.postscript``)
needs an external Ghostscript install to rasterize, which most users won't
have. Requires Pillow (``pip install pillow``); raises RuntimeError if it's
not available, which callers should catch and report.

Mirrors the shapes/colors/footprints used by the on-screen vector and
sprite renderers in ``app.py`` (dashed outlines are simplified to solid,
since PIL has no native dash style).
"""

from __future__ import annotations

from typing import Dict

from . import constants, sprites
from .model import Level

try:
    from PIL import Image, ImageDraw, ImageFont
    _HAVE_PIL = True
except ImportError:
    _HAVE_PIL = False

BACKGROUND = "#f5f5f5"
GRIDLINE_COLOR = "#cccccc"
BASE_CELL_SIZE = 22.0  # the on-screen size all the hand-tuned offsets below were designed for


def _font(size: int):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()


def _paste(base: "Image.Image", sprite: "Image.Image", x: int, y: int) -> None:
    base.paste(sprite, (int(round(x)), int(round(y))), sprite)


def render_level_image(
    level: Level,
    icon_style: str,
    layer_visible: Dict[str, bool],
    show_gridlines: bool,
    cell_size: int = 32,
) -> "Image.Image":
    if not _HAVE_PIL:
        raise RuntimeError("Pillow is required to export images (pip install pillow).")

    scale = cell_size / BASE_CELL_SIZE
    width, height = level.cols * cell_size, level.rows * cell_size
    img = Image.new("RGBA", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(img)

    font_tiny = _font(max(6, round(6 * scale)))
    font_small = _font(max(7, round(7 * scale)))
    font_bold = _font(max(8, round(8 * scale)))

    def s(v: float) -> float:
        return v * scale

    # -- sign footprints (bottom layer) --
    if layer_visible.get("bg", True):
        for sign in level.signs:
            if not level.in_bounds(sign.row, sign.col):
                continue
            half = constants.SIGN_WIDTH // 2
            x0, y0 = (sign.col - half) * cell_size, (sign.row - 3) * cell_size
            x1, y1 = (sign.col + half + 1) * cell_size, (sign.row + 1) * cell_size
            drawn = False
            if icon_style == "sprite":
                sprite = sprites.get_pil_image("bg", constants.SIGN_BG_ID, x1 - x0, y1 - y0)
                if sprite:
                    _paste(img, sprite, x0, y0)
                    drawn = True
            if not drawn:
                draw.rectangle([x0 + 1, y0 + 1, x1 - 1, y1 - 1], outline="#cc8800", width=max(1, round(scale)))
                cx = (x0 + x1) / 2
                draw.line([(cx, y1 - s(6)), (cx, y0 + s(10))], fill="#8a5a00", width=max(1, round(2 * scale)))
                draw.rectangle(
                    [cx - s(10), y0 + s(6), cx + s(10), y0 + s(18)], fill="#d35400", outline="#5a3400"
                )

    # -- background objects (trees, bushes, etc; not signs) --
    if layer_visible.get("bg", True):
        for r in range(level.rows):
            for c in range(level.cols):
                val = level.bg[r][c]
                if not val or val == constants.SIGN_BG_ID:
                    continue
                x0, y0 = c * cell_size, r * cell_size
                x1, y1 = x0 + cell_size, y0 + cell_size

                if val == constants.TREE_BG_ID:
                    tx0, ty0 = (c - 1) * cell_size, (r - 2) * cell_size
                    tx1, ty1 = (c + 2) * cell_size, (r + 1) * cell_size
                    drawn = False
                    if icon_style == "sprite":
                        sprite = sprites.get_pil_image("bg", constants.TREE_BG_ID, tx1 - tx0, ty1 - ty0)
                        if sprite:
                            _paste(img, sprite, tx0, ty0)
                            drawn = True
                    if not drawn:
                        span_h = ty1 - ty0
                        tcx = (tx0 + tx1) / 2
                        color = constants.color_for("bg", constants.TREE_BG_ID)
                        draw.line(
                            [(tcx, ty1 - 2), (tcx, ty1 - span_h * 0.18)], fill="#6b3e1a",
                            width=max(1, round(3 * scale)),
                        )
                        draw.polygon(
                            [(tcx, ty0 + span_h * 0.22), (tx0 + 3, ty1 - span_h * 0.22), (tx1 - 3, ty1 - span_h * 0.22)],
                            fill=color, outline="#12451f",
                        )
                        draw.polygon(
                            [(tcx, ty0 + 2), (tx0 + s(8), ty0 + span_h * 0.5), (tx1 - s(8), ty0 + span_h * 0.5)],
                            fill=color, outline="#12451f",
                        )
                    continue

                drawn = False
                if icon_style == "sprite":
                    size = sprites.scaled_size("bg", val, cell_size)
                    if size:
                        sprite = sprites.get_pil_image("bg", val, *size)
                        if sprite:
                            cx = (x0 + x1) / 2
                            _paste(img, sprite, cx - size[0] / 2, y1 - size[1])
                            drawn = True
                if drawn:
                    continue
                color = constants.color_for("bg", val)
                if val == 1:  # bush
                    draw.ellipse([x0 + s(1), y0 + s(6), x0 + s(11), y0 + s(14)], fill=color)
                else:
                    draw.rectangle([x0 + s(2), y0 + s(2), x0 + s(8), y0 + s(8)], fill=color)

    # -- ground --
    if layer_visible.get("ground", True):
        for r in range(level.rows):
            for c in range(level.cols):
                val = level.ground[r][c]
                if not val:
                    continue
                x0, y0 = c * cell_size, r * cell_size
                x1, y1 = x0 + cell_size, y0 + cell_size

                drawn = False
                if icon_style == "sprite" and sprites.has_image("ground", val):
                    sprite = sprites.get_pil_image("ground", val, cell_size, cell_size)
                    if sprite:
                        _paste(img, sprite, x0, y0)
                        drawn = True
                if not drawn:
                    color = constants.color_for("ground", val)
                    if color:
                        draw.rectangle([x0, y0, x1 - 1, y1 - 1], fill=color)
                    if val in (4, 5, 6):  # ladder
                        for frac in (0.3, 0.7):
                            y = y0 + (y1 - y0) * frac
                            draw.line([(x0 + s(3), y), (x1 - s(3), y)], fill="#5a3a1a", width=max(1, round(2 * scale)))
                        draw.line([(x0 + s(3), y0), (x0 + s(3), y1)], fill="#5a3a1a", width=max(1, round(2 * scale)))
                        draw.line([(x1 - s(3), y0), (x1 - s(3), y1)], fill="#5a3a1a", width=max(1, round(2 * scale)))
                    elif val == 7:  # metal hatch
                        midx, midy = (x0 + x1) / 2, (y0 + y1) / 2
                        draw.line([(x0 + s(3), y1 - s(3)), (x1 - s(3), y0 + s(3))], fill="#4a4a4a")
                        draw.line([(x0 + s(3), midy), (midx, y0 + s(3))], fill="#4a4a4a")
                        draw.line([(midx, y1 - s(3)), (x1 - s(3), midy)], fill="#4a4a4a")
                    elif val == 8:  # trampoline arc
                        draw.arc(
                            [x0 + s(2), y0 + (y1 - y0) * 0.35, x1 - s(2), y1 + (y1 - y0) * 0.55],
                            start=0, end=180, fill="#0a5c2e", width=max(1, round(2 * scale)),
                        )
                    elif val in (9, 10):  # conveyor arrow
                        arrow = "→" if val == 10 else "←"
                        draw.text(((x0 + x1) / 2, (y0 + y1) / 2), arrow, fill="#111111", font=font_bold, anchor="mm")

    # -- objects (non-platform), foreground --
    if layer_visible.get("objects", True):
        for r in range(level.rows):
            for c in range(level.cols):
                val = level.objects[r][c]
                if not val or val in constants.PLATFORM_WIDTHS:
                    continue
                x0, y0 = c * cell_size, r * cell_size
                x1, y1 = x0 + cell_size, y0 + cell_size
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

                drawn = False
                if icon_style == "sprite":
                    size = sprites.scaled_size("objects", val, cell_size)
                    if size:
                        sprite = sprites.get_pil_image("objects", val, *size)
                        if sprite:
                            _paste(img, sprite, cx - size[0] / 2, y1 - size[1])
                            drawn = True
                if drawn:
                    continue

                color = constants.color_for("objects", val)
                r_ = (x1 - x0) / 2 - s(3)

                if val in constants.SPAWN_IDS:
                    label = "P1" if val == 1 else "P2"
                    draw.line([(cx, y1 - s(2)), (cx, y0 + s(3))], fill="#333333", width=max(1, round(2 * scale)))
                    draw.polygon(
                        [(cx, y0 + s(2)), (cx + r_, y0 + r_ * 0.6), (cx, y0 + r_ * 1.1)],
                        fill=color, outline="#222222",
                    )
                    draw.text((cx, y1 - s(5)), label, fill="#000000", font=font_tiny, anchor="mm")
                elif val == 3:  # snowflake
                    for dx, dy in ((r_, 0), (r_ * 0.5, r_ * 0.866), (-r_ * 0.5, r_ * 0.866)):
                        draw.line([(cx - dx, cy - dy), (cx + dx, cy + dy)], fill=color, width=max(1, round(2 * scale)))
                elif val == 19:  # spikes
                    n = 3
                    step = (x1 - x0) / n
                    for i in range(n):
                        sx0 = x0 + i * step
                        draw.polygon(
                            [(sx0 + 1, y1 - 2), (sx0 + step / 2, y0 + s(4)), (sx0 + step - 1, y1 - 2)],
                            fill=color, outline="#661111",
                        )
                elif val == 18:  # living gap
                    draw.ellipse([x0 + s(4), y0 + s(4), x1 - s(4), y1 - s(4)], outline=color, width=max(1, round(2 * scale)))
                    draw.text((cx, cy), str(val), fill="#000000", font=font_small, anchor="mm")
                elif val in (15, 20):  # horned dragons
                    draw.polygon([(cx, y0 + s(3)), (x1 - s(3), y1 - s(3)), (x0 + s(3), y1 - s(3))], fill=color, outline="#000000")
                    draw.text((cx, cy + s(3)), str(val), fill="#000000", font=font_small, anchor="mm")
                else:
                    draw.ellipse([x0 + s(4), y0 + s(4), x1 - s(4), y1 - s(4)], fill=color, outline="#333333")
                    draw.text((cx, cy), str(val), fill="#000000", font=font_small, anchor="mm")

    # -- platforms (topmost) --
    if layer_visible.get("objects", True):
        for r in range(level.rows):
            for c in range(level.cols):
                val = level.objects[r][c]
                plat_width = constants.PLATFORM_WIDTHS.get(val)
                if not plat_width:
                    continue
                end_col = min(c + plat_width, level.cols)
                span_w = (end_col - c) * cell_size
                x0_full, y0_full = c * cell_size, r * cell_size

                drawn = False
                if icon_style == "sprite":
                    sprite = sprites.get_pil_image("objects", val, span_w, cell_size)
                    if sprite:
                        _paste(img, sprite, x0_full, y0_full)
                        drawn = True
                if drawn:
                    continue

                x0, x1 = x0_full + s(3), x0_full + span_w - s(3)
                y0 = y0_full + cell_size / 2 - s(5)
                y1 = y0_full + cell_size / 2 + s(5)
                color = constants.color_for("objects", val)
                draw.rectangle([x0, y0, x1, y1], fill=color, outline="#222222")
                if val in (5, 7):
                    glyph = "^"
                elif val in (6, 8):
                    glyph = "v"
                else:
                    glyph = str(val)
                draw.text(((x0 + x1) / 2, (y0 + y1) / 2), glyph, fill="#000000", font=font_bold, anchor="mm")

    if show_gridlines:
        for c in range(level.cols + 1):
            x = c * cell_size
            draw.line([(x, 0), (x, height)], fill=GRIDLINE_COLOR, width=1)
        for r in range(level.rows + 1):
            y = r * cell_size
            draw.line([(0, y), (width, y)], fill=GRIDLINE_COLOR, width=1)

    return img
