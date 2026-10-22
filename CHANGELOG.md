# Changelog

## [Unreleased] (v0.2.0)

### Changed
- **Calibrated model grading.** v0.1.0 caught every planted problem but also flagged 4 of 5 clean requirements. Added a rubric defining good / needs work / rewrite, with examples taken from outside the test spec (radar, pump, heater, console) so the sample spec results stay honest.
- Model is told not to invent details the author didn't write, and not to call plain words ambiguous unless a tester would be stuck.
- When pattern checks find nothing, the model is told so, to stop it from hunting for problems.
- Thinking mode off (`think: false`) and output capped at 400 tokens to cut CPU time. Falls back cleanly for models without a thinking switch.

## [0.1.0] - 2026-10-22

### Added
- Extracts shall statements and IDs from .docx, .pdf, .txt, .md
- Deterministic pattern checks: vague terms, TBD/TBR, escape clauses, compound requirements, and/or, open-ended lists, optimization goals, negatives, passive voice, numbers without units
- Local Gemma review via Ollama with a fixed JSON schema: verdict, verification method, how to verify, rewrite
- HTML redline report and CSV export
- Watch-folder mode and answer cache

### Baseline results (sample pet feeder spec, 20 reqs, 16 GB laptop, CPU only)
| | gemma4:e4b | gemma4:e2b |
|---|---|---|
| Time | 14.7 min | 7.7 min |
| Problems caught (of 15) | 15 | 15 |
| Clean reqs left alone (of 5) | 1 | 5 |
