"""Pull requirement statements out of a spec document.

Supports .docx, .pdf, .txt and .md. A "requirement" is any sentence that
contains a binding verb (shall / must / will / should). Each one is tagged
with an ID if the line carries one (e.g. SYS-042, [R-12], 3.2.1.4).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

BINDING = re.compile(r"\b(shall|must|will|should)\b", re.I)

# Common requirement ID styles: SYS-042, ABC_REQ-12, [R-7], 3.2.1.4
ID_PATTERNS = [
    re.compile(r"^\s*\[?([A-Z][A-Z0-9_]{1,15}-\d{1,6})\]?[\s:.)-]+"),
    re.compile(r"^\s*(\d+(?:\.\d+){2,6})[\s.)-]+"),
]


@dataclass
class Requirement:
    rid: str
    text: str
    source_line: int
    findings: list = field(default_factory=list)
    llm: dict | None = None


def _read_text(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        import docx  # python-docx

        doc = docx.Document(str(path))
        lines = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells]
                lines.append("  ".join(dict.fromkeys(cells)))  # dedupe merged cells
        return lines
    if suffix == ".pdf":
        import pdfplumber

        lines: list[str] = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                lines.extend((page.extract_text() or "").splitlines())
        return lines
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def _join_wrapped(lines: list[str]) -> list[tuple[int, str]]:
    """Glue PDF-style hard-wrapped lines back into paragraphs."""
    paras: list[tuple[int, str]] = []
    buf, start = [], 0
    for i, raw in enumerate(lines, 1):
        line = raw.strip()
        starts_new = not line or any(p.match(line) for p in ID_PATTERNS)
        if starts_new and buf:
            paras.append((start, " ".join(buf)))
            buf = []
        if line:
            if not buf:
                start = i
            buf.append(line)
    if buf:
        paras.append((start, " ".join(buf)))
    return paras


def _split_sentences(text: str) -> list[str]:
    # don't split on decimals, section numbers, or e.g./i.e.
    protected = re.sub(r"\b(e\.g|i\.e|etc|approx|min|max|vs)\.", lambda m: m.group(0).replace(".", "§"), text, flags=re.I)
    parts = re.split(r"(?<=[.;])\s+(?=[A-Z(])", protected)
    return [p.replace("§", ".").strip() for p in parts if p.strip()]


def extract(path: str | Path) -> list[Requirement]:
    path = Path(path)
    reqs: list[Requirement] = []
    auto = 0
    for line_no, para in _join_wrapped(_read_text(path)):
        rid = None
        body = para
        for pat in ID_PATTERNS:
            m = pat.match(para)
            if m:
                rid = m.group(1)
                body = para[m.end():].strip()
                break
        sentences = [s for s in _split_sentences(body) if BINDING.search(s)]
        for n, sent in enumerate(sentences):
            auto += 1
            this_id = rid or f"AUTO-{auto:03d}"
            if rid and len(sentences) > 1:
                this_id = f"{rid}.{chr(97 + n)}"  # SYS-042.a, .b
            reqs.append(Requirement(rid=this_id, text=sent, source_line=line_no))
    return reqs
