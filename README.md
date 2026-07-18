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

## Private analysis artifacts

For operator-only processing, `analyze` creates a new output directory with a
lossless decoder-native `raw.json.zst`, the existing normalized v1
`snapshot.json`, and `result.json`. It hashes every input file before and after
decoding, refuses output inside the input tree, and atomically publishes only
after the input remains unchanged. The raw artifact and result manifest contain
restricted save information; keep the whole output directory out of WebUI,
browser, logs, public endpoints, and public CI.
Successful stdout is a sanitized receipt containing the snapshot digest and
output-artifact metadata. Source-relative paths and the complete source
manifest are written only to the private `result.json`.

```sh
palworld-save-facts analyze \
  --input /srv/palworld/snapshots/2026-07-17T20-00-00Z \
  --output /srv/palworld/private-analysis/2026-07-17T20-00-00Z
```

## Private corpus qualification

Approved commits may be validated only on the controlled host with an
operator-owned corpus. The corpus is outside this repository and is never
mounted in public CI or exposed to untrusted pull-request code. Run:

```sh
python scripts/private_validate.py --corpus /private/palworld-corpus --report /private/reports/qualification.json
```

The corpus has the private family directories `current`, `adjacent`,
`historical`, `incomplete`, `corrupt`, `missing-player`, and `future`. The
report remains private; stdout is only `pass` or `fail` and is the sole value
permitted in a public attestation. Promote only an approved, exact commit to
this procedure and never attach the corpus to a public GitHub runner.

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
