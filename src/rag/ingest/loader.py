"""Download the FastAPI tutorial pages and turn them into Documents.

Ingestion step 2 (see ingest/__main__.py). Input: nothing. Output: list[Document].

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
    # Step 2f: the pages a NEW user's first questions are about (what is FastAPI,
    # why use it, how to install it, who made it). The tutorial alone can't answer
    # them. See docs/learning/02f-corpus-overview-pages.md.
    "index",
    "features",
    "history-design-future",
    "alternatives",
    "deployment/index",
]

# Sections that are marketing or page chrome, not documentation. They would only
# add chunks that match nothing a user asks. Removed whole, by heading title.
DROP_SECTIONS = {
    "index": [
        "Sponsors",
        "Opinions",
        "FastAPI mini documentary",
        "**Typer**, the FastAPI of CLIs",
    ],
}

# Matches a whole line like:  {* ../../docs_src/body/tutorial001_py310.py hl[2] *}
# and captures the file path ("../../docs_src/body/tutorial001_py310.py").
# The "hl[2]" part (lines to highlight on the website) is ignored.
INCLUDE_RE = re.compile(r"^\{\*\s+(?P<path>\S+)(?P<rest>.*?)\*\}\s*$", re.MULTILINE)

# Matches the page title line:  # Query Parameters { #query-parameters }
# and captures "Query Parameters" (without the { #anchor } part).
TITLE_RE = re.compile(r"^#\s+(.+?)(?:\s*\{\s*#[^}]*\})?\s*$", re.MULTILINE)

# A Fetcher is any function "repo path -> file text". The real one downloads over
# HTTP; tests pass a dict lookup instead. Passing the function in (instead of
# calling httpx directly) is what makes this module testable without a network.
Fetcher = Callable[[str], str]


def page_url(page: str) -> str:
    """Where the page lives on the website, used for citation links.

    tutorial/query-params        -> https://fastapi.tiangolo.com/tutorial/query-params/
    tutorial/dependencies/index  -> https://fastapi.tiangolo.com/tutorial/dependencies/
    """
    path = page.removesuffix("index").removesuffix("/")
    return f"{SITE_BASE}{path}/" if path else SITE_BASE


FRONT_MATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
STYLE_RE = re.compile(r"<style>.*?</style>\s*", re.DOTALL)
CENTERED_RE = re.compile(r"<p align=\"center\">.*?</p>\s*", re.DOTALL)  # logo and badges
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)(?:\s*\{\s*#[^}]*\})?\s*$")


def drop_sections(text: str, titles: list[str]) -> str:
    """Remove each section with one of these titles, up to the next heading of the
    same or a higher level (so its sub-sections go with it)."""
    out: list[str] = []
    skip_level = 0  # 0 = not skipping
    for line in text.split("\n"):
        m = HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            if skip_level and level <= skip_level:
                skip_level = 0
            if not skip_level and m.group(2).strip() in titles:
                skip_level = level
        if not skip_level:
            out.append(line)
    return "\n".join(out)


def clean_page(page: str, text: str) -> str:
    """Take out page chrome that is noise for search: front matter, <style>, the
    centered logo/badge block and the sections listed in DROP_SECTIONS. Pages
    without any of these come out unchanged."""
    text = FRONT_MATTER_RE.sub("", text)
    text = STYLE_RE.sub("", text)
    text = CENTERED_RE.sub("", text)
    return drop_sections(text, DROP_SECTIONS.get(page, []))


def resolve_includes(markdown: str, fetch: Fetcher) -> str:
    """Replace every {* path *} directive with the file's content as a code block.

    Before:   {* ../../docs_src/body/tutorial001_py310.py hl[2] *}
    After:    ```python
              from fastapi import FastAPI
              ...
              ```
    """

    # re.sub calls replace() once per match and puts its return value in place
    # of the matched line.
    def replace(match: re.Match) -> str:
        # The path is written relative to docs/en/docs/ ("../../docs_src/x.py"),
        # but the files actually live at the repo root ("docs_src/x.py").
        rel = match.group("path").split("docs_src/", 1)[-1]
        try:
            code = fetch(f"docs_src/{rel}").rstrip()
        except httpx.HTTPError:
            # One missing example should not fail the whole page: drop it and go on.
            return ""
        return f"```python\n{code}\n```"

    return INCLUDE_RE.sub(replace, markdown)


def make_fetcher(version: str, cache_dir: str | Path, client: httpx.Client) -> Fetcher:
    """Build a Fetcher that downloads repo files and caches them on disk.

    First call for a path:  HTTP GET from raw.githubusercontent.com, save to
                            data/raw/<version>/<path>, return the text.
    Later calls:            read the saved file, no network.
    The cache makes re-runs fast and lets ingestion work offline.
    """
    cache = Path(cache_dir) / version

    # fetch() is a closure: it "remembers" cache, client and version from the
    # enclosing function, so callers only pass the path.
    def fetch(repo_path: str) -> str:
        cached = cache / repo_path
        if cached.exists():
            return cached.read_text(encoding="utf-8")
        resp = client.get(RAW_BASE.format(version=version) + repo_path)
        resp.raise_for_status()  # turn 404/500 into an exception instead of saving an error page
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(resp.text, encoding="utf-8")
        return resp.text

    return fetch


def load_page(page: str, fetch: Fetcher) -> Document:
    """One page path -> one Document with its code examples inlined."""
    raw = fetch(f"docs/en/docs/{page}.md")  # e.g. docs/en/docs/tutorial/body.md
    text = resolve_includes(clean_page(page, raw), fetch)
    m = TITLE_RE.search(text)
    title = m.group(1).strip() if m else page
    return Document(id=page, title=title, url=page_url(page), text=text)


def load_documents(version: str, cache_dir: str | Path) -> list[Document]:
    """Entry point used by ingestion: all pages in PAGES, in order."""
    # One HTTP client for all requests: it reuses the TCP/TLS connection, which
    # is much faster than opening a new connection for each of ~200 files.
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        fetch = make_fetcher(version, cache_dir, client)
        return [load_page(p, fetch) for p in PAGES]
