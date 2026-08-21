# ppa-bench

A benchmark for agents that optimise chip PPA (power, performance, area)
through the OpenROAD flow — and, more to the point, a **grader that such an
agent cannot fool**.

Built on [OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts)
at pinned commit `02ba50d53`, Nangate45 and SkyWater130. No proprietary tools
or PDKs.

## The problem this exists to solve

Point an agent at a chip design flow and ask it to improve the numbers, and the
cheapest way to improve the numbers is to stop measuring.

Delete `set_input_delay` from the constraints and the tool stops checking those
paths, so reported slack *improves* — while the design gets worse. An agent
doing gradient descent on visible metrics is driven **toward** destroying the
design. That is not an edge case; it is the gradient.

So the scarce artifact is not the optimising agent. It is the grader.

## How grading works

Two assertion sets, borrowed directly from SWE-bench:

| set | meaning | alone, defeated by |
|---|---|---|
| **PASS_TO_PASS** | baseline invariants that must survive | doing nothing |
| **FAIL_TO_PASS** | what the injected defect broke | any destructive shortcut |

`resolved = all(P2P) ∧ all(F2P)`. QoR score is reported separately and never
blended into the verdict.

The load-bearing detail is *which numbers* the assertions read. SWE-bench stops
an agent editing the tests with one line — `git checkout base_commit -- tests/`.
We do the same thing to constraints:

> The agent edits `impl.sdc`. Grading discards it and re-times the agent's
> **layout** against a `golden.sdc` it never saw.

Loosening a constraint therefore cannot buy score, because the loosened
constraint is not the one used to judge. This is standard practice in silicon —
implementation constraints versus sign-off constraints — and it is validated to
be exact: with `golden == impl`, sign-off reproduces the flow's own timing to
the digit on all six metrics.

Note this is a **re-time, not a re-run**. The layout is frozen; only the
measuring stick changes.

## Two safeguards against two different attacks

|  | attack | defence |
|---|---|---|
| 1 | agent games the grader | held-out golden SDC sign-off |
| 2 | agent finds or recalls the answer | `public/`+`private/` split, **randomised goldens** |

The second is easy to underestimate. `golden.sdc` is normally upstream's own
`constraint.sdc`, and the answer turns out to be recoverable five ways: the
pristine file, git history, stale `results/*/6_final.sdc`, `rules-base.json`,
and `autotuner.json`'s declared period range. ORFS is also public, so the value
is plausibly in model training data — the same contamination criticism levelled
at SWE-bench.

Sanitisation alone is unfalsifiable; you can never prove you found every path.
Randomising the golden makes every leaked copy *wrong*:

> **An instance that did not exist before we generated it cannot have been
> memorised.**

Sampling is keyed on a secret held outside the agent-visible tree — without it,
the public seed plus this repo's own sampler would recompute the golden in one
line.

## Layout

```
ppa_bench/
  metrics.py             merge 16 ORFS stage JSONs -> canonical QoR
  injector.py            SDC defect operators (C1, C2, C3, C5 + CX probe)
  randomize.py           secret-keyed golden sampling
  generate_instances.py  materialise public/ + private/
  grader.py              P2P / F2P assertions, verdict, score
  validate.py            BASELINE_PASS / BROKEN_FAIL
tcl/signoff_sta.tcl      re-time a finished layout against a golden SDC
bin/signoff.sh           sign-off driver
docs/FINDINGS.md         measured results, including the negatives
docs/PLAN.md             build plan and scope decisions
```

Each instance:

```
<instance_id>/
  public/    impl.sdc  prompt.md  instance.json     <- all the agent may see
  private/   golden.sdc  ground_truth.md  answer.json  validation.json
```

## Defect classes

| id | mutation | silent? | tests |
|---|---|---|---|
| C1 | clock period unit slip (×1000) | no | unambiguous ground truth |
| C2 | delete `set_input_delay` | **yes** | impl run looks *better* |
| C3 | delete `set_output_delay` | **yes** | as C2, output side |
| C5 | inflate `clk_io_pct` | no | QoR judgment, not repair |
| CX | rewrite period as `[expr ...]` | — | **not a task** — see below |

Classes were chosen from a survey of all 83 SDCs in ORFS: the corpus is a
four-command monoculture (`create_clock` 74, `set_input_delay` 67,
`set_output_delay` 66, `set_clock_latency` 64; zero generated clocks), and 48
of 83 are the identical template. Injectors that remove false paths or clock
groups would have nothing to remove.

**CX is a documented negative.** ORFS scrapes the clock period out of the SDC by
regex and feeds it to ABC, so an `[expr ...]` form — valid SDC, identical to
STA — silently sends ABC the literal string `[expr`. Confirmed end to end, no
warning anywhere. Then measured: it changes nothing on gcd or aes, even under a
6× period change. A real corruption channel with no consequence: a good finding
and a bad benchmark task. Kept so the negative stays reproducible.

## Instances are self-proving

Generating an instance is free and proves nothing. Every instance must
demonstrate:

- `BASELINE_PASS` — the golden SDC produces a run passing every gate
- `BROKEN_FAIL` — the injected SDC produces a run that fails at least one
- `REFFIX_PASS` — the reference fix restores the gates

An instance that does not show that flip is discarded, not shipped. That is how
CX died. Until validation runs, every manifest reads `"validated": false`.

## Reproducing

Everything runs inside the ORFS container (no host Python required):

```bash
docker cp . orfs:/ppa-bench
docker exec orfs bash -lc 'cd /ppa-bench && python3 -m ppa_bench.generate_instances \
    --seeds 1 2 --designs nangate45/gcd'
docker exec orfs bash -lc 'cd /ppa-bench && python3 -m ppa_bench.validate \
    instances/nangate45_gcd_C{1,2,3,5}_s1'
```

Runtime: nangate45/gcd ≈ 40 s/run, nangate45/aes ≈ 8.7 min/run. Validating N
classes at one seed costs 1 + N runs, since the baseline is shared.

## Why the numbers can be trusted

ORFS QoR is **bit-exact deterministic** across thread counts — verified on two
platforms, `NUM_CORES` ∈ {1,2,4,8}, all 16 stage JSONs. The only run-to-run
variation is runtime instrumentation. So the grader's independent re-run
reproduces the agent's run exactly, no tolerance band required, and any metric
delta is signal rather than noise.

See `docs/FINDINGS.md` for the measurements, including the ones that killed
ideas.
