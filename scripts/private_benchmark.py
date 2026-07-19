#!/usr/bin/env python3
"""Run a private, fail-closed analysis benchmark without disclosing save data.

This script is intentionally not used by public CI.  It runs only against an
operator-owned corpus and emits the single public-safe word ``pass`` or
``fail``.  Its optional report is for the controlled host and carries no input
path, source hash, entity count, or decoded value.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Final

from palworld_save_facts.limits import DEFAULT_ANALYSIS_LIMITS


_POLL_SECONDS: Final = 0.1


def _peak_working_set_bytes(process_id: int) -> int:
    """Return Linux VmHWM in bytes, or zero before the process reports it."""
    try:
        for line in Path(f"/proc/{process_id}/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmHWM:"):
                return int(line.split()[1]) * 1024
    except (FileNotFoundError, IndexError, ValueError):
        pass
    return 0


def _single_analysis_lock() -> int:
    """Acquire a private-host Linux advisory lock for one active benchmark."""
    import fcntl

    lock_path = Path(tempfile.gettempdir()) / "palworld-save-facts.analysis.lock"
    descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        os.close(descriptor)
        raise RuntimeError("analysis-concurrency-limit-exceeded") from error
    return descriptor


def _write_private_report(path: Path, *, passed: bool, duration_seconds: float, peak_working_set_bytes: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schemaVersion": "palworld-save-facts/private-benchmark/v1",
                "passed": passed,
                "durationSeconds": round(duration_seconds, 3),
                "peakWorkingSetBytes": peak_working_set_bytes,
                "limits": {
                    "maxConcurrentAnalyses": DEFAULT_ANALYSIS_LIMITS.max_concurrent_analyses,
                    "timeoutSeconds": DEFAULT_ANALYSIS_LIMITS.timeout_seconds,
                    "maxWorkingSetBytes": DEFAULT_ANALYSIS_LIMITS.max_working_set_bytes,
                    "maxRawArtifactBytes": DEFAULT_ANALYSIS_LIMITS.max_raw_artifact_bytes,
                    "maxNormalizedOutputBytes": DEFAULT_ANALYSIS_LIMITS.max_normalized_output_bytes,
                },
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def benchmark(executable: str, snapshot: Path, output: Path, report: Path | None) -> bool:
    if output.exists():
        raise RuntimeError("output-directory-already-exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = _single_analysis_lock()
    started = time.monotonic()
    peak = 0
    passed = False
    try:
        process = subprocess.Popen(
            [executable, "analyze", "--input", str(snapshot), "--output", str(output)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        while process.poll() is None:
            peak = max(peak, _peak_working_set_bytes(process.pid))
            if time.monotonic() - started > DEFAULT_ANALYSIS_LIMITS.timeout_seconds:
                process.kill()
                process.wait()
                raise RuntimeError("analysis-timeout-exceeded")
            if peak > DEFAULT_ANALYSIS_LIMITS.max_working_set_bytes:
                process.kill()
                process.wait()
                raise RuntimeError("analysis-working-set-limit-exceeded")
            time.sleep(_POLL_SECONDS)
        peak = max(peak, _peak_working_set_bytes(process.pid))
        if process.returncode != 0:
            raise RuntimeError("analysis-failed")
        raw = output / "raw.json.zst"
        snapshot_output = output / "snapshot.json"
        if not raw.is_file() or raw.stat().st_size > DEFAULT_ANALYSIS_LIMITS.max_raw_artifact_bytes:
            raise RuntimeError("raw-artifact-size-limit-exceeded")
        if not snapshot_output.is_file() or snapshot_output.stat().st_size > DEFAULT_ANALYSIS_LIMITS.max_normalized_output_bytes:
            raise RuntimeError("normalized-output-size-limit-exceeded")
        passed = True
        return True
    finally:
        duration = time.monotonic() - started
        if report is not None:
            _write_private_report(report, passed=passed, duration_seconds=duration, peak_working_set_bytes=peak)
        os.close(lock)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Private Palworld analysis resource benchmark")
    parser.add_argument("--executable", default="palworld-save-facts")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        benchmark(args.executable, args.input, args.output, args.report)
    except (OSError, RuntimeError, subprocess.SubprocessError):
        print("fail")
        return 2
    print("pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
