"""Resource limits for private snapshot analysis.

The decoder operates on operator-owned immutable snapshots.  These defaults are
part of the deployment contract, not a substitute for an OS/container resource
limit.  The private benchmark harness verifies the process-level limits before
an operator promotes a release.
"""

from __future__ import annotations

from dataclasses import dataclass


GIB = 1024 * 1024 * 1024
MIB = 1024 * 1024


@dataclass(frozen=True)
class AnalysisLimits:
    """Closed defaults used by ``analyze`` and private qualification."""

    max_concurrent_analyses: int = 1
    timeout_seconds: int = 10 * 60
    max_working_set_bytes: int = 2 * GIB
    max_raw_artifact_bytes: int = 4 * GIB
    max_normalized_output_bytes: int = 128 * MIB


DEFAULT_ANALYSIS_LIMITS = AnalysisLimits()
