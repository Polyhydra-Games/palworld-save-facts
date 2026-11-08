"""Structural hardening rules for .github/workflows/release.yml (no network)."""
import os
import re
from pathlib import Path

import yaml

WORKFLOW = Path(os.environ.get(
    "RELEASE_WORKFLOW",
    Path(__file__).resolve().parent.parent / ".github/workflows/release.yml",
))
SHA = re.compile(r"^[0-9a-f]{40}$")
WRITE = {"write", "write-all"}


def load():
    return yaml.safe_load(WORKFLOW.read_text())


def steps():
    for name, job in load()["jobs"].items():
        for step in job.get("steps", []):
            yield name, step


def test_top_level_permissions_read_only():
    perms = load()["permissions"]
    assert perms == {"contents": "read"}


def test_every_job_declares_permissions():
    for name, job in load()["jobs"].items():
        assert "permissions" in job, f"{name} lacks permissions"


def test_only_expected_jobs_get_write_scopes():
    allowed = {
        "oci": {"packages"},
        "publish": {"contents", "attestations", "id-token"},
    }
    for name, job in load()["jobs"].items():
        writes = {k for k, v in job["permissions"].items() if v in WRITE}
        assert writes <= allowed.get(name, set()), f"{name} has excess write: {writes}"


def test_every_checkout_disables_persisted_credentials():
    seen = 0
    for name, step in steps():
        if step.get("uses", "").startswith("actions/checkout@"):
            seen += 1
            assert step.get("with", {}).get("persist-credentials") is False, name
    assert seen >= 4


def test_every_action_pinned_to_full_sha():
    for name, step in steps():
        uses = step.get("uses")
        if uses and not uses.startswith("./"):
            ref = uses.split("@", 1)[1]
            assert SHA.match(ref), f"{name}: {uses} is not SHA-pinned"
    for line in WORKFLOW.read_text().splitlines():
        m = re.search(r"uses:\s*\S+@[0-9a-f]{40}(.*)$", line)
        if m:
            assert re.match(r"\s+#\s*v\d", m.group(1)), f"missing version comment: {line}"


def test_allow_overwrite_input_defaults_false():
    inp = load()[True]["workflow_dispatch"]["inputs"]["allow_overwrite"]  # YAML 'on' -> True
    assert inp["type"] == "boolean" and inp["default"] is False


def test_overwrite_and_recheck_steps_present_in_order():
    jobs = load()["jobs"]
    runs = lambda j: [s.get("run", "") for s in jobs[j]["steps"]]
    assert any("check-no-overwrite.sh release" in r for r in runs("verify_tag"))
    assert any("check-no-overwrite.sh image" in r for r in runs("oci"))
    pub = jobs["publish"]["steps"]
    idx_re = next(i for i, s in enumerate(pub) if "recheck-release-tag.sh" in s.get("run", ""))
    idx_rel = next(i for i, s in enumerate(pub) if s.get("uses", "").startswith("softprops/action-gh-release@"))
    assert idx_re < idx_rel


def test_no_inline_expressions_in_run_scripts_for_untrusted_inputs():
    for name, step in steps():
        run = step.get("run", "")
        assert "inputs." not in run and "github.event.inputs" not in run, name
