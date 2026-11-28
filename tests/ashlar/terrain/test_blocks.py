"""Shared block helpers: bounding-box writes, applying layers, player-block reports."""
from __future__ import annotations

from sitegen import make_site
from terrain import blocks


def test_cells_write_round_trips_through_apply_writes(tmp_path):
    site = make_site(tmp_path / "s", (0, 60, 0, 4, 70, 4))
    write = blocks.cells_write({(1, 65, 1): "minecraft:stone", (3, 66, 2): "minecraft:rail[shape=north_south]"})
    after = blocks.apply_writes(site, [("build", write)])
    assert write.palette[0] == "skip"
    assert after.block(1, 65, 1) == "minecraft:stone"
    assert after.block(3, 66, 2) == "minecraft:rail[shape=north_south]"
    assert after.block(0, 65, 0) == site.block(0, 65, 0)


def test_cells_write_of_nothing_is_none():
    assert blocks.cells_write({}) is None


def test_touched_blocks_lists_player_blocks_with_the_callback_reason(tmp_path):
    site = make_site(tmp_path / "s", (0, 60, 0, 4, 70, 4), cells={(2, 65, 2): "minecraft:chest[facing=north]"})
    write = blocks.cells_write({(2, 65, 2): "minecraft:air", (1, 63, 1): "minecraft:air"})
    items = blocks.touched_blocks(site, [("carve", write)], lambda mode, cell: f"{mode} at {cell}")
    assert items == [{"cell": [2, 65, 2], "block": "minecraft:chest[facing=north]", "action": "carve",
                      "why": "carve at (2, 65, 2)", "loses_data": True}]


def test_touched_blocks_natural_set_decides_what_is_a_player_block(tmp_path):
    from terrain.site import natural_for
    site = make_site(tmp_path / "s", (0, 60, 0, 4, 70, 4), cells={(2, 65, 2): "minecraft:netherrack"})
    write = blocks.cells_write({(2, 65, 2): "minecraft:air"})
    why = lambda mode, cell: mode
    assert [i["cell"] for i in blocks.touched_blocks(site, [("carve", write)], why)] == [[2, 65, 2]]
    assert blocks.touched_blocks(site, [("carve", write)], why, natural=natural_for("nether")) == []


def test_natural_for_dimension():
    from terrain.site import NATURAL, natural_for
    assert natural_for("overworld") is NATURAL
    assert "minecraft:netherrack" not in NATURAL
    assert "minecraft:netherrack" in natural_for("nether")
    assert "minecraft:stone" in natural_for("nether")


def test_portal_blocks_emit_light_eleven():
    assert blocks.light_of("minecraft:nether_portal[axis=x]") == 11


def test_a_portal_block_is_no_full_cube_and_lets_light_through():
    assert not blocks.full_cube("minecraft:nether_portal[axis=x]")
    assert blocks.lets_light("minecraft:nether_portal[axis=z]")
