import httpx

from rag.ingest.loader import load_page, page_url, resolve_includes


def test_page_url_handles_index_pages():
    assert page_url("tutorial/body") == "https://fastapi.tiangolo.com/tutorial/body/"
    assert page_url("tutorial/dependencies/index") == (
        "https://fastapi.tiangolo.com/tutorial/dependencies/"
    )


def test_include_directive_is_replaced_with_code():
    files = {"docs_src/body/tutorial001_py310.py": "from fastapi import FastAPI\n"}
    md = "Text\n\n{* ../../docs_src/body/tutorial001_py310.py hl[2] *}\n\nMore"
    out = resolve_includes(md, lambda p: files[p])
    assert "```python\nfrom fastapi import FastAPI\n```" in out
    assert "{*" not in out


def test_missing_include_does_not_break_the_page():
    def fetch(path):
        raise httpx.HTTPStatusError("404", request=None, response=None)

    out = resolve_includes("A\n{* ../../docs_src/missing.py *}\nB", fetch)
    assert out == "A\n\nB"


def test_load_page_extracts_title():
    files = {"docs/en/docs/tutorial/body.md": "# Request Body { #request-body }\n\nHello"}
    doc = load_page("tutorial/body", lambda p: files[p])
    assert doc.title == "Request Body"
    assert doc.id == "tutorial/body"
