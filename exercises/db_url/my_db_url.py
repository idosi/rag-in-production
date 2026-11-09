"""EXERCISE 3d-1: a database URL that is safe to log, and safe to connect to.

Run the tests:   uv run pytest exercises/db_url -q
They all fail now. Make them pass one by one, and commit after each green test.

WHY
    Locally the database is on your laptop: postgresql://rag:rag@localhost:5432/rag
    In the cloud it is Neon, across the internet:
        postgresql://neondb_owner:npg_S3cr3t@ep-cool-river-123.eu-central-1.aws.neon.tech/neondb?sslmode=require

    Two things can go wrong with that string:
    1. It contains the PASSWORD. The day someone writes log.info(f"connecting to {url}"),
       the password is in Cloud Logging, readable by everyone with log access, for 30 days.
       redact() gives a version that is safe to print.
    2. Without sslmode=require, the connection MAY be unencrypted: the password and every
       chunk travel the internet in plain text. libpq's default is sslmode=prefer, which
       means "TLS if the server offers it, otherwise plain text, silently". require_tls()
       refuses to start with a remote URL that does not insist on TLS.
       (Neon refuses plain connections itself, but our code should not depend on that:
       the next database provider may not.)

THE SPEC
    redact(url) -> str
        The same URL with the password replaced by "***". Everything else unchanged
        (user, host, port, database, ?query). A URL without a password is returned as is.

    require_tls(url) -> None
        Local hosts (localhost, 127.0.0.1, db): fine, return.
        ("db" is the database's name inside docker compose.)
        Any other host: the query must say sslmode=require, verify-ca or verify-full.
        Otherwise raise ValueError. The message names the host and must NOT contain the password.

HINTS (open one at a time, only when stuck)
    1. from urllib.parse import urlsplit, parse_qs
       parts = urlsplit(url) gives parts.hostname, parts.password, parts.query
    2. parse_qs("sslmode=require&channel_binding=require") ->
       {"sslmode": ["require"], "channel_binding": ["require"]}   (lists! one key can repeat)
    3. For redact, the simplest correct trick: the password appears in the URL exactly once
       as ":<password>@". Replace that piece.
    4. "prefer" and "allow" are NOT enough: both fall back to plain text silently.
"""

LOCAL_HOSTS = {"localhost", "127.0.0.1", "db"}
SAFE_SSLMODES = {"require", "verify-ca", "verify-full"}


def redact(url: str) -> str:
    raise NotImplementedError("your code here")


def require_tls(url: str) -> None:
    raise NotImplementedError("your code here")
