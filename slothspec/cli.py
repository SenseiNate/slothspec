"""slothspec: drop a spec in, get a redline back.

  slothspec review spec.docx            # one file, report lands next to it
  slothspec watch ~/Specs/inbox         # leave it running, drop files in, walk away
  slothspec review spec.pdf --rules-only  # no model, instant
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import llm
from .extract import extract
from .report import write_csv, write_html
from .rules import check

SUPPORTED = {".docx", ".pdf", ".txt", ".md"}


def run(path: Path, out_dir: Path, model: str | None, quiet: bool = False) -> Path:
    t0 = time.time()
    reqs = extract(path)
    if not quiet:
        print(f"[slothspec] {path.name}: {len(reqs)} requirement statements")
    for r in reqs:
        r.findings = check(r.text)

    if model:
        cache = llm.Cache(out_dir / ".slothspec_cache.json")
        for i, r in enumerate(reqs, 1):
            hits = [f"{f.rule} ({f.match})" for f in r.findings]
            try:
                r.llm = llm.review(r.text, hits, model=model, cache=cache)
            except Exception as e:  # noqa: BLE001  keep going, one bad call shouldn't sink the run
                r.llm = {"verdict": "needs work", "verifiable": False, "singular": False,
                         "issues": [f"model error: {e}"], "verification_method": "Inspection",
                         "how_to_verify": "", "rewrite": r.text}
            if not quiet:
                print(f"  {i}/{len(reqs)} {r.rid}: {r.llm.get('verdict')}", flush=True)

    stem = path.stem
    html_path = out_dir / f"{stem}.redline.html"
    write_html(reqs, html_path, path.name, model, time.time() - t0)
    write_csv(reqs, out_dir / f"{stem}.redline.csv")
    if not quiet:
        print(f"[slothspec] done in {time.time() - t0:.0f}s -> {html_path}")
    return html_path


def watch(folder: Path, model: str | None, interval: int) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    done = folder / "reviewed"
    done.mkdir(exist_ok=True)
    print(f"[slothspec] watching {folder}. Drop specs in and go do something else.")
    while True:
        for p in sorted(folder.iterdir()):
            if p.is_file() and p.suffix.lower() in SUPPORTED and not p.name.startswith((".", "~$")):
                # wait until the file stops growing (still copying / still saving)
                size = -1
                while size != p.stat().st_size:
                    size = p.stat().st_size
                    time.sleep(1)
                try:
                    run(p, done, model)
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
        s.add_argument("--model", default=llm.DEFAULT_MODEL, help="Ollama model tag (default: %(default)s)")
        s.add_argument("--rules-only", action="store_true", help="skip the model, pattern checks only")
        if name == "review":
            s.add_argument("--out", type=Path, help="output folder (default: next to the file)")
        else:
            s.add_argument("--interval", type=int, default=10, help="seconds between folder checks")
    a = ap.parse_args(argv)

    model = None if a.rules_only else a.model
    if model:
        try:
            llm.ping(model)
        except llm.OllamaUnavailable as e:
            sys.exit(f"[slothspec] {e}")

    if a.cmd == "review":
        out = a.out or a.path.parent
        out.mkdir(parents=True, exist_ok=True)
        run(a.path, out, model)
    else:
        watch(a.path, model, a.interval)


if __name__ == "__main__":
    main()
