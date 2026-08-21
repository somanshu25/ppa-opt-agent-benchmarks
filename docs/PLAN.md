# PPA Optimization Agent Benchmark — Build Plan

Status: v1 scope locked. Findings below are measured, not assumed.

## 0. Measured findings that shape the design

### F1 — ORFS QoR is bit-exact deterministic across thread count

Verified on two platforms, `NUM_CORES` in {1, 2, 4, 8}, each run in an isolated
`FLOW_VARIANT` so runs cannot collide:

| platform / design | runs | result |
|---|---|---|
| sky130hd / gcd | 4 | all `6_report.json` bit-identical (md5 `caacb9ff...`) |
| nangate45 / gcd | 4 | all `6_report.json` bit-identical (md5 `dfe2ef7c...`) |

Ruled out the "make no-op" explanation: stage mtimes show a full re-run from
`1_synth` through `6_report` for every repeat.

Comparing all 16 stage JSONs (nangate45/gcd, c1 vs c8), exactly one file
differs — `5_1_grt.json` — and all 9 differing keys are `_s`-suffixed runtime
instrumentation (`..._fastroute__monotonic_s` etc.). **No QoR metric differs.**
Wall time varies (45.5s -> 36.9s); results do not.

Consequence: the grader needs no statistical deadband for thread variation.
Any QoR delta is signal.

Caveats to state explicitly: gcd sets `SYNTH_REPEATABLE_BUILD ?= 1`; both
designs are small. Determinism is re-checked on aes, which sets neither.

### F2 — The real noise floor is perturbation sensitivity, not thread count

An agent's fix will rarely be textually identical to the reference SDC.  The
number that sets the grader threshold is sensitivity to *semantically null*
edits: line reordering, `0.46` vs `4.6e-1`, `[all_inputs -no_clocks]` vs an
explicit port list.  Probe planned (~4 runs x 40s on gcd).  If QoR is
unchanged, grade by exact comparison; otherwise the measured spread becomes the
tolerance band.

### F3 — sky130hd/gcd is intentionally over-constrained; use nangate45

sky130hd/gcd baseline: WS -1.62 ns on a 1.1 ns clock, TNS -71 ns, 197
timing-repair buffers = 33% of area.  This is **not** a broken environment:
upstream `designs/sky130hd/gcd/rules-base.json` expects WS >= -1.68,
TNS >= -71.2.  We match upstream.

nangate45/gcd expects WS -0.056, TNS -0.404 — essentially closing.

Consequence: **nangate45 is the primary platform.**  On a design with a -71 ns
TNS floor, inject-degrade-fix-recover has no clean signal, and a "no
violations" gate would fail the baseline itself.

### F4 — The ORFS SDC corpus is a four-command monoculture

Survey of all 83 `*.sdc` under `flow/designs/` (10 platforms):

| command | files | command | files |
|---|---|---|---|
| `create_clock` | 74 | `set_clock_uncertainty` | 13 |
| `set_input_delay` | 67 | `set_false_path` | 8 |
| `set_output_delay` | 66 | `set_clock_groups` | 4 |
| `set_clock_latency` | 64 | `set_multicycle_path` | 1 |
| | | `create_generated_clock` | **0** |

48 of 83 (58%) are the identical `clk_io_pct` template.

Consequence: injector classes must target those four commands.  Mutations that
remove uncertainty, false paths, or generated clocks have nothing to remove.
This bounds what any ORFS-based SDC benchmark can cover — a finding worth
presenting, not hiding.

### F5 — Reuse ORFS's own CI grading primitive

ORFS ships per-design `rules-base.json` plus `util/checkMetadata.py`.  The
grader extends that mechanism rather than inventing a parallel one.

### F6 — Environment: no mounts, no host Python

The `orfs` container has zero mounts and the Windows host has no Python.  All
artifacts so far exist only because they were hand-copied.  The harness is
therefore `docker cp` + `docker exec`, scripted, with metrics copied out by
convention.  Nothing is reproducible until this is done.

## 1. Scope (locked)

- **Platform**: nangate45
- **Designs**: gcd (~40 s/run) + aes (timing probe in flight; included if
  affordable).  ibex dropped — an unvalidated instance is worth less than a
  validated one.
- **Injector classes**: C1, C2, C3, C5 (below)
- **Edits allowed**: SDC only.  This is a deliberate scoping decision, not an
  accident: golden-SDC signoff is only well-defined while port names are
  stable.  Permitting RTL/netlist edits would silently degrade the central
  gate.

## 2. Workstreams

### W0 — Reproducibility scaffolding (prerequisite)

`ppa-bench/` repo, git-init'd, outside the ORFS tree.  `runner.py` wraps
`docker exec` with an explicit `FLOW_VARIANT` per run and copies metrics out by
convention.  Every instance is an overlay against pinned upstream ORFS
`02ba50d53`.

### W1 — Parser (`ppa_bench/metrics.py`)

Unions all stage JSONs — they are flat and self-prefixed, so it is a dict
union — then projects onto ~25 canonical QoR fields.  Two subtleties handled:
final DRC comes from the **last** `__iter:N` key, not the first; a stage killed
mid-write leaves truncated JSON and is treated as absent rather than crashing
the parse.  This replaces the finish-only view (71 keys) with true merged
metadata, making synth and route behaviour visible.

### W2 — SDC survey (`survey/`)

Script + writeup producing F4.  Framing: *what an SDC benchmark on ORFS can and
cannot cover.*

### W3 — Injector (`ppa_bench/injector.py`)

Each operator emits `impl.sdc` (mutated), `golden.sdc` (reference), a task
prompt, and hidden ground truth.

| id | mutation | why it is a good task |
|---|---|---|
| C1 | `clk_period` ns/ps unit slip | unambiguous ground truth, enormous signal |
| C2 | delete `set_input_delay` | implementation run looks *better* while the design is worse — only signoff catches it |
| C3 | delete `set_output_delay` | as C2, output side |
| C5 | `clk_io_pct` 0.2 -> 0.45 | degrades area/power while breaking nothing — tests QoR judgment, not repair |

**Deliberately reshaped:** "clock period too tight" is cut as a *repair* task.
The agent cannot know the original period, so every answer is defensible and
there is no reference.  It returns later as a *diagnosis* task ("report the
achievable period"), graded against a swept ground truth.

### W4 — Grader (`ppa_bench/grader.py`)

Core is **two-SDC discipline**:

- `impl.sdc` — what the agent edits; what the flow runs with.
- `golden.sdc` — held out, never shown to the agent; used for sign-off STA on
  the agent's *final* netlist.

This is the anti-cheat, and it mirrors real implementation-vs-signoff practice.
Without it the benchmark is trivially gamed by loosening constraints.

**Gates (pass/fail):**
1. flow completes, `errors == 0`
2. `drc_errors == 0`, antenna violating nets `== 0`, placement violations `== 0`
3. signoff timing under `golden.sdc` not worse than baseline beyond tolerance
4. `golden.sdc` still binds to the agent's netlist (catches port renaming)
5. diff confined to the allowed file set

**Score (only if all gates pass):** area, power, utilization, wirelength vs
baseline.

Timing is a **gate, not a score** — otherwise an agent trades 3x area for 10 ps.

### W5 — Instance validation (`ppa_bench/validate.py`)

The SWE-bench FAIL->PASS analog.  Per instance:

- `BASELINE_PASS` — clean instance runs, all gates pass
- `BROKEN_FAIL` — injected instance fails its designated gate by a margin
  exceeding the F2 tolerance
- `REFFIX_PASS` — applying the reference fix restores metrics to baseline
- `NON_TRIVIAL` — a **null agent** (does nothing) fails, *and* a **cheat agent**
  (deletes the SDC / relaxes the period) also fails

The cheat-agent decoy is cheap to run and is a strong presentation artifact: it
is direct evidence the grader cannot be gamed.

## 3. Budget

nangate45/gcd is ~40 s/run.  4 classes x 3 validation runs = 12 runs ~ 9 min.
aes timing probe in flight; included if a run lands under ~5 min.
