"""Tests for exercise 3f. Do not edit; make them pass by editing my_deploy.yml.

Run:   uv run pytest exercises/cd -q
"""

from pathlib import Path

import pytest
import yaml

FILE = Path(__file__).parent / "my_deploy.yml"


@pytest.fixture(scope="module")
def wf():
    return yaml.safe_load(FILE.read_text())


def triggers(wf):
    return wf.get("on", wf.get(True))  # PyYAML turns the key `on` into True


def steps(wf):
    return wf["jobs"]["deploy"]["steps"]


def index_of(wf, *needles):
    """Position of the first step whose text contains ALL the needles (-1 if none)."""
    for i, step in enumerate(steps(wf)):
        text = str(step)
        if all(n in text for n in needles):
            return i
    return -1


def test_1_runs_after_ci_finishes_on_main_not_on_push(wf):
    t = triggers(wf)
    assert "push" not in t and "pull_request" not in t
    run = t["workflow_run"]
    assert run["workflows"] == ["CI"]
    assert run["types"] == ["completed"]
    assert run["branches"] == ["main"]


def test_2_only_deploys_when_ci_succeeded(wf):
    cond = str(wf["jobs"]["deploy"].get("if", ""))
    assert "workflow_run.conclusion" in cond and "success" in cond


def test_3_least_privilege_id_token_only_on_the_deploy_job(wf):
    assert wf["permissions"] == {"contents": "read"}
    assert wf["jobs"]["deploy"]["permissions"] == {"contents": "read", "id-token": "write"}


def test_4_one_deploy_at_a_time_and_never_cancelled_half_way(wf):
    c = wf["concurrency"]
    assert c["group"]
    assert c["cancel-in-progress"] is False


def test_5_checks_out_the_commit_that_ci_tested(wf):
    first = steps(wf)[0]
    assert first["uses"].startswith("actions/checkout@")
    assert first["with"]["ref"] == "${{ github.event.workflow_run.head_sha }}"


def test_6_authenticates_with_workload_identity_federation_and_no_key_file(wf):
    assert "credentials_json" not in yaml.safe_dump(wf)  # comments do not count, only real keys
    i = index_of(wf, "google-github-actions/auth@")
    assert i >= 0
    w = steps(wf)[i]["with"]
    assert "vars." in w["workload_identity_provider"]
    assert "vars." in w["service_account"]
    assert w["token_format"] == "access_token"


def test_7_logs_in_to_artifact_registry_with_the_access_token(wf):
    i = index_of(wf, "docker/login-action@")
    assert i >= 0
    w = steps(wf)[i]["with"]
    assert w["registry"].endswith("docker.pkg.dev")
    assert w["username"] == "oauth2accesstoken"
    assert "access_token" in w["password"]


def test_8_image_is_pushed_tagged_with_the_commit_sha_never_latest(wf):
    i = index_of(wf, "docker/build-push-action@")
    assert i >= 0
    w = steps(wf)[i]["with"]
    assert w["push"] is True
    tags = str(w["tags"])
    if "env.IMAGE" in tags:  # the name may live in the job's env, one place for build and deploy
        tags += str(wf["jobs"]["deploy"].get("env", {}).get("IMAGE", ""))
    assert "head_sha" in tags
    assert "latest" not in tags


def test_9_new_revision_gets_no_traffic_and_a_candidate_tag(wf):
    i = index_of(wf, "deploy", "--no-traffic", "--tag")
    assert i >= 0
    assert "candidate" in str(steps(wf)[i])


def test_10_smoke_test_runs_on_the_candidate_url_before_traffic_moves(wf):
    deploy = index_of(wf, "--no-traffic")
    smoke = index_of(wf, "smoke.sh", "candidate---")
    promote = index_of(wf, "update-traffic", "--to-latest")
    assert deploy >= 0 and smoke >= 0 and promote >= 0
    assert deploy < smoke < promote


def test_11_the_candidate_tag_is_removed_at_the_end(wf):
    promote = index_of(wf, "update-traffic", "--to-latest")
    cleanup = index_of(wf, "update-traffic", "--remove-tags")
    assert 0 <= promote < cleanup


def test_12_every_third_party_action_is_versioned(wf):
    used = [step["uses"] for step in steps(wf) if "uses" in step]
    assert len(used) >= 5
    assert all("@" in u for u in used)  # never an unpinned action
