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

Rules for your answer:
- Be blunt and specific. No filler.
- Never invent numbers. If a threshold is missing, put a placeholder like <<max latency, ms>> in the rewrite.
- Keep the original intent. Don't add scope.
- If the statement bundles several requirements, the rewrite should be several "shall" sentences separated by newlines.
- Pick the verification method a test engineer would most likely use: Inspection, Analysis, Demonstration, or Test.
- If the requirement is already good, say so and return it unchanged as the rewrite."""

SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["good", "needs work", "rewrite"]},
        "verifiable": {"type": "boolean"},
        "singular": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
        "verification_method": {"type": "string", "enum": ["Inspection", "Analysis", "Demonstration", "Test"]},
        "how_to_verify": {"type": "string"},
        "rewrite": {"type": "string"},
    },
    "required": ["verdict", "verifiable", "singular", "issues", "verification_method", "how_to_verify", "rewrite"],
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

    hints = "\n".join(f"- {h}" for h in rule_hits) or "- none"
    user = f"Requirement:\n{text}\n\nThe pattern checker already flagged:\n{hints}\n\nReview it."
    r = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": model,
            "stream": False,
            "format": SCHEMA,
            "options": {"temperature": 0, "num_ctx": 4096},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        },
        timeout=300,
    )
    r.raise_for_status()
    out = json.loads(r.json()["message"]["content"])
    if cache:
        cache.put(k, out)
    return out
