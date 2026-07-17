# Palworld Save Facts

`palworld-save-facts` is a read-only, GPL-3.0-or-later command-line decoder
for completed Palworld save snapshots. It writes one
`palworld-save-facts/v1` JSON document to standard output and never modifies
the input snapshot.

It is designed for operator-owned systems: its output contains native player
and guild identifiers and must remain inside your private processing boundary.
Use the separate [MIT contracts and schema repository](https://github.com/Polyhydra-Games/palworld-save-facts-contracts)
to strongly type that output in another application without linking this GPL
decoder into that application.

## Install

Download the self-contained archive for your platform from
[Releases](https://github.com/Polyhydra-Games/palworld-save-facts/releases),
verify its `SHA256SUMS.txt` entry, extract it, and put `palworld-save-facts` on
your `PATH`.

```sh
palworld-save-facts --input /srv/palworld/snapshots/2026-07-17T20-00-00Z \
  --schema palworld-save-facts/v1 > facts.json
```

The input directory must contain `Level.sav`. When player fact extraction is
enabled, its matching `Players/<native-id>.sav` files must also be present.
Failures are written to standard error; stdout is reserved for the single JSON
document so a sidecar can consume it safely.

## Development

The vendored submodule is pinned to the reviewed `palsav-flex` 0.2.0 decoder,
GPL-3.0-or-later. Clone recursively, create a virtual environment, then
install the local decoder packages before installing this project:

```sh
git clone --recurse-submodules https://github.com/Polyhydra-Games/palworld-save-facts.git
cd palworld-save-facts
python3 -m venv .venv
.venv/bin/pip install vendor/PalworldSaveTools/src/palsav/palooz
.venv/bin/pip install --no-deps vendor/PalworldSaveTools/src/palsav
.venv/bin/pip install 'orjson>=3.11.8'
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest
```

## Licensing

This project is GPL-3.0-or-later. `vendor/PalworldSaveTools` is a pinned
upstream source submodule; the decoder within `src/palsav` and its `palooz`
dependency are GPL-3.0-or-later. See the upstream source and included license
notices before redistributing modified builds.
