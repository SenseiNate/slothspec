# 🦥 SlothSpec

Drop a requirements spec in a folder. Go get coffee. Come back to a redline.

SlothSpec reads a spec (.docx, .pdf, .txt, .md), pulls out every "shall" statement, and flags the stuff a reviewer would circle in red: vague words, TBDs, escape clauses, compound requirements, numbers with no units. Then a local open-weight model (Gemma via Ollama) gives each one a verdict, a likely verification method, and a suggested rewrite.

Nothing leaves your machine. No API key, no cloud, no per-token bill.

## Why local

A lot of specs can't be pasted into a hosted chatbot. Proprietary, export controlled, or just "please don't." Running the model on your own box means the tool is actually allowed to touch the documents it was built for.

## Quick start

```bash
# 1. get Ollama + a Gemma model
ollama pull gemma4

# 2. install
pip install -e .

# 3. one file
slothspec review examples/sample_spec.txt

# or the lazy way: leave it watching a folder
slothspec watch ~/Specs/inbox
```

Reports land as `<name>.redline.html` (open in a browser) and `<name>.redline.csv` (drop into your RVTM or a spreadsheet).

## Options

| flag | what it does |
|---|---|
| `--model gemma4:e4b` | any Ollama model tag. Swap freely. |
| `--rules-only` | skip the model. Instant, works on anything. |
| `--out DIR` | where to write the report |
| `--interval N` | watch mode: seconds between folder checks |

Env vars: `OLLAMA_HOST` (default `http://localhost:11434`), `SLOTHSPEC_MODEL`.

## How it works

1. **Extract.** Splits the doc into sentences with a binding verb and grabs IDs like `SYS-042` or `3.2.1.4`.
2. **Pattern checks.** Deterministic regex rules. Fast, free, repeatable.
3. **Model review.** Each requirement plus its pattern hits goes to the local model with a JSON schema, so the output is always structured. Temperature 0. The model is told never to invent numbers; missing thresholds come back as `<<placeholders>>`.
4. **Cache.** Answers are cached by model + text, so re-running after you fix 3 requirements only re-checks those 3.

## License

MIT
