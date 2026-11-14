#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TERMINAL BIRD  --  a complete arcade game that runs inside your terminal.

No GUI, no canvas, no browser, no images: every star, cloud, pipe, feather
and blade of grass is drawn with ANSI colours and Unicode half blocks.

Run it in a real terminal:

    python3 flappy.py

Controls:  SPACE / W / UP  flap    P  pause    R  restart    Q  quit
"""

from __future__ import annotations

import argparse
import atexit
import json
import math
import os
import random
import select
import shutil
import signal
import sys
import termios
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

APP = "terminal-bird"
VERSION = "1.0.0"
MIN_COLS = 40
MIN_ROWS = 16

# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def mix_rgb(c1: int, c2: int, t: float) -> int:
    t = clamp(t, 0.0, 1.0)
    r1, g1, b1 = (c1 >> 16) & 255, (c1 >> 8) & 255, c1 & 255
    r2, g2, b2 = (c2 >> 16) & 255, (c2 >> 8) & 255, c2 & 255
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return (r << 16) | (g << 8) | b


def mul_rgb(c: int, factor: float) -> int:
    r = int(clamp(((c >> 16) & 255) * factor, 0, 255))
    g = int(clamp(((c >> 8) & 255) * factor, 0, 255))
    b = int(clamp((c & 255) * factor, 0, 255))
    return (r << 16) | (g << 8) | b


def hash01(n: int) -> float:
    """Cheap deterministic hash -> float in [0, 1)."""
    n = (n << 13) ^ n
    n = (n * (n * n * 15731 + 789221) + 1376312589) & 0x7FFFFFFF
    return n / 0x7FFFFFFF


def ease_out_cubic(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    return 1.0 - (1.0 - t) ** 3


# --------------------------------------------------------------------------
# palette
# --------------------------------------------------------------------------

C_SKY_TOP = 0x050817
C_SKY_MID = 0x0B1430
C_SKY_LOW = 0x172A4C
C_HORIZON = 0x2A4165
C_VOID = 0x04060F

C_MOON = 0xF1EED2
C_MOON_GLOW = 0x384B70
C_STAR = 0xE9F1FF
C_STAR_BLUE = 0xA9C9FF
C_STAR_GOLD = 0xFFE7A3

C_CLOUD_FAR = 0x2A4268
C_CLOUD_FAR_HI = 0x456795
C_CLOUD_NEAR = 0x16263F
C_CLOUD_NEAR_HI = 0x24405F

C_RIDGE_FAR = 0x1A2C4C
C_RIDGE_FAR_SNOW = 0x58749B
C_RIDGE_NEAR = 0x0E1B32
C_RIDGE_NEAR_LIGHT = 0x152640
C_TREE = 0x081221

C_GRASS_DARK = 0x123F22
C_GRASS = 0x2E8B3E
C_GRASS_LIGHT = 0x58C85A
C_GRASS_GLOW = 0x9AF07C
C_DIRT = 0x6B4A2E
C_DIRT_DARK = 0x4A3120
C_DIRT_LIGHT = 0x8A6440
C_DIRT_PEBBLE = 0xA98255

C_PIPE_OUT = 0x082E10
C_PIPE_DARK = 0x176326
C_PIPE_BODY = 0x2FAE45
C_PIPE_LIGHT = 0x5BDD68
C_PIPE_SHINE = 0xA8F7A4
C_PIPE_SHADOW = 0x1D7C30
C_PIPE_CAP_HI = 0x86EE85

C_GOLD = 0xF6C445
C_GOLD_HI = 0xFFE88A
C_CREAM = 0xFFF3C4
C_WHITE = 0xE9F0FA
C_CYAN = 0x7FE7E0
C_DIM = 0x8090B4
C_RED = 0xFF6B5A
C_GREEN = 0x6BE07A
C_PANEL = 0x0A1222
C_PANEL_EDGE = 0x223756
C_PANEL_SHADOW = 0x02040A
C_INK = 0x05070F

BIRD_PALETTE = {
    "K": 0x2B1A0E,
    "Y": 0xFFD43B,
    "W": 0xFFF0A8,
    "O": 0xF08A1E,
    "M": 0xFFC04A,
    "o": 0x8A4B08,
    "B": 0xFF7A1A,
    "H": 0xFFB154,
    "D": 0xB83A09,
    "E": 0xFFFDF5,
    "P": 0x17120C,
    ".": None,
}

BIRD_MID = (
    ".....KKKKK.......",
    "...KKYYYYYKK.....",
    "..KYYYYYYYYYK....",
    ".KYYYWWWWWWYYK...",
    "KYYWWWWWWEEEEYK..",
    "KYYWWWWWEEEEPEYK.",
    "KYYooWWEEEEEEHHBK",
    "KYYoMOoYYYYBBBBDK",
    ".KYYoooYYYYBBBDK.",
    "..KKKKYYYYKKKKK..",
    "....KKKKKKK......",
)
BIRD_UP = (
    ".....KKKKK.......",
    "...KKYYYYYKK.....",
    "..KYYYYYYYYYK....",
    ".KYYYWWWWWWYYK...",
    "KYYooWWWWEEEEYK..",
    "KYYoMOoWEEEEPEYK.",
    "KYYoOoWEEEEEEHHBK",
    "KYYWWWWWYYYBBBBDK",
    ".KYYWWWWYYYBBBDK.",
    "..KKKYYYYYKKKKK..",
    "....KKKKKKK......",
)
BIRD_DOWN = (
    ".....KKKKK.......",
    "...KKYYYYYKK.....",
    "..KYYYYYYYYYK....",
    ".KYYYWWWWWWYYK...",
    "KYYWWWWWWEEEEYK..",
    "KYYWWWWWEEEEPEYK.",
    "KYYWWWWEEEEEEHHBK",
    "KYYoMOoYYYBBBBDK.",
    ".KYYoooYYYBBBDK..",
    "..KKKooooYKKKKK..",
    "....KKKKKKK......",
)
BIRD_W, BIRD_H = 17, 11

for _name, _art in (("MID", BIRD_MID), ("UP", BIRD_UP), ("DOWN", BIRD_DOWN)):
    if len(_art) != BIRD_H or any(len(row) != BIRD_W for row in _art):
        raise RuntimeError(f"bird sprite {_name} has a wrong shape")


# --------------------------------------------------------------------------
# 5x7 bitmap font
# --------------------------------------------------------------------------
# Each glyph is seven rows of five bits.  The font is deliberately tiny and
# chunky so it reads well when turned into coloured pixels.

_FONT_SRC = {
    "A": "01110/10001/10001/11111/10001/10001/10001",
    "B": "11110/10001/10001/11110/10001/10001/11110",
    "C": "01111/10000/10000/10000/10000/10000/01111",
    "D": "11110/10001/10001/10001/10001/10001/11110",
    "E": "11111/10000/10000/11110/10000/10000/11111",
    "F": "11111/10000/10000/11110/10000/10000/10000",
    "G": "01111/10000/10000/10111/10001/10001/01111",
    "H": "10001/10001/10001/11111/10001/10001/10001",
    "I": "11111/00100/00100/00100/00100/00100/11111",
    "J": "00111/00010/00010/00010/10010/10010/01100",
    "K": "10001/10010/10100/11000/10100/10010/10001",
    "L": "10000/10000/10000/10000/10000/10000/11111",
    "M": "10001/11011/10101/10101/10001/10001/10001",
    "N": "10001/11001/10101/10011/10001/10001/10001",
    "O": "01110/10001/10001/10001/10001/10001/01110",
    "P": "11110/10001/10001/11110/10000/10000/10000",
    "Q": "01110/10001/10001/10001/10101/10010/01101",
    "R": "11110/10001/10001/11110/10100/10010/10001",
    "S": "01111/10000/10000/01110/00001/00001/11110",
    "T": "11111/00100/00100/00100/00100/00100/00100",
    "U": "10001/10001/10001/10001/10001/10001/01110",
    "V": "10001/10001/10001/10001/10001/01010/00100",
    "W": "10001/10001/10001/10101/10101/11011/10001",
    "X": "10001/10001/01010/00100/01010/10001/10001",
    "Y": "10001/10001/01010/00100/00100/00100/00100",
    "Z": "11111/00001/00010/00100/01000/10000/11111",
    "0": "01110/10001/10011/10101/11001/10001/01110",
    "1": "00100/01100/00100/00100/00100/00100/01110",
    "2": "01110/10001/00001/00010/00100/01000/11111",
    "3": "11110/00001/00001/01110/00001/00001/11110",
    "4": "00010/00110/01010/10010/11111/00010/00010",
    "5": "11111/10000/11110/00001/00001/10001/01110",
    "6": "00110/01000/10000/11110/10001/10001/01110",
    "7": "11111/00001/00010/00100/01000/01000/01000",
    "8": "01110/10001/10001/01110/10001/10001/01110",
    "9": "01110/10001/10001/01111/00001/00010/01100",
    " ": "00000/00000/00000/00000/00000/00000/00000",
    ":": "00000/00100/00100/00000/00100/00100/00000",
    ".": "00000/00000/00000/00000/00000/00110/00110",
    ",": "00000/00000/00000/00000/00110/00110/01100",
    "!": "00100/00100/00100/00100/00100/00000/00100",
    "?": "01110/10001/00001/00010/00100/00000/00100",
    "-": "00000/00000/00000/11111/00000/00000/00000",
    "+": "00000/00100/00100/11111/00100/00100/00000",
    "/": "00001/00010/00010/00100/01000/01000/10000",
    "'": "00100/00100/00000/00000/00000/00000/00000",
    "%": "11001/11010/00010/00100/01000/01011/10011",
    "#": "01010/01010/11111/01010/11111/01010/01010",
    "(": "00110/01000/10000/10000/10000/01000/00110",
    ")": "01100/00010/00001/00001/00001/00010/01100",
}
FONT = {ch: tuple(rows.split("/")) for ch, rows in _FONT_SRC.items()}
for _ch, _glyph in FONT.items():
    if len(_glyph) != 7 or any(len(row) != 5 for row in _glyph):
        raise RuntimeError(f"font glyph {_ch!r} has a wrong shape")


def text_width(text: str, scale: int = 1, spacing: int = 1) -> int:
    if not text:
        return 0
    return (len(text) * (5 + spacing) - spacing) * scale


# --------------------------------------------------------------------------
# pixel canvas
# --------------------------------------------------------------------------


class Canvas:
    """A w x h buffer of packed 0xRRGGBB pixels."""

    __slots__ = ("w", "h", "buf")

    def __init__(self, w: int, h: int, fill: int = 0) -> None:
        self.w = w
        self.h = h
        self.buf = [fill] * (w * h)

    def clone(self) -> "Canvas":
        c = Canvas(self.w, self.h)
        c.buf = self.buf[:]
        return c

    def clear(self, color: int = 0) -> None:
        self.buf = [color] * (self.w * self.h)

    def copy_from(self, other: "Canvas") -> None:
        self.buf[:] = other.buf

    def px(self, x: int, y: int, color: int) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            self.buf[y * self.w + x] = color

    def blend(self, x: int, y: int, color: int, alpha: float) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            i = y * self.w + x
            self.buf[i] = mix_rgb(self.buf[i], color, alpha)

    def hline(self, x: int, y: int, length: int, color: int) -> None:
        self.rect(x, y, length, 1, color)

    def vline(self, x: int, y: int, length: int, color: int) -> None:
        self.rect(x, y, 1, length, color)

    def rect(self, x: int, y: int, w: int, h: int, color: int) -> None:
        if w <= 0 or h <= 0:
            return
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(self.w, int(x) + int(w))
        y1 = min(self.h, int(y) + int(h))
        if x0 >= x1 or y0 >= y1:
            return
        self.blit_row_span(x0, y0, x1, y1, color)

    def blend_rect(self, x: int, y: int, w: int, h: int, color: int, alpha: float) -> None:
        if w <= 0 or h <= 0:
            return
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(self.w, int(x) + int(w))
        y1 = min(self.h, int(y) + int(h))
        for yy in range(y0, y1):
            base = yy * self.w
            for xx in range(x0, x1):
                self.buf[base + xx] = mix_rgb(self.buf[base + xx], color, alpha)

    def blit_row_span(self, x0: int, y0: int, x1: int, y1: int, color: int) -> None:
        run = [color] * (x1 - x0)
        for yy in range(y0, y1):
            base = yy * self.w
            self.buf[base + x0:base + x1] = run

    def disc(self, cx: int, cy: int, radius: int, color: int) -> None:
        if radius < 1:
            return
        r2 = radius * radius
        for dy in range(-radius, radius + 1):
            span = int(math.sqrt(max(0, r2 - dy * dy)))
            self.rect(cx - span, cy + dy, span * 2 + 1, 1, color)

    def round_rect(self, x: int, y: int, w: int, h: int, radius: int, color: int) -> None:
        if w <= 0 or h <= 0:
            return
        radius = int(clamp(radius, 0, min(w, h) // 2))
        if radius == 0:
            self.rect(x, y, w, h, color)
            return
        for yy in range(h):
            if yy < radius:
                inset = radius - int(math.sqrt(max(0, radius * radius - (radius - yy - 1) ** 2)))
            elif yy >= h - radius:
                inset = radius - int(math.sqrt(max(0, radius * radius - (yy - (h - radius)) ** 2)))
            else:
                inset = 0
            self.rect(x + inset, y + yy, w - inset * 2, 1, color)

    def dim(self, factor: float) -> None:
        target = C_VOID
        amount = 1.0 - clamp(factor, 0.0, 1.0)
        if amount <= 0:
            return
        self.buf = [mix_rgb(c, target, amount) for c in self.buf]

    def shift(self, dx: int, dy: int) -> None:
        if dx == 0 and dy == 0:
            return
        w, h, buf = self.w, self.h, self.buf
        new = [0] * (w * h)
        for y in range(h):
            sy = int(clamp(y - dy, 0, h - 1))
            row = buf[sy * w:(sy + 1) * w]
            if dx > 0:
                newrow = [row[0]] * dx + row[:w - dx]
            elif dx < 0:
                newrow = row[-dx:] + [row[-1]] * (-dx)
            else:
                newrow = row
            new[y * w:(y + 1) * w] = newrow
        self.buf = new

    def sprite(self, art: Iterable[str], x: int, y: int, palette: dict, scale: int = 1) -> None:
        for row_i, row in enumerate(art):
            for col_i, ch in enumerate(row):
                color = palette.get(ch)
                if color is not None:
                    self.rect(x + col_i * scale, y + row_i * scale, scale, scale, color)

    def pixel_text(
        self,
        text: str,
        x: int,
        y: int,
        color: int,
        *,
        scale: int = 1,
        spacing: int = 1,
        align: str = "left",
        outline: Optional[int] = None,
        shadow: Optional[int] = None,
        gradient: Optional[list[int]] = None,
    ) -> int:
        """Draw text with the 5x7 font.  Returns the drawn width in pixels."""
        text = text.upper()
        width = text_width(text, scale, spacing)
        if align == "center":
            x -= width // 2
        elif align == "right":
            x -= width

        mask: list[tuple[int, int, int]] = []
        cx = 0
        for ch in text:
            glyph = FONT.get(ch)
            if glyph:
                for gy, row in enumerate(glyph):
                    for gx, bit in enumerate(row):
                        if bit == "1":
                            mask.append((cx + gx, gy, gy))
            cx += 5 + spacing
        if not mask:
            return width

        occupied = {(mx, my) for mx, my, _ in mask}
        if shadow is not None:
            off = max(1, scale)
            for mx, my in {(mx + off, my + off) for mx, my in occupied}:
                self.rect(x + mx * scale, y + my * scale, scale, scale, shadow)
        if outline is not None:
            edge: set[tuple[int, int]] = set()
            for mx, my in occupied:
                for ox in (-1, 0, 1):
                    for oy in (-1, 0, 1):
                        p = (mx + ox, my + oy)
                        if p not in occupied:
                            edge.add(p)
            for mx, my in edge:
                self.rect(x + mx * scale, y + my * scale, scale, scale, outline)
        for mx, my, gy in mask:
            c = gradient[min(gy, len(gradient) - 1)] if gradient else color
            self.rect(x + mx * scale, y + my * scale, scale, scale, c)
        return width


# --------------------------------------------------------------------------
# ANSI colour handling
# --------------------------------------------------------------------------

ANSI16_RGB = (
    (0, 0, 0), (128, 0, 0), (0, 128, 0), (128, 128, 0),
    (0, 0, 128), (128, 0, 128), (0, 128, 128), (192, 192, 192),
    (128, 128, 128), (255, 0, 0), (0, 255, 0), (255, 255, 0),
    (0, 0, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255),
)
XTERM_LEVELS = (0, 95, 135, 175, 215, 255)


def _nearest16(color: int) -> int:
    r, g, b = (color >> 16) & 255, (color >> 8) & 255, color & 255
    best_i, best_d = 0, 1 << 40
    for i, (rr, gg, bb) in enumerate(ANSI16_RGB):
        d = (r - rr) ** 2 + (g - gg) ** 2 + (b - bb) ** 2
        if d < best_d:
            best_i, best_d = i, d
    return best_i


def _quant256(color: int) -> int:
    r, g, b = (color >> 16) & 255, (color >> 8) & 255, color & 255
    ri = min(range(6), key=lambda i: abs(r - XTERM_LEVELS[i]))
    gi = min(range(6), key=lambda i: abs(g - XTERM_LEVELS[i]))
    bi = min(range(6), key=lambda i: abs(b - XTERM_LEVELS[i]))
    cr, cg, cb = XTERM_LEVELS[ri], XTERM_LEVELS[gi], XTERM_LEVELS[bi]
    cube = 16 + 36 * ri + 6 * gi + bi
    gray_avg = (r + g + b) // 3
    gray_i = min(23, max(0, round((gray_avg - 8) / 10)))
    gray = 8 + 10 * gray_i
    gray_code = 232 + gray_i
    if (gray - gray_avg) ** 2 < (cr - r) ** 2 + (cg - g) ** 2 + (cb - b) ** 2:
        return gray_code
    return cube


def resolve_color_mode(requested: str) -> str:
    if requested != "auto":
        return requested
    colorterm = os.environ.get("COLORTERM", "").lower()
    term = os.environ.get("TERM", "").lower()
    if colorterm in ("truecolor", "24bit") or "truecolor" in term:
        return "truecolor"
    if "256color" in term:
        return "256"
    if term in ("dumb", ""):
        return "16"
    return "256"


# --------------------------------------------------------------------------
# screen output
# --------------------------------------------------------------------------


@dataclass
class TextLine:
    row: int
    col: int
    text: str
    fg: int = C_WHITE
    bg: Optional[int] = None
    bold: bool = False


class Renderer:
    """Turns a pixel Canvas + text lines into one flicker-free ANSI frame.

    The canvas is converted to half-block cells (two pixels per cell), then
    changed rows are re-emitted.  A simple RLE groups equal styles so a
    typical frame is far smaller than a naive cell-by-cell repaint.
    """

    def __init__(self, fd: int, color_mode: str = "auto") -> None:
        self.fd = fd
        self.mode = resolve_color_mode(color_mode)
        self.cols = 0
        self.rows = 0
        self.prev_cells: Optional[list[list[tuple[str, int, int, bool]]]] = None
        self._style_cache: dict[tuple[int, int, bool], str] = {}
        self._quant_cache: dict[int, int] = {}
        self._small_sig: Optional[tuple[int, int]] = None
        self._entered = False

    # -- low level ---------------------------------------------------------
    def _write(self, data: str) -> None:
        raw = data.encode("utf-8", "replace")
        while raw:
            try:
                n = os.write(self.fd, raw)
            except InterruptedError:
                continue
            except OSError:
                return
            raw = raw[n:]

    def enter(self) -> None:
        if self._entered:
            return
        self._write(
            "\x1b[?1049h"      # alternate screen
            "\x1b[?25l"        # hide cursor
            "\x1b[0m"
            "\x1b[2J\x1b[H"
        )
        self._entered = True

    def leave(self) -> None:
        if not self._entered:
            return
        self._write("\x1b[0m\x1b[?2026l\x1b[?25h\x1b[?1049l")
        self._entered = False

    def resize(self, cols: int, rows: int) -> None:
        if cols == self.cols and rows == self.rows:
            return
        self.cols, self.rows = cols, rows
        self.prev_cells = None
        self._small_sig = None
        self._write("\x1b[2J")

    def _sgr(self, fg: int, bg: int, bold: bool) -> str:
        key = (fg, bg, bold)
        cached = self._style_cache.get(key)
        if cached is not None:
            return cached
        fg_code = self._color_code(fg, False)
        bg_code = self._color_code(bg, True)
        code = f"\x1b[{fg_code};{bg_code};{'1' if bold else '22'}m"
        self._style_cache[key] = code
        return code

    def _color_code(self, color: int, is_bg: bool) -> str:
        color &= 0xFFFFFF
        if self.mode == "truecolor":
            r, g, b = (color >> 16) & 255, (color >> 8) & 255, color & 255
            return f"{48 if is_bg else 38};2;{r};{g};{b}"
        if self.mode == "256":
            idx = self._quant_cache.get(color)
            if idx is None:
                idx = _quant256(color)
                self._quant_cache[color] = idx
            return f"{48 if is_bg else 38};5;{idx}"
        idx = self._quant_cache.get(color)
        if idx is None:
            idx = _nearest16(color)
            self._quant_cache[color] = idx
        if idx < 8:
            return str((40 if is_bg else 30) + idx)
        return str((100 if is_bg else 90) + idx - 8)

    # -- frame construction -----------------------------------------------
    def _cells(self, canvas: Canvas, texts: list[TextLine]) -> list[list[tuple[str, int, int, bool]]]:
        w, h = canvas.w, canvas.h
        buf = canvas.buf
        rows = h // 2
        cells: list[list[tuple[str, int, int, bool]]] = []
        for r in range(rows):
            base = r * 2 * w
            top = buf[base:base + w]
            if r * 2 + 1 < h:
                bottom = buf[base + w:base + 2 * w]
            else:
                bottom = top
            cells.append([("\u2580", top[x], bottom[x], False) for x in range(w)])

        for line in texts:
            if not (0 <= line.row < rows):
                continue
            row = cells[line.row]
            col = line.col
            bg = line.bg
            for ch in line.text:
                if 0 <= col < w and ch >= " ":
                    old = row[col]
                    row[col] = (ch, line.fg, old[2] if bg is None else bg, line.bold)
                col += 1
                if col >= w:
                    break
        return cells

    def _row_body(self, cells: list[tuple[str, int, int, bool]]) -> str:
        parts: list[str] = []
        if not cells:
            return ""
        start = 0
        style = (cells[0][1], cells[0][2], cells[0][3])
        length = len(cells)
        for x in range(1, length + 1):
            if x == length or (cells[x][1], cells[x][2], cells[x][3]) != style:
                chunk = "".join(c[0] for c in cells[start:x])
                parts.append(self._sgr(style[0], style[1], style[2]))
                parts.append(chunk)
                if x < length:
                    style = (cells[x][1], cells[x][2], cells[x][3])
                    start = x
        return "".join(parts)

    def _changed_spans(self, old: list[tuple[str, int, int, bool]],
                       new: list[tuple[str, int, int, bool]]) -> list[tuple[int, int]]:
        """Narrow a changed row to a handful of dirty column spans."""
        width = len(new)
        spans: list[tuple[int, int]] = []
        x = 0
        while x < width:
            while x < width and old[x] == new[x]:
                x += 1
            if x >= width:
                break
            start = x
            last = x
            while x < width:
                if old[x] != new[x]:
                    last = x
                    x += 1
                    continue
                look = x
                while look < width and look - x < 3 and old[look] == new[look]:
                    look += 1
                if look < width and old[look] != new[look]:
                    x = look
                else:
                    break
            spans.append((start, last))
            x = last + 1
        return spans

    def _span_body(self, cells: list[tuple[str, int, int, bool]],
                   lo: int, hi: int) -> str:
        parts: list[str] = []
        style = None
        for x in range(lo, hi + 1):
            ch, fg, bg, bold = cells[x]
            key = (fg, bg, bold)
            if key != style:
                parts.append(self._sgr(fg, bg, bold))
                style = key
            parts.append(ch)
        return "".join(parts)

    def render(self, canvas: Canvas, texts: list[TextLine]) -> None:
        if not self._entered:
            return
        if canvas.w != self.cols or canvas.h // 2 != self.rows:
            self.resize(canvas.w, canvas.h // 2)
        cells = self._cells(canvas, texts)
        old_rows = self.prev_cells
        out: list[str] = []
        for r in range(self.rows):
            new = cells[r]
            if old_rows is None:
                spans = [(0, self.cols - 1)]
            else:
                old = old_rows[r]
                if old == new:
                    continue
                spans = self._changed_spans(old, new)
            for lo, hi in spans:
                if hi < lo:
                    continue
                out.append(f"\x1b[{r + 1};{lo + 1}H")
                out.append(self._span_body(new, lo, hi))
        self.prev_cells = cells
        if out:
            self._write("\x1b[?2026h" + "".join(out) + "\x1b[?2026l")

    def render_too_small(self, cols: int, rows: int) -> None:
        if not self._entered:
            return
        sig = (cols, rows)
        if sig == self._small_sig:
            return
        self._small_sig = sig
        self.cols, self.rows = cols, rows
        self.prev_cells = None
        lines = [
            "",
            "T E R M I N A L   B I R D",
            "",
            f"NEED AT LEAST {MIN_COLS} COLS x {MIN_ROWS} ROWS",
            f"THIS WINDOW IS {cols} x {rows}",
            "",
            "PLEASE MAKE THE TERMINAL BIGGER",
            "OR PRESS Q TO QUIT",
        ]
        out = ["\x1b[?2026h", "\x1b[0m\x1b[2J"]
        gold = self._sgr(C_GOLD, C_VOID, True)
        dim = self._sgr(C_DIM, C_VOID, False)
        start = max(0, (rows - len(lines)) // 2)
        for i, line in enumerate(lines):
            if not line:
                continue
            r = start + i
            if r >= rows:
                break
            c = max(1, (cols - len(line)) // 2 + 1)
            style = gold if i == 1 else dim
            out.append(f"\x1b[{r + 1};1H{self._sgr(C_VOID, C_VOID, False)}{' ' * cols}")
            out.append(f"\x1b[{r + 1};{c}H{style}{line}")
        out.append("\x1b[?2026l")
        self._write("".join(out))


# --------------------------------------------------------------------------
# terminal session
# --------------------------------------------------------------------------


class TerminalSession:
    """Raw keyboard input without ever leaving the terminal broken."""

    def __init__(self, in_fd: int, out_fd: int) -> None:
        self.in_fd = in_fd
        self.out_fd = out_fd
        self.saved = None
        self.active = False
        self._pending = bytearray()
        self._esc_at = 0.0

    def __enter__(self) -> "TerminalSession":
        self.enter()
        return self

    def __exit__(self, *exc_info) -> None:
        self.restore()

    def enter(self) -> None:
        if self.active:
            return
        self.saved = termios.tcgetattr(self.in_fd)
        attrs = termios.tcgetattr(self.in_fd)
        attrs[0] &= ~(termios.IXON | termios.IXOFF | termios.IXANY)
        attrs[3] &= ~(termios.ECHO | termios.ICANON | termios.IEXTEN)
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        # Ctrl-Z should not suspend a full-screen raw app behind our back.
        try:
            attrs[6][termios.VSUSP] = 0
        except (AttributeError, IndexError):
            pass
        termios.tcsetattr(self.in_fd, termios.TCSADRAIN, attrs)
        self.active = True

    def restore(self) -> None:
        if not self.active:
            return
        self.active = False
        try:
            termios.tcsetattr(self.in_fd, termios.TCSADRAIN, self.saved)
        except termios.error:
            pass

    def write(self, text: str) -> None:
        self._write_bytes(text.encode("utf-8", "replace"))

    def _write_bytes(self, raw: bytes) -> None:
        while raw:
            try:
                n = os.write(self.out_fd, raw)
            except InterruptedError:
                continue
            except OSError:
                return
            raw = raw[n:]

    def _parse(self) -> list[str]:
        data = self._pending
        keys: list[str] = []
        i = 0
        n = len(data)
        while i < n:
            b = data[i]
            if b == 0x1B:
                if i + 1 >= n:
                    if self._esc_at == 0.0:
                        self._esc_at = time.monotonic()
                    break  # wait briefly to see if this is an arrow key
                self._esc_at = 0.0
                if data[i + 1] in (ord("["), ord("O")):
                    if i + 2 >= n:
                        break
                    j = i + 2
                    while j < n and not (0x40 <= data[j] <= 0x7E):
                        j += 1
                    if j >= n:
                        break
                    final = data[j]
                    if final == ord("A"):
                        keys.append("up")
                    elif final == ord("B"):
                        keys.append("down")
                    i = j + 1
                else:
                    keys.append("esc")
                    i += 1
            elif b in (10, 13):
                keys.append("enter")
                i += 1
            elif b in (8, 127):
                keys.append("backspace")
                i += 1
            elif b == 3:
                keys.append("ctrl-c")
                i += 1
            elif b == 26:
                i += 1
            elif b < 32:
                i += 1
            else:
                # ASCII keys are all this game needs; UTF-8 continuation
                # bytes are simply harmless.
                if b < 128:
                    keys.append(chr(b).lower())
                    i += 1
                else:
                    i += 1
        if i:
            del data[:i]
        if len(data) > 256:
            data.clear()
        return keys

    def read_keys(self, timeout: float = 0.0) -> list[str]:
        keys: list[str] = []
        ready, _, _ = select.select([self.in_fd], [], [], timeout)
        if ready:
            try:
                chunk = os.read(self.in_fd, 4096)
            except (BlockingIOError, InterruptedError):
                chunk = b""
            except OSError:
                chunk = b""
            if chunk:
                self._pending.extend(chunk)
                keys.extend(self._parse())
        # A lone ESC is ambiguous: it may be the start of an arrow key.
        # Give the rest of a sequence ~45 ms to arrive, then treat it as Esc.
        if self._pending == b"\x1b":
            now = time.monotonic()
            if self._esc_at == 0.0:
                self._esc_at = now
            elif now - self._esc_at >= 0.045:
                self._pending.clear()
                self._esc_at = 0.0
                keys.append("esc")
        elif not self._pending:
            self._esc_at = 0.0
        return keys


# --------------------------------------------------------------------------
# high scores
# --------------------------------------------------------------------------


def scores_path() -> Path:
    override = os.environ.get("TERMINAL_BIRD_DATA")
    if override:
        return Path(override).expanduser() / "highscore.json"
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return base / APP / "highscore.json"


def load_scores(path: Optional[Path] = None) -> dict:
    path = path or scores_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError
        best = int(raw.get("best", 0))
        games = int(raw.get("games", 0))
        return {"best": max(0, best), "games": max(0, games)}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {"best": 0, "games": 0}


def save_scores(record: dict, path: Optional[Path] = None) -> bool:
    path = path or scores_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"best": max(0, int(record.get("best", 0))),
             "games": max(0, int(record.get("games", 0)))},
            indent=2,
        )
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(payload + "\n", encoding="utf-8")
        os.replace(tmp, path)
        return True
    except OSError:
        return False


# --------------------------------------------------------------------------
# game entities
# --------------------------------------------------------------------------


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    color: int
    size: int = 1
    gravity: float = 0.0
    drag: float = 0.0

    def update(self, dt: float) -> bool:
        self.life -= dt
        if self.life <= 0:
            return False
        self.vy += self.gravity * dt
        if self.drag:
            damp = max(0.0, 1.0 - self.drag * dt)
            self.vx *= damp
            self.vy *= damp
        self.x += self.vx * dt
        self.y += self.vy * dt
        return True


@dataclass
class Pipe:
    x: float
    gap_y: float
    gap_h: float
    scored: bool = False
    variant: int = 0


@dataclass
class Bird:
    x: float
    y: float
    w: int
    h: int
    vy: float = 0.0
    wing_t: float = 0.0


@dataclass
class Star:
    x: float
    y: float
    size: int
    phase: float
    speed: float
    color: int
    cross: bool
    drift: float


@dataclass
class Cloud:
    x: float
    y: float
    scale: int
    speed: float
    puffs: list[tuple[int, int, int]]
    near: bool


@dataclass
class Firefly:
    x: float
    y: float
    phase: float
    speed: float
    amp: float


@dataclass
class ShootingStar:
    x: float
    y: float
    vx: float
    vy: float
    born: float
    life: float


# --------------------------------------------------------------------------
# scenery: sky, stars, moon, clouds, mountains, fireflies
# --------------------------------------------------------------------------


class Scenery:
    """The living background.  It owns no gameplay state."""

    def __init__(self, w: int, h: int, sky_h: int, seed: int) -> None:
        self.w = 0
        self.h = 0
        self.sky_h = 0
        self.sky: list[int] = []
        self.stars: list[Star] = []
        self.clouds: list[Cloud] = []
        self.fireflies: list[Firefly] = []
        self.rng = random.Random(seed ^ 0x5EEDB1)
        self.resize(w, h, sky_h)

    def resize(self, w: int, h: int, sky_h: int) -> None:
        if w == self.w and h == self.h and sky_h == self.sky_h:
            return
        self.w, self.h, self.sky_h = w, h, sky_h
        rng = self.rng
        self._build_sky()
        self._build_stars(rng)
        self._build_clouds(rng)
        self.fireflies = [
            Firefly(rng.random(), 0.62 + rng.random() * 0.35,
                    rng.random() * math.tau, 0.4 + rng.random() * 0.9,
                    1.5 + rng.random() * 2.0)
            for _ in range(max(3, w // 30))
        ]

    def _build_sky(self) -> None:
        w, sky = self.w, self.sky_h
        buf: list[int] = []
        for y in range(sky):
            t = y / max(1, sky - 1)
            if t < 0.46:
                c = mix_rgb(C_SKY_TOP, C_SKY_MID, t / 0.46)
            elif t < 0.82:
                c = mix_rgb(C_SKY_MID, C_SKY_LOW, (t - 0.46) / 0.36)
            else:
                c = mix_rgb(C_SKY_LOW, C_HORIZON, (t - 0.82) / 0.18)
            buf.extend([c] * w)
        # Soft moon halo, baked into the static sky once.
        mx = int(w * 0.84)
        my = int(sky * 0.19)
        mr = max(4, int(sky * 0.065))
        glow_r = mr * 6
        for dy in range(-glow_r, glow_r + 1):
            yy = my + dy
            if not (0 <= yy < sky):
                continue
            span = int(math.sqrt(max(0, glow_r * glow_r - dy * dy)))
            for dx in range(-span, span + 1):
                xx = mx + dx
                if not (0 <= xx < w):
                    continue
                dist = math.hypot(dx, dy)
                alpha = max(0.0, 1.0 - dist / glow_r) ** 2.2 * 0.72
                if alpha > 0.004:
                    i = yy * w + xx
                    buf[i] = mix_rgb(buf[i], C_MOON_GLOW, alpha)
        self.sky = buf

    def _build_stars(self, rng: random.Random) -> None:
        w, sky = self.w, self.sky_h
        count = int(clamp(w * sky / 220, 20, 80))
        stars: list[Star] = []
        for _ in range(count):
            x = rng.random()
            y = rng.random() * 0.80
            size = 2 if rng.random() < 0.12 else 1
            color = C_STAR if rng.random() < 0.68 else (
                C_STAR_BLUE if rng.random() < 0.6 else C_STAR_GOLD)
            stars.append(Star(
                x=x, y=y, size=size,
                phase=rng.random() * math.tau,
                speed=0.5 + rng.random() * 2.2,
                color=color,
                cross=rng.random() < 0.08,
                drift=(rng.random() - 0.5) * 1.6,
            ))
        self.stars = stars

    def _build_clouds(self, rng: random.Random) -> None:
        clouds: list[Cloud] = []
        for i in range(max(3, self.w // 26)):
            scale = 1 if rng.random() < 0.7 else 2
            near = rng.random() < 0.34
            width = (18 + rng.randrange(8)) * scale
            puffs: list[tuple[int, int, int]] = []
            n = 6 + rng.randrange(3)
            for j in range(n):
                dx = int(-width / 2 + width * (j / max(1, n - 1)) + (rng.random() - 0.5) * 3)
                dy = int(-abs(math.sin(j * 1.7)) * (2 + scale) + (rng.random() - 0.5) * 2)
                r = 2 + rng.randrange(2) + (1 if j in (1, n - 2) else 0)
                puffs.append((dx, dy, r * scale))
            clouds.append(Cloud(
                x=rng.random(),
                y=(0.34 + rng.random() * 0.26) if near else (0.16 + rng.random() * 0.36),
                scale=scale, speed=1.4 + rng.random() * 3.2,
                puffs=puffs, near=near,
            ))
        self.clouds = clouds

    # -- drawing -----------------------------------------------------------
    def draw(self, canvas: Canvas, t: float, scroll: float) -> None:
        w = self.w
        sky = self.sky_h
        canvas.buf[:w * sky] = self.sky
        self._draw_moon(canvas)
        self._draw_stars(canvas, t)
        for cloud in self.clouds:
            if not cloud.near:
                self._draw_cloud(canvas, cloud, t)
        self._draw_ridge(canvas, t, far=True)
        for cloud in self.clouds:
            if cloud.near:
                self._draw_cloud(canvas, cloud, t)
        self._draw_ridge(canvas, t, far=False)
        self._draw_fireflies(canvas, t, scroll)

    def _draw_moon(self, canvas: Canvas) -> None:
        w, sky = self.w, self.sky_h
        mx = int(w * 0.84)
        my = int(sky * 0.19)
        mr = max(4, int(sky * 0.065))
        # The crescent: subtract a slightly larger circle offset up/right.
        ox, oy = int(mr * 0.45), int(-mr * 0.15)
        for dy in range(-mr, mr + 1):
            y = my + dy
            if not (0 <= y < sky):
                continue
            span = int(math.sqrt(max(0, mr * mr - dy * dy)))
            for dx in range(-span, span + 1):
                x = mx + dx
                if not (0 <= x < w):
                    continue
                bx, by = dx - ox, dy - oy
                if bx * bx + by * by <= mr * mr:
                    continue
                shade = 0.86 + 0.14 * math.sin(dx * 2.1 + dy * 1.3)
                canvas.px(x, y, mul_rgb(C_MOON, shade))
        # A tiny soft crater / shade on the lit side.
        canvas.blend(mx + mr // 2, my + mr // 3, 0xCFCBAA, 0.35)
        canvas.blend(mx + mr // 2 + 1, my + mr // 3 + 2, 0xCFCBAA, 0.25)

    def _draw_stars(self, canvas: Canvas, t: float) -> None:
        w, sky = self.w, self.sky_h
        for star in self.stars:
            x = int((star.x * w + t * star.drift) % w)
            y = int(star.y * sky)
            if not (0 <= y < sky):
                continue
            base = self.sky[y * w + x]
            tw = 0.5 + 0.5 * math.sin(t * star.speed + star.phase)
            bright = 0.45 + 0.55 * tw * tw
            color = mix_rgb(base, star.color, bright)
            canvas.px(x, y, color)
            if star.size >= 2:
                dim = mix_rgb(base, star.color, bright * 0.55)
                canvas.px(x - 1, y, dim)
                canvas.px(x + 1, y, dim)
                canvas.px(x, y - 1, dim)
                canvas.px(x, y + 1, dim)
            if star.cross:
                dim = mix_rgb(base, star.color, bright * 0.32)
                for d in (-2, 2):
                    canvas.px(x + d, y, dim)
                    canvas.px(x, y + d, dim)

    def _draw_cloud(self, canvas: Canvas, cloud: Cloud, t: float) -> None:
        w, sky = self.w, self.sky_h
        span = 24 * cloud.scale
        x = (cloud.x * (w + span * 2) - t * cloud.speed) % (w + span * 2) - span
        ix = int(x)
        y = int(cloud.y * sky)
        base = C_CLOUD_NEAR if cloud.near else C_CLOUD_FAR
        hi = C_CLOUD_NEAR_HI if cloud.near else C_CLOUD_FAR_HI
        for dx, dy, r in cloud.puffs:
            canvas.disc(ix + dx, y + dy, r, base)
        # Sunlit top arcs give the puffs their volume without turning them
        # into flat grey blobs.
        for dx, dy, r in cloud.puffs:
            if r >= 2:
                half = max(1, int(math.sqrt(max(0, 2 * r - 2))))
                canvas.hline(ix + dx - half, y + dy - r + 1, half * 2 + 1, hi)
                canvas.blend_rect(ix + dx - half + 1, y + dy - r + 2,
                                  max(1, half * 2 - 1), 1, hi, 0.25)
        # A soft shadow along each puff's underside.
        lower = mix_rgb(base, C_VOID, 0.30)
        for dx, dy, r in cloud.puffs:
            half = max(1, int(math.sqrt(max(0, 2 * r - 4))))
            canvas.hline(ix + dx - half, y + dy + r - 2, half * 2 + 1, lower)

    def _ridge_top(self, x: float, t: float, far: bool) -> int:
        sky = self.sky_h
        if far:
            u = x + t * 4.0
            base = sky * 0.83
            amp = sky * 0.42
            h = (0.50 * abs(math.sin(u * 0.045 + 1.3))
                 + 0.30 * abs(math.sin(u * 0.083 + 4.1))
                 + 0.20 * abs(math.sin(u * 0.160 + 2.2)))
        else:
            u = x + t * 8.0
            base = sky * 1.02
            amp = sky * 0.30
            h = (0.55 * abs(math.sin(u * 0.060 + 0.2))
                 + 0.30 * abs(math.sin(u * 0.120 + 2.9))
                 + 0.15 * abs(math.sin(u * 0.220 + 1.1)))
        top = int(base - amp * h)
        return int(clamp(top, 0, max(0, sky - 1)))

    def _draw_ridge(self, canvas: Canvas, t: float, far: bool) -> None:
        w, sky = self.w, self.sky_h
        color = C_RIDGE_FAR if far else C_RIDGE_NEAR
        light = C_RIDGE_FAR_SNOW if far else C_RIDGE_NEAR_LIGHT
        for x in range(w):
            top = self._ridge_top(x, t, far)
            canvas.rect(x, top, 1, sky - top, color)
            if far:
                if top < int(sky * 0.52):
                    snow = C_RIDGE_FAR_SNOW if top < int(sky * 0.46) else light
                    canvas.px(x, top, snow)
                    if top + 1 < sky and (top < int(sky * 0.43)
                                          or hash01(x * 13 + 5) > 0.52):
                        canvas.px(x, top + 1, mix_rgb(color, C_RIDGE_FAR_SNOW, 0.45))
                elif hash01(x * 11 + 7) > 0.72:
                    canvas.px(x, top, mix_rgb(color, light, 0.55))
            else:
                if hash01(x * 5 + 3) > 0.46:
                    canvas.px(x, top, light)
                if hash01(x * 17 + 9) > 0.8:
                    canvas.px(x, top + 1, mix_rgb(color, light, 0.5))
        if not far:
            # Little pines anchored to world positions on the near ridge,
            # so they slide past with the parallax instead of flickering.
            offset = t * 8.0
            period = 13
            first = int(math.floor((offset - 12) / period)) * period
            last = int(offset + w + period)
            for wx in range(first, last, period):
                sx = int(round(wx - offset))
                if not (0 <= sx < w):
                    continue
                top = self._ridge_top(sx, t, False)
                th = 2 + int(hash01((wx // period) * 17 + 3) * 4)
                for i in range(th):
                    half = max(0, (th - i) // 2)
                    canvas.rect(sx - half, top - i, half * 2 + 1, 1, C_TREE)

    def _draw_fireflies(self, canvas: Canvas, t: float, scroll: float) -> None:
        w, sky = self.w, self.sky_h
        for f in self.fireflies:
            x = int((f.x * w + math.sin(t * f.speed + f.phase) * f.amp * 4) % w)
            y = int(sky * f.y + math.sin(t * f.speed * 1.7 + f.phase * 2) * 2)
            if not (0 <= y < sky):
                continue
            pulse = 0.5 + 0.5 * math.sin(t * 2.2 + f.phase)
            color = mix_rgb(C_GRASS_LIGHT, 0xFFF48A, pulse * 0.7)
            if pulse > 0.45:
                canvas.blend(x, y, color, 0.22 * pulse)
                canvas.px(x, y, color)
        # A shooting star, if one is active, is drawn by the view.

    def draw_shooting_stars(self, canvas: Canvas, stars: list[ShootingStar], now: float) -> None:
        w, sky = self.w, self.sky_h
        for s in stars:
            age = now - s.born
            if age < 0 or age > s.life:
                continue
            fade = 1.0 - age / s.life
            x = s.x + s.vx * age
            y = s.y + s.vy * age
            for i in range(7):
                px = int(x - s.vx * i * 0.012)
                py = int(y - s.vy * i * 0.012)
                if 0 <= px < w and 0 <= py < sky and i <= age * 30 + 2:
                    a = fade * (1.0 - i / 7)
                    base = self.sky[py * w + px]
                    canvas.px(px, py, mix_rgb(base, C_STAR, 0.25 + a * 0.75))


# --------------------------------------------------------------------------
# the game world
# --------------------------------------------------------------------------

FLAP_KEYS = {" ", "w", "up", "enter"}


class World:
    """All gameplay.  No terminal I/O happens here, which keeps it testable."""

    def __init__(
        self,
        cols: int,
        rows: int,
        seed: int = 7,
        record: Optional[dict] = None,
        persist: bool = True,
        path: Optional[Path] = None,
        autopilot: bool = False,
        demo: bool = False,
    ) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.persist = persist
        self.path = path or scores_path()
        self.record = dict(record or {"best": 0, "games": 0})
        self.autopilot = autopilot or demo
        self.demo = demo
        self.cols = 0
        self.rows = 0
        self.W = 0
        self.H = 0
        self.ground_h = 0
        self.sky_h = 0
        self.scenery = None
        self.state = "START"
        self.state_time = 0.0
        self.bg_time = 0.0
        self.ui_time = 0.0
        self.scroll = 0.0
        self.score = 0
        self.best_at_start = int(self.record.get("best", 0))
        self.new_best = False
        self.pipes: list[Pipe] = []
        self.particles: list[Particle] = []
        self.meteors: list[ShootingStar] = []
        self.next_meteor = 5.0
        self.score_flash = 0.0
        self.flash = 0.0
        self.shake = 0.0
        self.flap_cd = 0.0
        self.pipe_timer = 0.0
        self.bird: Bird = Bird(0, 0, BIRD_W, BIRD_H)
        self.configure(cols, rows, initial=True)

    # -- geometry ----------------------------------------------------------
    def configure(self, cols: int, rows: int, initial: bool = False) -> None:
        cols = int(clamp(cols, 1, 320))
        rows = int(clamp(rows, 1, 110))
        if not initial and cols == self.cols and rows == self.rows:
            return
        old_W, old_sky = self.W, self.sky_h
        self.cols, self.rows = cols, rows
        self.W, self.H = cols, rows * 2
        self.ground_h = max(5, min(14, round(self.H * 0.095)))
        self.sky_h = max(8, self.H - self.ground_h)
        sky = self.sky_h
        self.bs = 1 if sky < 100 else 2
        self.bird_w = BIRD_W * self.bs
        self.bird_h = BIRD_H * self.bs
        self.bird_x = int(clamp(self.W * 0.21, 6, 48))
        self.pipe_w = max(8, round(sky * 0.185))
        self.cap_h = max(4, round(sky * 0.085))
        self.cap_over = max(2, self.bs * 2)
        self.gap_base = int(clamp(round(sky * 0.52), self.bird_h + 7, sky * 0.62))
        self.gap_min = max(self.bird_h + 5, round(self.gap_base * 0.76))
        self.base_speed = max(14.0, self.W / 3.1)
        self.gravity = sky * 2.6
        self.flap_power = -sky * 1.08
        self.max_fall = sky * 1.4
        if self.scenery is None or not initial:
            if self.scenery is None:
                self.scenery = Scenery(self.W, self.H, sky, self.seed)
            else:
                self.scenery.resize(self.W, self.H, sky)
        if initial:
            self.bird_y_home = sky * 0.45 - self.bird_h / 2
            self.bird = Bird((self.W - self.bird_w) // 2,
                             sky * 0.64 - self.bird_h / 2,
                             self.bird_w, self.bird_h)
        else:
            ratio = sky / max(1, old_sky)
            if old_sky > 0:
                rel_y = (self.bird.y + self.bird.h / 2) / old_sky
                self.bird.w, self.bird.h = self.bird_w, self.bird_h
                self.bird.x = self.bird_x
                self.bird.y = clamp(rel_y * sky - self.bird.h / 2,
                                    -self.bird.h, sky)
                self.bird.vy *= ratio
                for p in self.pipes:
                    p.x = p.x / max(1, old_W) * self.W
                    p.gap_y = clamp(p.gap_y * ratio, 0, sky)
                    p.gap_h = clamp(p.gap_h * ratio, self.gap_min, sky * 0.8)
                for q in self.particles:
                    q.x = q.x / max(1, old_W) * self.W
                    q.y *= ratio
                self.scroll *= ratio
            self.bird_y_home = sky * 0.45 - self.bird.h / 2

    def resize(self, cols: int, rows: int) -> None:
        self.configure(cols, rows)

    def flap_velocity(self) -> float:
        return self.flap_power

    # -- derived gameplay values ------------------------------------------
    def current_speed(self) -> float:
        return self.base_speed * (1.0 + 0.0125 * min(self.score, 55))

    def current_gap(self) -> float:
        shrink = max(0.76, 1.0 - 0.0052 * min(self.score, 55))
        return max(self.gap_min, self.gap_base * shrink)

    def current_interval(self) -> float:
        return max(1.08, 1.55 - 0.0082 * min(self.score, 55))

    def tread_speed(self) -> float:
        return self.current_speed()

    def hitbox(self) -> tuple[float, float, float, float]:
        ix = 4 * self.bs
        iy = 3 * self.bs
        return (self.bird.x + ix, self.bird.y + iy,
                self.bird.w - ix * 2, self.bird.h - iy * 2)

    def gap_top(self, pipe: Pipe) -> float:
        return pipe.gap_y - pipe.gap_h / 2

    def gap_bottom(self, pipe: Pipe) -> float:
        return pipe.gap_y + pipe.gap_h / 2

    def pipe_rects(self, pipe: Pipe) -> list[tuple[float, float, float, float]]:
        x, pw, over, cap = pipe.x, self.pipe_w, self.cap_over, self.cap_h
        gt, gb = self.gap_top(pipe), self.gap_bottom(pipe)
        return [
            (x, 0.0, pw, max(0.0, gt - cap)),
            (x - over, gt - cap, pw + over * 2, cap),
            (x - over, gb, pw + over * 2, cap),
            (x, gb + cap, pw, max(0.0, self.sky_h - (gb + cap))),
        ]

    @staticmethod
    def _overlap(a, b) -> bool:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by

    def bird_collides(self) -> bool:
        hb = self.hitbox()
        if hb[1] <= 0:
            return True
        if hb[1] + hb[3] >= self.sky_h:
            return True
        for pipe in self.pipes:
            if pipe.x - self.cap_over > hb[0] + hb[2] or pipe.x + self.pipe_w < hb[0]:
                continue
            for rect in self.pipe_rects(pipe):
                if self._overlap(hb, rect):
                    return True
        return False

    def next_pipe(self) -> Optional[Pipe]:
        for pipe in self.pipes:
            if pipe.x + self.pipe_w + self.cap_over >= self.bird.x:
                return pipe
        return None

    # -- lifecycle ---------------------------------------------------------
    def start_run(self) -> None:
        self.state = "PLAY"
        self.state_time = 0.0
        self.score = 0
        self.best_at_start = int(self.record.get("best", 0))
        self.new_best = False
        self.pipes.clear()
        self.particles.clear()
        self.meteors.clear()
        self.next_meteor = 5.0
        self.score_flash = 0.0
        self.flash = 0.0
        self.shake = 0.0
        self.flap_cd = 0.0
        self.pipe_timer = 0.35
        self.bird.x = self.bird_x
        self.bird.w, self.bird.h = self.bird_w, self.bird_h
        self.bird.y = self.bird_y_home
        self.bird.vy = 0.0
        self.bird.wing_t = 0.2
        self.flap(force=True)

    def flap(self, force: bool = False) -> None:
        if self.state != "PLAY":
            return
        if not force and self.flap_cd > 0:
            return
        self.bird.vy = self.flap_power
        self.flap_cd = 0.075
        self.bird.wing_t = 0.18
        self.score_flash = max(self.score_flash, 0.0)
        # a couple of tiny feathers drift off the wings
        for _ in range(2):
            self.particles.append(Particle(
                x=self.bird.x + self.bird.w * (0.2 + self.rng.random() * 0.5),
                y=self.bird.y + self.bird.h * (0.4 + self.rng.random() * 0.35),
                vx=-self.current_speed() * (0.15 + self.rng.random() * 0.25),
                vy=-(10 + self.rng.random() * 25),
                life=0.35 + self.rng.random() * 0.25,
                max_life=0.6, color=mix_rgb(0xFFD43B, 0xFFF6B8, self.rng.random()),
                size=1, gravity=self.sky_h * 0.25,
            ))
        self._trim_particles()

    def pause(self) -> None:
        if self.state == "PLAY":
            self.state = "PAUSED"
            self.state_time = 0.0

    def resume(self) -> None:
        if self.state == "PAUSED":
            self.state = "PLAY"

    def die(self, reason: str = "pipe") -> None:
        if self.state != "PLAY":
            return
        self.state = "DYING"
        self.state_time = 0.0
        self.death_reason = reason
        self.best_before_death = self.best_at_start
        if self.score > int(self.record.get("best", 0)):
            self.record["best"] = self.score
        self.new_best = self.score > self.best_at_start and self.score > 0
        self.record["games"] = int(self.record.get("games", 0)) + 1
        if self.persist:
            save_scores(self.record, self.path)
        self.flash = 1.0
        self.shake = 1.0
        self.bird.vy = min(self.bird.vy, -self.sky_h * 0.35)
        self._burst(self.bird.x + self.bird.w / 2, self.bird.y + self.bird.h / 2, 26)

    def _burst(self, cx: float, cy: float, count: int) -> None:
        colors = [0xFFD43B, 0xFFF6B8, 0xFF7A1A, 0xFFB154, C_STAR]
        for i in range(count):
            ang = self.rng.random() * math.tau
            spd = 15 + self.rng.random() * (self.sky_h * 1.4)
            self.particles.append(Particle(
                x=cx + (self.rng.random() - 0.5) * self.bird.w * 0.5,
                y=cy + (self.rng.random() - 0.5) * self.bird.h * 0.5,
                vx=math.cos(ang) * spd,
                vy=math.sin(ang) * spd - self.sky_h * 0.25,
                life=0.5 + self.rng.random() * 0.55,
                max_life=1.0,
                color=self.rng.choice(colors),
                size=1 if self.rng.random() < 0.7 else 2,
                gravity=self.sky_h * 1.1,
                drag=0.35,
            ))
        self._trim_particles()

    def _trim_particles(self) -> None:
        if len(self.particles) > 320:
            del self.particles[:len(self.particles) - 320]

    def finalize(self) -> None:
        """Best-effort save on quit, without counting an unfinished game."""
        if not self.persist:
            return
        changed = False
        if self.score > int(self.record.get("best", 0)):
            self.record["best"] = self.score
            changed = True
        if changed:
            save_scores(self.record, self.path)

    @property
    def best(self) -> int:
        return max(int(self.record.get("best", 0)), self.score if self.state == "PLAY" else 0)

    # -- key handling ------------------------------------------------------
    def press(self, key: str) -> Optional[str]:
        key = key.lower()
        if key in ("q", "ctrl-c", "esc"):
            return "quit"
        if key == "r":
            self.start_run()
            return None
        if self.state == "START":
            if key in FLAP_KEYS:
                self.start_run()
        elif self.state == "PLAY":
            if key in FLAP_KEYS:
                self.flap()
            elif key == "p":
                self.pause()
        elif self.state == "PAUSED":
            if key in FLAP_KEYS or key == "p":
                self.resume()
        elif self.state == "GAMEOVER":
            if key in FLAP_KEYS:
                self.start_run()
        return None

    # -- simulation --------------------------------------------------------
    def update(self, dt: float) -> None:
        if self.state == "PAUSED":
            self.ui_time += dt
            return
        self.ui_time += dt
        self.bg_time += dt
        self.flash = max(0.0, self.flash - dt * 5.5)
        self.shake = max(0.0, self.shake - dt * 2.4)
        self.score_flash = max(0.0, self.score_flash - dt * 2.2)
        self._update_meteors(dt)
        alive: list[Particle] = []
        for p in self.particles:
            if p.update(dt):
                alive.append(p)
        self.particles = alive

        if self.state == "START":
            self.state_time += dt
            self.scroll += dt * 8.5
            if self.scenery is not None:
                self.bird.x = (self.W - self.bird.w) // 2
                self.bird.y = (self.sky_h * 0.64 - self.bird.h / 2
                               + math.sin(self.bg_time * 2.3) * 3.0 * self.bs)
                self.bird.vy = 0.0
            if self.demo and self.state_time > 1.1:
                self.start_run()
        elif self.state == "PLAY":
            self.state_time += dt
            self._update_play(dt)
        elif self.state in ("DYING", "GAMEOVER"):
            self.state_time += dt
            self._update_death(dt)
            if self.state == "DYING" and self.state_time > 1.0:
                self.state = "GAMEOVER"
                self.state_time = 0.0
            elif self.state == "GAMEOVER" and self.demo and self.state_time > 2.2:
                self.start_run()

    def _update_meteors(self, dt: float) -> None:
        self.next_meteor -= dt
        if self.next_meteor <= 0 and self.scenery is not None:
            self.next_meteor = 8.0 + self.rng.random() * 10.0
            if self.state in ("START", "PLAY", "GAMEOVER"):
                sx = self.W * (0.25 + self.rng.random() * 0.65)
                sy = self.sky_h * (0.05 + self.rng.random() * 0.3)
                spd = self.W * (0.5 + self.rng.random() * 0.6)
                self.meteors.append(ShootingStar(
                    x=sx, y=sy, vx=-spd, vy=spd * 0.32,
                    born=self.bg_time, life=0.45 + self.rng.random() * 0.4,
                ))
        self.meteors = [s for s in self.meteors if self.bg_time - s.born <= s.life]

    def _auto_flap(self) -> None:
        if self.flap_cd > 0:
            return
        target_pipe = self.next_pipe()
        if target_pipe is not None:
            target = target_pipe.gap_y
            # Aim a hair below the gap center: gravity will carry us through.
            target += target_pipe.gap_h * 0.24
        else:
            target = self.sky_h * 0.45
        cy = self.bird.y + self.bird.h / 2
        vy = self.bird.vy
        # A tiny lead term smooths out the bang-bang hover.
        projected = cy + max(0.0, vy) * 0.05
        if projected >= target and vy > -self.sky_h * 0.12:
            self.flap()
        elif cy > self.sky_h * 0.80:
            self.flap()

    def _update_play(self, dt: float) -> None:
        self.flap_cd = max(0.0, self.flap_cd - dt)
        self.bird.wing_t = max(0.0, self.bird.wing_t - dt)
        if self.autopilot:
            self._auto_flap()
        self.bird.vy = min(self.bird.vy + self.gravity * dt, self.max_fall)
        self.bird.y += self.bird.vy * dt
        speed = self.current_speed()
        self.scroll += speed * dt
        self.pipe_timer -= dt
        if self.pipe_timer <= 0:
            self._spawn_pipe()
            self.pipe_timer = self.current_interval()
        for pipe in self.pipes:
            pipe.x -= speed * dt
            if not pipe.scored and pipe.x + self.pipe_w * 0.5 < self.bird.x + self.bird.w / 2:
                pipe.scored = True
                self.score += 1
                self.score_flash = 1.0
                self._score_sparks(pipe)
        self.pipes = [p for p in self.pipes if p.x + self.pipe_w + self.cap_over > -4]
        if self.bird_collides():
            if self.hitbox()[1] <= 0:
                self.die("ceiling")
            elif self.hitbox()[1] + self.hitbox()[3] >= self.sky_h:
                self.die("ground")
            else:
                self.die("pipe")

    def _score_sparks(self, pipe: Pipe) -> None:
        cx = pipe.x + self.pipe_w / 2
        cy = self.gap_top(pipe) + 2
        for _ in range(7):
            self.particles.append(Particle(
                x=cx + (self.rng.random() - 0.5) * self.pipe_w,
                y=cy + self.rng.random() * 4,
                vx=-20 + self.rng.random() * 40,
                vy=-10 - self.rng.random() * 40,
                life=0.25 + self.rng.random() * 0.25,
                max_life=0.5,
                color=self.rng.choice([C_GOLD, C_GOLD_HI, C_CREAM]),
                size=1, gravity=self.sky_h * 0.35,
            ))

    def _update_death(self, dt: float) -> None:
        self.bird.wing_t = max(0.0, self.bird.wing_t - dt)
        self.bird.vy = min(self.bird.vy + self.gravity * dt, self.max_fall)
        self.bird.y += self.bird.vy * dt
        floor = self.sky_h - self.bird.h
        if self.bird.y >= floor:
            if self.bird.vy > 40:
                for _ in range(6):
                    self.particles.append(Particle(
                        x=self.bird.x + self.rng.random() * self.bird.w,
                        y=self.sky_h - 1,
                        vx=-15 + self.rng.random() * 30,
                        vy=-10 - self.rng.random() * 30,
                        life=0.25 + self.rng.random() * 0.3,
                        max_life=0.5, color=C_DIRT_LIGHT,
                        size=1, gravity=self.sky_h * 1.3,
                    ))
            self.bird.y = floor
            self.bird.vy = 0

    def _spawn_pipe(self) -> None:
        gap = self.current_gap()
        cy = self.sky_h * 0.5
        min_c = self.cap_h + gap / 2 + 3
        max_c = self.sky_h - self.cap_h - gap / 2 - 5
        if max_c <= min_c:
            center = cy
        else:
            prev = self.pipes[-1].gap_y if self.pipes else self.bird.y + self.bird.h / 2
            span = self.sky_h * 0.26
            lo = max(min_c, prev - span)
            hi = min(max_c, prev + span)
            if hi <= lo:
                lo, hi = min_c, max_c
            center = self.rng.uniform(lo, hi)
        self.pipes.append(Pipe(
            x=self.W + self.cap_over + 2,
            gap_y=center, gap_h=gap,
            variant=self.rng.randrange(3),
        ))
        self._trim_particles()

    # -- drawing helpers ---------------------------------------------------
    def bird_art(self) -> tuple[str, ...]:
        if self.state in ("DYING", "GAMEOVER"):
            return BIRD_DOWN
        if self.bird.wing_t > 0.0:
            return BIRD_UP
        if self.bird.vy < -self.sky_h * 0.18:
            return BIRD_UP
        if self.bird.vy > self.sky_h * 0.52:
            return BIRD_DOWN
        return BIRD_MID

    def wing_phase(self) -> int:
        if self.state == "START":
            return int(self.bg_time * 7.0) % 3
        return 0

    def feather_count(self) -> int:
        return len(self.particles)


# --------------------------------------------------------------------------
# view: everything that turns the world into coloured pixels and text
# --------------------------------------------------------------------------


class GameView:
    def __init__(self, world: World) -> None:
        self.world = world
        self.canvas = Canvas(world.W, world.H)
        self.debug_text = ""

    # -- low level scenery pieces -----------------------------------------
    @staticmethod
    def _pipe_body(canvas: Canvas, x: int, y: int, w: int, h: int,
                   top_pipe: bool) -> None:
        if h <= 0:
            return
        canvas.rect(x, y, w, h, C_PIPE_OUT)
        if w >= 4:
            canvas.rect(x + 1, y, w - 2, h, C_PIPE_BODY)
            canvas.vline(x + 1, y, h, C_PIPE_LIGHT)
            if w >= 6:
                canvas.vline(x + 2, y, h, C_PIPE_SHINE)
            canvas.vline(x + w - 2, y, h, C_PIPE_SHADOW)
        # little dark rims at the far ends of the body
        if top_pipe:
            canvas.vline(x, y, h, C_PIPE_OUT)
        else:
            canvas.vline(x, y + h - 1, h, C_PIPE_OUT)

    @staticmethod
    def _pipe_cap(canvas: Canvas, x: int, y: int, w: int, h: int,
                  top_pipe: bool) -> None:
        if w <= 2 or h <= 2:
            canvas.rect(x, y, w, h, C_PIPE_OUT)
            return
        # A 1px outline with clipped corners; no bright knobs.
        canvas.rect(x + 1, y, w - 2, h, C_PIPE_OUT)
        canvas.rect(x, y + 1, w, h - 2, C_PIPE_OUT)
        canvas.rect(x + 2, y + 1, w - 4, h - 2, C_PIPE_BODY)
        canvas.rect(x + 1, y + 2, w - 2, h - 4, C_PIPE_BODY)
        # vertical lighting on the cap face
        canvas.vline(x + 1, y + 2, h - 4, C_PIPE_LIGHT)
        if w >= 9:
            canvas.vline(x + 2, y + 2, h - 4, C_PIPE_SHINE)
        canvas.vline(x + w - 2, y + 2, h - 4, C_PIPE_SHADOW)
        if top_pipe:
            canvas.hline(x + 2, y + 1, w - 4, C_PIPE_CAP_HI)
            canvas.hline(x + 2, y + h - 3, w - 4, mix_rgb(C_PIPE_BODY, C_PIPE_OUT, 0.52))
            canvas.hline(x + 2, y + h - 2, w - 4, C_PIPE_DARK)
            canvas.hline(x + 1, y + h - 1, w - 2, C_PIPE_OUT)
        else:
            canvas.hline(x + 1, y, w - 2, C_PIPE_OUT)
            canvas.hline(x + 2, y + 1, w - 4, C_PIPE_DARK)
            canvas.hline(x + 2, y + 2, w - 4, C_PIPE_CAP_HI)
            canvas.hline(x + 2, y + h - 2, w - 4, C_PIPE_SHADOW)
        # rivets on the wide cap faces
        if w >= 10 and h >= 5:
            ry = y + h // 2
            for bx, bolt in ((x + 3, C_PIPE_CAP_HI), (x + w - 4, C_PIPE_DARK)):
                canvas.px(bx, ry, C_PIPE_OUT)
                canvas.px(bx, ry - 1, bolt)

    def draw_pipe(self, canvas: Canvas, pipe: Pipe) -> None:
        w = self.world
        x = int(round(pipe.x))
        pw, over, cap = w.pipe_w, w.cap_over, w.cap_h
        gt = int(round(w.gap_top(pipe)))
        gb = int(round(w.gap_bottom(pipe)))
        # top pipe: body hangs from the ceiling, cap at the gap
        top_body_h = max(0, gt - cap)
        if top_body_h > 0:
            self._pipe_body(canvas, x, 0, pw, top_body_h, True)
        else:
            top_body_h = 0
        self._pipe_cap(canvas, x - over, gt - cap, pw + over * 2, cap, True)
        # bottom pipe: cap first, body down to the ground
        self._pipe_cap(canvas, x - over, gb, pw + over * 2, cap, False)
        bottom_body_h = max(0, w.sky_h - (gb + cap))
        if bottom_body_h > 0:
            self._pipe_body(canvas, x, gb + cap, pw, bottom_body_h, False)

    def draw_ground(self, canvas: Canvas) -> None:
        w = self.world
        gy, gh, W = w.sky_h, w.ground_h, w.W
        canvas.rect(0, gy, W, gh, C_DIRT)
        grass_h = max(2, round(gh * 0.42))
        canvas.rect(0, gy, W, grass_h, C_GRASS)
        canvas.hline(0, gy, W, C_GRASS_DARK)
        canvas.hline(0, gy + 1, W, C_GRASS_LIGHT)
        if gh > 2:
            canvas.hline(0, gy + grass_h, W, C_DIRT_DARK)
        # dirt strata
        if gh > 4:
            canvas.hline(0, gy + grass_h + 2, W, mix_rgb(C_DIRT, C_DIRT_DARK, 0.45))
        if gh > 6:
            canvas.hline(0, gy + gh - 2, W, mix_rgb(C_DIRT, C_DIRT_LIGHT, 0.3))
        off = int(w.scroll)
        last = w.H - 1
        for x in range(W):
            wx = x + off
            # grass blades reaching up into the sky
            if hash01(wx // 5 + 3) > 0.62:
                bh = 1 + (1 if hash01(wx * 3 + 1) > 0.50 else 0)
                if hash01(wx * 7 + 2) > 0.84:
                    bh += 1
                canvas.vline(x, gy - bh, bh, C_GRASS_GLOW if bh > 1 else C_GRASS_LIGHT)
            # pebbles and dark specks in the dirt
            ph = hash01(wx * 5 + 11)
            if ph > 0.86:
                py = gy + grass_h + 1 + int(hash01(wx * 7 + 1) * max(1, gh - grass_h - 2))
                canvas.px(x, min(last, py), C_DIRT_PEBBLE)
            elif ph < 0.05:
                py = gy + grass_h + 1 + int(hash01(wx * 9 + 4) * max(1, gh - grass_h - 1))
                canvas.px(x, min(last, py), C_DIRT_DARK)
            # long scrolling stripes make the speed visible
            if gh > 3 and (wx + 9) % 31 < 5:
                canvas.px(x, gy + gh - 2, C_DIRT_DARK)
                if (wx + 9) % 31 < 2:
                    canvas.px(x, gy + gh - 1, mix_rgb(C_DIRT, C_DIRT_DARK, 0.5))
        # a bright lip exactly where the sky meets the earth
        canvas.hline(0, gy - 1, W, mix_rgb(C_GRASS_DARK, C_GRASS_LIGHT, 0.35))

    def draw_bird(self, canvas: Canvas) -> None:
        w = self.world
        art = w.bird_art()
        x = int(round(w.bird.x))
        y = int(round(w.bird.y))
        if w.state == "START":
            phase = w.wing_phase()
            art = (BIRD_UP, BIRD_MID, BIRD_DOWN)[phase]
        canvas.sprite(art, x, y, BIRD_PALETTE, w.bs)

    def draw_particles(self, canvas: Canvas) -> None:
        w = self.world
        for p in w.particles:
            alpha = clamp(p.life / max(0.001, p.max_life) * 2.4, 0.0, 0.9)
            if p.y < -4 or p.y > w.sky_h + 2:
                continue
            if p.size <= 1:
                canvas.blend(int(p.x), int(p.y), p.color, alpha)
            else:
                canvas.blend_rect(int(p.x), int(p.y), p.size, p.size, p.color, alpha)

    @staticmethod
    def draw_panel(canvas: Canvas, x: int, y: int, w: int, h: int, accent: int) -> None:
        # floating shadow
        canvas.blend_rect(x + 3, y + 4, w, h, C_PANEL_SHADOW, 0.55)
        # gold/cyan rim, then a dark inset body
        canvas.round_rect(x, y, w, h, 6, accent)
        canvas.round_rect(x + 1, y + 1, w - 2, h - 2, 5, C_PANEL)
        # inner hairline and top light
        canvas.hline(x + 7, y + 1, w - 14, mix_rgb(accent, C_WHITE, 0.35))
        canvas.hline(x + 7, y + h - 2, w - 14, mix_rgb(C_PANEL, C_PANEL_SHADOW, 0.6))
        # corner rivets
        for rx, ry in ((x + 4, y + 4), (x + w - 6, y + 4),
                       (x + 4, y + h - 6), (x + w - 6, y + h - 6)):
            canvas.px(rx, ry, mix_rgb(accent, C_PANEL, 0.25))

    def draw_score_hud(self, canvas: Canvas) -> None:
        w = self.world
        if w.state in ("PAUSED", "GAMEOVER"):
            return
        scale = 1 if w.W < 120 or w.sky_h < 64 else 2
        y = 3 if scale == 1 else 2
        bright = w.score_flash > 0.25
        if bright:
            grad = [C_CREAM, C_CREAM, C_GOLD_HI, C_GOLD_HI, C_GOLD, C_GOLD_HI, C_CREAM]
        else:
            grad = [C_CREAM, C_GOLD_HI, C_GOLD_HI, C_GOLD, C_GOLD, 0xF0A92E, 0xDE8C22]
        canvas.pixel_text(
            str(w.score), w.W // 2, y, C_GOLD,
            scale=scale, spacing=1, align="center",
            outline=C_INK, shadow=C_PANEL_SHADOW,
            gradient=grad,
        )

    # -- title / pause / game over ----------------------------------------
    def draw_start(self, canvas: Canvas, texts: list[TextLine]) -> None:
        w = self.world
        W, rows, sky = w.W, w.rows, w.sky_h
        compact = rows < 20 or W < 78
        grad = [C_CREAM, C_CREAM, C_GOLD_HI, C_GOLD_HI, C_GOLD, C_GOLD, 0xE0A02A]
        if compact:
            if W >= 50:
                for i, line in enumerate(("T E R M I N A L", "B I R D")):
                    texts.append(TextLine(
                        2 + i, max(0, (W - len(line)) // 2), line,
                        C_CYAN if i == 0 else C_GOLD, bold=True))
            else:
                line = "TERMINAL BIRD"
                texts.append(TextLine(2, max(0, (W - len(line)) // 2), line,
                                      C_GOLD, bold=True))
        else:
            if W >= 56:
                sub = "A  T E R M I N A L  A R C A D E"
                texts.append(TextLine(0, max(0, (W - len(sub)) // 2), sub, C_CYAN))
            if W >= 200 and sky >= 64:
                line, scale, spacing = "FLAPPY BIRD", 3, 1
                ty = max(8, int(sky * 0.08))
                canvas.pixel_text(line, W // 2, ty, C_GOLD, scale=scale,
                                  spacing=spacing, align="center",
                                  outline=C_INK, shadow=C_PANEL_SHADOW,
                                  gradient=grad)
            elif W >= 136:
                line, scale, spacing = "FLAPPY BIRD", 2, 1
                ty = max(6, int(sky * 0.10))
                canvas.pixel_text(line, W // 2, ty, C_GOLD, scale=scale,
                                  spacing=spacing, align="center",
                                  outline=C_INK, shadow=C_PANEL_SHADOW,
                                  gradient=grad)
            else:
                ty = max(4, int(sky * 0.075))
                canvas.pixel_text("FLAPPY", W // 2, ty, C_GOLD, scale=1,
                                  spacing=2, align="center", outline=C_INK,
                                  shadow=C_PANEL_SHADOW, gradient=grad)
                canvas.pixel_text("BIRD", W // 2, ty + 10, C_GOLD, scale=1,
                                  spacing=2, align="center", outline=C_INK,
                                  shadow=C_PANEL_SHADOW, gradient=grad)
        # prompt above the grass
        prompt_row = max(2, rows - 4)
        blink = int(w.ui_time * 2.2) % 2 == 0
        prompt = "PRESS SPACE TO FLY"
        if W < len(prompt) + 4:
            prompt = "SPACE TO FLY"
        strip_w = min(W, len(prompt) + 8)
        strip_x = (W - strip_w) // 2
        canvas.rect(strip_x, prompt_row * 2, strip_w, 2, C_PANEL)
        canvas.hline(strip_x, prompt_row * 2, strip_w,
                     mix_rgb(C_GOLD, C_PANEL, 0.62))
        texts.append(TextLine(
            prompt_row, max(0, (W - len(prompt)) // 2), prompt,
            C_GOLD_HI if blink else C_GOLD, bold=True, bg=C_PANEL))
        # footer arcade bar
        if rows >= 14:
            by = (rows - 1) * 2
            canvas.rect(0, by, W, 2, C_PANEL)
            canvas.hline(0, by, W, mix_rgb(C_GOLD, C_PANEL, 0.55))
            if W >= 62:
                foot = "SPACE  FLAP    P  PAUSE    R  RESTART    Q  QUIT"
            elif W >= 44:
                foot = "SPACE  FLAP    P  PAUSE    Q  QUIT"
            else:
                foot = "SPACE  FLAP    Q  QUIT"
            texts.append(TextLine(rows - 1, max(0, (W - len(foot)) // 2),
                                  foot, C_DIM))

    def draw_pause(self, canvas: Canvas, texts: list[TextLine]) -> None:
        w = self.world
        W, rows = w.W, w.rows
        canvas.dim(0.48)
        pw = min(W - 6, 42)
        ph = min(rows - 4, 9)
        sy = max(0, (rows - ph) // 2)
        x = (W - pw) // 2
        self.draw_panel(canvas, x, sy * 2, pw, ph * 2, C_CYAN)
        title = "P A U S E D"
        texts.append(TextLine(sy + 2, max(0, (W - len(title)) // 2), title,
                              C_CYAN, bold=True))
        score = f"SCORE  {w.score}"
        texts.append(TextLine(sy + 4, max(0, (W - len(score)) // 2), score,
                              C_CREAM))
        resume = "P / SPACE   RESUME" if W >= 46 else "P/SPACE RESUME"
        texts.append(TextLine(sy + 6, max(0, (W - len(resume)) // 2), resume,
                              C_WHITE, bold=True))
        sub = "R  RESTART      Q  QUIT" if W >= 46 else "R RESTART   Q QUIT"
        texts.append(TextLine(sy + 7, max(0, (W - len(sub)) // 2), sub, C_DIM))

    def draw_gameover(self, canvas: Canvas, texts: list[TextLine]) -> None:
        w = self.world
        W, rows = w.W, w.rows
        canvas.dim(0.42)
        score_scale = 2 if (rows >= 20 and W >= 56) else 1
        score_rows = (7 * score_scale + 1) // 2
        ph = min(rows - 2, score_rows + 9)
        ph = max(11, ph)
        sy = max(0, (rows - ph) // 2)
        pw = min(W - 4, 52)
        x = (W - pw) // 2
        self.draw_panel(canvas, x, sy * 2, pw, ph * 2, C_GOLD)
        title = "G A M E   O V E R"
        texts.append(TextLine(sy + 2, max(0, (W - len(title)) // 2), title,
                              C_GOLD, bold=True))
        # score counts up with a little arcade flourish
        t = clamp((w.state_time - 0.04) / 0.55, 0.0, 1.0)
        shown = int(round(w.score * ease_out_cubic(t)))
        sy_px = (sy + 3) * 2
        grad = [C_CREAM, C_CREAM, C_GOLD_HI, C_GOLD_HI, C_GOLD, C_GOLD, 0xE0A02A]
        canvas.pixel_text(
            str(shown), W // 2, sy_px, C_GOLD,
            scale=score_scale, spacing=1, align="center",
            outline=C_INK, gradient=grad,
        )
        best_row = sy + 3 + score_rows + 1
        prompt_row = best_row + 2
        sub_row = prompt_row + 1
        if w.new_best:
            best = "N E W   B E S T !" if W >= 52 else "NEW BEST!"
            texts.append(TextLine(best_row, max(0, (W - len(best)) // 2), best,
                                  C_GOLD_HI, bold=True))
            for i, (dx, dy) in enumerate(((6, 7), (pw - 8, 11), (9, ph * 2 - 9),
                                          (pw - 7, ph * 2 - 12))):
                pulse = 0.55 + 0.45 * math.sin(w.ui_time * 4.2 + i * 1.7)
                sx = x + dx
                syy = sy * 2 + dy
                c = mix_rgb(C_GOLD, C_WHITE, pulse)
                canvas.px(sx, syy, c)
                canvas.px(sx - 1, syy, mix_rgb(C_GOLD, C_PANEL, 0.3))
                canvas.px(sx + 1, syy, mix_rgb(C_GOLD, C_PANEL, 0.3))
                canvas.px(sx, syy - 1, mix_rgb(C_GOLD, C_PANEL, 0.3))
                canvas.px(sx, syy + 1, mix_rgb(C_GOLD, C_PANEL, 0.3))
        else:
            best = f"BEST  {w.record.get('best', 0)}"
            texts.append(TextLine(best_row, max(0, (W - len(best)) // 2), best,
                                  C_DIM))
        prompt = "SPACE  FLY AGAIN"
        if W < len(prompt) + 4:
            prompt = "SPACE AGAIN"
        texts.append(TextLine(prompt_row, max(0, (W - len(prompt)) // 2), prompt,
                              C_WHITE, bold=True))
        sub = "R  RESTART      Q  QUIT"
        if W < len(sub) + 4:
            sub = "R RESTART  Q QUIT"
        texts.append(TextLine(sub_row, max(0, (W - len(sub)) // 2), sub, C_DIM))

    # -- full frame --------------------------------------------------------
    def build_hud(self, texts: list[TextLine]) -> None:
        w = self.world
        W = w.W
        live = w.state != "START"
        best = f"BEST {w.best}"
        if live:
            best = f" {best} "
        texts.append(TextLine(0, 1 if live else 2, best, C_GOLD, bold=True,
                              bg=C_PANEL if live else None))
        if w.state == "START":
            if w.demo:
                texts.append(TextLine(0, max(0, W - 6), "DEMO", C_GOLD, bold=True))
            elif W >= 80:
                texts.append(TextLine(0, max(0, W - 7), f"V{VERSION}", C_DIM))
        else:
            if w.demo:
                right = "DEMO"
            elif W >= 74:
                right = "P PAUSE   R RESTART   Q QUIT"
            elif W >= 54:
                right = "P PAUSE   Q QUIT"
            else:
                right = "P   Q"
            if live:
                right = f" {right} "
            texts.append(TextLine(0, max(0, W - len(right) - (1 if live else 2)),
                                  right, C_GOLD if w.demo else C_DIM,
                                  bg=C_PANEL if live else None))

    def render(self, renderer: Renderer) -> None:
        w = self.world
        if self.canvas.w != w.W or self.canvas.h != w.H:
            self.canvas = Canvas(w.W, w.H)
        cv = self.canvas
        assert w.scenery is not None
        w.scenery.draw(cv, w.bg_time, w.scroll)
        w.scenery.draw_shooting_stars(cv, w.meteors, w.bg_time)
        for pipe in w.pipes:
            self.draw_pipe(cv, pipe)
        self.draw_bird(cv)
        self.draw_ground(cv)
        self.draw_particles(cv)
        texts: list[TextLine] = []
        if w.state == "START":
            self.draw_start(cv, texts)
        elif w.state in ("PLAY", "DYING"):
            self.draw_score_hud(cv)
        elif w.state == "PAUSED":
            self.draw_pause(cv, texts)
        elif w.state == "GAMEOVER":
            self.draw_gameover(cv, texts)
        if w.flash > 0.0:
            cv.blend_rect(0, 0, w.W, w.H, C_WHITE, min(0.42, w.flash * 0.42))
        if w.shake > 0.01:
            amp = 1.0 + 4.0 * w.shake
            dx = int(round(math.sin(w.ui_time * 73.0) * amp))
            dy = int(round(math.cos(w.ui_time * 61.0) * amp * 0.7))
            cv.shift(dx, dy)
        self.build_hud(texts)
        if self.debug_text:
            row = w.rows - 1
            cv.rect(0, row * 2, w.W, 2, C_PANEL)
            texts.append(TextLine(row, 1, self.debug_text[:max(0, w.W - 2)], C_CYAN))
        renderer.render(cv, texts)


# --------------------------------------------------------------------------
# command line / main loop
# --------------------------------------------------------------------------


def terminal_size() -> tuple[int, int]:
    try:
        sz = os.get_terminal_size(sys.stdout.fileno())
        return max(1, sz.columns), max(1, sz.lines)
    except OSError:
        sz = shutil.get_terminal_size((80, 24))
        return max(1, sz.columns), max(1, sz.lines)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="flappy.py",
        description="Terminal Bird -- a full arcade game drawn entirely "
                    "in ANSI colour and Unicode half blocks.",
        epilog="Controls: SPACE/W/UP flap, P pause, R restart, Q/ESC quit.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--color", choices=("auto", "truecolor", "256", "16"),
                   default="auto", help="colour depth (default: auto-detect)")
    p.add_argument("--fps", type=int, default=60,
                   help="render frame cap, 20-120 (default: 60)")
    p.add_argument("--seed", type=int, default=None,
                   help="fixed seed for reproducible pipes")
    p.add_argument("--autopilot", action="store_true",
                   help="let the bird fly itself (press SPACE to start)")
    p.add_argument("--demo", action="store_true",
                   help="autoplay and auto-restart; handy for recording")
    p.add_argument("--no-save", action="store_true",
                   help="do not write the high score file")
    p.add_argument("--reset-best", "--reset-score", dest="reset_score",
                   action="store_true",
                   help="erase the saved high score and exit")
    p.add_argument("--debug", action="store_true",
                   help=argparse.SUPPRESS)
    p.add_argument("--version", action="version",
                   version=f"Terminal Bird {VERSION}")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)

    if args.reset_score:
        path = scores_path()
        try:
            if path.exists():
                path.unlink()
            print(f"High score reset ({path})")
            return 0
        except OSError as exc:
            print(f"Could not reset {path}: {exc}", file=sys.stderr)
            return 1

    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print(
            "Terminal Bird is a terminal game: run it in a real terminal,\n"
            "not through a pipe or a graphical launcher.\n\n"
            "    python3 flappy.py\n",
            file=sys.stderr,
        )
        return 2

    fps = int(clamp(args.fps, 20, 120))
    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(1, 2**31)
    record = load_scores()
    persist = not args.no_save and not args.demo
    world = World(
        *terminal_size(), seed=seed, record=record, persist=persist,
        autopilot=args.autopilot, demo=args.demo,
    )
    view = GameView(world)
    session = TerminalSession(sys.stdin.fileno(), sys.stdout.fileno())
    renderer = Renderer(sys.stdout.fileno(), args.color)
    stop = {"requested": False}

    def request_stop(signum, frame) -> None:
        stop["requested"] = True

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        try:
            signal.signal(sig, request_stop)
        except (ValueError, OSError):
            pass

    atexit.register(renderer.leave)
    atexit.register(session.restore)
    running = True
    exit_code = 0
    last = time.monotonic()
    acc = 0.0
    small = False
    frame_target = 1.0 / fps
    step = 1.0 / 120.0
    fps_timer = 0.0
    fps_frames = 0
    drawn_ms = 0.0

    try:
        session.enter()
        renderer.enter()
        cols, rows = terminal_size()
        renderer.resize(cols, rows)
        while running and not stop["requested"]:
            cols, rows = terminal_size()
            if cols < MIN_COLS or rows < MIN_ROWS:
                if not small:
                    renderer.render_too_small(cols, rows)
                    small = True
                for key in session.read_keys(0.02):
                    if key in ("q", "ctrl-c"):
                        running = False
                if stop["requested"]:
                    break
                continue
            if small:
                small = False
                renderer.resize(cols, rows)
                renderer._write("\x1b[2J")
                last = time.monotonic()
                acc = 0.0
            if cols != world.cols or rows != world.rows:
                world.resize(cols, rows)
                view.canvas = Canvas(world.W, world.H)
                last = time.monotonic()
                acc = 0.0
            frame_start = time.monotonic()
            for key in session.read_keys():
                if world.press(key) == "quit":
                    running = False
                    break
            if not running or stop["requested"]:
                break
            now = time.monotonic()
            dt = min(0.1, max(0.0, now - last))
            last = now
            acc += dt
            substeps = 0
            while acc >= step and substeps < 14:
                world.update(step)
                acc -= step
                substeps += 1
            if substeps >= 14:
                acc = 0.0
            view.render(renderer)
            draw_ms = (time.monotonic() - frame_start) * 1000.0
            if args.debug:
                fps_frames += 1
                fps_timer += time.monotonic() - now
                drawn_ms += (draw_ms - drawn_ms) * 0.1
                if fps_timer >= 0.35:
                    measured = fps_frames / max(0.001, fps_timer)
                    view.debug_text = (
                        f"{measured:5.1f} FPS  {drawn_ms:4.1f} MS  "
                        f"{world.W}x{world.rows}  {world.state}  "
                        f"SCORE {world.score}  PX {world.feather_count()}"
                    )
                    fps_frames = 0
                    fps_timer = 0.0
            spent = time.monotonic() - frame_start
            if spent < frame_target:
                time.sleep(frame_target - spent)
    except KeyboardInterrupt:
        pass
    except Exception:
        renderer.leave()
        session.restore()
        import traceback
        traceback.print_exc()
        exit_code = 1
    finally:
        try:
            world.finalize()
        except Exception:
            pass
        renderer.leave()
        session.restore()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())