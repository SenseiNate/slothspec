# Changelog

All results are on `examples/sample_spec.txt` (20 requirements: 15 with planted problems, 5 clean), run on a 16 GB laptop with integrated AMD graphics, CPU inference.

## [0.4.0] - 2026-10-22

First run on a real document: NASA KSC-DE-512-SM Rev L, a 97-page public-release ground support equipment design standard. v0.3.0 had only ever seen the clean 20-line sample spec.

### Results
| NASA doc, gemma4 | baseline | v0.4.0 |
|---|---|---|
| Flagged | 312 of 333 (94%) | 238 (71%) |
| "in accordance with" flagged | 141 of 149 | 77 |
| Real catches kept | 42 | 42 (none lost) |
| Time | 58 min | 56 min |

Sample spec (regression check): 15/15 caught, 3/5 clean left alone, 13/15 rewrites fixed. Same as v0.3.0 within noise.

### Known limitation
- Still flags 71% of an approved NASA standard. What's left is spread across vague, compound, and missing-actor complaints with no single fixable cause. The 42 requirements where a medium/high pattern check and the model agree are the high-confidence comments; the report sorts pattern hits to the top, so they're easy to find.

### Fixed
- **PDF extraction on real documents.** v0.3.0 pulled 451 "requirements" from the NASA doc, with page footers glued onto them, table-of-contents lines, the revision history, and a referenced standard's name ("IPC-6018") stamped on 16 of them as an ID. Now:
  - running headers/footers stripped (lines repeating across pages, page numbers ignored)
  - table-of-contents dot-leader lines skipped
  - IDs follow the document's own outline: heading `5.4.7` + item `a.` = `5.4.7a`, nested `(2)` then `(a)` = `6.3.1.1b(2)(a)`
  - headings must count up in order, so table rows and numbered lists can't pose as sections
  - "Rationale:" / "Note:" text and sentences that only mention "shall" in quotes are skipped
  - stops at the DD 1426 / SF 298 forms stapled to the back of NASA and DoD documents
  - explicit IDs like `SPF-001` must be followed by the sentence, so a standard named at the start of a list line isn't read as an ID
  - Result on the NASA doc: 333 shall requirements, every one with its real section ID, no duplicates, no junk. Sample spec output unchanged.

- **Pattern-check false alarms on real engineering text.** On the NASA doc, v0.3.0 flagged 224 of 333 requirements, mostly noise. Now 104, with 42 medium/high:
  - "number without unit" (82 to 7): skips references (Table 1, see 6, NFPA 70, Article 500, Category 1, criticality 1, 1S, or 2), title numbers (29 CFR 1910), slash standards (AMS 2759/9), factors of safety, inline list markers; knows MPa, psia, psig, ksi; keeps thousands like 1,240 together. The 7 left are chemical subscripts the PDF stores as loose digits (N2O4 comes out as "N O 2 4").
  - "passive voice" (155 to 38): only fires when someone has to do something and the sentence doesn't say who ("shall be performed", "shall be applied"). "GS shall be designed in accordance with X" is normal spec language.
  - "vague term": dropped "standard" (usually means the document) and "flexible" (usually a cable type).
  - Only change on the sample spec: SPF-024 no longer gets a low-severity passive flag for "shall be made of food-safe materials".

### Changed
- **Pointing to a standard is no longer treated as a defect.** Baseline run on the NASA doc flagged 141 of its 149 "shall be in accordance with [standard]" requirements for relying on an external document. That's how design standards are supposed to work. Rubric gains one example (FCC Part 15, a field the NASA doc never mentions) and one rule line. See `examples/nasa-ksc/RESULTS.md`.

### Added
- `examples/nasa-ksc/RESULTS.md` and `results-baseline.csv`: the first full model run on the NASA doc and a breakdown of what got flagged.
- `examples/nasa-ksc/`: the NASA KSC-DE-512-SM Rev L PDF (public release, U.S. Government work) with a SOURCE.md giving provenance, distribution statement, SHA-256, and the command to reproduce.
- `tests/test_regression.py`: no model, no network, about a second. Locks in the sample spec's extraction and rule hits, the number/passive rules (15 real-world cases from the NASA doc), the `--verbs` filter, and the rewrite cleanup. Runs with pytest or plain `python tests/test_regression.py`.
- `--verbs` option. Some specs define "should" as guidance, not a requirement (this NASA doc says so in its foreword). `--verbs shall` respects that. Default is still all four verbs.

## [0.3.0] - 2026-10-22

### Results
| | single, gemma4 (e4b) | hybrid (e2b grades, e4b rewrites) |
|---|---|---|
| Time | 3.4 min | 4.9 min |
| Problems caught (of 15) | 15 | 15 |
| Clean reqs left alone (of 5) | 3 | 5 |
| Rewrites that fixed it (of 15) | 11 to 14 | 11 |

**Single mode with gemma4 stays the recommended default.** Hybrid fixed the false alarms but was slower and its rewrites were no better.

### Tried and reverted
- Gave the hybrid editor a `problems` scratchpad before the rewrite, on the theory that single mode's issues list acts as a reasoning step. Result: 7 of 15 fixed (down from 11), edit pass 2.0 to 3.8 min. Told to "find what the grader missed," it added scope: integrity checks nobody asked for, a food type, an escape clause put back in. Reverted in 65d8ebc.

### Known limitation
- "and/or" on SPF-024 became two mandatory requirements in every run, every model, despite a prompt rule against it.

### Added
- **Hybrid mode** (`--grader` / `--editor`, experimental). A small model grades every requirement; a bigger model rewrites only the ones flagged by the grader or by a medium/high pattern check. Based on v0.2.0 results: e2b was the better grader, e4b the better editor.
- Report header and CSV show time per pass and which model wrote each rewrite (`Rewritten by` column, added at the end so existing columns don't move).

### Changed
- Prompts split into pieces (rubric, grading rules, rewrite rules, verification rules) so each model only gets instructions for its own job.
- Two new rewrite rules from observed misses: don't drop any part of the requirement (e2b dropped "quietly" from SPF-003) and keep and/or logic honest (e4b turned and/or into AND on SPF-024). Applies to single mode too.

### Fixed
- Rewrites leaking into the "how to verify" field (about 9 of 20 rows with e4b in v0.2.0). Ollama fills JSON fields in schema order, and `how_to_verify` came before `rewrite`. Reordered the schema and defined the field in the prompt.
- Single mode tacking other fields onto the rewrite (3 of 20 rows with e4b had a "how_to_verify:" line, one had a trailing "(Test)"). Prompt now says the rewrite holds only shall statements, and `clean_rewrite()` strips label lines and trailing method tags as a deterministic safety net.
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
