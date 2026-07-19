from __future__ import annotations

from datetime import datetime, timezone
import json
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


def _first_field(data: dict[str, Any], *keys: str, numeric: bool = False) -> dict[str, Any]:
    """Return the first decoder field known for a normalized fact.

    Decoder versions have renamed a few native properties.  A missing value is
    still represented explicitly rather than being guessed from a related fact.
    """
    for key in keys:
        if key in data:
            return _field(data, key, numeric=numeric)
    return {"state": "absent", "value": None}


def _reference_field(data: dict[str, Any], key: str, prefix: str) -> dict[str, Any]:
    """Convert a native relationship ID to a snapshot-local typed reference."""
    field = _field(data, key)
    if field["state"] != "present":
        return field
    return {"state": "present", "value": f"{prefix}:{field['value']}"}


def _list_field(data: dict[str, Any], key: str) -> dict[str, Any]:
    if key not in data:
        return {"state": "absent", "values": []}
    return {"state": "present", "values": _property_values(data[key])}


def _references(data: dict[str, Any], key: str, prefix: str) -> list[dict[str, str]]:
    """Map decoder scalar/list IDs to deterministic snapshot-local references."""
    if key not in data:
        return []
    values = _reference_values(data[key])
    return [{"snapshotLocalId": f"{prefix}:{item}"} for item in values if item not in (None, "")]


def _reference_values(value: Any) -> list[str]:
    """Read scalar, list, and decoder struct-wrapped native IDs.

    Item-container IDs are commonly encoded as ``value.ID.value`` rather than
    as a plain scalar.  Keeping this decoding local to reference fields avoids
    changing the legacy scalar/list semantics used by v1 projections.
    """
    def unwrap(candidate: Any) -> Any:
        if not isinstance(candidate, dict):
            return candidate
        if "value" in candidate:
            nested = unwrap(candidate["value"])
            if nested is not None:
                return nested
        for name in ("ID", "Id", "id"):
            if name in candidate:
                nested = unwrap(candidate[name])
                if nested is not None:
                    return nested
        return None

    raw = value.get("value", value) if isinstance(value, dict) else value
    if isinstance(raw, dict) and "values" in raw:
        raw = raw["values"]
    items = raw if isinstance(raw, list) else [raw]
    return sorted({str(item) for item in (unwrap(item) for item in items) if item not in (None, "")})


def _timestamp_field(data: dict[str, Any], key: str) -> dict[str, Any]:
    """Normalize decoder epoch values to the v2 RFC 3339 timestamp contract."""
    if key not in data:
        return {"state": "absent", "value": None}
    value = _value(data[key])
    if value is None:
        return {"state": "unknown", "value": None}
    try:
        timestamp = datetime.fromtimestamp(int(value), timezone.utc)
    except (OverflowError, OSError, TypeError, ValueError):
        return {"state": "unknown", "value": None}
    return {"state": "present", "value": timestamp.isoformat().replace("+00:00", "Z")}


def _world(decoded: dict[str, Any]) -> dict[str, Any]:
    return decoded.get("properties", {}).get("worldSaveData", {}).get("value", {})


def _save_data(decoded: dict[str, Any]) -> dict[str, Any]:
    return decoded.get("properties", {}).get("SaveData", {}).get("value", {})


def _character_data(entry: dict[str, Any]) -> dict[str, Any]:
    return entry.get("value", {}).get("RawData", {}).get("value", {}).get("object", {}).get("SaveParameter", {}).get("value", {})


def _player_id(entry: dict[str, Any]) -> str:
    return str(_value(entry.get("key", {}).get("PlayerUId"), ""))


def _guild_memberships(world: dict[str, Any]) -> tuple[int, dict[str, tuple[str, dict[str, Any]]]]:
    memberships: dict[str, tuple[str, dict[str, Any]]] = {}
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
                player_info = player.get("player_info")
                if not isinstance(player_info, dict):
                    player_info = {}
                memberships[native_id] = (
                    guild_id,
                    _timestamp_field(player_info, "last_online_real_time"),
                )
    return guilds, memberships


def extract_v2_pals(level: dict[str, Any], observed_at: datetime) -> list[dict[str, Any]]:
    """Project Pal character records without inferring capture or trade causes.

    ``firstObservedAt`` is this observation only; retained-history aggregation
    is intentionally outside this single-snapshot extractor.
    """
    candidates: list[tuple[str, str, dict[str, Any]]] = []
    for entry in _world(level).get("CharacterSaveParameterMap", {}).get("value", []):
        data = _character_data(entry)
        if _value(data.get("IsPlayer"), False):
            continue
        native_id = str(_value(entry.get("key", {}).get("InstanceId"), ""))
        if not native_id:
            continue
        pal = {
            "nativeId": {"state": "present", "value": native_id},
            "species": _field(data, "CharacterID"), "nickname": _field(data, "NickName"),
            "owner": _reference_field(data, "OwnerPlayerUId", "player"),
            "ownershipObservedAt": {"state": "unknown", "value": None},
            "firstObservedAt": {"state": "present", "value": observed_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")},
            "level": _field(data, "Level", numeric=True), "experience": _field(data, "Exp", numeric=True),
            "rank": _field(data, "Rank", numeric=True), "gender": _field(data, "Gender"),
            "traits": _list_field(data, "TalentRank"),
            "ivStats": {
                "health": _first_field(data, "Talent_HP", "TalentHp", numeric=True),
                "melee": _first_field(data, "Talent_Melee", "TalentMelee", numeric=True),
                "ranged": _first_field(data, "Talent_Shot", "TalentShot", numeric=True),
                "defense": _first_field(data, "Talent_Defense", "TalentDefense", numeric=True),
            },
            "souls": _first_field(data, "SoulRank", "SoulRankValue", numeric=True),
            "passiveSkills": _list_field(data, "PassiveSkillList"), "activeSkills": _list_field(data, "EquipWaza"),
            "vitals": {"health": _field(data, "HP", numeric=True), "sanity": _field(data, "SanityValue", numeric=True), "hunger": _field(data, "Hunger", numeric=True), "friendship": _field(data, "Friendship", numeric=True)},
            "workSuitability": _list_field(data, "WorkSuitability"),
            "container": _reference_field(data, "SlotID", "container"),
            "slot": _first_field(data, "SlotIndex", "SlotIDIndex", numeric=True),
            "party": _reference_field(data, "PartyID", "party"),
            "palbox": _reference_field(data, "PalBoxID", "palbox"),
            "base": _reference_field(data, "BaseCampId", "base"),
            "guild": _reference_field(data, "GroupId", "guild"),
        }
        # Native instance IDs are expected to be unique.  When a damaged or
        # future-format save repeats one, a canonical record representation
        # gives the duplicate a deterministic, collision-free local ID.
        candidates.append((native_id, json.dumps(pal, sort_keys=True, separators=(",", ":")), pal))

    pals: list[dict[str, Any]] = []
    occurrence: dict[str, int] = {}
    # Reserve every primary ID first.  A damaged save may contain a literal
    # native ID that looks like a generated duplicate suffix, so allocation
    # must avoid both prior output and every real primary ID.
    reserved = {f"pal:{native_id}" for native_id, _, _ in candidates}
    allocated: set[str] = set()
    for native_id, _, pal in sorted(candidates, key=lambda candidate: (candidate[0], candidate[1])):
        occurrence[native_id] = occurrence.get(native_id, 0) + 1
        snapshot_local_id = f"pal:{native_id}"
        if occurrence[native_id] > 1:
            snapshot_local_id = f"{snapshot_local_id}:duplicate:{occurrence[native_id]}"
            while snapshot_local_id in reserved or snapshot_local_id in allocated:
                snapshot_local_id += ":x"
        allocated.add(snapshot_local_id)
        pals.append({"snapshotLocalId": snapshot_local_id, **pal})
    return pals


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
        character_last_online = _timestamp_field(data, "LastOnlineTime")
        roster_last_online = memberships[native_id][1] if native_id in memberships else {"state": "absent", "value": None}
        players.append({
            "snapshotLocalId": f"player:{native_id}",
            "nativeId": {"state": "present", "value": native_id},
            "displayName": _field(data, "NickName"),
            "guild": {"state": "present", "value": f"guild:{memberships[native_id][0]}"} if native_id in memberships else {"state": "absent", "value": None},
            "level": _field(data, "Level", numeric=True), "experience": _field(data, "Exp", numeric=True),
            "points": _field(save_data, "TechnologyPoint", numeric=True),
            "technology": _list_field(save_data, "UnlockedTechnologyNames"),
            "recipes": _list_field(save_data, "UnlockedRecipeTechnologyNames"),
            "quests": _list_field(save_data, "CompletedQuestArray"),
            "lastOnline": character_last_online if character_last_online["state"] == "present" else roster_last_online,
            "inventoryReferences": _references(save_data, "InventoryContainerIds", "container"),
            "equipmentReferences": _references(save_data, "EquipItemContainerId", "equipment"),
            "position": {"state": "absent", "value": None}, "state": _field(data, "State"),
        })
    return sorted(players, key=lambda player: player["snapshotLocalId"]), sorted(set(warnings))


WORLD_FAMILIES = ("guilds", "settlements", "workers", "facilities", "structures", "containers", "itemSlots", "equipment", "mapObjects", "workState", "dungeons", "camps", "invaders", "oilRigs", "supplySystems")


def extract_v2_world(level: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """Build closed world-family projections; unknown native shapes stay raw-only."""
    world = _world(level)
    result: dict[str, list[dict[str, Any]]] = {family: [] for family in WORLD_FAMILIES}
    warnings: list[str] = []
    source_keys = {"guilds": "GroupSaveDataMap", "settlements": "BaseCampSaveData", "mapObjects": "MapObjectSaveData"}
    for family, source_key in source_keys.items():
        raw = world.get(source_key)
        if raw is None:
            warnings.append(f"{family}-absent")
            continue
        values = raw.get("value", []) if isinstance(raw, dict) else []
        if not isinstance(values, list):
            warnings.append(f"{family}-malformed")
            continue
        for index, value in enumerate(values):
            result[family].append({"snapshotLocalId": f"{family}:{index}", "references": [], "state": "present"})
    for family in WORLD_FAMILIES:
        if family not in source_keys:
            warnings.append(f"{family}-unsupported")
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
        "domainCounts": {"players": len(players), "pals": len(pals), **{key: len(value) for key, value in world.items()}},
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
            "guildId": memberships.get(native_id, (None, {"state": "absent", "value": None}))[0],
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
