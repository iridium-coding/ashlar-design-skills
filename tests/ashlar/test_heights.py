"""Height reads (F2): matrix parsing, tiling and the heights command."""
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_place_mcp import PLACER, calls, config, run  # noqa: E402

_spec = importlib.util.spec_from_file_location("ashlar_place", PLACER)
ap = importlib.util.module_from_spec(_spec)
sys.modules["ashlar_place"] = ap
_spec.loader.exec_module(ap)


def world_file(tmp_path, cells=None):
    path = tmp_path / "world.json"
    path.write_text(json.dumps({"ground": 63, "cells": cells or {}}), encoding="utf-8")
    return path


def test_parse_matrix_reads_rows_and_origin():
    text = ("Area x=[-5..-3] z=[-3..-2] (3x2). Surface y: …\n"
            "Height matrix (z rows top-to-bottom, x columns left-to-right, top-left = x=-5 z=-3):\n"
            "z=-3: 62 63 -\nz=-2: 64 64 64")
    assert ap.parse_matrix(text) == (-5, {-3: [62, 63, None], -2: [64, 64, 64]})


def test_heights_negative_origin(tmp_path):
    world = world_file(tmp_path, {
        "-5,62,-3": "minecraft:oak_leaves",       # leaves replace stone at 62: hidden from ground and surface, not top
        "-5,70,-3": "minecraft:oak_leaves",
        "-4,63,-3": "minecraft:water[level=0]",   # liquid: surface yes, ground no
        "-3,64,-2": "minecraft:dirt"})
    out = tmp_path / "h.json"
    proc = run("heights", "--area", "-5", "-3", "4", "2", "--out", str(out),
               "--config", str(config(tmp_path, FAKE_WORLD=str(world))))
    assert proc.returncode == 0, proc.stderr
    f2 = json.loads(out.read_text(encoding="utf-8"))
    assert f2["version"] == 1 and f2["world"] is None
    assert f2["origin"] == [-5, -3] and f2["size"] == [10, 6]
    for key in ("ground", "surface", "top"):
        assert len(f2[key]) == 60
    assert f2["ground"][0] == 61 and f2["surface"][0] == 61 and f2["top"][0] == 70
    zi = 0
    xi = 1  # x=-4, z=-3
    assert f2["ground"][xi * 6 + zi] == 62 and f2["surface"][xi * 6 + zi] == 63
    assert f2["ground"][2 * 6 + 1] == 64            # x=-3, z=-2
    assert f2["ground"][9 * 6 + 5] == 62


def test_heights_tiles_large_areas(tmp_path):
    out = tmp_path / "h.json"
    proc = run("heights", "--area", "0", "0", "499", "499", "--out", str(out),
               "--world", "nether",
               "--config", str(config(tmp_path, FAKE_WORLD=str(world_file(tmp_path)))))
    assert proc.returncode == 0, proc.stderr
    surveys = [c["arguments"] for c in calls(tmp_path) if c["name"] == "mc_survey"]
    assert len(surveys) == 6 and all(s["matrix"] is True and s["world"] == "nether"
                                     for s in surveys)
    for s in surveys:
        cells = (s["to"][0] - s["from"][0] + 1) * (s["to"][1] - s["from"][1] + 1)
        assert cells <= 200_000
    assert sorted({s["type"] for s in surveys}) == ["ANY", "SOLID", "SOLID_OR_LIQUID_NO_LEAVES"]
    f2 = json.loads(out.read_text(encoding="utf-8"))
    assert f2["world"] == "nether" and f2["size"] == [500, 500]
    assert all(len(f2[k]) == 250_000 and f2[k][-1] == 62 for k in ("ground", "surface", "top"))


def test_tile_boundary_exactly_at_the_cap():
    assert ap.height_tiles((0, 0, 499, 399)) == [(0, 0, 499, 399)]
    assert ap.height_tiles((0, 0, 499, 400)) == [(0, 0, 499, 399), (0, 400, 499, 400)]
    assert ap.height_tiles((-3, -2, 0, 1)) == [(-3, -2, 0, 1)]


def test_short_matrix_is_a_server_error(tmp_path):
    class Client:
        def call(self, name, args):
            return ("Area\nHeight matrix (top-left = x=0 z=0):\nz=0: 1 2", False)

        def redact(self, text):
            return text
    try:
        ap.read_heights(Client(), (0, 0, 2, 0), None)
    except ap.PlacerError as exc:
        assert exc.code == ap.EXIT_SERVER
    else:
        raise AssertionError("expected PlacerError")


def test_server_error_is_exit_5(tmp_path):
    proc = run("heights", "--area", "0", "0", "3", "3", "--out", str(tmp_path / "h.json"),
               "--config", str(config(tmp_path)))  # no FAKE_WORLD -> isError
    assert proc.returncode == ap.EXIT_SERVER
    assert not (tmp_path / "h.json").exists()
