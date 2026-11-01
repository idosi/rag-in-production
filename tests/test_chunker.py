import itertools

from rag.ingest.chunker import chunk_document, split_sections
from rag.models import Document

DOC = """# Query Parameters { #query-parameters }

Intro paragraph about query parameters.

## Defaults { #defaults }

Query parameters can have defaults.

```python
# This is a comment, not a heading
def read(skip: int = 0):
    return skip
```

## Optional parameters { #optional-parameters }

Use None as default.
"""


def make_doc(text=DOC):
    return Document(
        id="tutorial/query-params",
        title="Query Parameters",
        url="https://fastapi.tiangolo.com/tutorial/query-params/",
        text=text,
    )


def test_sections_follow_headings_and_ignore_hash_in_code():
    sections = split_sections(DOC)
    assert [s.path for s in sections] == [
        ["Query Parameters"],
        ["Query Parameters", "Defaults"],
        ["Query Parameters", "Optional parameters"],
    ]
    assert "# This is a comment" in "\n".join(sections[1].lines)


def test_chunks_carry_heading_path_and_deep_link():
    chunks = chunk_document(make_doc(), chunk_size=1000, chunk_overlap=100)
    defaults = chunks[1]
    assert defaults.heading == "Query Parameters > Defaults"
    assert defaults.text.startswith("Query Parameters > Defaults\n\n")
    assert defaults.url.endswith("/query-params/#defaults")
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_code_block_is_not_split():
    chunks = chunk_document(make_doc(), chunk_size=1000, chunk_overlap=100)
    code_chunks = [c for c in chunks if "```python" in c.text]
    assert len(code_chunks) == 1
    assert code_chunks[0].text.count("```") == 2


def test_chunks_respect_size_and_overlap():
    paragraphs = "\n\n".join(f"Paragraph {i} " + "word " * 30 for i in range(30))
    text = f"# Big page {{ #big }}\n\n{paragraphs}\n"
    chunks = chunk_document(make_doc(text), chunk_size=500, chunk_overlap=200)
    assert len(chunks) > 1
    assert all(len(c.text) <= 500 for c in chunks)
    # Overlap: each chunk after the first starts with the last paragraph of the previous one.
    for prev, cur in itertools.pairwise(chunks):
        last_para = prev.text.split("\n\n")[-1]
        assert cur.text.split("\n\n")[1] == last_para


def test_oversized_block_is_hard_split():
    text = "# Huge\n\n" + "\n".join(f"line {i} " + "x" * 50 for i in range(100))
    chunks = chunk_document(make_doc(text), chunk_size=400, chunk_overlap=0)
    assert len(chunks) > 1
    assert all(len(c.text) <= 400 for c in chunks)
