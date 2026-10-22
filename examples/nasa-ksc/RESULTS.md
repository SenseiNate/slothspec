# Results: NASA KSC-DE-512-SM Rev L

Real-world test of SlothSpec on a published, approved NASA design standard. See [SOURCE.md](SOURCE.md) for provenance.

**Setup:** `slothspec review KSC-DE-512-SM-RevL.pdf --verbs shall`, single mode, `gemma4` (e4b), Ollama, 16 GB laptop with integrated AMD graphics, CPU only.

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

### Takeaways

- Extraction and runtime held up on a real 97-page document: every requirement got its real section ID, zero crashes, about an hour unattended.
- The useful signal is where the pattern checks and the model agree. The report sorts worst first, so those land at the top.
- One blind spot drove nearly half the noise: treating "in accordance with [standard]" as a defect. Addressed in the next commit with one rubric example (taken from an unrelated field, FCC Part 15, which this document never mentions).
