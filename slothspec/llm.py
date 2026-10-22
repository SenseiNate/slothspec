"""Local model pass through Ollama.

Everything goes to localhost. No API key, no outbound traffic, so a spec
that can't leave the building doesn't have to.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import requests

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("SLOTHSPEC_MODEL", "gemma4")

SYSTEM = """You are a senior systems engineer doing a requirements review before an SRR.
You grade single requirement statements against the usual good-requirement
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
Example rewrite: "The system shall be user-friendly." (nothing to test)

Rules for your answer:
- Be specific. No filler. Issues are short, one line each. Empty list if good.
- Don't invent details the author didn't write (formats, units of display, extra behaviors). Use <<placeholders>> instead.
- Don't redefine plain words ("connect", "on schedule") as ambiguous unless a tester would genuinely be stuck.
- Never invent numbers. If a threshold is missing, put a placeholder like <<max latency, ms>> in the rewrite.
- Keep the original intent. Don't add scope.
- If the statement bundles several requirements, the rewrite should be several "shall" sentences separated by newlines.
- Pick the verification method a test engineer would most likely use: Inspection, Analysis, Demonstration, or Test.
- how_to_verify is one sentence describing what the tester physically does (e.g. "Drop the unit from the
  specified height onto concrete and run a functional check."). It is never a requirement and never just a method name.
- If the requirement is already good, say so and return it unchanged as the rewrite."""

# Field order matters: the model fills these top to bottom. Putting rewrite right after
# issues keeps the fix from leaking into how_to_verify (seen in v0.2.0 with gemma4:e4b).
SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["good", "needs work", "rewrite"]},
        "verifiable": {"type": "boolean"},
        "singular": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
        "rewrite": {"type": "string"},
        "verification_method": {"type": "string", "enum": ["Inspection", "Analysis", "Demonstration", "Test"]},
        "how_to_verify": {"type": "string"},
    },
    "required": ["verdict", "verifiable", "singular", "issues", "rewrite", "verification_method", "how_to_verify"],
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
    names = {m["name"].split(":")[0] for m in r.json().get("models", [])} | {m["name"] for m in r.json().get("models", [])}
    if model not in names and model.split(":")[0] not in names:
        raise OllamaUnavailable(f"Model '{model}' isn't pulled yet. Run: ollama pull {model}")


class Cache:
    """Re-running on the same spec costs nothing: answers are keyed by model + text."""

    def __init__(self, path: Path):
        self.path = path
        try:
            self.data = json.loads(path.read_text())
        except Exception:  # noqa: BLE001
            self.data = {}

    def key(self, model: str, text: str) -> str:
        return hashlib.sha256(f"{model}\n{SYSTEM}\n{text}".encode()).hexdigest()[:24]

    def get(self, k):
        return self.data.get(k)

    def put(self, k, v):
        self.data[k] = v
        self.path.write_text(json.dumps(self.data, indent=1))


def review(text: str, rule_hits: list[str], model: str = DEFAULT_MODEL, cache: Cache | None = None) -> dict:
    k = cache.key(model, text) if cache else None
    if cache and (hit := cache.get(k)):
        return hit

    if rule_hits:
        hints = "The pattern checker already flagged:\n" + "\n".join(f"- {h}" for h in rule_hits)
    else:
        hints = "The pattern checker found nothing. Only mark it needs work if there's a real verification problem."
    user = f"Requirement:\n{text}\n\n{hints}\n\nReview it."
    body = {
        "model": model,
        "stream": False,
        "format": SCHEMA,
        # no hidden reasoning tokens: this is a quick per-line judgment, and on a CPU every token costs
        "think": False,
        "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 400},
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
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
