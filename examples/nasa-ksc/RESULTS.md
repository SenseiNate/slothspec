# Results: NASA KSC-DE-512-SM Rev L

Real-world test of SlothSpec on a published, approved NASA design standard. See [SOURCE.md](SOURCE.md) for provenance.

**Setup:** `slothspec review KSC-DE-512-SM-RevL.pdf --verbs shall`, single mode, `gemma4` (e4b), Ollama, 16 GB laptop with integrated AMD graphics, CPU only.

## Summary

| | Baseline (2d5d7aa) | v0.4.0 (71f71b0) |
|---|---|---|
| Shall requirements | 333 | 333 |
| Flagged | 312 (94%) | **238 (71%)** |
| "in accordance with [standard]" flagged | 141 of 149 | **77 of 149** |
| Real catches kept (pattern + model agree) | 42 | **42, none lost** |
| Time | 58 min 17 s | 56 min (shared the CPU with another run for its first ~4 min) |
| Model errors | 0 | 1 (5.4.19.2, answer cut off at the output cap; fixed in v0.4.1, see below) |

One rubric line (pointing to a named standard is complete) cleared 74 false alarms, 64 of them pure standard references like "Vacuum systems shall be designed in accordance with ASME B31.9." Every real catch from the baseline is still flagged.

**How to read the report:** it sorts worst first by pattern-check score, so requirements with pattern hits come up top. The ones the model also flagged (42 with a medium/high hit) are the high-confidence comments. Model-only flags further down are worth a skim but are pickier.

## Baseline run (code at 2d5d7aa)

File: [results-baseline.csv](results-baseline.csv)

| | |
|---|---|
| Pages | 97 |
| Shall requirements extracted | 333 |
| Total time | 58 min 17 s (about 10.5 s per requirement) |
| Model errors | 0 |
| Verdicts | 21 good, 287 needs work, 25 rewrite |
| **Flagged** | **312 of 333 (94%)** |

### What the 312 flags actually were

| Bucket | Count | Assessment |
|---|---|---|
| "shall be in accordance with [standard]" | 141 of 149 such requirements flagged | Mostly false alarms. Delegating to a referenced standard is how design standards are supposed to work; you verify by inspecting against the standard. The model kept asking for the standard's contents to be spelled out. |
| Model flagged AND a medium/high pattern check fired | 42 | Mostly real. 22 of these are escape clauses, vague terms, and/or, or optimization words. |
| Model only, no pattern hit at all | 217 total model flags on pattern-clean requirements (overlaps the first bucket) | Mixed. Some real (see 4.2.3.1a below), many picky. |

### Real catches (what a reviewer would actually send back)

| ID | Problem | Suggested rewrite (excerpt) |
|---|---|---|
| 4.2.3.4j | "mitigated to an *acceptable* level" | "...mitigated to a risk level of `<<acceptable risk level>>`..." |
| 6.3.1.3.2c | "risk is above an *acceptable* level" | "...above a risk level of `<<acceptable risk level>>`..." |
| 6.4.8c | filters located "as close *as possible*" to flight hardware | "...located within `<<distance, mm>>` of the flight hardware interface." |
| 6.2c | certified "*as required*" | flagged; the rewrite kept "as required by the procuring document" |
| 4.2.3.4k | "FMEA *and/or* Hazard Analysis" | split into two requirements |
| 4.2.3.4a | assessment performed "*early* in the design phase" | "...at `<<design phase milestone>>`..." |
| 4.2.3.1a | "physically oriented or separated" with no separation criteria (model only, no pattern hit) | flagged as unverifiable without a separation distance or orientation criteria |

## v0.4.0 run (code at 71f71b0)

File: [results-v0.4.0.csv](results-v0.4.0.csv)

Verdicts: 95 good, 217 needs work, 21 rewrite. Transitions from baseline: 74 needs work to good, 5 rewrite to needs work, 1 needs work to rewrite, everything else unchanged.

What's still flagged (238) is spread out, with no single blind spot left: vague or not measurable (88, some fair, some picky), compound (39), external reference (27, mostly "program-defined methodology", which is a fair catch), missing actor (26), plus a long tail. Stopped tuning here; another round would be chasing noise.

All seven example catches above are still flagged in v0.4.0.

**Correction (v0.4.1):** this run had 1 model error, not 0 as first reported. The answer for 5.4.19.2, a requirement that lists a long run of IPC standards, hit the 400-token output cap and came back as broken JSON. The tool labeled the failure "needs work", so it was counted as a flag the model never made. v0.4.1 retries cut-off answers with a bigger cap and labels failures "error". Re-running just that requirement (the other 332 came from cache) gave a real "needs work", so the totals above are unchanged: 238 flagged, 42 high confidence, 95 good, now 0 errors.

### Takeaways

- Extraction and runtime held up on a real 97-page document: every requirement got its real section ID, zero crashes, about an hour unattended.
- The useful signal is where the pattern checks and the model agree. The report sorts pattern hits to the top, so that's where to start reading.
- One blind spot drove nearly half the noise: treating "in accordance with [standard]" as a defect. One rubric example (from an unrelated field, FCC Part 15, which this document never mentions) cut flags from 94% to 71% without losing a single real catch.
- The model is still pickier than a human reviewer would be. Trust the top of the report; skim the rest.
