"""Pull requirement statements out of a spec document.

Supports .docx, .pdf, .txt and .md. A "requirement" is any sentence that
contains a binding verb (by default shall / must / will / should; narrow it
with verbs=). IDs come from, in order of preference:

  1. an explicit ID at the start of the line   SYS-042, [R-12], 3.2.1.4 The system shall...
  2. the document's own outline                 5.4.7 heading + "a." item  ->  5.4.7a
  3. a fallback counter                         AUTO-001

Real PDFs are messy. Running headers/footers, table-of-contents lines,
"Rationale:" notes, and sentences that only *mention* "shall" in quotes are
dropped before anything reaches the checks. (Found by running a 97-page NASA
KSC standard through v0.3.0, which glued page footers onto requirements and
stamped a referenced standard's name on 16 of them as an ID.)
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ALL_VERBS = ("shall", "must", "will", "should")

# explicit requirement IDs: SYS-042, ABC_REQ-12, [R-7], or a deep outline number with text after it
EXPLICIT_ID = [
    re.compile(r"^\s*\[?([A-Z][A-Z0-9_]{1,15}-\d{1,6})\]?[\s:.)-]+(?=[A-Z\"“])"),  # must be followed by the sentence
    re.compile(r"^\s*(\d+(?:\.\d+){2,6})[\s.)-]+(?=\S)"),
]
# outline structure
HEADING = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+([A-Z][^.]{0,90})$")     # "5.4.7 Electrical-Power Receptacles"
LETTER_ITEM = re.compile(r"^\s*([a-z])[.)]\s+(?=\S)")                       # "a. ..."  "b) ..."
PAREN_LETTER = re.compile(r"^\s*\(([a-z])\)\s+(?=\S)")                       # "(a) ..." (nested under (1) if one is open)
NUMBER_ITEM = re.compile(r"^\s*\((\d{1,2})\)\s+(?=\S)")                    # "(1) ..."
# noise
TOC_LINE = re.compile(r"\.{5,}\s*\d*\s*$")                                 # "5.2.14 Piping ......... 40"
NOTE_START = re.compile(r"^\s*(rationale|note|notes|guidance)\s*[:.-]", re.I)
# standard US government forms stapled to the back of NASA/DoD documents (DD 1426, SF 298): stop here
BACK_MATTER = re.compile(r"^\s*(STANDARDIZATION DOCUMENT IMPROVEMENT PROPOSAL|REPORT DOCUMENTATION PAGE)\s*$")
PAGE_TOKEN = re.compile(r"^(\d+|[ivxlcdm]+)$", re.I)


@dataclass
class Requirement:
    rid: str
    text: str
    source_line: int
    findings: list = field(default_factory=list)
    llm: dict | None = None


def _norm(line: str) -> str:
    """Normalize a line for header/footer matching: drop page-number tokens at the ends, then any digits."""
    toks = line.split()
    while toks and PAGE_TOKEN.match(toks[0]):
        toks.pop(0)
    while toks and PAGE_TOKEN.match(toks[-1]):
        toks.pop()
    return re.sub(r"\d+", "#", " ".join(toks)).lower()


def _strip_running_lines(pages: list[list[str]]) -> list[str]:
    """Drop lines that repeat across many pages (headers, footers, distribution statements)."""
    if len(pages) < 4:
        return [ln for p in pages for ln in p]
    seen = Counter()
    for p in pages:
        seen.update({_norm(ln) for ln in p if ln.strip()})
    running = {k for k, v in seen.items() if v >= max(3, 0.3 * len(pages))}
    out = []
    for p in pages:
        for ln in p:
            s = ln.strip()
            if not s or PAGE_TOKEN.match(s) or _norm(s) in running:
                continue
            out.append(ln)
    return out


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

        with pdfplumber.open(str(path)) as pdf:
            pages = [(page.extract_text() or "").splitlines() for page in pdf.pages]
        return _strip_running_lines(pages)
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def _plausible_heading(num: str, title: str, top: int | None) -> bool:
    """Real outlines count up. Rejects table rows ("2 Single failure that could...") and
    numbered lists that happen to look like headings ("2. Clarified applicability of...")."""
    parts = num.split(".")
    first = int(parts[0])
    if len(parts) == 1:
        if title.isupper() and len(title.split()) <= 8:
            return True                      # "4. GENERAL REQUIREMENTS": a real chapter heading
        return first == (1 if top is None else top + 1)
    # subsection: belongs to the current chapter, or the next one if its heading was missed
    return top is None or first in (top, top + 1)


def _blocks(lines: list[str]):
    """Walk the lines, tracking the outline, and yield (line_no, id, text) blocks.

    A block ends at a blank line, a heading, a list item, an explicit ID, or a note."""
    section = None
    top = None        # current top-level section number, e.g. 4 while inside 4.x.y
    letter = None
    number = None     # open "(1)" item, so a following "(a)" nests under it
    buf: list[str] = []
    buf_id: str | None = None
    buf_start = 0
    skip = False

    def flush():
        nonlocal buf, buf_id, skip
        if buf and not skip:
            yield_block.append((buf_start, buf_id, " ".join(buf)))
        buf, buf_id, skip = [], None, False

    yield_block: list[tuple[int, str | None, str]] = []
    for i, raw in enumerate(lines, 1):
        line = raw.strip()
        if BACK_MATTER.match(line):
            break
        if not line:
            flush()
            continue
        if TOC_LINE.search(line):
            continue

        m_explicit = next((m for p in EXPLICIT_ID if (m := p.match(line))), None)
        m_head = HEADING.match(line)
        if m_head and not any(v in line.lower().split() for v in ALL_VERBS) and _plausible_heading(m_head.group(1), m_head.group(2).strip(), top):
            flush()
            section, letter, number = m_head.group(1), None, None
            top = int(section.split(".")[0])
            continue
        if m_explicit:
            flush()
            buf_id, buf_start, buf = m_explicit.group(1), i, [line[m_explicit.end():].strip()]
            if re.match(r"\d", buf_id):
                section, letter, number = buf_id, None, None
                top = int(buf_id.split(".")[0])
            continue
        if NOTE_START.match(line):
            flush()
            skip, buf_start, buf = True, i, [line]
            continue
        m_pl = PAREN_LETTER.match(line)
        if m_pl and section and number:
            flush()  # 6.3.1.1a(2)(a)
            buf_id, buf_start, buf = f"{section}{letter or ''}({number})({m_pl.group(1)})", i, [line[m_pl.end():]]
            continue
        m_let = LETTER_ITEM.match(line) or m_pl
        if m_let and section:
            flush()
            letter, number = m_let.group(1), None
            buf_id, buf_start, buf = f"{section}{letter}", i, [line[m_let.end():]]
            continue
        m_num = NUMBER_ITEM.match(line)
        if m_num and section:
            flush()
            number = m_num.group(1)
            buf_id, buf_start, buf = f"{section}{letter or ''}({number})", i, [line[m_num.end():]]
            continue
        if not buf:
            buf_start, buf_id = i, section
        buf.append(line)
    flush()
    return yield_block


def _split_sentences(text: str) -> list[str]:
    # don't split on decimals, section numbers, or e.g./i.e.
    protected = re.sub(r"\b(e\.g|i\.e|etc|approx|min|max|vs)\.", lambda m: m.group(0).replace(".", "§"), text, flags=re.I)
    parts = re.split(r"(?<=[.;])\s+(?=[A-Z(])", protected)
    return [p.replace("§", ".").strip() for p in parts if p.strip()]


def _only_quoted(sentence: str, verb_re: re.Pattern) -> bool:
    """True if every binding verb in the sentence is inside quotes (talking ABOUT "shall", not using it)."""
    unquoted = re.sub(r"[\"“”'‘’][^\"“”'‘’]{0,40}[\"“”'‘’]", " ", sentence)
    return not verb_re.search(unquoted)


def extract(path: str | Path, verbs: tuple[str, ...] = ALL_VERBS) -> list[Requirement]:
    path = Path(path)
    verb_re = re.compile(r"\b(" + "|".join(map(re.escape, verbs)) + r")\b", re.I)
    reqs: list[Requirement] = []
    auto = 0
    for line_no, rid, body in _blocks(_read_text(path)):
        body = re.split(r"\b(?:Rationale|Note|NOTE)\s*:", body)[0]  # rationale tacked onto a requirement
        sentences = [s for s in _split_sentences(body) if verb_re.search(s) and not _only_quoted(s, verb_re)]
        sentences = [s for s in sentences if not NOTE_START.match(s)]
        for n, sent in enumerate(sentences, 1):
            auto += 1
            this_id = rid or f"AUTO-{auto:03d}"
            if rid and len(sentences) > 1:
                this_id = f"{rid}#{n}"  # 5.4.3#2: second requirement sentence in one paragraph
            reqs.append(Requirement(rid=this_id, text=sent, source_line=line_no))
    return reqs
