"""Per-version feature and biome id lists: loading, fallback, checks."""
import json

import pytest

from terrain import climate, ids


def _write_version(data_dir, version, features, biomes):
    folder = data_dir / version
    folder.mkdir(parents=True)
    for name, items in (("features.json", features), ("biomes.json", biomes)):
        payload = {"version": version, "source": "test", "ids": sorted(items)}
        (folder / name).write_text(json.dumps(payload), encoding="utf-8")


def test_nearest_older_version_is_used(tmp_path):
    _write_version(tmp_path, "1.21.4", ["minecraft:oak"], ["minecraft:plains"])
    _write_version(tmp_path, "26.1", ["minecraft:oak", "minecraft:birch"], ["minecraft:plains"])

    assert ids.available_versions(tmp_path) == ["1.21.4", "26.1"]

    features, biomes, used = ids.load_ids("26.3", tmp_path)
    assert used == "26.1"
    assert features == frozenset({"minecraft:oak", "minecraft:birch"})
    assert biomes == frozenset({"minecraft:plains"})


def test_too_old_version_raises(tmp_path):
    _write_version(tmp_path, "26.1", ["minecraft:oak"], ["minecraft:plains"])

    with pytest.raises(ValueError) as excinfo:
        ids.load_ids("1.21.4", tmp_path)
    message = str(excinfo.value)
    assert "1.21.4" in message
    assert "26.1" in message


def test_check_ids_splits_known_and_unknown():
    known = frozenset({"minecraft:oak", "minecraft:birch"})

    found, missing = ids.check_ids(
        ["minecraft:birch", "minecraft:cherry", "minecraft:oak", "minecraft:cherry", "minecraft:oak"],
        known,
    )

    assert found == ["minecraft:birch", "minecraft:oak", "minecraft:oak"]
    assert missing == ["minecraft:cherry", "minecraft:cherry"]


def test_checked_biome_content_drops_unknown(tmp_path):
    known = frozenset({"minecraft:oak", "minecraft:birch"})
    before = {biome: dict(entry, features=list(entry["features"]))
              for biome, entry in climate.BIOME_CONTENT.items()}

    content, dropped = ids.checked_biome_content(known)

    assert "minecraft:cherry" not in {f for entry in content.values() for f in entry["features"]}
    assert "minecraft:birch" in content["minecraft:forest"]["features"]
    assert "minecraft:fancy_oak" not in content["minecraft:forest"]["features"]
    assert "minecraft:fancy_oak" in dropped
    assert dropped == sorted(set(dropped))
    # Other keys are kept as they are.
    assert content["minecraft:forest"]["density"] == climate.BIOME_CONTENT["minecraft:forest"]["density"]
    assert content["minecraft:forest"]["surface"] == climate.BIOME_CONTENT["minecraft:forest"]["surface"]
    # The module global is not mutated.
    after = {biome: dict(entry, features=list(entry["features"]))
             for biome, entry in climate.BIOME_CONTENT.items()}
    assert after == before
