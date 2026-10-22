*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 3: Slow and Steady](https://dev.to/challenges/hacktoberfest-week3-2026-10-19)*

## What I Built

I'm a Digital Systems Engineering Manager in defense aerospace. Air Force, then industry, about ten years total. A big chunk of that has been reading other people's requirements and telling them, politely, that "the system shall be user-friendly" is not a requirement.

Here's the dirty secret of requirements review: most bad requirements are bad in the same ten ways. Vague words. TBDs. "If possible." Three requirements duct-taped into one sentence with "and shall." A number with no unit, so you get to guess whether the drop test is 1 meter or 1 mile. You end up writing the same comment 40 times, and by requirement 300 your brain has left the building and you start missing the ones that actually matter.

So I built **SlothSpec**. Drop a spec in a folder, go do literally anything else, come back to a redline:

- every shall statement pulled out with its ID
- the usual suspects highlighted (vague words, TBDs, escape clauses, compound requirements, numbers with no units)
- a verdict from a local Gemma 4 model: **good**, **needs work**, or **rewrite**
- how you'd verify it (Inspection / Analysis / Demonstration / Test) and what the tester physically does
- a suggested rewrite, with `<<placeholders>>` where a number is missing, because the model is not allowed to make numbers up. Ever.

I still make the calls. I just don't have to go hunting for "if possible" anymore. The sloth does that.

## Demo

- **Toy spec report:** https://senseinate.github.io/slothspec/
- **Real NASA spec report:** https://senseinate.github.io/slothspec/nasa.html

The toy spec is a smart pet feeder I wrote badly on purpose: 20 requirements, 15 with planted problems, 5 that are fine. From the live report:

```
SPF-022 The SPF shall be robust to tampering by pets, including but not
        limited to pawing, tipping, and chewing.
```

"Robust" plus "including but not limited to" means you can't test it and you can't scope it. Gemma 4 handed back:

```
The SPF shall withstand pawing forces up to <<max force, N>> without functional degradation.
The SPF shall withstand tipping forces up to <<max force, N>> without functional degradation.
The SPF shall withstand chewing forces from <<pet type>> without functional degradation.
```

Three requirements wearing a trench coat, split into three you can actually test. Not perfect (the chewing line still needs a force value), which is kind of the point. It's a first pass, not a replacement for the engineer.

But a toy spec I wrote myself proves nothing. So I pointed it at a real one.

[SCREENSHOT: redline report]

## Code

{% github SenseiNate/slothspec %}

## How I Built It

Everything runs on my laptop. 16 GB of RAM, integrated AMD graphics, no real GPU. It never touches the internet.

**Stack:** Python, [Ollama](https://ollama.com), and Google's open-weight **Gemma 4** (`gemma4`, a.k.a. e4b, and `gemma4:e2b`).

Two layers, on purpose:

**1. Pattern checks. No model.** Regex for things that are always wrong: "adequate," "near real-time," "TBD," "and/or," "if possible," "including but not limited to," "minimize," numbers with no units, "should" where you mean "shall." Fast, free, and the same spec gets the same flags every time. That matters when you have to defend a comment in front of a review board.

**2. Gemma.** Each requirement goes to the local model along with whatever the pattern checks found. It answers in a fixed JSON schema (Ollama's `format` parameter), so I'm never parsing prose. Temperature 0.

Plus the stuff that makes it usable: **watch mode** (drop a file in a folder, the redline shows up in `reviewed/`), a **cache** (fix 3 requirements, rerun, only those 3 hit the model), and **CSV out** for pasting into a comment matrix.

### Round 1: the toy spec

**v0.1 was a nitpicker.** Caught 15 of 15 planted problems, and also flagged 4 of the 5 that were fine. It wanted "shall not dispense more than 3 portions per hour" rewritten because "shall not" is negative, and then its rewrite said "does not exceed." Same thing, more words. 14.7 minutes for 20 requirements.

**v0.2 got a rubric** for what good / needs work / rewrite actually mean, with examples. I caught myself cheating here: my first examples came straight from the test spec, which is handing it the answer key. Swapped them for a radar, a pump, and a heater. Then the big surprise: Gemma 4's thinking mode was on by default, writing a hidden essay before every one-line verdict. One flag (`think: false`) took the run from **14.7 minutes to 5.2**.

**v0.3 was the experiment that lost.** The data said the small model (e2b) was the better grader and the big one (e4b) the better editor, so I built a hybrid: e2b grades, e4b rewrites only what got flagged. It had fewer false alarms but was slower, and the rewrites were no better. I tried giving the editor a scratchpad, and it got *worse*: told to "find what the grader missed," it started inventing requirements. Firmware integrity checks on a pet feeder. I reverted it, and the revert commit has the numbers. The default stayed boring: **one model, e4b, 3.4 minutes.**

### Round 2: a real NASA spec

[KSC-DE-512-SM](https://ntrs.nasa.gov/api/citations/20150001362/downloads/20150001362.pdf) is NASA Kennedy's design standard for ground support equipment. It's 97 pages, approved for public release, and it's the kind of document I actually review for a living. It's in the repo, so anyone can rerun this.

**The PDF reader fell apart first.** v0.3 pulled 451 "requirements" out of it, including page footers glued onto sentences, the table of contents, the revision history, and the name of a *referenced standard* ("IPC-6018") stamped on 16 requirements as their ID. My clean little text file had never prepared it for a real PDF. The fix:
- strip anything that repeats across pages
- skip dot-leader TOC lines
- build IDs from the document's own outline, so you get `5.4.7a` and `6.3.1.1b(2)(a)`, exactly how a reviewer would cite them
- require section numbers to count up, so a table row starting with "2" can't pose as section 2
- stop at the government forms stapled to the back

The result was **333 clean shall requirements**, every one with its real ID.

**Then the pattern checks cried wolf.** "Table **1**" and "NFPA **70**" got flagged as numbers with no units. "GS shall be designed in accordance with..." got flagged as passive voice, when it's just normal spec language. I tuned the rules against real text: flags went from 224 to 104, and the real catches survived.

**Then the model flagged 94% of it.** 312 of 333 requirements, in a published, approved NASA standard. Nobody reads 312 comments.

I went through them. **141 were the same complaint:** "shall be in accordance with [standard]" got dinged for relying on an external document. That's not a defect, it's how design standards work. "Vacuum systems shall be designed in accordance with ASME B31.9" is complete; you verify against B31.9.

One rubric line fixed it, with an example from an unrelated field (FCC Part 15, which this NASA doc never mentions, so no answer key this time). Then I reran the full hour:

| NASA spec, 333 reqs | Before | After |
|---|---|---|
| Flagged | 312 (94%) | **238 (71%)** |
| "In accordance with" flagged | 141 of 149 | **77** |
| Real catches kept | 42 | **42, none lost** |
| Time, unattended | 58 min | 56 min |

The real catches are the kind of thing I'd actually put in a comment matrix:

- **4.2.3.4j:** hazards "mitigated to an *acceptable* level." Acceptable to whom? → `<<acceptable risk level>>`
- **6.4.8c:** filters "as close *as possible*" to flight hardware → `within <<distance, mm>>`
- **6.2c:** materials certified "*as required*." Required by what?
- **4.2.3.4k:** "FMEA *and/or* Hazard Analysis" → split into two requirements
- **4.2.3.1a:** redundant systems "physically oriented or separated" with no separation criteria. No regex catches that one; the model did.

71% is still too high, and I'm not going to pretend otherwise. What's left has no single cause I could fix, just a model with a picky streak. The useful signal is where the pattern checks and the model *agree*: those 42 are the comments worth sending, so the report puts them first with a green "high confidence" badge and a filter button. Read the top, skim the rest.

**Known limitation:** "food-safe materials and/or BPA-free plastic" came back as two mandatory requirements (AND) in every run, every model, even with a prompt rule specifically against it. If your spec uses and/or, read those rewrites closely.

## Why Does Open Innovation Matter?

For this job, a closed API isn't a tradeoff. It's a non-starter.

The specs I'd want to run this on are proprietary or export-controlled. They don't go into a public chatbot, period, no matter how smart the chatbot is. A tool that ships the document to someone else's server is a tool I'm not allowed to use. Running Gemma on my own machine is the only reason this thing can touch the documents it was built for.

(To be clear: SlothSpec is a personal side project. The demos are a fake pet feeder and a public-release NASA document. No work data was harmed in the making of this post.)

The rest of the case is basically this whole post:

- **I could actually run the experiments.** Two model sizes, four prompt versions, a hybrid, a revert, and two full hour-long passes over a 333-requirement spec. Something like a dozen full runs, and the bill was zero. With a metered API I'd have stopped tuning much sooner, and I'd never have run the NASA doc twice.
- **Swapping models is one flag.** That's how I found the grader/editor split.
- **I own every knob.** Thinking mode, temperature, the schema, even the order of the JSON fields (which turned out to matter: the model was leaking rewrites into the wrong field until I reordered them). When it was wrong, I changed it and reran. No support ticket.
- **An hour unattended costs electricity.** Watch mode can grind through a spec overnight.
- **It works offline.** Plane, basement, wherever.

Where closed would win: speed and raw quality. A frontier model would be faster and probably less picky. But faster at something I'm not allowed to do doesn't help me.

## My Agent Session

I built this with Claude as a pair programmer. It wrote and tested the code; I ran every version on my actual laptop and fed it the real results. Claude would propose a change, my run would say whether it worked, and we'd decide together. When the editor scratchpad made things worse, the call was to revert it, not keep tuning.

The best record of the session is the [commit history](https://github.com/SenseiNate/slothspec/commits/main) and the [CHANGELOG](https://github.com/SenseiNate/slothspec/blob/main/CHANGELOG.md). Every change says what changed, why, and the numbers behind it, including the ones that didn't work. Every version is tagged, and there are regression tests, so the toy spec results can't quietly break while I'm fixing the NASA ones.

## The Lazy Payoff

A 97-page NASA standard. 333 requirements. **Under an hour, on a laptop with no GPU, while I did something else.** I'm not doing that first pass by hand in an hour. Not even close.

I've been chasing this for a while. A few years ago I rigged DOORS to Tableau to auto-generate redlines because I was sick of building them by hand, and it saved people up to 8 hours each on big specs. This is the same itch, except now the robot also suggests the fix.

The real win isn't the minutes. It's that the "as possible"s and "acceptable level"s get caught every single time, so my brain is free for the requirements that are wrong for actual engineering reasons. No regex or 4B model is catching those. Yet.

## Prize Categories

- Best Use of Gemma

---

Built by @nathanbienvenu97. MIT licensed. If you write requirements for a living, throw a spec at it and tell me what it misses.
