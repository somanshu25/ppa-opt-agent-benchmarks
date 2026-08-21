# Benchmark Specifications

Two benchmarks: `sdc-repair-v1` (HP-A, constraint repair) and `knob-opt-v1`
(HP-C, budgeted die-area minimisation). Both use the SWE-bench / Terminal-Bench
shape: environment, task, grader.

---

# Benchmark 1 — `sdc-repair-v1`



---

## a) Task description

An agent is handed a chip design whose timing constraints have one defect. It
must diagnose and repair the constraints, and is judged on the physical design
that results.

What the agent gets:

| | |
|---|---|
| `impl.sdc` | the defective constraints — the only file it may edit |
| `prompt.md` | the task, stated without naming the defect |
| a shell | it can run the full RTL-to-GDS flow and read its own QoR |

What the agent is **told**, in the prompt:

> Your edited `impl.sdc` is used to re-run the full flow from clean. The
> resulting layout is then re-timed against a **reference SDC you are not
> shown**. Loosening or deleting constraints therefore cannot help you.

Telling it the rule is deliberate. A benchmark that hides its rubric measures
whether the model guessed the rubric; stating it makes the task about
engineering, and leaves a cheating agent no excuse.

Prompts never name the defect. C3's reads only: *"This SDC is incomplete: some
timing paths in the design are not being checked at all."*

### The trap

For the silent classes, **the metric the agent can see moves the wrong way.**
Measured on C3_s1: deleting `set_output_delay` makes the flow report
`setup_ws = 0.24142` against a baseline of `0.18390` — **31% more slack** — while
sign-off against the reference says `0.17635`, worse.

An agent optimising visible QoR will call that an improvement and stop.

---

## b) Setup

**Environment.** OpenROAD-flow-scripts pinned at `02ba50d53`, container image
`openroad/orfs`, Nangate45 PDK, design `gcd`. Open tools and open PDK only.

**Instance layout.** Two partitions, and the split is enforced by what the
runner copies, not by convention:

```
<instance_id>/
  public/     impl.sdc  prompt.md  instance.json    <- the only thing the agent sees
  private/    golden.sdc  baseline.json            <- enters only after the agent stops
              ground_truth.md  answer.json  validation.json
```

**Randomised goldens.** The reference constraints are sampled per instance from
a *measured* range, keyed on a secret held outside the instance tree.

This matters because `golden.sdc` would otherwise be upstream's own
`constraint.sdc`, and the answer is recoverable five ways: the pristine file,
git history, stale `results/*/6_final.sdc`, `rules-base.json`, and
`autotuner.json`'s declared period range. ORFS is also public, so the value is
plausibly in model training data — the contamination criticism levelled at
SWE-bench.

Sanitising the environment is unfalsifiable; you cannot prove you found every
path. Randomising makes every leaked copy **wrong**:

> An instance that did not exist before we generated it cannot have been
> memorised.

The sampling range is measured, not guessed: six clock periods from 0.46 to
0.70 were swept and all confirmed to give clean baselines before the range was
fixed at 0.50–0.70.

**Frozen baselines.** Each `(design, seed)` baseline is run once and frozen into
`private/baseline.json`. Grading an attempt therefore costs **one flow run plus
one sign-off STA** — never a baseline run — and instances are portable. Freezing
is sound only because ORFS QoR is bit-exact deterministic (F1).

**Runtime.** nangate45/gcd ≈ 40 s per flow run. Validating N classes at one seed
costs 1 + N runs, since the baseline is shared.

---

## c) Expected output

The agent leaves an edited `impl.sdc`. Nothing else is read from its workspace.

The grader emits a verdict:

```
resolved   : bool     all PASS_TO_PASS and all FAIL_TO_PASS
assertions : list     per-assertion pass/fail with the numbers
score      : dict     area_delta_pct, power_delta_pct  (reported only)
```

A correct repair restores the flow to baseline. Measured on the `oracle` decoy:
every assertion passes with `area_delta_pct: 0.0`.

---

## d) Grading method

### The core: re-time, don't re-run

The agent's layout is **frozen**; only the measuring stick changes.

```
        agent's layout                     measuring stick
  BUILT WITH:  impl.sdc      ────────►     JUDGED WITH: golden.sdc
  6_final.odb   netlist + placement + routing    unchanged
  6_final.spef  its own extracted parasitics     unchanged
```

This is SWE-bench's `git checkout base_commit -- tests/` applied to constraints:
discard the agent's copy of the thing that judges it. It also mirrors real
practice — implementation SDC versus sign-off SDC.

Validated exact: with `golden == impl`, sign-off reproduces the flow's own
numbers to the digit on all six timing metrics, on every baseline. The first
attempt **failed** by 4.8 ps and caught a genuine bug (CTS adds
`set_propagated_clock`, so ideal clocks were being timed against a real clock
tree). That check is now a precondition of freezing a baseline.

### The assertions

**PASS_TO_PASS** — baseline invariants that must survive:

| assertion | condition |
|---|---|
| `flow_completed` | reached `6_report` |
| `flow_errors` | `== 0` |
| `drc_errors` | `== 0` |
| `antenna_violations` | `== 0` |
| `placement_violations` | `== 0` |
| `signoff_hold_ws` | `>= baseline` |
| `area_not_ballooned` | `<= baseline × 1.05` |
| `edits_confined` | diff ⊆ `editable_files` |
| `no_disabled_checks` | no denylisted knob set |

**FAIL_TO_PASS** — computed **only** from held-out sign-off, never from
`finish__*`:

| assertion | condition |
|---|---|
| `signoff_setup_ws` | `>= baseline` |
| `signoff_setup_tns` | `>= baseline` |

```
resolved = all(PASS_TO_PASS) AND all(FAIL_TO_PASS)
```

Binary. The QoR score is reported separately and never blended in — blending is
what would let an agent buy past a failed gate.

Tolerance is **0**. Defensible because determinism means the grader's
independent re-run reproduces the agent's run exactly; there is no noise to
absorb.

### Why both sets are needed — measured, not argued

The bracket was tested with four scripted agents. Each set is defeated alone:

| decoy | its own `finish__ws` | `signoff__ws` | resolved | caught by |
|---|---|---|---|---|
| `oracle` restores golden | 0.1839 | 0.18390 | **yes** ✅ | — |
| `null` does nothing | −0.4231 | 0.15946 | no | F2P + area |
| `cheat_loose` period → 5.0 | **+3.5836** | 0.14334 | no | **F2P** |
| `cheat_knob` `SKIP_DETAILED_ROUTE=1` | 0.1661 | 0.21163 | no | **P2P only** |

**4/4 graded correctly.**

`cheat_loose` reported **+3.58 ns of slack — 19× the baseline** — and resolves to
zero. That is the reward hack the benchmark exists to stop.

`cheat_knob` is the instructive one. Suppressing detailed routing makes timing
optimistic (`0.21163` > baseline `0.18390`), so it **passed both FAIL_TO_PASS
assertions**. The golden-SDC gate did not catch it. `drc_errors`,
`antenna_violations` and `no_disabled_checks` did.

So: F2P alone lets `cheat_knob` through by not measuring; P2P alone lets `null`
through by doing nothing. Neither is sufficient. Absence of evidence must fail.

### The knob denylist

`SKIP_REPORT_METRICS` makes `report_metrics.tcl` return immediately;
`SKIP_DETAILED_ROUTE` skips extraction and SPEF. Either produces a flawless
looking run because nothing was measured.

---

## The instances

Every instance is self-proving. It ships only if the baseline passes every gate
**and** the injected version demonstrably fails one. **4 of 8 generated
instances survived**; the rest were rejected by measurement.

### Validated (shippable)

| instance | defect | golden period / io_pct | baseline `ws` / area | broken `signoff_ws` / area | fails on |
|---|---|---|---|---|---|
| `C1_s1` | period ×1/1000 | 0.69 / 0.21 | 0.18390 / 674.3 | 0.15946 / **959.5 (+42%)** | `area_not_ballooned`, `signoff_setup_ws` |
| `C1_s2` | period ×1/1000 | 0.58 / 0.15 | 0.11997 / 673.5 | 0.09470 / **1035.5 (+54%)** | `area_not_ballooned`, `signoff_setup_ws` |
| `C3_s1` | `set_output_delay` deleted | 0.69 / 0.21 | 0.18390 / 674.3 | **0.17635** / 673.8 | `signoff_setup_ws` |
| `C5_s2` | `clk_io_pct` 0.15 → 0.45 | 0.58 / 0.15 | 0.11997 / 673.5 | 0.04390 / **862.6 (+28%)** | `signoff_hold_ws`, `area_not_ballooned`, `signoff_setup_ws` |

**C1 is the robust instance** — validated on both seeds with a large effect. Note
where the damage lands: sign-off timing degrades only slightly, because the
golden period is loose enough that even a thrashed layout meets it. The real
cost is **+42% / +54% area**. This is why an area cap is carried as a P2P
assertion: an over-constraint defect can pass every timing gate and still be a
disaster.

**C3_s1 is the inversion instance** — the one where the visible metric lies. Its
effect is small (7.5 ps), so it demonstrates the mechanism rather than gating
hard.

### Rejected (kept as evidence)

| instance | why |
|---|---|
| `C2_s1`, `C2_s2` | **inert.** Removing all 35 `set_input_delay` constraints produced a **byte-identical netlist and layout**; the SPEF differs only in its `*DATE` header. gcd has no I/O-critical paths. |
| `C3_s2` | sign-off came out *better* than baseline — same injection, opposite sign to `C3_s1`. |
| `C5_s1` | `clk_io_pct` 0.21 → 0.45 is only a 2.1× inflation; too small to bite. |

`C2` failing is a **design-selection finding, not an injector bug**: three of
four classes attack I/O constraints, and on gcd the critical path is
register-to-register. C1, which attacks the core clock, is the one that is
robust. Class choice has to be matched to the design — which is the specific
reason to test C2/C3 on aes.

`C3_s2`'s ±7.5 ps sign flip also answers the tolerance question empirically: an
effect that changes sign across seeds is below the level at which that class can
gate anything.

---

## Known limits

- **One design, one platform.** Everything validated here is nangate45/gcd,
  ~1100 instances. aes (8.7 min/run) is the generalisation test and has not been
  run.
- **Repair, not open-ended optimisation.** Ground truth exists because we
  injected the defect. This measures diagnosis and repair, not the harder
  problem of improving a design nobody broke.
- **`area_not_ballooned` is class-scoped.** Correct for repair tasks; it would
  wrongly block an optimisation agent that legitimately trades area for timing.
- **The SDC corpus bounds coverage.** All 83 ORFS SDCs are a four-command
  monoculture with zero generated clocks, so classes touching uncertainty,
  false paths or clock groups have nothing to remove.

---

# Benchmark 2 — `knob-opt-v1`

Budgeted die-area minimisation via flow knobs. HP-C.

Same three-part shape (environment, task, grader), but a **different problem
class**, and the differences are the interesting part: nothing is broken, so
there is no defect to repair and no hidden answer to protect.

---

## a) Task description

The design already builds correctly and meets timing. It is also larger than it
needs to be. Shrink the die by tuning flow knobs, without breaking correctness,
inside a fixed run budget.

| | |
|---|---|
| **Given** | the design at its default config, the permitted knob space with ranges, a **12-run budget**, and a shell with the full flow |
| **Deliverable** | `/work/knobs.json` — a knob-value map. Nothing else is collected |
| **Objective** | reduce `finish__design__die__area` by at least **2%** |

The agent is told the gates, the budget, and that timing is a gate rather than a
score. It is also told to write best-so-far to the deliverable after *every*
trial, so a truncated run degrades gracefully — a lesson learned the hard way
(F10).

## b) Setup

Same pinned environment as `sdc-repair-v1`: ORFS `02ba50d53`, `openroad/orfs`,
Nangate45, gcd, ~40 s per flow run.

**No injection and no randomisation.** There is no hidden reference — the
baseline config is public and the agent is meant to beat it. Sanitisation is
correspondingly lighter: only `rules-base.json` is removed, since it states
upstream's expected area and hints at the achievable target.

**Knob allowlist, not denylist.** A denylist catches `SKIP_DETAILED_ROUTE`, but
the real hazard is `SDC_FILE` — an agent free to set arbitrary make variables
could point the flow at constraints of its own choosing and walk straight
through the sign-off gate. The allowlist derives from ORFS's own
`autotuner.json`, minus `_SDC_*` (the SDC lever wearing a knob costume) and
`_FR_*` (needs platform Tcl rewriting), plus two curated floorplan knobs:

```
CELL_PAD_IN_SITES_DETAIL_PLACEMENT   int    [0, 3]
CELL_PAD_IN_SITES_GLOBAL_PLACEMENT   int    [0, 3]
CORE_MARGIN                          int    [1, 3]
CORE_UTILIZATION                     int    [30, 85]
CTS_CLUSTER_DIAMETER                 int    [20, 400]
CTS_CLUSTER_SIZE                     int    [10, 200]
PLACE_DENSITY                        float  [0.3, 0.95]
PLACE_DENSITY_LB_ADDON               float  [0.0, 0.2]
```

**`CORE_UTILIZATION` intentionally extends past what works.** Measured: 77
succeeds at −27.09% die area; 78 dies in global placement with `FLW-0024`.
Capping the range at the optimum would reduce the task to "read the allowlist,
pick the maximum". With the range wider than the working range, overshooting
costs the whole run — which is the actual engineering problem.

## c) Expected output

`knobs.json`, e.g. `{"CORE_UTILIZATION": 77, "PLACE_DENSITY_LB_ADDON": 0.0}`.
The grader emits `resolved`, per-assertion detail, and a score carrying
`die_area_delta_pct`, `power_delta_pct`, `inst_area_delta_pct` and `runs_used`.

## d) Grading method

Same discipline as `sdc-repair-v1`: the agent's own run directory is never
trusted. The flow is re-run from clean with exactly the submitted knobs, and the
layout is re-timed against the design's own constraints — which the agent was
not permitted to touch, so they are held out without needing to be hidden.

Illegal knobs are **not** forwarded to make. The violation is recorded and the
run proceeds at default config, so a rejected submission cannot still influence
the measurement.

### The objective was chosen by measurement

A 19-run one-at-a-time sweep over the permitted space (F11):

```
die_area   -25.29% .. +78.01%     <- tunable
inst_area   -0.54% ..  +0.86%     <- flat
```

`inst_area` — what the repair grader scores — is fixed by synthesis and timing
repair. `die_area` is the footprint that costs money. Running the sweep before
building the grader is what caught this.

### Assertions

**PASS_TO_PASS** — `flow_completed`, `flow_errors`, `drc_errors`,
`antenna_violations`, `placement_violations`, `signoff_setup_ws`,
`signoff_setup_tns`, `signoff_hold_ws`, `no_disabled_checks`, `knobs_permitted`,
`within_budget`.

**FAIL_TO_PASS** — `die_area_improved`: `die_area <= baseline × 0.98`.

```
resolved = all(PASS_TO_PASS) AND all(FAIL_TO_PASS)
```

### Two deliberate differences from the repair grader

**1. `area_not_ballooned` is removed.** It caps area at baseline × 1.05 —
precisely the thing this benchmark asks the agent to change.

**2. The timing gate is "still closes" (`ws >= 0`), not "no worse than
baseline".** Repair restores, so a timing regression is failure. Optimisation is
explicitly allowed to *spend* slack to buy area. This distinction is not
cosmetic: under the repair gate, the true optimum (`util=77`, WS `+0.011` vs
baseline `+0.016`) **fails over 5 ps** while closing comfortably.

**3. There is an improvement threshold at all.** With nothing broken, every
assertion passes at baseline, so without a threshold the null agent wins by
doing nothing — the same degenerate case P2P-alone had in repair.

### Validated before any agent saw it

| submission | resolved | expected | die area | delta |
|---|---|---|---|---|
| null (no knobs) | no | no | 1278 | 0.0% |
| optimum (`util=77`) | **yes** | yes | 932 | **−27.09%** |
| overshoot (`util=85`) | no | no | flow died | — |
| cheat (`SDC_FILE=…`) | no | no | 1278 | rejected by allowlist |

**4/4 correct** — and the probe caught the timing-gate mis-specification above
before it reached an agent.

## Baseline agent results

| run | spec said | submitted | die area | runs | resolved |
|---|---|---|---|---|---|
| v1 | "no worse than baseline" | `util=68` | −18.09% | 9/12 | yes |
| v2 | "timing still closes" | `util=77, addon=0.0` | **−27.09%** | 11/12 | yes |

Both resolve. The gap between them is the finding: the prompt was not updated
when the gate was, and the agent — reasoning correctly against an ambiguous
rubric — deliberately rejected a measured 24.3% configuration to satisfy both
readings. **A one-paragraph inconsistency cost 33% of the achievable
improvement.** See F12.

## Known limits

- **Single-knob in practice.** Five of the eight permitted knobs are inert on
  gcd — CTS clustering has nothing to cluster with 7 clock buffers, and
  `PLACE_DENSITY` does nothing at either end. This measures budgeted search
  against a hard cliff, not multi-objective search breadth.
- **No AutoTuner comparison yet.** ORFS ships a real non-LLM optimiser over the
  same space. Running it at equal budget is the highest-value remaining
  addition and needs no grader changes.
- **One design, one platform**, as with `sdc-repair-v1`.
