# Per-version id lists

The terrain toolkit checks feature ids and biome ids against a list for
each Minecraft version. `terrain/ids.py` reads these lists.

## Layout

```
data/
  <version>/             e.g. 26.1  (dotted numbers only)
    features.json        feature ids (what `/place feature` takes; configured features in older versions)
    biomes.json          biome ids
```

A folder counts only when it holds both files. Other folders are ignored.

## File format

Both files hold the same shape:

```json
{"version": "26.1", "source": "how the list was made", "ids": ["minecraft:birch", "minecraft:oak"]}
```

`ids` is sorted and holds strings. A file that does not match this shape makes the
loader fail with an error that names the file.

## Which version is used

A version with its own folder uses that folder. A version without one falls back to
the nearest older version that has a folder. For example, with folders `1.21.4` and
`26.1`, a request for `26.3` uses `26.1`. A request older than every folder fails.
The design approval states the version used when a fallback happens.

## How the lists are made

The lists are generated once per version from vanilla game data, after the user
approves the download. Nothing in this folder is written by hand.
