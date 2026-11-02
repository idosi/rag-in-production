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
