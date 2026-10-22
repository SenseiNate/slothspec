"""slothspec: drop a spec in, get a redline back.

  slothspec review spec.docx                 # one file, report lands next to it
  slothspec watch ~/Specs/inbox              # leave it running, drop files in, walk away
  slothspec review spec.pdf --rules-only     # no model, instant
  slothspec review spec.pdf --verbs shall    # only "shall" counts (when should = guidance)
  slothspec review spec.docx --grader gemma4:e2b --editor gemma4
                                             # hybrid: small model grades, big model rewrites
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from . import llm
from .extract import ALL_VERBS, extract
from .report import write_csv, write_html
from .rules import check

SUPPORTED = {".docx", ".pdf", ".txt", ".md"}


@dataclass
class Plan:
    """Which model(s) run. No models = rules only."""
    model: str | None = None   # single mode
    grader: str | None = None  # hybrid mode
    editor: str | None = None

    @property
    def hybrid(self) -> bool:
        return bool(self.grader and self.editor)

    @property
    def models(self) -> set[str]:
        return {m for m in (self.model, self.grader, self.editor) if m}

    @property
    def label(self) -> str | None:
        if self.hybrid:
            return f"grader {self.grader} + editor {self.editor}"
        return self.model


def _error_result(e: Exception, text: str) -> dict:
    # "error", not "needs work": a failed call must not be counted as a flag
    return {"verdict": "error", "verifiable": False, "singular": False,
            "issues": [f"model error: {e}"], "verification_method": "Inspection",
            "how_to_verify": "", "rewrite": text}


def _needs_edit(r) -> bool:
    """Send to the editor if the grader flagged it, or regex found a real problem.
    The regex is the safety net: a TBD gets fixed even if the small model shrugs."""
    return r.llm.get("verdict") not in ("good", "error") or any(f.severity in ("high", "med") for f in r.findings)


def run(path: Path, out_dir: Path, plan: Plan, quiet: bool = False, verbs: tuple[str, ...] = ALL_VERBS) -> Path:
    say = (lambda *a, **k: None) if quiet else (lambda *a, **k: print(*a, **k, flush=True))
    t0 = time.time()
    reqs = extract(path, verbs)
    say(f"[slothspec] {path.name}: {len(reqs)} requirement statements")
    for r in reqs:
        r.findings = check(r.text)
    timing: dict[str, float] = {}
    cached = 0

    if plan.models:
        cache = llm.Cache(out_dir / ".slothspec_cache.json")
        hits = {r.rid: [f"{f.rule} ({f.match})" for f in r.findings] for r in reqs}

        if not plan.hybrid:
            t = time.time()
            for i, r in enumerate(reqs, 1):
                try:
                    r.llm = llm.review(r.text, hits[r.rid], model=plan.model, cache=cache)
                except Exception as e:  # noqa: BLE001  one bad call shouldn't sink the run
                    r.llm = _error_result(e, r.text)
                say(f"  {i}/{len(reqs)} {r.rid}: {r.llm.get('verdict')}")
            timing["review"] = time.time() - t
            cached = cache.hits
        else:
            # pass 1: small model grades everything
            t = time.time()
            say(f"[slothspec] pass 1: grading with {plan.grader}")
            for i, r in enumerate(reqs, 1):
                try:
                    r.llm = llm.grade(r.text, hits[r.rid], model=plan.grader, cache=cache)
                except Exception as e:  # noqa: BLE001
                    r.llm = _error_result(e, r.text)
                r.llm["rewrite"] = r.text
                say(f"  {i}/{len(reqs)} {r.rid}: {r.llm.get('verdict')}")
            timing["grade"] = time.time() - t

            # pass 2: big model rewrites only what needs it
            t = time.time()
            todo = [r for r in reqs if _needs_edit(r)]
            say(f"[slothspec] pass 2: rewriting {len(todo)} of {len(reqs)} with {plan.editor}")
            for i, r in enumerate(todo, 1):
                try:
                    r.llm["rewrite"] = llm.edit(r.text, hits[r.rid], r.llm.get("issues", []),
                                                model=plan.editor, cache=cache)
                    r.llm["editor"] = plan.editor
                except Exception as e:  # noqa: BLE001
                    r.llm.setdefault("issues", []).append(f"editor error: {e}")
                say(f"  {i}/{len(todo)} {r.rid}: rewritten")
            timing["edit"] = time.time() - t
            cached = cache.hits

    stem = path.stem
    html_path = out_dir / f"{stem}.redline.html"
    write_html(reqs, html_path, path.name, plan.label, time.time() - t0, timing, cached)
    write_csv(reqs, out_dir / f"{stem}.redline.csv")
    stages = "  ".join(f"{k} {v:.0f}s" for k, v in timing.items())
    say(f"[slothspec] done in {time.time() - t0:.0f}s ({stages}) -> {html_path}" if stages
        else f"[slothspec] done in {time.time() - t0:.0f}s -> {html_path}")
    return html_path


def watch(folder: Path, plan: Plan, interval: int, verbs: tuple[str, ...] = ALL_VERBS) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    done = folder / "reviewed"
    done.mkdir(exist_ok=True)
    print(f"[slothspec] watching {folder} ({plan.label or 'rules only'}). Drop specs in and go do something else.")
    while True:
        for p in sorted(folder.iterdir()):
            if p.is_file() and p.suffix.lower() in SUPPORTED and not p.name.startswith((".", "~$")):
                # wait until the file stops growing (still copying / still saving)
                size = -1
                while size != p.stat().st_size:
                    size = p.stat().st_size
                    time.sleep(1)
                try:
                    run(p, done, plan, verbs=verbs)
                    p.rename(done / p.name)
                except Exception as e:  # noqa: BLE001
                    print(f"[slothspec] {p.name} failed: {e}", file=sys.stderr)
                    p.rename(p.with_suffix(p.suffix + ".failed"))
        time.sleep(interval)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="slothspec", description="Local requirements linter. Your spec never leaves the box.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("review", "watch"):
        s = sub.add_parser(name)
        s.add_argument("path", type=Path)
        s.add_argument("--model", default=llm.DEFAULT_MODEL, help="single mode: one model does everything (default: %(default)s)")
        s.add_argument("--grader", help="hybrid mode: model that grades every requirement (e.g. gemma4:e2b)")
        s.add_argument("--editor", help="hybrid mode: model that rewrites flagged requirements (e.g. gemma4)")
        s.add_argument("--rules-only", action="store_true", help="skip the model, pattern checks only")
        s.add_argument("--verbs", default=",".join(ALL_VERBS),
                       help="which binding verbs count as requirements (default: %(default)s). "
                            "Use --verbs shall for specs where should/will mean guidance.")
        if name == "review":
            s.add_argument("--out", type=Path, help="output folder (default: next to the file)")
        else:
            s.add_argument("--interval", type=int, default=10, help="seconds between folder checks")
    a = ap.parse_args(argv)

    verbs = tuple(v.strip().lower() for v in a.verbs.split(",") if v.strip())
    if not verbs or any(v not in ALL_VERBS for v in verbs):
        sys.exit(f"[slothspec] --verbs must be a comma list of: {', '.join(ALL_VERBS)}")

    if a.rules_only:
        plan = Plan()
    elif a.grader or a.editor:
        # either flag turns on hybrid; the missing one falls back to --model
        plan = Plan(grader=a.grader or a.model, editor=a.editor or a.model)
    else:
        plan = Plan(model=a.model)

    for m in plan.models:
        try:
            llm.ping(m)
        except llm.OllamaUnavailable as e:
            sys.exit(f"[slothspec] {e}")

    if a.cmd == "review":
        out = a.out or a.path.parent
        out.mkdir(parents=True, exist_ok=True)
        run(a.path, out, plan, verbs=verbs)
    else:
        watch(a.path, plan, a.interval, verbs)


if __name__ == "__main__":
    main()
