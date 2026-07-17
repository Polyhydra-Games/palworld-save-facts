from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SCHEMA_V1 = "palworld-save-facts/v1"


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


def _world(decoded: dict[str, Any]) -> dict[str, Any]:
    return decoded.get("properties", {}).get("worldSaveData", {}).get("value", {})


def _save_data(decoded: dict[str, Any]) -> dict[str, Any]:
    return decoded.get("properties", {}).get("SaveData", {}).get("value", {})


def _character_data(entry: dict[str, Any]) -> dict[str, Any]:
    return entry.get("value", {}).get("RawData", {}).get("value", {}).get("object", {}).get("SaveParameter", {}).get("value", {})


def _player_id(entry: dict[str, Any]) -> str:
    return str(_value(entry.get("key", {}).get("PlayerUId"), ""))


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
