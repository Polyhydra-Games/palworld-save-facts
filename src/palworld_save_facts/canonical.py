from __future__ import annotations

import hashlib
import json
from typing import Any


def canonicalize(value: Any) -> Any:
    """Normalize decoder output into deterministic JSON-compatible values."""
    if isinstance(value, dict):
        return {str(key): canonicalize(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple, set)):
        values = [canonicalize(item) for item in value]
        return sorted(values, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(canonicalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"


def snapshot_id(source_manifest: list[dict[str, str]]) -> str:
    return hashlib.sha256(canonical_bytes(source_manifest)).hexdigest()


def adjacent_summary(previous: dict[str, Any], current: dict[str, Any], domains: tuple[str, ...] = ("players", "pals")) -> dict[str, dict[str, int]]:
    """Return only added/removed/changed counts; never infer gameplay causes."""
    result: dict[str, dict[str, int]] = {}
    for domain in domains:
        before = {_entity_id(item): canonicalize(item) for item in previous.get(domain, []) if _entity_id(item)}
        after = {_entity_id(item): canonicalize(item) for item in current.get(domain, []) if _entity_id(item)}
        result[domain] = {
            "added": len(after.keys() - before.keys()),
            "removed": len(before.keys() - after.keys()),
            "changed": sum(before[key] != after[key] for key in before.keys() & after.keys()),
        }
    return result


def _entity_id(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return str(value.get("snapshotLocalId") or value.get("nativeId") or "")
