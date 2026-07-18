#!/usr/bin/env python3
"""Operator-only validator for a controlled Palworld snapshot corpus.

The corpus is never a repository fixture.  Each immediate subdirectory is a
test family (current, adjacent, historical, incomplete, corrupt,
missing-player, future).  Reports stay at --report; stdout is a deliberately
sanitized attestation suitable for a public issue comment.
"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from palworld_save_facts.analyze import analyze, source_manifest
from palworld_save_facts.cli import _load, _player_saves

REQUIRED_FAMILIES = ("current", "adjacent", "historical", "incomplete", "corrupt", "missing-player", "future")


def validate(corpus: Path, report: Path) -> bool:
    if not corpus.is_dir() or report.resolve().is_relative_to(corpus.resolve()):
        raise ValueError("invalid-private-validator-path")
    details: list[dict[str, object]] = []
    passed = True
    scratch_parent = Path(tempfile.mkdtemp(prefix="palworld-private-validator-"))
    try:
        for family in REQUIRED_FAMILIES:
            snapshots = sorted(path for path in (corpus / family).iterdir()) if (corpus / family).is_dir() else []
            if not snapshots:
                details.append({"family": family, "status": "missing"})
                passed = False
                continue
            for index, snapshot in enumerate(snapshots):
                before = source_manifest(snapshot)
                output = scratch_parent / f"{family}-{index}"
                try:
                    analyze(snapshot, output, _load, _player_saves)
                    result = "success"
                except Exception as error:  # Private report may retain diagnostic class only.
                    result = type(error).__name__
                after = source_manifest(snapshot)
                unchanged = before == after
                details.append({"family": family, "result": result, "inputUnchanged": unchanged})
                # Current/adjacent/historical must decode; negative/future samples must fail closed.
                expected_success = family in {"current", "adjacent", "historical"}
                passed &= unchanged and ((result == "success") == expected_success)
    finally:
        shutil.rmtree(scratch_parent, ignore_errors=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({"results": details}, sort_keys=True) + "\n", encoding="utf-8")
    return passed


def main() -> int:
    parser = argparse.ArgumentParser(description="Private Palworld corpus validator")
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        passed = validate(args.corpus, args.report)
    except Exception:
        passed = False
    print("palworld-save-private-validation: " + ("pass" if passed else "fail"))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
