"""Safe handling of the database URL (step 3d). Written by Ido as exercise 3d-1.

WHERE IT SITS
    config.py holds the URL  ->  db.connect() calls require_tls() and logs redact(url)

Locally the URL is postgresql://rag:rag@localhost:5432/rag. In the cloud (Neon) it is
postgresql://user:SECRET@ep-xxx.neon.tech/neondb?sslmode=require: it carries the PASSWORD
and travels the internet.
"""

from urllib.parse import parse_qs, urlsplit

LOCAL_HOSTS = {"localhost", "127.0.0.1", "db"}  # "db" = the service name in docker compose
SAFE_SSLMODES = {"require", "verify-ca", "verify-full"}


def redact(url: str) -> str:
    """The URL with the password replaced by ***: safe to print or log."""
    password = urlsplit(url).password
    if password is None:
        return url
    return url.replace(f":{password}@", ":***@")


def require_tls(url: str) -> None:
    """Refuse a remote database unless every sslmode in the URL forces encryption.

    libpq's default is sslmode=prefer: TLS if the server offers it, otherwise plain text,
    silently. Every value is checked (not just the first) because libpq uses the LAST one
    when a key is repeated, and we don't want to depend on that rule.
    """
    parts = urlsplit(url)
    if parts.hostname in LOCAL_HOSTS:
        return
    modes = parse_qs(parts.query).get("sslmode", [None])
    if any(mode not in SAFE_SSLMODES for mode in modes):
        # The message names the host, never the password.
        raise ValueError(
            f"Host {parts.hostname} requires sslmode=require, verify-ca or verify-full"
        )
