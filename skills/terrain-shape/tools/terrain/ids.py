"""Per-Minecraft-version lists of feature ids (what ``/place feature`` takes; configured
features in older versions) and biome ids.

The lists live in ``data/<version>/features.json`` and ``data/<version>/biomes.json``,
each ``{"version": str, "source": str, "ids": [sorted ids]}``. A version without its
own folder uses the nearest older version that has one; see ``data/README.md``.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Iterable

from .climate import BIOME_CONTENT

DATA = Path(__file__).resolve().parent / "data"

_DOTTED_INT = re.compile(r"^[0-9]+(\.[0-9]+)*$")
_FILES = ("features.json", "biomes.json")


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _is_version(name: str) -> bool:
    return _DOTTED_INT.match(name) is not None


def available_versions(data_dir: Path = DATA) -> list[str]:
    """Versions that have both list files, sorted by their numeric parts."""
    if not data_dir.is_dir():
        return []
    versions = [
        folder.name
        for folder in data_dir.iterdir()
        if folder.is_dir() and _is_version(folder.name)
        and all((folder / name).is_file() for name in _FILES)
    ]
    return sorted(versions, key=_version_key)


def _read_ids(path: Path) -> frozenset[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"malformed id list {path}: {exc}") from exc
    items = payload.get("ids") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
        raise ValueError(f"malformed id list {path}: expected an object with an 'ids' list of strings")
    return frozenset(items)


def load_ids(version: str, data_dir: Path = DATA) -> tuple[frozenset[str], frozenset[str], str]:
    """Feature ids, biome ids and the version whose lists were used.

    Uses ``version`` when it has a folder, else the newest older version. Raises
    ``ValueError`` when no version at or below ``version`` is available.
    """
    if not _is_version(version):
        raise ValueError(f"version {version!r} is not a dotted number such as 1.21.4")
    available = available_versions(data_dir)
    if version in available:
        used = version
    else:
        older = [v for v in available if _version_key(v) < _version_key(version)]
        if not older:
            listed = ", ".join(available) or "none"
            raise ValueError(
                f"no id lists for {version} or any older version; available: {listed}")
        used = older[-1]
    folder = data_dir / used
    return _read_ids(folder / "features.json"), _read_ids(folder / "biomes.json"), used


def check_ids(ids: Iterable[str], known: frozenset[str]) -> tuple[list[str], list[str]]:
    """Split ``ids`` into (known, unknown), keeping input order and duplicates."""
    found: list[str] = []
    missing: list[str] = []
    for item in ids:
        (found if item in known else missing).append(item)
    return found, missing


def checked_biome_content(features: frozenset[str]) -> tuple[dict, list[str]]:
    """Copy of ``BIOME_CONTENT`` with unknown feature ids removed, and the dropped ids."""
    content = copy.deepcopy(BIOME_CONTENT)
    dropped: set[str] = set()
    for entry in content.values():
        kept = []
        for feature in entry["features"]:
            if feature in features:
                kept.append(feature)
            else:
                dropped.add(feature)
        entry["features"] = kept
    return content, sorted(dropped)
