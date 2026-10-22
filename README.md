# 🦥 SlothSpec

Drop a requirements spec in a folder. Go get coffee. Come back to a redline.

SlothSpec reads a spec (.docx, .pdf, .txt, .md), pulls out every "shall" statement, and flags the stuff a reviewer would circle in red: vague words, TBDs, escape clauses, compound requirements, numbers with no units. Then local open-weight models (Gemma 4 via Ollama) grade each one, say how you'd verify it, and suggest a rewrite.

Nothing leaves your machine. No API key, no cloud, no per-token bill.

**Live sample report:** https://senseinate.github.io/slothspec/

## Why local

A lot of specs can't be pasted into a hosted chatbot. Proprietary, export controlled, or just "please don't." Running the model on your own box means the tool is actually allowed to touch the documents it was built for.

## Quick start

```bash
# 1. get Ollama + Gemma 4 (both sizes for hybrid mode)
ollama pull gemma4        # e4b, the editor
ollama pull gemma4:e2b    # the grader

# 2. install
pip install -e .

# 3. recommended: hybrid mode
slothspec review examples/sample_spec.txt --grader gemma4:e2b --editor gemma4

# or the lazy way: leave it watching a folder
slothspec watch ~/Specs/inbox --grader gemma4:e2b --editor gemma4
```

On Windows, if `slothspec` isn't found after install, use `python -m slothspec` instead.

Reports land as `<name>.redline.html` (open in a browser) and `<name>.redline.csv` (paste into a comment matrix or RVTM).

## Modes

| mode | command | what happens |
|---|---|---|
| **hybrid** (recommended) | `--grader gemma4:e2b --editor gemma4` | Small model grades every requirement. Big model rewrites only the ones that need it. |
| single | `--model gemma4` (default) | One model grades and rewrites everything. |
| rules only | `--rules-only` | Pattern checks only. No model, instant. |

Why hybrid: on the sample spec, the two sizes turned out to be good at different jobs.

| sample spec, 20 reqs, 16 GB laptop, CPU only | gemma4 (e4b) | gemma4:e2b |
|---|---|---|
| Planted problems caught (of 15) | 15 | 15 |
| Clean requirements left alone (of 5) | 3 | **5** |
| Rewrites that actually fixed it (of 15) | **13** | 8 |
| Time, single mode | 5.2 min | 3.5 min |

The small model is the better judge; the big model is the better editor. Hybrid uses each for what it's good at, and the big model never wastes time on requirements that are already fine.

A requirement goes to the editor if the grader flags it **or** if the pattern checks found a medium/high problem. The regex is the safety net: a TBD gets fixed even if the small model misses it.

## Options

| flag | what it does |
|---|---|
| `--grader MODEL` / `--editor MODEL` | hybrid mode. If you give only one, the other uses `--model`. |
| `--model MODEL` | single mode model (default `gemma4`). Any Ollama tag works. |
| `--rules-only` | skip the model |
| `--out DIR` | where to write the report (review) |
| `--interval N` | seconds between folder checks (watch) |

Env vars: `OLLAMA_HOST` (default `http://localhost:11434`), `SLOTHSPEC_MODEL`.

## How it works

1. **Extract.** Splits the doc into sentences with a binding verb and grabs IDs like `SYS-042` or `3.2.1.4`.
2. **Pattern checks.** Deterministic regex rules. Fast, free, same flags every time.
3. **Model pass.** Each requirement plus its pattern hits goes to the local model with a fixed JSON schema, so output is always structured. Temperature 0, thinking off. The model is told never to invent numbers; missing thresholds come back as `<<placeholders>>`.
4. **Cache.** Answers are keyed by model + prompt + text, so re-running after you fix 3 requirements only re-checks those 3.

See [CHANGELOG.md](CHANGELOG.md) for what changed between versions and the results behind each change.

## License

MIT
