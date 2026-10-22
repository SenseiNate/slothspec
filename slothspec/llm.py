"""Local model pass through Ollama.

Everything goes to localhost. No API key, no outbound traffic, so a spec
that can't leave the building doesn't have to.

Two ways to run:
  single  one model grades AND rewrites each requirement (review)
  hybrid  a small model grades everything (grade), a bigger model only
          rewrites what got flagged (edit). In testing, gemma4:e2b was the
          better grader and gemma4:e4b the better editor.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import requests

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("SLOTHSPEC_MODEL", "gemma4")

# ---------------------------------------------------------------------------
# Prompt pieces. Each model only gets the instructions for its own job.
# ---------------------------------------------------------------------------
RUBRIC = """You are a senior systems engineer doing a requirements review before an SRR.
You judge single requirement statements against the usual good-requirement
characteristics: necessary, unambiguous, singular, verifiable, complete, feasible.

Verdict rubric (be calibrated, not picky):
- good: one testable thing, clear subject, a tester could write pass/fail criteria today.
  Style nitpicks and "could add more detail" do NOT make it needs work. Plenty of real requirements are good.
- needs work: intent is clear but one small fix is needed (add a unit, swap one vague word, split in two, fill a TBD).
- rewrite: can't be verified as written, or a reader can't tell what is actually required.

Example good: "The radar shall report target range with an accuracy of 10 m (1 sigma) or better."
Example good: "The pump shall deliver 5 to 50 L/min, adjustable in 1 L/min steps." (range + resolution is one capability, not compound)
Example good: "The heater shall not exceed a surface temperature of 60 °C." (a bounded "shall not" is fine)
Example needs work: "The console should log errors." (should, and which errors?)
Example rewrite: "The system shall be user-friendly." (nothing to test)"""

RULES_COMMON = """- Be specific. No filler. Issues are short, one line each. Empty list if good.
- Don't invent details the author didn't write (formats, units of display, extra behaviors). Use <<placeholders>> instead.
- Don't redefine plain words ("connect", "on schedule") as ambiguous unless a tester would genuinely be stuck."""

RULES_REWRITE = """- Never invent numbers. If a threshold is missing, put a placeholder like <<max latency, ms>> in the rewrite.
- Keep the original intent. Don't add scope, and don't drop any part of what was required.
- Every vague word must be gone from the rewrite: replace it with a measurable criterion or a <<placeholder>>.
- Keep "and/or" logic honest: if the original allowed either option, the rewrite must too.
- If the statement bundles several requirements, the rewrite should be several "shall" sentences separated by newlines."""

RULES_VERIFY = """- Pick the verification method a test engineer would most likely use: Inspection, Analysis, Demonstration, or Test.
- how_to_verify is one sentence describing what the tester physically does (e.g. "Drop the unit from the
  specified height onto concrete and run a functional check."). It is never a requirement and never just a method name."""

# single mode: one model does everything (same behavior as v0.2)
SYSTEM = f"""{RUBRIC}

Rules for your answer:
{RULES_COMMON}
{RULES_REWRITE}
{RULES_VERIFY}
- If the requirement is already good, say so and return it unchanged as the rewrite."""

# hybrid pass 1: grade only
GRADER_SYSTEM = f"""{RUBRIC}

You are only grading. A different engineer will write the fix, so do not rewrite anything.

Rules for your answer:
{RULES_COMMON}
{RULES_VERIFY}"""

# hybrid pass 2: rewrite only
EDITOR_SYSTEM = f"""You are a senior systems engineer fixing a requirement that a reviewer already flagged.
The reviewer's notes tell you what's wrong. Your only job is the rewrite.

Rules for your rewrite:
{RULES_REWRITE}
- Don't invent details the author didn't write. Use <<placeholders>> instead.
- Output only "shall" statements. No commentary, no numbering."""

# Field order matters: the model fills these top to bottom. Putting rewrite right after
# issues keeps the fix from leaking into how_to_verify (seen in v0.2.0 with gemma4:e4b).
_VERDICT = {"type": "string", "enum": ["good", "needs work", "rewrite"]}
_METHOD = {"type": "string", "enum": ["Inspection", "Analysis", "Demonstration", "Test"]}
_ISSUES = {"type": "array", "items": {"type": "string"}, "maxItems": 4}

SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": _VERDICT, "verifiable": {"type": "boolean"}, "singular": {"type": "boolean"},
        "issues": _ISSUES, "rewrite": {"type": "string"},
        "verification_method": _METHOD, "how_to_verify": {"type": "string"},
    },
    "required": ["verdict", "verifiable", "singular", "issues", "rewrite", "verification_method", "how_to_verify"],
}
GRADE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": _VERDICT, "verifiable": {"type": "boolean"}, "singular": {"type": "boolean"},
        "issues": _ISSUES, "verification_method": _METHOD, "how_to_verify": {"type": "string"},
    },
    "required": ["verdict", "verifiable", "singular", "issues", "verification_method", "how_to_verify"],
}
EDIT_SCHEMA = {
    "type": "object",
    "properties": {"rewrite": {"type": "string"}},
    "required": ["rewrite"],
}


class OllamaUnavailable(RuntimeError):
    pass


def ping(model: str = DEFAULT_MODEL) -> None:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        raise OllamaUnavailable(
            f"Can't reach Ollama at {OLLAMA_URL}. Start it with `ollama serve`, or run with --rules-only."
        ) from e
    def norm(tag: str) -> str:
        # Ollama treats "gemma4" and "gemma4:latest" as the same model; any other tag must match exactly
        return tag if ":" in tag else f"{tag}:latest"

    pulled = {norm(m["name"]) for m in r.json().get("models", [])}
    if norm(model) not in pulled:
        raise OllamaUnavailable(f"Model '{model}' isn't pulled yet. Run: ollama pull {model}")


class Cache:
    """Re-running on the same spec costs nothing: answers are keyed by model + prompt + input."""

    def __init__(self, path: Path):
        self.path = path
        try:
            self.data = json.loads(path.read_text())
        except Exception:  # noqa: BLE001
            self.data = {}

    @staticmethod
    def key(model: str, system: str, user: str) -> str:
        return hashlib.sha256(f"{model}\n{system}\n{user}".encode()).hexdigest()[:24]

    def get(self, k):
        return self.data.get(k)

    def put(self, k, v):
        self.data[k] = v
        self.path.write_text(json.dumps(self.data, indent=1))


def _hints(rule_hits: list[str]) -> str:
    if rule_hits:
        return "The pattern checker already flagged:\n" + "\n".join(f"- {h}" for h in rule_hits)
    return "The pattern checker found nothing. Only mark it needs work if there's a real verification problem."


def _call(model: str, system: str, user: str, schema: dict, cache: Cache | None) -> dict:
    k = Cache.key(model, system, user)
    if cache and (hit := cache.get(k)):
        return hit
    body = {
        "model": model,
        "stream": False,
        "format": schema,
        # no hidden reasoning tokens: thinking was on by default and cost ~2/3 of runtime in v0.1
        "think": False,
        "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 400},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    r = requests.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=300)
    if r.status_code == 400 and "think" in r.text.lower():
        body.pop("think")  # model without a thinking switch
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=300)
    r.raise_for_status()
    out = json.loads(r.json()["message"]["content"])
    if cache:
        cache.put(k, out)
    return out


def review(text: str, rule_hits: list[str], model: str = DEFAULT_MODEL, cache: Cache | None = None) -> dict:
    """Single mode: one model grades and rewrites."""
    user = f"Requirement:\n{text}\n\n{_hints(rule_hits)}\n\nReview it."
    return _call(model, SYSTEM, user, SCHEMA, cache)


def grade(text: str, rule_hits: list[str], model: str, cache: Cache | None = None) -> dict:
    """Hybrid pass 1: verdict, issues, verification. No rewrite."""
    user = f"Requirement:\n{text}\n\n{_hints(rule_hits)}\n\nGrade it."
    return _call(model, GRADER_SYSTEM, user, GRADE_SCHEMA, cache)


def edit(text: str, rule_hits: list[str], issues: list[str], model: str, cache: Cache | None = None) -> str:
    """Hybrid pass 2: rewrite one flagged requirement using the grader's notes."""
    notes = "\n".join(f"- {i}" for i in [*rule_hits, *issues]) or "- (no specific notes)"
    user = f"Requirement:\n{text}\n\nReviewer notes:\n{notes}\n\nRewrite it."
    return _call(model, EDITOR_SYSTEM, user, EDIT_SCHEMA, cache)["rewrite"].strip()
