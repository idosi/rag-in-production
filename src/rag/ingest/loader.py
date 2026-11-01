"""Download the FastAPI tutorial pages and turn them into Documents.

The FastAPI docs are markdown files in the fastapi GitHub repo. Code examples are
not written inline; they are pulled in from separate files with a directive like:

    {* ../../docs_src/query_params/tutorial001_py310.py hl[9] *}

A RAG system that skips those would answer "how do I ..." questions without code,
so we fetch each referenced file and inline it as a fenced code block.
"""

import re
from collections.abc import Callable
from pathlib import Path

import httpx

from rag.models import Document

RAW_BASE = "https://raw.githubusercontent.com/fastapi/fastapi/{version}/"
SITE_BASE = "https://fastapi.tiangolo.com/"

# A fixed, curated list keeps the corpus small enough to understand end to end
# and stable enough to evaluate against. Paths are relative to docs/en/docs/.
PAGES = [
    "tutorial/first-steps",
    "tutorial/path-params",
    "tutorial/query-params",
    "tutorial/body",
    "tutorial/query-params-str-validations",
    "tutorial/path-params-numeric-validations",
    "tutorial/body-multiple-params",
    "tutorial/body-fields",
    "tutorial/body-nested-models",
    "tutorial/schema-extra-example",
    "tutorial/extra-data-types",
    "tutorial/cookie-params",
    "tutorial/header-params",
    "tutorial/response-model",
    "tutorial/extra-models",
    "tutorial/response-status-code",
    "tutorial/request-forms",
    "tutorial/request-files",
    "tutorial/request-forms-and-files",
    "tutorial/handling-errors",
    "tutorial/path-operation-configuration",
    "tutorial/encoder",
    "tutorial/body-updates",
    "tutorial/dependencies/index",
    "tutorial/dependencies/classes-as-dependencies",
    "tutorial/dependencies/sub-dependencies",
    "tutorial/dependencies/dependencies-in-path-operation-decorators",
    "tutorial/dependencies/global-dependencies",
    "tutorial/dependencies/dependencies-with-yield",
    "tutorial/security/index",
    "tutorial/security/first-steps",
    "tutorial/security/get-current-user",
    "tutorial/security/simple-oauth2",
    "tutorial/security/oauth2-jwt",
    "tutorial/middleware",
    "tutorial/cors",
    "tutorial/sql-databases",
    "tutorial/bigger-applications",
    "tutorial/background-tasks",
    "tutorial/metadata",
    "tutorial/static-files",
    "tutorial/testing",
    "tutorial/debugging",
]

INCLUDE_RE = re.compile(r"^\{\*\s+(?P<path>\S+)(?P<rest>.*?)\*\}\s*$", re.MULTILINE)
TITLE_RE = re.compile(r"^#\s+(.+?)(?:\s*\{\s*#[^}]*\})?\s*$", re.MULTILINE)

Fetcher = Callable[[str], str]


def page_url(page: str) -> str:
    """tutorial/dependencies/index -> https://fastapi.tiangolo.com/tutorial/dependencies/"""
    path = page.removesuffix("/index").removesuffix("index")
    return f"{SITE_BASE}{path}/"


def resolve_includes(markdown: str, fetch: Fetcher) -> str:
    """Replace every {* path *} directive with the file's content as a code block."""

    def replace(match: re.Match) -> str:
        # "../../docs_src/x.py" is relative to docs/en/docs; the files live at repo root.
        rel = match.group("path").split("docs_src/", 1)[-1]
        try:
            code = fetch(f"docs_src/{rel}").rstrip()
        except httpx.HTTPError:
            return ""  # a missing example must not break ingestion of the page
        return f"```python\n{code}\n```"

    return INCLUDE_RE.sub(replace, markdown)


def make_fetcher(version: str, cache_dir: str | Path, client: httpx.Client) -> Fetcher:
    """Fetch repo files over HTTP, caching them on disk.

    The cache makes re-running ingestion fast and lets it work offline.
    """
    cache = Path(cache_dir) / version

    def fetch(repo_path: str) -> str:
        cached = cache / repo_path
        if cached.exists():
            return cached.read_text(encoding="utf-8")
        resp = client.get(RAW_BASE.format(version=version) + repo_path)
        resp.raise_for_status()
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(resp.text, encoding="utf-8")
        return resp.text

    return fetch


def load_page(page: str, fetch: Fetcher) -> Document:
    raw = fetch(f"docs/en/docs/{page}.md")
    text = resolve_includes(raw, fetch)
    m = TITLE_RE.search(text)
    title = m.group(1).strip() if m else page
    return Document(id=page, title=title, url=page_url(page), text=text)


def load_documents(version: str, cache_dir: str | Path) -> list[Document]:
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        fetch = make_fetcher(version, cache_dir, client)
        return [load_page(p, fetch) for p in PAGES]
