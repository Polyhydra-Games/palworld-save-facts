from datetime import datetime, timezone
from pathlib import Path

from palworld_save_facts.cli import main
from palworld_save_facts.extract import SCHEMA_V1, extract_v1


def property(value):
    return {"value": value}


def test_extracts_private_v1_facts_without_writing_input():
    level = {
        "properties": {"worldSaveData": {"value": {
            "CharacterSaveParameterMap": {"value": [
                {"key": {"PlayerUId": property("player-a")}, "value": {"RawData": {"value": {"object": {"SaveParameter": {"value": {
                    "IsPlayer": property(True), "Level": property(23)}}}}}}},
                {"key": {}, "value": {"RawData": {"value": {"object": {"SaveParameter": {"value": {"IsPlayer": property(False)}}}}}}},
            ]},
            "GroupSaveDataMap": {"value": [{"key": property("guild-a"), "value": {"RawData": {"value": {
                "group_type": "EPalGroupType::Guild", "players": [{"player_uid": "player-a"}]}}}}]},
            "BaseCampSaveData": {"value": [{}, {}]},
        }}}}
    player = {"properties": {"SaveData": {"value": {
        "TechnologyPoint": property(7),
        "UnlockedRecipeTechnologyNames": property({"values": [property("RecipeA"), property("RecipeB")]}),
        "CompletedQuestArray": property({"values": [property("QuestA")]}),
    }}}}

    facts = extract_v1(level, {"player-a": player}, datetime(2026, 7, 17, 20, 0, tzinfo=timezone.utc))

    assert facts == {
        "schemaVersion": SCHEMA_V1,
        "observedAt": "2026-07-17T20:00:00Z",
        "players": [{"nativeId": "player-a", "level": 23, "recipes": ["RecipeA", "RecipeB"], "completedQuests": ["QuestA"], "technologyPoints": 7, "guildId": "guild-a"}],
        "guildCount": 1,
        "baseCount": 2,
        "palCount": 1,
    }


def test_cli_writes_one_json_document_from_a_decoded_fixture(capsys):
    fixture = Path(__file__).parent / "fixtures" / "snapshot"

    assert main(["--input", str(fixture), "--schema", SCHEMA_V1]) == 0

    output = capsys.readouterr()
    document = __import__("json").loads(output.out)
    assert output.err == ""
    assert document["schemaVersion"] == SCHEMA_V1
    assert document["players"][0]["nativeId"] == "player-a"
