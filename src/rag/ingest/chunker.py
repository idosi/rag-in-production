"""Split markdown documents into chunks.

Ingestion step 5b (see ingest/__main__.py). Input: one Document. Output: list[Chunk].

Strategy (structure-aware, not fixed-size):

1. Split the page into sections at headings. A section is a natural unit of meaning,
   and the heading tells us what it is about.
2. Split each section into blocks (paragraphs, lists, code blocks). A code block is
   never cut in the middle unless it alone is bigger than a chunk.
3. Pack blocks into chunks up to `chunk_size` characters. When a chunk is full, the
   next one starts with the last block of the previous one (overlap), so a thought
   that spans the boundary is not lost.
4. Prefix every chunk with its heading path ("Query Parameters > Defaults"). The
   chunk is embedded and shown to the model with that context, even though the
   heading itself appeared once, far above.

Worked example. This markdown:

    # Query Parameters { #query-parameters }
    Intro text.
    ## Defaults { #defaults }
    Para A.
    ```python
    def read(skip: int = 0): ...
    ```

becomes 2 sections -> 2 chunks:

    Chunk 0  heading="Query Parameters"              url=".../query-params/#query-parameters"
             text="Query Parameters\n\nIntro text."
    Chunk 1  heading="Query Parameters > Defaults"   url=".../query-params/#defaults"
             text="Query Parameters > Defaults\n\nPara A.\n\n```python\n...```"

Read the functions bottom-up: chunk_document() at the end is the entry point and
calls the others in order (split_sections -> split_blocks -> pack -> hard_split).
"""

import re
from dataclasses import dataclass

from rag.models import Chunk, Document

# Matches a markdown heading line and captures its parts:
#   "## Defaults { #defaults }"  ->  hashes="##", text="Defaults", anchor="defaults"
# The anchor is the id of that section on the website; we use it for deep links.
HEADING_RE = re.compile(
    r"^(?P<hashes>#{1,6})\s+(?P<text>.*?)(?:\s*\{\s*#(?P<anchor>[\w-]+)\s*\})?\s*$"
)

# Matches the opening or closing line of a code block (``` or ~~~).
FENCE_RE = re.compile(r"^\s*(```|~~~)")


@dataclass
class Section:
    path: list[str]  # heading texts from the page title down to this section
    anchor: str | None  # "#defaults" part of the URL, if the heading has one
    lines: list[str]  # the section's body, without the heading line itself


def split_sections(text: str) -> list[Section]:
    """Cut the page into sections, one per heading.

    `stack` tracks where we are in the heading tree. Example while reading:
        "# Query Parameters"   -> stack = [(1, "Query Parameters")]
        "## Defaults"          -> stack = [(1, "Query Parameters"), (2, "Defaults")]
        "## Optional"          -> pop the level-2 entry, push the new one:
                                  stack = [(1, "Query Parameters"), (2, "Optional")]
    so every section knows its full path: "Query Parameters > Optional".
    """
    sections: list[Section] = []
    stack: list[tuple[int, str]] = []  # (level, heading text)
    current = Section(path=[], anchor=None, lines=[])  # text before the first heading
    in_code = False

    for line in text.splitlines():
        # Inside a code block, "# comment" is Python, not a heading. We flip the
        # in_code flag on every fence line, so we always know which side we're on.
        if FENCE_RE.match(line):
            in_code = not in_code
        m = None if in_code else HEADING_RE.match(line)

        if m:
            # A new heading closes the current section and opens a new one.
            sections.append(current)
            level = len(m.group("hashes"))  # "##" -> 2
            # Leave any headings at the same or a deeper level: they are siblings
            # or children of a previous section, not parents of this one.
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, m.group("text").strip()))
            current = Section(path=[h for _, h in stack], anchor=m.group("anchor"), lines=[])
        else:
            current.lines.append(line)

    sections.append(current)
    # Drop sections with no body (e.g. a heading immediately followed by a sub-heading).
    return [s for s in sections if "".join(s.lines).strip()]


def split_blocks(lines: list[str]) -> list[str]:
    """Split a section into blocks at blank lines, keeping each code block whole.

    A blank line inside a code block does NOT end the block, otherwise a function
    with an empty line in it would be cut in two.
    """
    blocks: list[str] = []
    buf: list[str] = []  # lines of the block being built
    in_code = False
    for line in lines:
        if FENCE_RE.match(line):
            in_code = not in_code
        if not in_code and not line.strip():
            # Blank line outside code: the current block is finished.
            if buf:
                blocks.append("\n".join(buf))
                buf = []
            continue
        buf.append(line)
    if buf:
        blocks.append("\n".join(buf))
    return blocks


def hard_split(block: str, size: int) -> list[str]:
    """Last resort for a single block bigger than a chunk: split on line boundaries.

    Only used for rare cases like a very long code example. Splitting it is bad,
    but a chunk the embedding model would silently truncate is worse.
    """
    pieces: list[str] = []
    buf = ""
    for line in block.splitlines(keepends=True):
        while len(line) > size:  # a single line longer than a whole chunk
            if buf:
                pieces.append(buf)
                buf = ""
            pieces.append(line[:size])
            line = line[size:]
        if len(buf) + len(line) > size and buf:
            pieces.append(buf)
            buf = ""
        buf += line
    if buf:
        pieces.append(buf)
    return [p.strip("\n") for p in pieces if p.strip()]


def pack(blocks: list[str], size: int, overlap: int) -> list[str]:
    """Greedily fill chunks with whole blocks, up to `size` characters each.

    Example with size=100 and blocks A(40) B(40) C(40), overlap=50:
        chunk 1 = A + B          (A+B+C would be 120 > 100, so we stop before C)
        chunk 2 = B + C          (B is repeated: that's the overlap)
    """
    # Any block that is too big on its own gets cut first, so every unit fits.
    units: list[str] = []
    for b in blocks:
        units.extend(hard_split(b, size) if len(b) > size else [b])

    chunks: list[str] = []
    current: list[str] = []  # blocks in the chunk being filled
    for unit in units:
        candidate = "\n\n".join([*current, unit])
        if current and len(candidate) > size:
            # Adding this unit would overflow: close the current chunk.
            chunks.append("\n\n".join(current))
            # Overlap: start the next chunk with the previous chunk's last block,
            # but only if that block is small (<= overlap) and still leaves room.
            tail = current[-1]
            keep_tail = len(tail) <= overlap and len(tail) + len(unit) + 2 <= size
            current = [tail] if keep_tail else []
        current.append(unit)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def chunk_document(doc: Document, chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    """Entry point: Document -> list[Chunk]. Called from ingest/pipeline.py."""
    chunks: list[Chunk] = []
    for section in split_sections(doc.text):
        heading = " > ".join(section.path) or doc.title
        # Deep link straight to the section, so a citation opens the right spot.
        url = f"{doc.url}#{section.anchor}" if section.anchor else doc.url
        # The heading is prepended to every chunk, so subtract its length from the
        # budget to keep the final chunk text within chunk_size.
        body_size = max(200, chunk_size - len(heading) - 2)
        for body in pack(split_blocks(section.lines), body_size, chunk_overlap):
            chunks.append(
                Chunk(
                    document_id=doc.id,
                    index=len(chunks),  # position in the page: 0, 1, 2, ...
                    heading=heading,
                    url=url,
                    # This exact text is what gets embedded AND what the LLM reads.
                    text=f"{heading}\n\n{body}",
                )
            )
    return chunks
