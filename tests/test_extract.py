from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import zstandard

from palworld_save_facts.cli import main
from palworld_save_facts.canonical import adjacent_summary, canonical_bytes, snapshot_id
from palworld_save_facts.extract import SCHEMA_V1, SCHEMA_V2, extract_v1, extract_v2, extract_v2_pals, extract_v2_players, extract_v2_world
from palworld_save_facts.analyze import analyze
from palworld_save_facts.extract import ExtractionError
from palworld_save_facts.limits import AnalysisLimits, DEFAULT_ANALYSIS_LIMITS


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


def test_v2_pal_projection_is_deterministic_and_does_not_model_causes():
    level = {"properties": {"worldSaveData": {"value": {"CharacterSaveParameterMap": {"value": [
        {"key": {"InstanceId": property("pal-b")}, "value": {"RawData": {"value": {"object": {"SaveParameter": {"value": {"IsPlayer": property(False), "CharacterID": property("SheepBall"), "Level": property(4)}}}}}}},
        {"key": {"InstanceId": property("pal-a")}, "value": {"RawData": {"value": {"object": {"SaveParameter": {"value": {"IsPlayer": property(False), "CharacterID": property("Lamball"), "Level": property(3)}}}}}}},
    ]}}}}}
    pals = extract_v2_pals(level, datetime(2026, 7, 18, tzinfo=timezone.utc))
    assert [pal["snapshotLocalId"] for pal in pals] == ["pal:pal-a", "pal:pal-b"]
    assert pals[0]["species"] == {"state": "present", "value": "Lamball"}
    assert "captureCause" not in pals[0]


def test_canonicalization_and_adjacent_summary_are_deterministic_and_cause_neutral():
    left = {"pals": [{"snapshotLocalId": "pal-b", "rank": 1}, {"snapshotLocalId": "pal-a", "rank": 1}]}
    right = {"pals": [{"rank": 2, "snapshotLocalId": "pal-a"}, {"snapshotLocalId": "pal-c", "rank": 1}]}
    assert canonical_bytes(left) == canonical_bytes({"pals": list(reversed(left["pals"]))})
    assert snapshot_id([{"sha256": "b", "path": "b"}, {"path": "a", "sha256": "a"}]) == snapshot_id([{"path": "a", "sha256": "a"}, {"sha256": "b", "path": "b"}])
    assert adjacent_summary(left, right)["pals"] == {"added": 1, "removed": 1, "changed": 1}


def test_v2_players_are_ordered_and_missing_saves_are_redacted_warnings():
    level = {"properties": {"worldSaveData": {"value": {"CharacterSaveParameterMap": {"value": [
        {"key": {"PlayerUId": property("player-b")}, "value": {"RawData": {"value": {"object": {"SaveParameter": {"value": {"IsPlayer": property(True), "Level": property(2)}}}}}}},
        {"key": {"PlayerUId": property("player-a")}, "value": {"RawData": {"value": {"object": {"SaveParameter": {"value": {"IsPlayer": property(True), "Level": property(1)}}}}}}},
    ]}, "GroupSaveDataMap": {"value": []}}}}}
    players, warnings = extract_v2_players(level, {})
    assert [player["snapshotLocalId"] for player in players] == ["player:player-a", "player:player-b"]
    assert warnings == ["player-save-missing"]


def test_v2_players_project_guild_roles_last_online_and_container_references():
    player_data = {"IsPlayer": property(True)}
    player_entry = {"key": {"PlayerUId": property("player-a")}, "value": {"RawData": {"value": {"object": {"SaveParameter": {"value": player_data}}}}}}
    guild_data = {
        "group_type": "EPalGroupType::Guild",
        "players": [{"player_uid": "player-a", "player_role": property("Admin"), "player_info": {"last_online_real_time": property(1234)}}],
    }
    guild_entry = {"key": property("guild-a"), "value": {"RawData": {"value": guild_data}}}
    world = {"CharacterSaveParameterMap": {"value": [player_entry]}, "GroupSaveDataMap": {"value": [guild_entry]}}
    level = {"properties": {"worldSaveData": {"value": world}}}
    save_data = {
        "InventoryContainerIds": property({"values": [{"ID": property("bag-b")}, {"ID": property("bag-a")}]}),
        "EquipItemContainerId": property({"ID": property("equip-a")}),
    }
    saves = {"player-a": {"properties": {"SaveData": {"value": save_data}}}}

    players, warnings = extract_v2_players(level, saves)

    assert warnings == []
    assert players[0]["guild"] == {"state": "present", "value": "guild:guild-a"}
    assert "guildRole" not in players[0]
    assert players[0]["lastOnline"] == {"state": "present", "value": "1970-01-01T00:20:34Z"}
    assert players[0]["inventoryReferences"] == [{"snapshotLocalId": "container:bag-a"}, {"snapshotLocalId": "container:bag-b"}]
    assert players[0]["equipmentReferences"] == [{"snapshotLocalId": "equipment:equip-a"}]


def test_v2_world_marks_absent_malformed_and_unsupported_families_without_raw_objects():
    level = {"properties": {"worldSaveData": {"value": {"BaseCampSaveData": {"value": [{}]}, "GroupSaveDataMap": {"value": "bad"}}}}}
    world, warnings = extract_v2_world(level)
    assert world["settlements"] == [{"snapshotLocalId": "settlements:0", "references": [], "state": "present"}]
    assert "guilds-malformed" in warnings and "facilities-unsupported" in warnings


def test_v2_snapshot_assembly_does_not_change_v1_output_contract():
    fixture = Path(__file__).parent / "fixtures" / "snapshot"
    level = __import__("json").loads((fixture / "Level.json").read_text())
    players = {"player-a": __import__("json").loads((fixture / "Players" / "player-a.json").read_text())}
    observed = datetime(2026, 7, 18, tzinfo=timezone.utc)
    legacy = extract_v1(level, players, observed)
    v2 = extract_v2(level, players, observed, snapshot_id="snapshot-a", source_digest="sha256:a", parser_version="test", decoder_version="test")
    assert legacy["schemaVersion"] == SCHEMA_V1 and v2["schemaVersion"] == SCHEMA_V2
    assert v2["snapshotId"] == "snapshot-a" and v2["domainCounts"]["players"] == 1
    assert "nativeId" not in legacy["players"][0] or legacy["players"][0]["nativeId"] == "player-a"


def test_v1_v2_compatibility_documentation_keeps_pal_mapping_and_removal_boundary_explicit():
    document = (Path(__file__).parents[1] / "docs" / "v1-v2-compatibility.md").read_text(encoding="utf-8")
    assert "`palCount`" in document
    assert "`domainCounts.pals`" in document
    assert "malformed/unaddressable" in document
    assert "Decoder-native" in document
    assert "separately approved removal" in document


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(path for path in root.rglob("*") if path.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_analyze_writes_private_artifacts_atomically_without_changing_input(tmp_path, capsys):
    fixture = Path(__file__).parent / "fixtures" / "snapshot"
    output = tmp_path / "private-analysis"
    before = _tree_digest(fixture)

    assert main(["analyze", "--input", str(fixture), "--output", str(output)]) == 0

    stdout = capsys.readouterr().out
    result = json.loads(stdout)
    assert _tree_digest(fixture) == before
    assert result["inputUnchanged"] is True
    assert result["raw"]["compression"] == "zstd"
    assert "sourceManifest" not in result
    assert "Players/" not in stdout
    assert "player-a" not in stdout
    assert set(path.name for path in output.iterdir()) == {"raw.json.zst", "snapshot.json", "result.json"}
    private_result = json.loads((output / "result.json").read_text())
    assert private_result["sourceManifest"] == [
        {
            "path": "Level.json",
            "sha256": hashlib.sha256((fixture / "Level.json").read_bytes()).hexdigest(),
        },
        {
            "path": "Players/player-a.json",
            "sha256": hashlib.sha256((fixture / "Players/player-a.json").read_bytes()).hexdigest(),
        },
    ]
    raw = json.loads(zstandard.ZstdDecompressor().decompress((output / "raw.json.zst").read_bytes()))
    snapshot = json.loads((output / "snapshot.json").read_text())
    assert raw["level"]["properties"]["worldSaveData"]
    assert raw["players"]["player-a"]
    assert snapshot["schemaVersion"] == SCHEMA_V1


def test_analyze_refuses_output_inside_input_or_existing_directory(tmp_path, capsys):
    fixture = Path(__file__).parent / "fixtures" / "snapshot"

    assert main(["analyze", "--input", str(fixture), "--output", str(fixture / "output")]) == 2
    assert capsys.readouterr().err == "palworld-save-facts: analysis-failed\n"

    output = tmp_path / "existing"
    output.mkdir()
    assert main(["analyze", "--input", str(fixture), "--output", str(output)]) == 2
    assert capsys.readouterr().err == "palworld-save-facts: analysis-failed\n"


def test_analysis_resource_defaults_match_the_private_release_contract():
    assert DEFAULT_ANALYSIS_LIMITS == AnalysisLimits(
        max_concurrent_analyses=1,
        timeout_seconds=600,
        max_working_set_bytes=2 * 1024 * 1024 * 1024,
        max_raw_artifact_bytes=4 * 1024 * 1024 * 1024,
        max_normalized_output_bytes=128 * 1024 * 1024,
    )


def test_analyze_fails_closed_when_a_resource_limit_is_exceeded(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "snapshot"

    with __import__("pytest").raises(ExtractionError, match="raw-artifact-size-limit-exceeded"):
        analyze(
            fixture,
            tmp_path / "output",
            lambda path: json.loads(path.read_text()),
            lambda snapshot: {"player-a": json.loads((snapshot / "Players" / "player-a.json").read_text())},
            limits=AnalysisLimits(max_raw_artifact_bytes=1),
        )
