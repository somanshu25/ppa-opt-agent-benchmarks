# Measured Findings

Everything here was measured in this environment (ORFS `02ba50d53`, container
`openroad/orfs:latest`). Negative results are kept deliberately -- they are the
reason several tempting benchmark ideas were cut.

---

## F1 — ORFS QoR is bit-exact deterministic across thread count

Four full runs per design at `NUM_CORES` = 1, 2, 4, 8, each in its own
`FLOW_VARIANT` so no two runs could share output directories.

| platform / design | runs | result |
|---|---|---|
| sky130hd / gcd | 4 | all `6_report.json` bit-identical (md5 `caacb9ff…`) |
| nangate45 / gcd | 4 | all `6_report.json` bit-identical (md5 `dfe2ef7c…`) |

**The "make did nothing" explanation is ruled out.** Stage mtimes show a full
re-run each time — for the sky130hd repeat, `1_synth` at 06:21:01 through
`6_report` at 06:22:58.

Comparing all 16 stage JSONs (nangate45/gcd, c1 vs c8), exactly **one** file
differs — `5_1_grt.json` — and all 9 differing keys are `_s`-suffixed runtime
instrumentation:

```
globalroute__global_route__fastroute__monotonic_s     c1=0.00126657  c8=0.00198937
globalroute__global_route__fastroute__finalization_s  c1=0.000188035 c8=0.000344065
```

**No QoR metric differs anywhere.** Wall time moves (45.5 s → 36.9 s); results
do not.

**Consequence:** the grader needs no statistical deadband for thread variation.
Any QoR delta is signal.

**Scope of the claim:** thread-count variation only, two small designs, one
machine. gcd sets `SYNTH_REPEATABLE_BUILD ?= 1`, which suppresses synthesis
nondeterminism by construction. This is *not* a claim that ORFS is deterministic
across machines, tool versions, or semantically-null input rewrites (see F5).

---

## F2 — sky130hd/gcd is intentionally over-constrained; nangate45 is the right platform

| | sky130hd/gcd | nangate45/gcd |
|---|---|---|
| clock period | 1.1 ns | 0.46 ns |
| measured setup WS | **−1.62 ns** | **+0.016 ns** |
| measured setup TNS | −70.99 ns | 0 |
| timing-repair buffers | 197 (33% of area) | 62 |
| DRC / antenna / placement violations | 0 | 0 |

The sky130hd numbers are **not** a broken environment. Upstream's own
`designs/sky130hd/gcd/rules-base.json` expects `finish__timing__setup__ws ≥
−1.68` and `finish__timing__setup__tns ≥ −71.2`. We match upstream.

**Consequence:** nangate45/gcd is timing-clean, so every grader gate is
satisfiable on the baseline — the ideal FAIL→PASS substrate. On a design with a
−71 ns TNS floor, an injected defect is swamped and a "no violations" gate would
fail the baseline itself. sky130hd instances are generated but excluded from v1
scope.

---

## F3 — The ORFS SDC corpus is a four-command monoculture

All 83 `*.sdc` under `flow/designs/`, 10 platforms:

| command | files | command | files |
|---|---|---|---|
| `create_clock` | 74 | `set_clock_uncertainty` | 13 |
| `set_input_delay` | 67 | `set_false_path` | 8 |
| `set_output_delay` | 66 | `set_clock_groups` | 4 |
| `set_clock_latency` | 64 | `set_multicycle_path` | 1 |
| | | `create_generated_clock` | **0** |

**48 of 83 (58%) are the identical `clk_io_pct` template.**

**Consequence:** injector classes must target those four commands. Mutations
that remove uncertainty, false paths, or generated clocks have nothing to
remove. This bounds what *any* ORFS-based SDC benchmark can cover — a limitation
worth stating rather than hiding.

**Upside:** the monoculture means injectors generalise for free. All 5 operators
apply cleanly to all 4 target design SDCs (20/20).

---

## F4 — Sign-off STA against a held-out golden SDC is exact (validated)

The anti-cheat core. The agent edits `impl.sdc`; grading re-times the layout it
produced against a `golden.sdc` it never saw. Loosening constraints cannot buy
score because the loosened SDC is not the one used to judge.

Validated by running sign-off with golden == the SDC the flow actually used, and
requiring it to reproduce the flow's own `finish__*` numbers:

| metric | flow `finish__` | `signoff__` | match |
|---|---|---|---|
| setup WS | 0.016009 | 0.016009 | ✅ |
| setup TNS | 0 | 0 | ✅ |
| hold WS | 0.110785 | 0.110785 | ✅ |
| hold TNS | 0 | 0 | ✅ |
| clock skew | 0.00111066 | 0.00111066 | ✅ |
| fmax | 2252300000.0 | 2252300000.0 | ✅ |

**The self-test earned its keep — the first run failed.** Setup WS came out
0.0208 vs 0.016009 (4.8 ps). Cause: CTS injects `set_propagated_clock` into the
in-flow SDC, so the flow times a real clock tree while the pre-CTS golden SDC
declares *ideal* clocks. Sign-off on a post-CTS design must propagate clocks.
Fixed in `tcl/signoff_sta.tcl`; now exact.

Without the self-test this would have shipped as a silently-biased gate.

---

## F5 — NEGATIVE: the SDC is scraped textually, but the corruption is inert

ORFS derives the synthesis timing target from the SDC **by regex**, not by
parsing it (`scripts/variables.mk:220`):

```make
export ABC_CLOCK_PERIOD_IN_PS := $(shell sed -nE "s/^set\s+clk_period\s+(\S+).*|.*-period\s+(\S+).*/\1\2/p" $(SDC_FILE) | head -1 ...)
```

That value flows to `clock_period.txt` → `SDC_FILE_CLOCK_PERIOD` →
`abc -D <value>` in `synth_preamble.tcl`.

**A Tcl-valid, STA-identical rewrite defeats the regex.** Tested spellings:

| SDC form | scraped value |
|---|---|
| `set clk_period 0.46` | `0.46` ✅ |
| `create_clock -period 0.46 …` | `0.46` ✅ |
| `set clk_period 4.6e-1` | `4.6e-1` ⚠ |
| `set clk_period [expr 1000.0/2174.0]` | **`[expr`** ❌ |
| `create_clock -period [expr 0.46] …` | **`[expr`** ❌ |

Confirmed end-to-end — Yosys logged `Setting clock period to [expr` and ABC
received `-D [expr`. **No error, no warning, anywhere.**

**But it does not matter.** Synthesis output is bit-identical regardless:

| design | ABC `-D` | stdcell area | cell count |
|---|---|---|---|
| gcd (area script) | `0.46` / `[expr` | 626.696 | 513 |
| gcd (speed script) | `0.46` / `[expr` / `5.0` | 603.82 | 396 |
| aes | `0.82` / `[expr` / `5.0` | 15351.4 | 11406 |

Even a **6× period change** leaves synthesis untouched on aes.

**Consequence:** cut as a benchmark class. It is a genuine silent-corruption
channel with no demonstrated QoR consequence on either design — a good finding
and a bad task. Retained as the `CX` probe so the negative result stays
reproducible, permanently marked out of scope.

**Secondary consequence:** on these designs the SDC clock period has no
synthesis-stage effect at all, so period-perturbing injectors (C1) must draw
their signal from placement, CTS, and routing — not from synthesis.

---

## F6 — Runtime budget

| design | full flow, `NUM_CORES=8` |
|---|---|
| nangate45/gcd | ~37–46 s |
| nangate45/aes | **524 s (8.7 min)** |

Validation costs 3 runs per instance (baseline / broken / reference-fix). gcd:
4 classes ≈ 9 min. aes: 4 classes ≈ 105 min. Both affordable; ibex remains
untimed and out of scope.

---

## F7 — Validation results: 4 of 8 gcd instances are real tasks

First full validation run. nangate45/gcd, 4 classes x 2 randomised seeds,
10 flow runs (baseline shared per seed) plus 10 sign-off re-times.

Baseline for both seeds passed every gate. Results for the injected runs:

| instance | golden period | `finish__ws` | `signoff__ws` | baseline `signoff__ws` | area | validated |
|---|---|---|---|---|---|---|
| C1_s1 | 0.69 | **-0.42310** | 0.15946 | 0.18390 | **959.5** (+42%) | **yes** |
| C1_s2 | 0.58 | **-0.44799** | 0.09470 | 0.11997 | **1035.5** (+54%) | **yes** |
| C2_s1 | 0.69 | 0.18390 | 0.18390 | 0.18390 | 674.3 (+0.0%) | no |
| C2_s2 | 0.58 | 0.11997 | 0.11997 | 0.11997 | 673.5 (+0.0%) | no |
| C3_s1 | 0.69 | **0.24142** | **0.17635** | 0.18390 | 673.8 | **yes** |
| C3_s2 | 0.58 | 0.13196 | 0.12210 | 0.11997 | 674.8 | no |
| C5_s1 | 0.69 | 0.01837 | 0.18397 | 0.18390 | 674.3 | no |
| C5_s2 | 0.58 | **-0.03197** | **0.04390** | 0.11997 | **862.6** (+28%) | **yes** |

### C1 is the robust instance

Validated on both seeds with a large, unambiguous effect. Note *where* the
damage lands: sign-off timing degrades only slightly (0.184 -> 0.159), because
the golden period is loose enough that even a thrashed layout still meets it.
The real damage is **area, +42% and +54%** — the tool burned half the design
again trying to hit an impossible 0.00069 ns target.

This vindicates carrying an area cap as a PASS_TO_PASS assertion rather than
grading on timing alone. An over-constraint defect can pass every timing gate
and still be a disaster.

### C3 shows the predicted inversion — but only on one seed

C3_s1 is the effect the whole benchmark was designed around:

```
              flow's own view      held-out sign-off
baseline          0.18390               0.18390
C3 broken         0.24142  (better)     0.17635  (worse)
```

**The implementation run reports 31% more slack while the design is genuinely
worse.** An agent optimising the visible metric would call this an improvement.
Only sign-off against the golden SDC contradicts it.

But the degradation is 7.5 ps, and on seed 2 sign-off came out *better* than
baseline, so the instance did not validate. C3 is real but marginal and
seed-dependent on this design.

### C2 is vacuous on gcd — NEGATIVE RESULT

Deleting `set_input_delay` changed **nothing**: `finish`, `signoff` and area are
bit-identical to baseline on both seeds.

The injection is not at fault. The broken run genuinely elaborated **0 input
delay constraints versus 35 in the baseline**:

```
$ grep -c set_input_delay results/.../val_nangate45_gcd_C2_s1/6_final.sdc   ->  0
$ grep -c set_input_delay results/.../val_base_nangate45_gcd_s1/6_final.sdc -> 35
```

Removing all 35 constraints produced an identical design. gcd's input paths are
so far from critical that constraining them is a no-op — the worst path is
register-to-register and always was.

**Consequence:** C2 cannot be validated on gcd and is not shipped for it. The
class is only meaningful on a design whose I/O paths are near-critical. aes is
the next candidate. This is the second class killed by measurement, after CX.

### C5 is conditional on the size of the over-constraint

C5_s1 inflated `clk_io_pct` 0.21 -> 0.45 (2.1x) and did nothing. C5_s2 inflated
0.15 -> 0.45 (3.0x) and cost 28% area plus a hold violation. The injector should
scale the multiplier relative to the sampled baseline rather than jumping to a
fixed 0.45.

### What this says about the method

Half the generated instances were rejected, by measurement, before any agent saw
them. That is the validation loop doing its job — the same loop that killed CX.
An unvalidated instance is a guess about what a defect does; these numbers are
what it actually does.

It also isolates a design property worth stating: **on gcd, I/O timing is
irrelevant**. Three of the four classes (C2, C3, C5) operate on I/O constraints,
which is why they are weak or vacuous here, while C1 — which attacks the core
clock — is robust. Class selection has to be matched to the design.

---

## F8 — The grader survives adversarial agents (4/4 correct)

Validation compares baseline against injected runs with no agent involved, so
`edits_confined`, `no_disabled_checks` and every missing-metric path were
untested code. Four scripted agents against `nangate45_gcd_C1_s1` (golden
period 0.69), three attacking and one honest:

| decoy | its own `finish__ws` | held-out `signoff__ws` | resolved | expected | failed on |
|---|---|---|---|---|---|
| `oracle` (restores golden) | 0.1839 | 0.18390 | **yes** | yes | — |
| `null` (does nothing) | −0.4231 | 0.15946 | no | no | `area_not_ballooned`, `signoff_setup_ws` |
| `cheat_loose` (period → 5.0) | **+3.5836** | 0.14334 | no | no | `signoff_setup_ws` |
| `cheat_knob` (`SKIP_DETAILED_ROUTE=1`) | 0.1661 | 0.21163 | no | no | `drc_errors`, `antenna_violations`, `signoff_hold_ws`, `no_disabled_checks` |

**4/4 graded correctly.**

### The reward hack, measured

`cheat_loose` relaxed the clock period to 5.0 ns. Its own run reports
**+3.5836 ns of slack — 19x the baseline's 0.1839**. By any metric the agent can
see, it produced a spectacular design.

Sign-off against the golden SDC says 0.14334, *worse* than the baseline's
0.18390. It resolves to **zero**.

This is the benchmark's whole thesis in one row: the visible metric improved
19-fold while the design got worse, and the grader was not fooled.

### The honest control matters

Without `oracle`, a grader that simply failed everything would look perfectly
secure. `oracle` resolves with every assertion passing and `area_delta_pct: 0.0`,
which proves the instance is solvable and the gates are satisfiable.

### `cheat_knob` defeated the sign-off gate — and was caught anyway

The most instructive result. Disabling detailed routing suppresses extraction,
so timing is computed on an unrouted approximation and comes out
**optimistic**: `signoff__ws = 0.21163` against a baseline of 0.18390.

That is *better* than baseline, so it **passed both FAIL_TO_PASS assertions**.
The golden-SDC gate — the centrepiece of this benchmark — did not catch it.

It was caught by PASS_TO_PASS instead: `drc_errors`, `antenna_violations`,
`signoff_hold_ws`, and the `no_disabled_checks` denylist.

This is SWE-bench's F2P/P2P bracket validated empirically rather than argued
from theory. Neither set is sufficient alone:

* F2P alone -> `cheat_knob` resolves by not measuring anything.
* P2P alone -> `null` resolves by doing nothing.

It is also the concrete justification for the knob denylist. An agent tuning
flow variables can switch off the measurement that the primary gate depends on,
and the only defence is refusing to accept a run that produced no evidence.

---

## F9 — Baseline agent (Claude Code, headless): 3/4 resolved

> **Superseded by F10.** The one failure was a task-design defect, not an agent
> limitation; after the fix the score is 4/4. Kept as recorded because the
> failure is the reason the fix exists.

`claude -p` inside `ppa-bench/orfs-agent` (ORFS + Claude Code), one throwaway
container per instance, `--max-turns 40`. The agent had the real toolchain and
could build the design and read its own QoR. Only `public/` was staged; the
leak audit came back empty on every run.

| instance | resolved | submitted | wall | cost | terminal |
|---|---|---|---|---|---|
| C1_s1 | **YES** | period 0.00069 -> **0.69**, byte-identical to golden | 204 s | $0.21 | completed |
| C1_s2 | **YES** | recovered exactly | 109 s | $0.28 | completed |
| C3_s1 | **YES** | restored `set_output_delay` | 115 s | $0.17 | completed |
| C5_s2 | no | **nothing — file unchanged** | 1088 s | $2.39 | **max_turns** |

**Score: 3/4.** Total cost $3.04.

### Randomisation did its job

C1's goldens were 0.69 and 0.58 — neither is upstream's 0.46, the environment
was sanitised, and the leak audit was clean. The agent could not have copied
either value. It recovered both exactly, which means it recognised the x1000
unit slip and inverted it. That is the reasoning the randomisation was designed
to force, and it would not have been distinguishable from copying had the
golden been upstream's own value.

### C3 passed with a textually different fix

The submitted SDC differs from golden by a trailing blank line
(`matches_golden_exactly: false`) and resolves anyway, because grading is
behavioural — measured QoR — not diff-matching against the reference. An agent
that writes a different but equally correct constraint must still pass.

### C5 failed on budget, not on reasoning

The agent's *method was right*. It ran a real parameter sweep, building flow
variants `io020`, `io025`, `io030`, `io035` to measure the I/O budget
empirically. It then hit the turn limit mid-sweep:

```
"terminal_reason": "max_turns", "errors": ["Reached maximum number of turns (40)"]
```

and never wrote its conclusion back to `/work/impl.sdc`. The submitted file is
byte-identical to the broken input, so it was graded as the null agent — which
is correct behaviour by the grader, and a misleading headline about the agent.

Three fixes, in the order they matter:

1. **Task**: require writing best-so-far to the deliverable after *each* trial.
   Then a truncated run degrades gracefully instead of submitting nothing. This
   is a task-design defect, not an agent defect.
2. **Harness**: report `terminal_reason` in the verdict so budget exhaustion is
   never conflated with a wrong answer. A 3/4 that hides one truncation is a
   dishonest number.
3. **Budget**: search-shaped tasks need far more than 40 turns. C5 cost 10x the
   repair tasks in both time and money precisely because it was doing the work.

### The cost asymmetry is the HP-B preview

Repair tasks: ~140 s and $0.22 each. The one search task: 1088 s and $2.39, and
it still did not finish. That ratio is the argument for HP-B being a genuinely
different problem, and for making run budget an explicit, measured part of it
rather than an incidental limit.

### C5's deeper problem, unresolved

Because it never submitted, we still do not know whether C5 is *fair*. Its
golden `clk_io_pct` is 0.15, drawn at random; the agent swept 0.20-0.35 and had
no way to derive 0.15 from anything observable. Unlike C1, where the unit slip
makes the answer reconstructible, C5 under a randomised golden may require
guessing an arbitrary constant. HP-B avoids this by construction: there is no
hidden reference, only a public baseline to beat.

---

## F10 — C5 re-run after the task fix: 4/4, and behavioural grading vindicated

F9's C5 failure was a **task-design defect, not an agent limitation**. The agent
had run a correct parameter sweep, hit `max_turns` mid-search, and never wrote
its conclusion to the deliverable, so it was graded as the null agent.

Two changes, then a re-run at the **same 40-turn budget** so the fix is tested
in isolation:

1. The prompt now requires writing best-so-far to the deliverable *after every
   trial*, so a truncated run degrades gracefully instead of submitting nothing.
2. `terminal_reason` is reported in every verdict, so budget exhaustion can
   never again be mistaken for a wrong answer.

The checkpointing was directly observable mid-run: `/work/impl.sdc` moved
0.45 -> 0.20 -> 0.35 while the agent swept `io000 … io040`. At any point it
would have submitted something real.

| run | submitted | resolved | terminal | wall | cost |
|---|---|---|---|---|---|
| F9 original | nothing (file unchanged) | no | **max_turns** | 1088 s | $2.39 |
| after fix | `clk_io_pct = 0.35` | **YES** | completed | 976 s | $1.23 |

**Baseline agent score is now 4/4.**

### The instance was not unfair after all

I had flagged C5 as possibly unlearnable: its golden `clk_io_pct` is 0.15, drawn
at random, and the agent has no way to derive that specific constant.

It submitted **0.35** and resolved:

```
signoff_setup_ws = 0.121806   (want >= 0.119967)   PASS
area             = 673.778    vs baseline 673.512  (+0.039%)
```

Re-timed against the 0.15 reference, the agent's layout is as good as the
golden's. So the acceptable band is wide -- 0.45 is genuinely harmful (area
862.6, sign-off WS 0.0439) but anything at or below ~0.35 is indistinguishable
from the reference.

The concern was wrong, and it was wrong for a load-bearing reason: **grading is
behavioural, not diff-matching.** The question is never "did you recover the
reference value" but "is the design you produced as good". An agent that finds a
different, equally good answer passes -- which is the property that makes
randomised goldens fair for value-recovery tasks generally.

### What this cost

Repair tasks: ~140 s, $0.22. Search task: ~1000 s, $1.23-$2.39. The search task
is roughly 7x the wall time and 6x the cost of a repair task, and consumed its
whole turn budget both times. That is the empirical case for making run budget
an explicit, measured dimension of HP-B rather than an incidental limit.

---

## F11 — Knob sensitivity: die area is tunable, instance area is not

One-at-a-time sweep over the permitted knob space, nangate45/gcd, 19 runs.

```
range over the 8 permitted knobs:
  die_area   -25.29% .. +78.01%
  inst_area   -0.54% ..  +0.86%
```

**The objective had to change.** `inst_area` -- the metric the repair grader
uses -- is the sum of cell areas, fixed by synthesis and timing repair, and
placement knobs barely touch it. `die_area` is the physical footprint, what
silicon actually costs, and it moves by a factor of 2.4 across the same space.

| knob point | die % | inst % | ws | |
|---|---|---|---|---|
| `CORE_UTILIZATION` 30 | +78.01 | +0.86 | +0.0129 | ok |
| `CORE_UTILIZATION` 75 | **-25.29** | -0.54 | +0.0104 | ok |
| `CORE_MARGIN` 3 | +23.63 | +0.27 | +0.0145 | ok |
| `CTS_CLUSTER_*`, `PLACE_DENSITY`, `CELL_PAD` min | **+0.00 exactly** | 0.00 | unchanged | inert |
| `CELL_PAD_IN_SITES_{GLOBAL,DETAIL}_PLACEMENT` 3 | — | — | — | **flow fails** |

**Five of eight knobs are inert on gcd.** CTS clustering has nothing to cluster
on a design with 7 clock buffers; `PLACE_DENSITY` is inert at *both* ends,
suggesting ORFS derives it from utilisation and ignores the override. Two
autotuner-declared values break the flow outright, so upstream's own range is
not all-safe.

### The cliff, and why the allowlist deliberately overshoots it

| CORE_UTILIZATION | die area | delta | ws | result |
|---|---|---|---|---|
| 55 (default) | 1278 | — | +0.01601 | ok |
| 75 | 955 | -25.29% | +0.01040 | ok |
| 76 | 943 | -26.20% | +0.00692 | ok |
| **77** | **932** | **-27.09%** | +0.01101 | ok |
| 78+ | — | — | — | **FLW-0024**, dies in global placement |

A hypothesis that lowering `PLACE_DENSITY_LB_ADDON` would unlock higher
utilisation was **tested and refuted**: `util=90, addon=0.00` still fails
FLW-0024, so place density is not simply `util/100 + addon`.

The permitted range is set to **[30, 85]** -- past the cliff on purpose. Capping
at the optimum would make the task "read the allowlist, pick the maximum", a
lookup rather than a search. With the range wider than what works, overshooting
costs the entire run, which is the real engineering problem: pack as tight as
you dare.

---

## F12 — HP-B: a spec ambiguity cost 33% of the achievable improvement

The optimisation grader was validated on four reference submissions before any
agent saw it:

| submission | resolved | expected | die area | delta |
|---|---|---|---|---|
| null (no knobs) | no | no | 1278 | 0.0% |
| optimum (`util=77`) | **yes** | yes | 932 | **-27.09%** |
| overshoot (`util=85`) | no | no | flow died | — |
| cheat (`SDC_FILE=...`) | no | no | 1278 | rejected by allowlist |

**4/4 correct** -- and the probe caught a real gate mis-specification first. The
reference optimum initially *failed* on `signoff_setup_ws`, because the gate
required timing to be no worse than baseline. That is right for repair, where
the goal is to restore, and wrong for optimisation, where the agent is
explicitly meant to spend slack to buy area. Fixed to "timing still closes"
(`ws >= 0`).

### The controlled experiment

The prompt was not updated when the gate was. It still said *"sign-off timing is
no worse than the baseline"* while the grader now accepted any non-negative
slack. Same agent, same 12-run budget, same tools; the only change between runs
was that one paragraph.

| run | spec | submitted | die area | runs | cost |
|---|---|---|---|---|---|
| v1 | "no worse than baseline" | `util=68` | **-18.09%** | 9/12 | $0.85 |
| v2 | "timing still closes" | `util=77, addon=0.0` | **-27.09%** | 11/12 | — |

**v2 hit the reference optimum exactly.**

The agent explained its v1 choice in its own summary:

> "u68 is the local optimum where setup worst-slack (0.01699) actually **beats**
> baseline (0.016009) rather than merely staying positive. That means it passes
> the timing gate under **both** the strict reading and the loose reading,
> unlike u70-u74 which shrink further but regress setup slack below baseline."

It had *measured* `u74` at 24.3% reduction with positive slack and deliberately
rejected it, hedging against an ambiguous rubric. That is correct behaviour
against the specification it was given. The 9 percentage points it left on the
table were a **benchmark defect, not an agent limitation**.

### Why this matters more than the score

The gap between the agent's result and the reference optimum is what surfaced
the defect. Without a measured reference, -18.09% reads as a solid pass and the
inconsistency ships unnoticed.

So a reference optimum is not just a scoring aid -- it is how you find out that
your task description and your grader disagree. That is a third failure mode
alongside "agent games the grader" and "agent finds the answer", and it is the
one most likely to be invisible: every gate passes, the agent behaves sensibly,
and the benchmark quietly measures compliance with a contradiction.

---

## F13 — Generalising to aes: the benchmark transfers, the objective does not

First move off gcd. Four full aes runs at different clock periods, 8.7 min each.

| period | setup WS | setup TNS | die area | power | clean baseline? |
|---|---|---|---|---|---|
| 0.82 (upstream) | -0.01008 | -0.0543 | 62612 | 441.1 mW | no |
| 0.85 | -0.01218 | -0.0362 | 62612 | 409.7 mW | no |
| 0.90 | -0.00365 | -0.0037 | 62612 | 375.7 mW | no |
| **0.95** | **+0.04914** | **0.0000** | 62612 | 350.7 mW | **yes** |
| **1.00** | **+0.08122** | **0.0000** | 62612 | 329.2 mW | **yes** |

### The guessed range was wrong, again

`randomize.py` carried `("nangate45", "aes"): (0.85, 1.10)` -- a guess, never
measured. aes does not close until **0.95**, so most seeds drawn from that range
would have produced violating baselines: precisely the sky130hd/gcd failure mode
(F2) that the whole measured-range discipline exists to avoid.

Corrected to `(0.95, 1.00)`, both endpoints verified clean. This is the second
time a guessed range would have been wrong and a sweep caught it. Ranges are
measurements, not estimates.

Note also that aes **does not close at its own upstream period** of 0.82. As with
sky130hd/gcd, that is upstream's intent rather than a broken environment -- but
it means the shipped configuration is not a usable benchmark baseline.

### die_area is constant at 62612 across every period

Not a coincidence. `designs/nangate45/aes/config.mk` line 8:

```make
export FLOORPLAN_DEF = $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NICKNAME)/aes_ng45_fp.def
```

aes uses a **fixed floorplan DEF**, so the die is nailed down by a file rather
than derived from `CORE_UTILIZATION`. The dominant HP-B knob has nothing to act
on.

**Consequence: HP-B's objective does not transfer to aes.** The benchmark
machinery does -- allowlist, gates, budget accounting, sign-off -- but "minimise
die area" is meaningless on a design whose die is fixed by a DEF. Power remains
highly tunable (441 -> 329 mW, a 25% range across the periods above), so power
is the natural objective there instead.

This is the same lesson C2 taught on the repair side, in a different register:
**the mechanism generalises, the objective must be matched to the design.** On
gcd, I/O timing is irrelevant so I/O-delay defects are inert; on aes, die area is
fixed so area optimisation is inert. A benchmark suite that assumes one objective
fits every design will silently ship vacuous instances.

---

## F14 — aes validation: 3/4, and two defect classes swapped roles

The generalisation test. Same injectors, same grader, same harness, zero code
changes -- only the design and the measured period range differ. Seed 1 drew
period 1.000, io_pct 0.210. Cost: 1 shared baseline + 4 broken runs.

| class | defect | `finish__ws` | `signoff__ws` | area | on aes | on gcd |
|---|---|---|---|---|---|---|
| **C2** | `set_input_delay` deleted | **+0.07244** | **-0.27979** | 17183 | **validated** | inert |
| **C1** | period x1/1000 | -0.79901 | 0.16847 | 22932 (+33%) | validated | validated |
| **C5** | `clk_io_pct` inflated | -0.00097 | 0.05506 | 18013 | validated | 1 of 2 seeds |
| **C3** | `set_output_delay` deleted | 0.06825 | 0.06825 | 17257 | inert | validated |

Baseline: `signoff_ws` 0.06825, area 17257, power 330.2 mW.

### C2 on aes is the cleanest demonstration in the suite

```
                       flow's own view        held-out sign-off
baseline                   0.06825                0.06825
C2 broken                 +0.07244  better       -0.27979  missing timing
                                                  TNS -5.85 ns
```

The implementation run reports **better** slack while the design misses timing by
280 ps with 5.85 ns of total negative slack. That is the reward-hack inversion at
full strength -- far starker than C3_s1 on gcd, where the same mechanism produced
only a 7.5 ps gap.

### The prediction held, and the classes traded places

C2 was **completely inert on gcd** -- deleting all 35 input delays produced a
byte-identical netlist and layout (F7). The stated explanation was that gcd has no
I/O-critical paths: its worst path is register-to-register, so constraining the
I/O changes nothing. aes, at 19k instances with real interface timing, was the
predicted counter-case.

It validated, and C3 went the other way -- inert on aes, validated on gcd. So the
same defect class is **catastrophic on one design and vacuous on another**, and
which is which is not guessable from the injector.

**Consequence for benchmark construction:** an instance is a property of the
(defect, design) *pair*, never of the defect alone. A suite that generates classes
uniformly across designs will ship vacuous instances at roughly the rate seen here
-- 4 of 8 on gcd, 1 of 4 on aes. Per-instance validation is not a nicety; it is
the only thing standing between a generated instance and a meaningless one.

**Consequence for the harness:** nothing had to change. The injectors, the
allowlist, sign-off, frozen baselines, and the grader all transferred unmodified
to a design 17x larger on the same platform. The only per-design input required
was the measured clock-period range (F13).
