from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .extract import ExtractionError, SCHEMA_V1, extract_v1


def _load(path: Path) -> dict[str, Any]:
    if path.suffix.casefold() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        from palsav.io import load_sav
    except ImportError as error:
        raise ExtractionError("decoder-dependency-unavailable") from error
    return load_sav(path).dump()


def _player_saves(snapshot: Path) -> dict[str, dict[str, Any]]:
    directory = snapshot / "Players"
    if not directory.is_dir():
        raise ExtractionError("players-directory-missing")
    result: dict[str, dict[str, Any]] = {}
    for path in directory.iterdir():
        if path.is_file() and path.suffix.casefold() in {".sav", ".json"}:
            result[path.stem.casefold()] = _load(path)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Palworld save facts decoder")
    parser.add_argument("--input", required=True, type=Path, help="Completed snapshot directory containing Level.sav")
    parser.add_argument("--schema", default=SCHEMA_V1, help=f"Output schema (only {SCHEMA_V1} is supported)")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    if args.schema != SCHEMA_V1:
        parser.error(f"unsupported schema: {args.schema}")
    level = args.input / "Level.sav"
    if not level.is_file():
        json_level = args.input / "Level.json"
        level = json_level if json_level.is_file() else level
    if not level.is_file():
        print("palworld-save-facts: Level.sav is required", file=sys.stderr)
        return 2
    try:
        document = extract_v1(_load(level), _player_saves(args.input), datetime.now(timezone.utc))
    except (ExtractionError, OSError, ValueError) as error:
        print(f"palworld-save-facts: {error}", file=sys.stderr)
        return 2
    json.dump(document, sys.stdout, separators=(",", ":"), sort_keys=True)
    sys.stdout.write("\n")
    return 0
