# Changelog

All results are on `examples/sample_spec.txt` (20 requirements: 15 with planted problems, 5 clean), run on a 16 GB laptop with integrated AMD graphics, CPU inference.

## [Unreleased] (v0.3.0)

### Added
- **Hybrid mode** (`--grader` / `--editor`). A small model grades every requirement; a bigger model rewrites only the ones flagged by the grader or by a medium/high pattern check. Based on v0.2.0 results: e2b was the better grader, e4b the better editor.
- Report header and CSV show time per pass and which model wrote each rewrite (`Rewritten by` column, added at the end so existing columns don't move).

### Changed
- Prompts split into pieces (rubric, grading rules, rewrite rules, verification rules) so each model only gets instructions for its own job.
- Two new rewrite rules from observed misses: don't drop any part of the requirement (e2b dropped "quietly" from SPF-003) and keep and/or logic honest (e4b turned and/or into AND on SPF-024). Applies to single mode too.

### Fixed
- Rewrites leaking into the "how to verify" field (about 9 of 20 rows with e4b in v0.2.0). Ollama fills JSON fields in schema order, and `how_to_verify` came before `rewrite`. Reordered the schema and defined the field in the prompt.
- Model check accepted any tag with a matching base name (asking for `gemma4:31b` passed if `gemma4:e2b` was pulled, then every request failed). Present since v0.1.0.

## [0.2.0] - 2026-10-22

### Changed
- **Calibrated grading.** Added a good / needs work / rewrite rubric with examples taken from outside the test spec (radar, pump, heater, console) so sample results stay honest.
- Model told not to invent details or call plain words ambiguous, and told when pattern checks found nothing.
- Thinking mode off and output capped at 400 tokens.

### Results
| | gemma4 (e4b) | gemma4:e2b |
|---|---|---|
| Time | 5.2 min (was 14.7) | 3.5 min (was 7.7) |
| Problems caught (of 15) | 15 | 15 |
| Clean reqs left alone (of 5) | 3 (was 1) | 5 |
| Rewrites that fixed it (of 15) | 13 | 8 |

Thinking mode was on by default and accounted for most of the v0.1.0 runtime.

## [0.1.0] - 2026-10-22

### Added
- Extracts shall statements and IDs from .docx, .pdf, .txt, .md
- Deterministic pattern checks: vague terms, TBD/TBR, escape clauses, compound requirements, and/or, open-ended lists, optimization goals, negatives, passive voice, numbers without units
- Local Gemma review via Ollama with a fixed JSON schema: verdict, verification method, how to verify, rewrite
- HTML redline report and CSV export
- Watch-folder mode and answer cache

### Results
| | gemma4 (e4b) | gemma4:e2b |
|---|---|---|
| Time | 14.7 min | 7.7 min |
| Problems caught (of 15) | 15 | 15 |
| Clean reqs left alone (of 5) | 1 | 5 |
