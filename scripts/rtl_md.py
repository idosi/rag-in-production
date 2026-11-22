"""Make a Hebrew markdown file render right-to-left on GitHub.

GitHub gives every paragraph, list item and heading dir="auto", so a line whose
first letter is English renders left-to-right even inside <div dir="rtl">.
This script:
  - prefixes every prose line / list item / heading / table cell with U+200F
    (RIGHT-TO-LEFT MARK), an invisible character that makes the line RTL
  - wraps fenced code blocks in <div dir="ltr"> so code stays left-aligned
  - leaves horizontal rules (---) alone: "RLM---" would render as literal text
  - wraps inline code that starts or ends with punctuation (`f()`, `--flag`,
    `/health`) in <span dir="ltr">, otherwise the RTL line moves the
    punctuation to the wrong side and `f()` shows as "()f"
It is idempotent: running it twice changes nothing.

    uv run python scripts/rtl_md.py docs/learning/02a-retrieval-evals.md
"""

import re
import sys
from pathlib import Path

RLM = "‏"


def mark(s: str) -> str:
    if s.startswith(RLM) or s.startswith("**" + RLM):
        return s
    # Put the mark INSIDE a leading ** : "RLM**`x`" breaks bold on GitHub
    # (the opening ** is followed by punctuation and preceded by a non-space).
    if s.startswith("**"):
        return "**" + RLM + s[2:]
    return RLM + s


LTR_OPEN = '<span dir="ltr">'
CODE_SPAN = re.compile("(" + re.escape(LTR_OPEN) + ")?`([^`]+)`")


def isolate_code(s: str) -> str:
    def wrap(m: re.Match) -> str:
        code = m.group(2)
        if m.group(1) or (code[0].isalnum() and code[-1].isalnum()):
            return m.group(0)
        return f"{LTR_OPEN}`{code}`</span>"

    return CODE_SPAN.sub(wrap, s)


def convert(text: str) -> str:
    out: list[str] = []
    in_code = False
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("```"):
            prev = out[-2] if len(out) >= 2 else ""
            if not in_code and prev != '<div dir="ltr">':
                out += ['<div dir="ltr">', ""]
            out.append(line)
            nxt = lines[i + 2] if i + 2 < len(lines) else ""
            if in_code and nxt != "</div>":
                out += ["", "</div>"]
            in_code = not in_code
            continue
        if (
            in_code
            or not line.strip()
            or line.startswith("<div")
            or line == "</div>"
            or re.fullmatch(r"-{3,}|\*{3,}|_{3,}", line.strip())
        ):
            out.append(line)
            continue
        if line.startswith("|"):
            if re.match(r"^\|[-|\s:]+\|$", line):
                out.append(line)
                continue
            cells = line.split("|")
            middle = [
                (" " + mark(isolate_code(c.lstrip()))) if c.strip() else c for c in cells[1:-1]
            ]
            out.append("|".join([cells[0], *middle, cells[-1]]))
        elif line.startswith("<details><summary><b>"):
            out.append(line.replace("<summary><b>", "<summary><b>" + RLM, 1).replace(RLM * 2, RLM))
        elif line.startswith("</details>"):
            out.append(line)
        elif m := re.match(r"^(#+ |\s*(?:[-*]|\d+\.) |> )(.*)$", line):
            out.append(m.group(1) + mark(isolate_code(m.group(2))))
        else:
            out.append(mark(isolate_code(line)))
    return "\n".join(out)


if __name__ == "__main__":
    for path in sys.argv[1:]:
        p = Path(path)
        p.write_text(convert(p.read_text(encoding="utf-8")), encoding="utf-8")
        print(f"converted {path}")
