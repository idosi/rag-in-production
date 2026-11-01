"""Split markdown documents into chunks.

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
"""

import re
from dataclasses import dataclass

from rag.models import Chunk, Document

HEADING_RE = re.compile(
    r"^(?P<hashes>#{1,6})\s+(?P<text>.*?)(?:\s*\{\s*#(?P<anchor>[\w-]+)\s*\})?\s*$"
)
FENCE_RE = re.compile(r"^\s*(```|~~~)")


@dataclass
class Section:
    path: list[str]  # heading texts from the page title down to this section
    anchor: str | None
    lines: list[str]


def split_sections(text: str) -> list[Section]:
    sections: list[Section] = []
    stack: list[tuple[int, str]] = []  # (level, heading text)
    current = Section(path=[], anchor=None, lines=[])
    in_code = False

    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_code = not in_code
        m = None if in_code else HEADING_RE.match(line)
        if m:
            sections.append(current)
            level = len(m.group("hashes"))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, m.group("text").strip()))
            current = Section(path=[h for _, h in stack], anchor=m.group("anchor"), lines=[])
        else:
            current.lines.append(line)

    sections.append(current)
    return [s for s in sections if "".join(s.lines).strip()]


def split_blocks(lines: list[str]) -> list[str]:
    """Split on blank lines, but treat a fenced code block as one block."""
    blocks: list[str] = []
    buf: list[str] = []
    in_code = False
    for line in lines:
        if FENCE_RE.match(line):
            in_code = not in_code
        if not in_code and not line.strip():
            if buf:
                blocks.append("\n".join(buf))
                buf = []
            continue
        buf.append(line)
    if buf:
        blocks.append("\n".join(buf))
    return blocks


def hard_split(block: str, size: int) -> list[str]:
    """Last resort for a single block bigger than a chunk: split on line boundaries."""
    pieces: list[str] = []
    buf = ""
    for line in block.splitlines(keepends=True):
        while len(line) > size:  # a single monster line
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
    units: list[str] = []
    for b in blocks:
        units.extend(hard_split(b, size) if len(b) > size else [b])

    chunks: list[str] = []
    current: list[str] = []
    for unit in units:
        candidate = "\n\n".join([*current, unit])
        if current and len(candidate) > size:
            chunks.append("\n\n".join(current))
            tail = current[-1]
            # Overlap: repeat the previous block if it is small enough and still fits.
            keep_tail = len(tail) <= overlap and len(tail) + len(unit) + 2 <= size
            current = [tail] if keep_tail else []
        current.append(unit)
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def chunk_document(doc: Document, chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in split_sections(doc.text):
        heading = " > ".join(section.path) or doc.title
        url = f"{doc.url}#{section.anchor}" if section.anchor else doc.url
        # Leave room for the heading prefix inside the size budget.
        body_size = max(200, chunk_size - len(heading) - 2)
        for body in pack(split_blocks(section.lines), body_size, chunk_overlap):
            chunks.append(
                Chunk(
                    document_id=doc.id,
                    index=len(chunks),
                    heading=heading,
                    url=url,
                    text=f"{heading}\n\n{body}",
                )
            )
    return chunks
