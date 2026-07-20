from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import shutil
import tempfile
import time
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import zstandard

from . import __version__
from .extract import SCHEMA_V2, ExtractionError, extract_v2
from .limits import AnalysisLimits, DEFAULT_ANALYSIS_LIMITS


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_manifest(snapshot: Path) -> list[dict[str, str]]:
    """Return a deterministic manifest without following links outside the snapshot."""
    entries: list[dict[str, str]] = []
    for path in sorted(snapshot.rglob("*")):
        if path.is_symlink():
            raise ExtractionError("snapshot-symlink-unsupported")
        if path.is_file():
            entries.append({"path": path.relative_to(snapshot).as_posix(), "sha256": _sha256(path)})
    return entries


def _canonical_bytes(document: Any) -> bytes:
    return json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    ).encode("utf-8") + b"\n"


def _json_default(value: Any) -> str:
    """Normalize decoder-native scalar types without using repr or object state."""
    if isinstance(value, UUID) or (type(value).__name__ == "UUID" and type(value).__module__.startswith("palsav.")):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    raise TypeError(f"unsupported-json-value:{type(value).__name__}")


def _manifest_digest(manifest: list[dict[str, str]]) -> str:
    return hashlib.sha256(_canonical_bytes(manifest)).hexdigest()


def _decoder_version() -> str:
    try:
        return importlib.metadata.version("palsav-flex")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _assert_output_is_separate(snapshot: Path, output: Path) -> None:
    try:
        output.resolve().relative_to(snapshot.resolve())
    except ValueError:
        return
    raise ExtractionError("output-directory-must-not-be-inside-input")


def analyze(
    snapshot: Path,
    output: Path,
    load: Callable[[Path], dict[str, Any]],
    player_saves: Callable[[Path], dict[str, dict[str, Any]]],
    observed_at: datetime | None = None,
    limits: AnalysisLimits = DEFAULT_ANALYSIS_LIMITS,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Decode an immutable snapshot and atomically publish private artifacts.

    No output is published until decoding succeeds and the input manifest is
    identical before and after the read-only operation.
    """
    if limits.max_concurrent_analyses != 1:
        raise ExtractionError("analysis-concurrency-limit-must-be-one")
    started_at = monotonic()

    def assert_within_timeout() -> None:
        if monotonic() - started_at > limits.timeout_seconds:
            raise ExtractionError("analysis-timeout-exceeded")

    if not snapshot.is_dir():
        raise ExtractionError("snapshot-directory-required")
    _assert_output_is_separate(snapshot, output)
    if output.exists():
        raise ExtractionError("output-directory-already-exists")

    before = source_manifest(snapshot)
    assert_within_timeout()
    level_path = snapshot / "Level.sav"
    if not level_path.is_file():
        level_path = snapshot / "Level.json"
    if not level_path.is_file():
        raise ExtractionError("Level.sav is required")

    level = load(level_path)
    assert_within_timeout()
    players = player_saves(snapshot)
    assert_within_timeout()
    after = source_manifest(snapshot)
    if before != after:
        raise ExtractionError("input-tree-changed-during-decode")
    manifest_digest = _manifest_digest(before)
    snapshot_document = extract_v2(
        level,
        players,
        observed_at or datetime.now(timezone.utc),
        snapshot_id=manifest_digest,
        source_digest=f"sha256:{manifest_digest}",
        parser_version=__version__,
        decoder_version=_decoder_version(),
    )
    if any(warning.get("code") == "player-save-missing" for warning in snapshot_document["warnings"]):
        raise ExtractionError("player-save-missing")
    assert_within_timeout()
    after_normalization = source_manifest(snapshot)
    if before != after_normalization:
        raise ExtractionError("input-tree-changed-during-decode")

    raw_document = {"level": level, "players": players}
    raw_bytes = _canonical_bytes(raw_document)
    snapshot_bytes = _canonical_bytes(snapshot_document)
    if len(raw_bytes) > limits.max_raw_artifact_bytes:
        raise ExtractionError("raw-artifact-size-limit-exceeded")
    if len(snapshot_bytes) > limits.max_normalized_output_bytes:
        raise ExtractionError("normalized-output-size-limit-exceeded")
    assert_within_timeout()
    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=parent))
    try:
        raw_path = staging / "raw.json.zst"
        raw_path.write_bytes(zstandard.ZstdCompressor(level=10).compress(raw_bytes))
        snapshot_path = staging / "snapshot.json"
        snapshot_path.write_bytes(snapshot_bytes)
        result = {
            "schemaVersion": "palworld-save-decode-manifest/v1",
            "snapshotId": manifest_digest,
            "sourceManifest": before,
            "inputUnchanged": True,
            "raw": {
                "path": "raw.json.zst",
                "sha256": _sha256(raw_path),
                "sizeBytes": raw_path.stat().st_size,
                "compression": "zstd",
            },
            "snapshot": {
                "path": "snapshot.json",
                "sha256": _sha256(snapshot_path),
                "sizeBytes": snapshot_path.stat().st_size,
                "schemaVersion": SCHEMA_V2,
            },
        }
        (staging / "result.json").write_bytes(_canonical_bytes(result))
        os.replace(staging, output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return result
