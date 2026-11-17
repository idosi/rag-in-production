"""Guardrails for the deployment files (step 3a). They can't build the image, but they
catch the mistakes that matter: a secret in the image, running as root, a broken
compose file, a CI job without a database."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def test_dockerfile_runs_as_a_non_root_user():
    lines = (ROOT / "Dockerfile").read_text().splitlines()
    users = [line.split()[1] for line in lines if line.startswith("USER ")]
    assert users and users[-1] != "root"


def test_dockerignore_keeps_secrets_out_of_the_image():
    ignored = (ROOT / ".dockerignore").read_text().splitlines()
    assert ".env" in ignored
    assert not any(
        line.startswith("COPY .env") for line in (ROOT / "Dockerfile").read_text().splitlines()
    )


def test_compose_api_is_behind_a_profile_and_waits_for_a_healthy_db():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    api = compose["services"]["api"]
    assert api["profiles"] == ["app"]  # so `make up` still starts only Postgres
    assert api["depends_on"]["db"]["condition"] == "service_healthy"
    assert "db:5432" in api["environment"]["DATABASE_URL"]  # the service name, not localhost


def test_ci_runs_tests_against_postgres_with_least_privilege():
    # PyYAML reads the key `on` as the boolean True; either spelling is accepted.
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    assert ci["permissions"] == {"contents": "read"}
    assert "pgvector/pgvector" in ci["jobs"]["test"]["services"]["postgres"]["image"]
    assert "docker" in ci["jobs"]


def test_cloud_build_uses_buildkit_and_pushes_the_tagged_image():
    build = yaml.safe_load((ROOT / "cloudbuild.yaml").read_text())
    step = build["steps"][0]
    assert "DOCKER_BUILDKIT=1" in step["env"]  # the Dockerfile needs it (RUN --mount)
    assert build["images"] == ["${_IMAGE}"]


def test_cloud_build_upload_never_includes_the_env_file():
    # gcloud uploads the source to Google. Without .gcloudignore it would use .gitignore.
    assert "#!include:.dockerignore" in (ROOT / ".gcloudignore").read_text()


def test_deploy_takes_secrets_from_secret_manager_not_from_plain_env_vars():
    make = (ROOT / "Makefile").read_text()
    deploy = make.split("\ndeploy:")[1].split("\n\n")[0]
    assert "--set-secrets" in deploy
    for name in ("ANTHROPIC_API_KEY", "DATABASE_URL", "API_KEYS"):
        assert f"{name}=" in deploy.split("--set-secrets")[1].split()[0]
    assert "--max-instances" in deploy  # a cap on cost and on the per-instance budget


def test_healthcheck_really_runs_and_follows_the_port(monkeypatch):
    # Not just "the words PORT and 8000 appear": the Python in the HEALTHCHECK is executed
    # (urlopen replaced by a recorder). A bad '%' format once passed a text check and would
    # have made the container permanently unhealthy.
    import json
    import re
    import urllib.request

    text = (ROOT / "Dockerfile").read_text().replace("\\\n", " ")
    check = [ln for ln in text.splitlines() if ln.startswith("HEALTHCHECK")][-1]
    argv = json.loads(re.search(r"\bCMD\s+(\[.*\])", check).group(1))
    urls = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=None: urls.append(url))
    monkeypatch.setenv("PORT", "8080")
    exec(argv[2], {})
    monkeypatch.delenv("PORT")
    exec(argv[2], {})
    assert urls == ["http://127.0.0.1:8080/health", "http://127.0.0.1:8000/health"]


# ---- CD (step 3f): .github/workflows/deploy.yml, written by Ido as exercise 3f ----


def _deploy_workflow():
    return yaml.safe_load((ROOT / ".github/workflows/deploy.yml").read_text())


def test_cd_runs_only_after_ci_succeeded_on_main_and_never_on_push():
    wf = _deploy_workflow()
    on = wf.get("on", wf.get(True))
    assert "push" not in on and "pull_request" not in on
    assert on["workflow_run"]["workflows"] == ["CI"]  # must match the name in ci.yml
    assert on["workflow_run"]["branches"] == ["main"]
    assert "success" in wf["jobs"]["deploy"]["if"]  # workflow_run also fires when CI failed


def test_cd_ci_workflow_name_matches_what_deploy_waits_for():
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    assert ci["name"] == "CI"


def test_cd_uses_no_key_file_and_only_the_deploy_job_can_ask_for_an_oidc_token():
    wf = _deploy_workflow()
    assert "credentials_json" not in yaml.safe_dump(wf)
    assert wf["permissions"] == {"contents": "read"}
    assert wf["jobs"]["deploy"]["permissions"] == {"contents": "read", "id-token": "write"}


def test_cd_deploys_the_commit_ci_tested_and_tags_the_image_with_it():
    job = _deploy_workflow()["jobs"]["deploy"]
    assert job["steps"][0]["with"]["ref"] == "${{ github.event.workflow_run.head_sha }}"
    assert "head_sha" in job["env"]["IMAGE"] and "latest" not in job["env"]["IMAGE"]


def test_cd_smoke_tests_the_candidate_before_any_traffic_moves():
    steps = [str(s) for s in _deploy_workflow()["jobs"]["deploy"]["steps"]]

    def first(*needles):
        return next(i for i, s in enumerate(steps) if all(n in s for n in needles))

    assert first("--no-traffic") < first("smoke.sh", "candidate---") < first("--to-latest")
