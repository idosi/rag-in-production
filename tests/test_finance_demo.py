"""Checks the synthetic finance-office demo corpus (examples/finance-office/).

The corpus is not ingested by default. These tests make sure it stays usable:
every golden-set answer points at a section the chunker really produces, so a
retrieval eval on it would measure search quality, not typos in the golden set.
No database, no network.
"""

import json
from pathlib import Path

from rag.ingest.chunker import chunk_document
from rag.models import Document

DEMO = Path(__file__).resolve().parent.parent / "examples" / "finance-office"


def load_demo_documents() -> list[Document]:
    docs = []
    for path in sorted((DEMO / "corpus").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title = text.splitlines()[0].lstrip("# ").split(" {")[0]
        docs.append(
            Document(
                id=path.stem,
                title=title,
                url=f"https://intranet.example/policies/{path.stem}/",
                text=text,
            )
        )
    return docs


def section_keys(docs: list[Document]) -> set[str]:
    keys = set()
    for doc in docs:
        for chunk in chunk_document(doc, chunk_size=1200, chunk_overlap=200):
            anchor = chunk.url.split("#", 1)[1] if "#" in chunk.url else ""
            keys.add(f"{chunk.document_id}#{anchor}")
    return keys


def test_every_golden_answer_points_at_a_real_section():
    golden = json.loads((DEMO / "golden_set.json").read_text(encoding="utf-8"))
    keys = section_keys(load_demo_documents())
    missing = {q["id"]: r for q in golden for r in q["relevant"] if r not in keys}
    assert missing == {}


def test_golden_set_has_unanswerable_questions_and_unique_ids():
    golden = json.loads((DEMO / "golden_set.json").read_text(encoding="utf-8"))
    ids = [q["id"] for q in golden]
    assert len(ids) == len(set(ids))
    unanswerable = [q for q in golden if q["category"] == "unanswerable"]
    assert len(unanswerable) >= 4
    assert all(q["relevant"] == [] for q in unanswerable)


def test_every_demo_document_says_it_is_synthetic():
    for doc in load_demo_documents():
        assert "SYNTHETIC DEMO DOCUMENT" in doc.text, doc.id
