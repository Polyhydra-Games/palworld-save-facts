from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SCHEMA_V1 = "palworld-save-facts/v1"
SCHEMA_V2 = "palworld-save-facts/v2"


class ExtractionError(ValueError):
    """The save is incomplete or does not expose a required v1 fact."""


def _value(value: Any, default: Any = None) -> Any:
    if not isinstance(value, dict):
        return default if value is None else value
    result = value.get("value", default)
    return _value(result, default) if isinstance(result, dict) else result


def _property_values(value: Any) -> list[str]:
    raw = value.get("value", []) if isinstance(value, dict) else value
    if isinstance(raw, dict):
        raw = raw.get("values", [])
    if not isinstance(raw, list):
        return []
    values = [_value(item) for item in raw]
    return sorted({str(item) for item in values if item not in (None, "")})


def _field(data: dict[str, Any], key: str, *, numeric: bool = False) -> dict[str, Any]:
    if key not in data:
        return {"state": "absent", "value": None}
    value = _value(data[key])
    if value is None:
        return {"state": "unknown", "value": None}
    return {"state": "present", "value": int(value) if numeric else str(value)}


def _list_field(data: dict[str, Any], key: str) -> dict[str, Any]:
    if key not in data:
        return {"state": "absent", "values": []}
    return {"state": "present", "values": _property_values(data[key])}


def _world(decoded: dict[str, Any]) -> dict[str, Any]:
    return decoded.get("properties", {}).get("worldSaveData", {}).get("value", {})


def _save_data(decoded: dict[str, Any]) -> dict[str, Any]:
    return decoded.get("properties", {}).get("SaveData", {}).get("value", {})


def _character_data(entry: dict[str, Any]) -> dict[str, Any]:
    return entry.get("value", {}).get("RawData", {}).get("value", {}).get("object", {}).get("SaveParameter", {}).get("value", {})


def _player_id(entry: dict[str, Any]) -> str:
    return str(_value(entry.get("key", {}).get("PlayerUId"), ""))


def _map_entries(world: dict[str, Any], source_key: str) -> tuple[str, list[dict[str, Any]]]:
    """Return a decoder map's state without exposing its native payload."""
    raw = world.get(source_key)
    if raw is None:
        return "absent", []
    values = raw.get("value", []) if isinstance(raw, dict) else []
    if not isinstance(values, list):
        return "malformed", []
    return "present", [entry for entry in values if isinstance(entry, dict)]


def _entry_payload(entry: dict[str, Any]) -> dict[str, Any]:
    """Read the typed portion of a map entry while keeping unknown objects raw-only."""
    raw = entry.get("value", {})
    if not isinstance(raw, dict):
        return {}
    raw_data = raw.get("RawData", raw)
    if not isinstance(raw_data, dict):
        return {}
    value: Any = raw_data
    while isinstance(value, dict) and "value" in value:
        value = value["value"]
    return value if isinstance(value, dict) else {}


def _identifier_value(value: Any) -> Any:
    """Read scalar IDs from ordinary properties or decoder struct-map keys."""
    scalar = _value(value)
    if scalar not in (None, ""):
        return scalar
    if isinstance(value, dict):
        for key in ("ID", "Id", "id"):
            if key in value:
                nested = _identifier_value(value[key])
                if nested not in (None, ""):
                    return nested
        if "value" in value:
            return _identifier_value(value["value"])
    return None


def _entry_id(entry: dict[str, Any], payload: dict[str, Any], *keys: str) -> str:
    """Select a native key solely to build a restricted snapshot-local ID."""
    candidates = [entry.get("key"), *(payload.get(key) for key in keys)]
    for candidate in candidates:
        value = _identifier_value(candidate)
        if value not in (None, ""):
            return str(value)
    return ""


def _local_reference(payload: dict[str, Any], prefix: str, *keys: str) -> str | None:
    for key in keys:
        if key not in payload:
            continue
        value = _identifier_value(payload[key])
        if value not in (None, ""):
            return f"{prefix}:{value}"
    return None


def _guild_memberships(world: dict[str, Any]) -> tuple[int, dict[str, str]]:
    memberships: dict[str, str] = {}
    guilds = 0
    for entry in world.get("GroupSaveDataMap", {}).get("value", []):
        raw = entry.get("value", {}).get("RawData", {}).get("value", {})
        if raw.get("group_type") != "EPalGroupType::Guild":
            continue
        guilds += 1
        guild_id = str(_value(entry.get("key"), ""))
        if not guild_id:
            raise ExtractionError("guild-id-missing")
        for player in raw.get("players", []):
            native_id = str(player.get("player_uid", ""))
            if native_id:
                memberships[native_id] = guild_id
    return guilds, memberships


def extract_v2_pals(level: dict[str, Any], observed_at: datetime) -> list[dict[str, Any]]:
    """Project Pal character records without inferring capture or trade causes.

    ``firstObservedAt`` is this observation only; retained-history aggregation
    is intentionally outside this single-snapshot extractor.
    """
    pals: list[dict[str, Any]] = []
    for entry in _world(level).get("CharacterSaveParameterMap", {}).get("value", []):
        data = _character_data(entry)
        if _value(data.get("IsPlayer"), False):
            continue
        native_id = str(_value(entry.get("key", {}).get("InstanceId"), ""))
        if not native_id:
            continue
        pals.append({
            "snapshotLocalId": f"pal:{native_id}",
            "nativeId": {"state": "present", "value": native_id},
            "species": _field(data, "CharacterID"), "nickname": _field(data, "NickName"),
            "owner": _field(data, "OwnerPlayerUId"), "ownershipObservedAt": {"state": "unknown", "value": None},
            "firstObservedAt": {"state": "present", "value": observed_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")},
            "level": _field(data, "Level", numeric=True), "experience": _field(data, "Exp", numeric=True),
            "rank": _field(data, "Rank", numeric=True), "gender": _field(data, "Gender"),
            "traits": _list_field(data, "TalentRank"), "ivStats": {}, "souls": _field(data, "Rank", numeric=True),
            "passiveSkills": _list_field(data, "PassiveSkillList"), "activeSkills": _list_field(data, "EquipWaza"),
            "vitals": {"health": _field(data, "HP", numeric=True), "sanity": _field(data, "SanityValue", numeric=True), "hunger": _field(data, "Hunger", numeric=True), "friendship": _field(data, "Friendship", numeric=True)},
            "workSuitability": _list_field(data, "WorkSuitability"), "container": _field(data, "SlotID"),
            "slot": {"state": "unknown", "value": None}, "party": _field(data, "PartyID"),
            "palbox": _field(data, "PalBoxID"), "base": _field(data, "BaseCampId"), "guild": _field(data, "GroupId"),
        })
    return sorted(pals, key=lambda pal: pal["snapshotLocalId"])


def extract_v2_players(level: dict[str, Any], player_saves: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Project players with deterministic references and non-sensitive warnings."""
    world = _world(level)
    guild_count, memberships = _guild_memberships(world)
    del guild_count
    players: list[dict[str, Any]] = []
    warnings: list[str] = []
    characters = world.get("CharacterSaveParameterMap", {}).get("value", [])
    if not isinstance(characters, list):
        raise ExtractionError("character-map-invalid")
    for entry in characters:
        data = _character_data(entry)
        if not _value(data.get("IsPlayer"), False):
            continue
        native_id = _player_id(entry)
        if not native_id:
            raise ExtractionError("player-id-missing")
        save = player_saves.get(native_id.casefold())
        if save is None:
            warnings.append("player-save-missing")
            save_data: dict[str, Any] = {}
        else:
            save_data = _save_data(save)
        players.append({
            "snapshotLocalId": f"player:{native_id}",
            "nativeId": {"state": "present", "value": native_id},
            "displayName": _field(data, "NickName"),
            "guild": {"state": "present", "value": memberships[native_id]} if native_id in memberships else {"state": "absent", "value": None},
            "level": _field(data, "Level", numeric=True), "experience": _field(data, "Exp", numeric=True),
            "points": _field(save_data, "TechnologyPoint", numeric=True),
            "technology": _list_field(save_data, "UnlockedTechnologyNames"),
            "recipes": _list_field(save_data, "UnlockedRecipeTechnologyNames"),
            "quests": _list_field(save_data, "CompletedQuestArray"),
            "lastOnline": {"state": "unknown", "value": None},
            "inventoryReferences": [], "equipmentReferences": [],
            "position": {"state": "absent", "value": None}, "state": _field(data, "State"),
        })
    return sorted(players, key=lambda player: player["snapshotLocalId"]), sorted(set(warnings))


WORLD_FAMILIES = ("guilds", "settlements", "workers", "facilities", "structures", "containers", "itemSlots", "equipment", "mapObjects", "workState", "dungeons", "camps", "invaders", "oilRigs", "supplySystems")


def extract_v2_world(level: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """Build closed world-family projections; unknown native shapes stay raw-only."""
    world = _world(level)
    result: dict[str, list[dict[str, Any]]] = {"families": [], **{family: [] for family in WORLD_FAMILIES}}
    warnings: list[str] = []
    source_keys = {
        "guilds": "GroupSaveDataMap",
        "settlements": "BaseCampSaveData",
        "containers": "ItemContainerSaveData",
        "mapObjects": "MapObjectSaveData",
    }
    family_state: dict[str, str] = {family: "unsupported" for family in WORLD_FAMILIES}
    family_warning: dict[str, str | None] = {family: f"{family}-unsupported" for family in WORLD_FAMILIES}
    for family, source_key in source_keys.items():
        state, entries = _map_entries(world, source_key)
        family_state[family] = state
        family_warning[family] = None if state == "present" else f"{family}-{state}"
        if state != "present":
            warnings.append(f"{family}-{state}")
            continue
        for entry in entries:
            payload = _entry_payload(entry)
            if family == "guilds":
                if payload.get("group_type") != "EPalGroupType::Guild":
                    continue
                native_id = _entry_id(entry, payload, "GroupId")
                references = sorted({
                    f"player:{player.get('player_uid')}"
                    for player in payload.get("players", [])
                    if isinstance(player, dict) and player.get("player_uid") not in (None, "")
                })
                references.extend(reference for reference in [_local_reference(payload, "base", "BaseCampId", "base_camp_id")] if reference)
            elif family == "settlements":
                native_id = _entry_id(entry, payload, "BaseCampId", "base_camp_id")
                references = [reference for reference in [_local_reference(payload, "guild", "GroupId", "group_id", "group_id_belong_to")] if reference]
            elif family == "containers":
                native_id = _entry_id(entry, payload, "ContainerId", "container_id")
                references = [reference for reference in [_local_reference(payload, "base", "BaseCampId", "base_camp_id")] if reference]
            else:
                native_id = _entry_id(entry, payload, "MapObjectId", "map_object_id")
                references = [reference for reference in [_local_reference(payload, "base", "BaseCampId", "base_camp_id")] if reference]
            if not native_id:
                warnings.append(f"{family}-id-missing")
                family_state[family] = "unknown"
                family_warning[family] = f"{family}-id-missing"
                continue
            result[family].append({
                "snapshotLocalId": f"{family[:-1] if family.endswith('s') else family}:{native_id}",
                "kind": {"state": "present", "value": family[:-1] if family.endswith("s") else family},
                "name": {"state": "absent", "value": None},
                "position": {"state": "absent", "value": None},
                "references": [{"snapshotLocalId": reference} for reference in sorted(set(references))],
                "state": {"state": "present", "value": "present"},
            })
    for family in WORLD_FAMILIES:
        if family not in source_keys:
            warnings.append(f"{family}-unsupported")
    for family in result:
        if family != "families":
            result[family].sort(key=lambda item: item["snapshotLocalId"])
    result["families"] = [
        {"family": family, "state": family_state[family], "warningCode": family_warning[family]}
        for family in WORLD_FAMILIES
    ]
    return result, sorted(warnings)


def extract_v2(
    level: dict[str, Any],
    player_saves: dict[str, dict[str, Any]],
    observed_at: datetime,
    *,
    snapshot_id: str,
    source_digest: str,
    parser_version: str,
    decoder_version: str,
    game_version: str | None = None,
) -> dict[str, Any]:
    """Compose the typed v2 snapshot without changing the legacy v1 path."""
    players, player_warnings = extract_v2_players(level, player_saves)
    pals = extract_v2_pals(level, observed_at)
    world, world_warnings = extract_v2_world(level)
    warning_codes = sorted(set(player_warnings + world_warnings))
    warnings = [{"code": code, "message": "source-field-unavailable"} for code in warning_codes]
    return {
        "schemaVersion": SCHEMA_V2,
        "snapshotId": snapshot_id,
        "sourceDigest": source_digest,
        "observedAt": observed_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "provenance": {"parserVersion": parser_version, "decoderVersion": decoder_version, "gameVersion": game_version},
        "completeness": "complete" if not warnings else "partial",
        "warnings": warnings,
        "domainCounts": {"players": len(players), "pals": len(pals), **{key: len(value) for key, value in world.items() if key != "families"}},
        "players": players,
        "pals": pals,
        "world": world,
    }


def extract_v1(level: dict[str, Any], player_saves: dict[str, dict[str, Any]], observed_at: datetime) -> dict[str, Any]:
    world = _world(level)
    characters = world.get("CharacterSaveParameterMap", {}).get("value", [])
    if not isinstance(characters, list):
        raise ExtractionError("character-map-invalid")
    guild_count, memberships = _guild_memberships(world)
    players: list[dict[str, Any]] = []
    pal_count = 0
    for entry in characters:
        data = _character_data(entry)
        if not _value(data.get("IsPlayer"), False):
            pal_count += 1
            continue
        native_id = _player_id(entry)
        if not native_id:
            raise ExtractionError("player-id-missing")
        player_save = player_saves.get(native_id.casefold())
        if player_save is None:
            raise ExtractionError(f"player-save-missing:{native_id}")
        save_data = _save_data(player_save)
        players.append({
            "nativeId": native_id,
            "level": int(_value(data.get("Level"), 0)),
            "recipes": _property_values(save_data.get("UnlockedRecipeTechnologyNames")),
            "completedQuests": _property_values(save_data.get("CompletedQuestArray")),
            "technologyPoints": int(_value(save_data.get("TechnologyPoint"), 0)),
            "guildId": memberships.get(native_id),
        })
    players.sort(key=lambda player: player["nativeId"])
    return {
        "schemaVersion": SCHEMA_V1,
        "observedAt": observed_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "players": players,
        "guildCount": guild_count,
        "baseCount": len(world.get("BaseCampSaveData", {}).get("value", [])),
        "palCount": pal_count,
    }
