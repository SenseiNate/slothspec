"""Deterministic checks. Fast, free, no model needed.

These cover the stuff a reviewer catches on the first read: weasel words,
TBDs, escape clauses, compound requirements. The model pass handles the
judgment calls (is this actually verifiable? what would a test look like?).
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Finding:
    rule: str
    severity: str  # high | med | low
    match: str
    why: str


def _words(*ws: str) -> re.Pattern:
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in ws) + r")\b", re.I)


VAGUE = _words(
    "adequate", "adequately", "appropriate", "appropriately", "sufficient", "sufficiently",
    "user-friendly", "user friendly", "easy", "easily", "quiet", "quietly", "low noise", "simple", "fast", "quickly", "rapid",
    "timely", "efficient", "efficiently", "robust", "reliable", "seamless",
    "seamlessly", "intuitive", "state-of-the-art", "high quality", "modern", "normal",
    "reasonable", "significant", "minimal", "large", "small", "several", "various",
    "approximately", "about", "typical", "typically", "best", "optimal",
    "acceptable", "suitable", "real-time", "real time", "near real-time",
)
ESCAPE = _words(
    "if possible", "where possible", "as possible", "if practical", "where practical",
    "if practicable", "as appropriate", "as required", "as necessary", "if necessary",
    "to the extent", "where feasible", "if feasible", "as applicable", "where applicable",
)
OPEN_ENDED = re.compile(r"\b(including but not limited to|not limited to|etc\.?|and so on|and so forth|such as)\b", re.I)
TBX = re.compile(r"\b(TBD|TBR|TBS|TBC|TBP|TBA)\b")
OPTIMIZE = _words("minimize", "minimise", "maximize", "maximise", "optimize", "optimise", "as much as", "as little as")
ANDOR = re.compile(r"\band/or\b|\s/\s", re.I)
PRONOUN_START = re.compile(r"^(it|they|this|that|these|those|he|she)\b", re.I)
SHALL = re.compile(r"\bshall\b", re.I)
WEAK = re.compile(r"\b(should|will|must|may|can|could|might)\b", re.I)
NEG = re.compile(r"\bshall\s+not\b", re.I)
ABSOLUTE = _words("always", "never", "all", "every", "none", "100%", "100 percent", "zero")
# Passive is only a problem when someone has to DO something and the sentence doesn't say who.
# "GS shall be designed in accordance with X" is normal spec language; "Firmware updates shall be
# applied" (by whom?) is not. (v0.3 flagged 155 of 333 real NASA requirements; nearly all fine.)
ACTOR_VERBS = (
    "applied", "performed", "conducted", "provided", "maintained", "verified", "documented",
    "approved", "reviewed", "submitted", "recorded", "reported", "notified", "inspected",
    "evaluated", "updated", "installed", "removed", "replaced", "monitored", "checked",
)
PASSIVE = re.compile(r"\bshall\s+be\s+(" + "|".join(ACTOR_VERBS) + r")\b(?!.*\bby\b)", re.I)

UNITS = (
    r"%|percent|ms|s|sec|secs|second|seconds|min|mins|minute|minutes|hr|hrs|hour|hours|day|days|"
    r"g|gram|grams|kilogram|kilograms|liter|liters|l|ml|oz|hz|khz|mhz|ghz|db|dbm|dbi|w|kw|mw|v|kv|mv|a|ma|ohm|ohms|°c|°f|c|f|k|kelvin|deg|degrees|"
    r"m|mm|cm|km|ft|in|inch|inches|nm|nmi|mi|kg|g|lb|lbs|kts|knots|mph|kph|m/s|ft/s|g's|gs|"
    r"bps|kbps|mbps|gbps|b|kb|mb|gb|tb|bytes|bits|psi|psia|psig|ksi|pa|kpa|mpa|gpa|n|kn|lbf|rad|mrad|"
    r"users|times|channels|targets|tracks|messages|frames|fps|sigma|σ|hours?/day|x"
)
LIST_TAIL = re.compile(r"\b[\w.]+(?:\s*,\s*(?:(?:or|and)\s+)?|\s+(?:or|and|through|to)\s+)$")
DIMENSIONLESS = re.compile(r"(factor of safety|safety factor|ratio|margin)\b[^.]*$", re.I)
# A number right after one of these is a reference, not a measurement:
# "Table 1", "(see 6)", "Category 1", "NFPA 70", "KNPR 8700.2", "MIL-STD-889"
REFERENCE_BEFORE = re.compile(
    r"(?:\b(?i:table|figure|fig\.|section|para|paragraph|see|appendix|annex|category|categories|class|zones?"
    r"|level|type|grade|group|revision|rev\.?|change|item|step|phase|volume|vol\.|part|chapter|note"
    r"|article|division|test|tests|criticality|classification|volumes|parts|articles|sections|tables|figures)"
    r"|\b[A-Z][A-Z0-9&/]{1,}(?:[- ][A-Z0-9]+)*[- ]?)\s*$"
)
NOT_NOUNS = {"onto", "across", "towards", "versus", "unless", "plus", "minus", "less", "does", "has", "was", "is"}
NUMBER_NO_UNIT = re.compile(
    rf"(?<![\w.\-/])(\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?|\d+(?:\.\d+)?)(?!\s*(?:{UNITS})\b)(?![\w.%\-/,])", re.I
)


def check(text: str) -> list[Finding]:
    f: list[Finding] = []
    t = text.strip()

    if not SHALL.search(t):
        m = WEAK.search(t)
        f.append(Finding("non-binding verb", "med", m.group(0) if m else "",
                         "No 'shall'. 'Will' reads as a statement of fact and 'should' as a goal, so nobody is on the hook to verify it."))
    if len(SHALL.findall(t)) > 1 or re.search(r"\bshall\b[^.;]*\band\b[^.;]*\b(shall|provide|support|display|record|transmit|allow)\b", t, re.I):
        f.append(Finding("compound requirement", "high", "multiple actions",
                         "More than one thing being required. Split it so each piece can pass or fail on its own."))
    for m in TBX.finditer(t):
        f.append(Finding("open item", "high", m.group(0), "Placeholder value. Can't be verified until it's closed out."))
    escapes = [m.span() for m in ESCAPE.finditer(t)]
    for m in VAGUE.finditer(t):
        if any(a <= m.start() < b for a, b in escapes):
            continue  # already reported as part of an escape clause
        f.append(Finding("vague term", "high", m.group(0), "Subjective word with no measurable threshold. Two testers would grade it differently."))
    for m in ESCAPE.finditer(t):
        f.append(Finding("escape clause", "high", m.group(0), "Gives the developer an out. Whoever decides 'possible' decides whether it's met."))
    for m in OPEN_ENDED.finditer(t):
        f.append(Finding("open-ended list", "med", m.group(0), "Unbounded scope. Enumerate the full set or reference a table."))
    for m in OPTIMIZE.finditer(t):
        f.append(Finding("optimization goal", "med", m.group(0), "Minimize/maximize has no pass line. Give a threshold value."))
    if ANDOR.search(t):
        f.append(Finding("and/or", "med", "and/or", "Ambiguous: is one enough, or are both required?"))
    if PRONOUN_START.match(t):
        f.append(Finding("unclear subject", "med", PRONOUN_START.match(t).group(0),
                         "Starts with a pronoun. Out of context, nobody knows what 'it' is."))
    if NEG.search(t):
        f.append(Finding("negative requirement", "low", "shall not",
                         "Proving something never happens is hard. Bound it (conditions, duration, probability)."))
    for m in ABSOLUTE.finditer(t):
        f.append(Finding("absolute", "low", m.group(0), "Absolutes are hard to verify. Confirm it's really meant to be unbounded."))
    if PASSIVE.search(t):
        f.append(Finding("passive voice", "low", PASSIVE.search(t).group(0),
                         "Passive with no actor. Say which system/element does it."))
    for m in NUMBER_NO_UNIT.finditer(t):
        # skip things that look like section refs or years
        if re.match(r"(19|20)\d\d$", m.group(1)):
            continue
        # "Table 1", "(see 6)", "NFPA 70", "KNPR 8700.2", "Category 1": references, not measurements.
        # Also the rest of a list that started with one: "criticality 1, 1S, 1R, or 2", "Zones 3 or 4"
        before = t[:m.start()]
        while True:
            if REFERENCE_BEFORE.search(before):
                break
            shorter = LIST_TAIL.sub("", before)
            if shorter == before:
                break
            before = shorter
        if REFERENCE_BEFORE.search(before):
            continue
        # "29 CFR 1910": a number right before an acronym is a title number
        if re.match(r"\s+[A-Z]{2,}\b", t[m.end():]):
            continue
        # factors of safety and ratios are dimensionless on purpose
        if DIMENSIONLESS.search(t[max(0, m.start() - 30):m.start()]):
            continue
        # inline list markers: "(1) ... (2) ..."
        if t[m.start() - 1:m.start()] == "(" and t[m.end():m.end() + 1] == ")":
            continue
        after = t[m.end():].lstrip()
        nxt = re.match(r"([A-Za-z]+)", after)
        # "20 to 200 grams": the unit comes after the range
        if re.match(rf"(to|-|and|through)\s*\d+(?:\.\d+)?\s*(?:{UNITS})\b", after, re.I):
            continue
        # "3 portions", "4 pets": a count of things is fine
        if nxt and nxt.group(1).lower().endswith("s") and len(nxt.group(1)) > 3 and nxt.group(1).lower() not in NOT_NOUNS:
            continue
        f.append(Finding("number without unit", "med", m.group(1), "Value with no unit or tolerance."))
    if len(t.split()) > 45:
        f.append(Finding("long statement", "low", f"{len(t.split())} words",
                         "Long requirements usually hide more than one requirement or a rationale that belongs elsewhere."))
    return f


SEV_WEIGHT = {"high": 3, "med": 2, "low": 1}


def score(findings: list[Finding]) -> int:
    return sum(SEV_WEIGHT[x.severity] for x in findings)
