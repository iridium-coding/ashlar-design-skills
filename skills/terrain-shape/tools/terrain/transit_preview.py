"""Plain Pillow previews of a transit route: plan map, long profile and cross-sections."""
from __future__ import annotations

import hashlib
import math
from collections.abc import Callable
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .route import Grid, Route
from .site import Site
from .transit_design import LineDesign

KIND_COLOURS = {"grade": (128, 128, 128), "cut": (230, 140, 40), "fill": (140, 90, 50),
                "bridge": (60, 110, 220), "tunnel": (150, 70, 190), "tube": (40, 170, 160)}
_BG = (24, 26, 30)
_EARTH = (96, 72, 48)
_MAX_SIDE = 900


def _colour(kind: str) -> tuple[int, int, int]:
    return KIND_COLOURS.get(kind, (255, 255, 255))


def _factor(img: Image.Image, longest: int = _MAX_SIDE, max_up: int = 8) -> float:
    return min(max_up, longest / max(img.size))


def _fit(img: Image.Image, longest: int = _MAX_SIDE, max_up: int = 8) -> Image.Image:
    factor = _factor(img, longest, max_up)
    size = (max(1, round(img.width * factor)), max(1, round(img.height * factor)))
    return img.resize(size, Image.NEAREST)


def route_map(design: LineDesign, grid: Grid | None, route: Route, path: Path) -> Path:
    """Top view: shaded ground where there is a grid, the route coloured by stretch class.

    The route is drawn after the ground is scaled, each cell at least one pixel, so a line one
    cell wide never drops out of a large grid's shrunken map.
    """
    xs, zs = [c[0] for c in route.cells], [c[1] for c in route.cells]
    if grid is not None:
        nx, nz = grid.ground.shape
        ox, oz = grid.origin
    else:
        ox, oz = min(xs) - 8, min(zs) - 8
        nx, nz = max(xs) - ox + 9, max(zs) - oz + 9
    img = np.zeros((nz, nx, 3), np.uint8)
    img[:] = _BG
    if grid is not None:
        g = grid.ground
        ok = ~np.isnan(g)
        if ok.any():
            lo, hi = float(np.nanmin(g)), float(np.nanmax(g))
            shade = np.where(ok, (np.nan_to_num(g, nan=lo) - lo) / max(hi - lo, 1) * 120 + 50, 0).astype(np.uint8)
            img[:, :, 1] = shade.T
            img[:, :, 0] = shade.T // 2
            img[:, :, 2] = shade.T // 3
        wet = ok & (grid.surface > g)
        img[wet.T] = (40, 70, 140)
    ground = Image.fromarray(img)
    factor = _factor(ground)
    out = _fit(ground)
    draw = ImageDraw.Draw(out)
    for (x, z), kind in zip(route.cells, route.kinds, strict=True):
        i, j = x - ox, z - oz
        if 0 <= i < nx and 0 <= j < nz:
            left, top = math.floor(i * factor), math.floor(j * factor)
            right = min(max(left, math.ceil((i + 1) * factor) - 1), out.width - 1)
            bottom = min(max(top, math.ceil((j + 1) * factor) - 1), out.height - 1)
            draw.rectangle([min(left, out.width - 1), min(top, out.height - 1), right, bottom], fill=_colour(kind))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    out.save(path)
    return Path(path)


def profile_view(route: Route, path: Path) -> Path:
    """Side view along the chainage: ground, water surface and the running level by stretch class."""
    n = len(route.cells)
    heights = [v for v in (*route.ground, *route.surface, *route.levels) if v is not None]
    lo, hi = math.floor(min(heights)) - 4, math.ceil(max(heights)) + 4
    width, height = min(max(n, 200), _MAX_SIDE), 300
    img = Image.new("RGB", (width, height), _BG)
    draw = ImageDraw.Draw(img)

    def px(i: int) -> int:
        return round(i * (width - 1) / max(n - 1, 1))

    def py(y: float) -> int:
        return round((hi - y) * (height - 1) / max(hi - lo, 1))

    for i in range(n):
        if route.ground[i] is not None:
            draw.line([(px(i), py(route.ground[i])), (px(i), height)], fill=_EARTH)
            if route.surface[i] is not None and route.surface[i] > route.ground[i]:
                draw.line([(px(i), py(route.surface[i])), (px(i), py(route.ground[i]))], fill=(40, 70, 140))
    for i, kind in enumerate(route.kinds):
        draw.line([(px(i), py(route.levels[i]) - 1), (px(i), py(route.levels[i]) + 1)], fill=_colour(kind))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return Path(path)


def _picks(route: Route, limit: int) -> list[int]:
    n = len(route.cells)
    picks = [0, *(i for i in range(1, n) if route.kinds[i] != route.kinds[i - 1]), n - 1]
    picks = sorted(set(picks))
    if len(picks) > limit:
        step = (len(picks) - 1) / (limit - 1) if limit > 1 else 0
        picks = sorted({picks[round(k * step)] for k in range(limit)})
    return picks


def _across(route: Route, i: int) -> tuple[int, int]:
    """Unit step across the line at cell `i`: along z where the line runs along x, else along x."""
    a, b = route.cells[max(i - 1, 0)], route.cells[min(i + 1, len(route.cells) - 1)]
    return (0, 1) if abs(b[0] - a[0]) >= abs(b[1] - a[1]) else (1, 0)


def _block_colour(state: str) -> tuple[int, int, int] | None:
    base = state.split("[")[0].removeprefix("minecraft:")
    if base in ("air", "cave_air", "void_air"):
        return None
    if base in ("water", "bubble_column"):
        return (40, 70, 140)
    h = hashlib.sha256(base.encode()).digest()
    return (70 + h[0] % 150, 70 + h[1] % 150, 70 + h[2] % 150)


def cross_sections(route: Route, folder: Path, *, element: str,
                   site_of: Callable[[int], Site] | None = None, limit: int = 12) -> list[Path]:
    """Sections across the line where the stretch class changes (and at both ends).

    Without `site_of` the ground and the running level come from the route's data; with it
    the blocks of the site read for that cell are drawn. The element's earlier sections in the
    folder (``<element>-xs-*.png``) are removed first, so none is left from a longer run.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for stale in folder.glob(f"{element}-xs-*.png"):
        stale.unlink()
    half = 12
    paths = []
    for n, i in enumerate(_picks(route, limit), start=1):
        dx, dz = _across(route, i)
        x, z = route.cells[i]
        level = route.levels[i]
        if site_of is not None:
            site = site_of(i)
            y1, y2 = site.box[1], site.box[4]
        else:
            site = None
            ref = [v for v in (route.ground[i], level) if v is not None]
            y1, y2 = math.floor(min(ref)) - 8, math.ceil(max(ref)) + 8
        w, h = 2 * half + 1, y2 - y1 + 1
        img = np.zeros((h, w, 3), np.uint8)
        img[:] = _BG
        for k in range(-half, half + 1):
            col = k + half
            cx, cz = x + dx * k, z + dz * k
            if site is not None:
                for y in range(y1, y2 + 1):
                    try:
                        c = _block_colour(site.block(cx, y, cz))
                    except KeyError:
                        continue
                    if c is not None:
                        img[y2 - y, col] = c
            else:
                if route.ground[i] is not None:
                    top = int(route.ground[i])
                    img[max(y2 - top, 0):, col] = _EARTH
                if abs(k) <= 1:
                    row = y2 - (math.floor(level) - 1)
                    if 0 <= row < h:
                        img[row, col] = _colour(route.kinds[i])
        out = _fit(Image.fromarray(img), longest=500)
        path = folder / f"{element}-xs-{n:02d}.png"
        out.save(path)
        paths.append(path)
    return paths
