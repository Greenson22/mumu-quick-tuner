"""Perhitungan tata letak jendela emulator agar tidak tumpang tindih."""

from __future__ import annotations

import math
from typing import Iterable, Sequence

DEFAULT_ASPECT: tuple[float, float] = (16.0, 9.0)
DEFAULT_MARGIN = 8
DEFAULT_TITLE_BAR = 32

Rect = tuple[int, int, int, int]


def _coerce_aspect(aspect: object) -> tuple[float, float]:
    try:
        width, height = aspect  # type: ignore[misc]
        width = float(width)
        height = float(height)
    except (TypeError, ValueError):
        return DEFAULT_ASPECT
    if width <= 0 or height <= 0:
        return DEFAULT_ASPECT
    return width, height


def plan_window_rects(
    aspects: Sequence[object] | Iterable[object],
    screen: tuple[int, int, int, int],
    margin: int = DEFAULT_MARGIN,
    title_bar: int = DEFAULT_TITLE_BAR,
) -> list[Rect]:
    """Hitung posisi & ukuran jendela dalam grid mulai pojok kiri atas.

    Args:
        aspects: rasio ``(lebar, tinggi)`` resolusi device, satu per jendela.
        screen: ``(x, y, lebar, tinggi)`` area layar yang boleh dipakai.
        margin: jarak antar jendela dan tepi layar dalam piksel.
        title_bar: perkiraan tinggi title bar jendela dalam piksel.

    Returns:
        Daftar ``(x, y, lebar, tinggi)`` berurutan kiri ke kanan lalu baris
        berikutnya. Jendela tidak saling menimpa dan tidak keluar layar.
    """
    items = list(aspects)
    count = len(items)
    if count == 0:
        return []

    screen_x = int(screen[0])
    screen_y = int(screen[1])
    screen_w = max(1, int(screen[2]))
    screen_h = max(1, int(screen[3]))

    margin = max(0, int(margin))
    title_bar = max(0, int(title_bar))

    usable_w = max(1, screen_w - margin * 2)
    usable_h = max(1, screen_h - margin * 2)

    columns = max(1, math.ceil(math.sqrt(count)))
    rows = math.ceil(count / columns)

    cell_w = max(1, (usable_w - margin * (columns - 1)) // columns)
    cell_h = max(1, (usable_h - margin * (rows - 1)) // rows)

    max_w = max(1, cell_w)
    max_h = max(1, cell_h - title_bar)

    rects: list[Rect] = []
    for position, raw_aspect in enumerate(items):
        aspect_w, aspect_h = _coerce_aspect(raw_aspect)
        scale = min(max_w / aspect_w, max_h / aspect_h)
        width = max(1, int(aspect_w * scale))
        height = max(1, int(aspect_h * scale))

        row, column = divmod(position, columns)
        cell_x = screen_x + margin + column * (cell_w + margin)
        cell_y = screen_y + margin + row * (cell_h + margin)

        x = cell_x + (cell_w - width) // 2
        y = cell_y + max(0, (cell_h - title_bar - height) // 2)

        x = max(screen_x, min(screen_x + screen_w - width, x))
        y = max(screen_y, min(screen_y + screen_h - height, y))
        rects.append((x, y, width, height))

    return rects
