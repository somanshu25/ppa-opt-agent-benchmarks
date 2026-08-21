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
