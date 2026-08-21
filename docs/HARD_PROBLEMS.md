# Task 1 — The Hard Problems

Four hard problems in agentic PPA optimisation, HP-A through HP-D. Each is
stated in the same five parts: why it is hard, why coding agents fail, what
inputs/outputs/evidence it needs, how it can be *correctly* measured, and what
product falls out of solving it.

Every number cited here was measured in this environment. Sources are
`docs/FINDINGS.md` (F1–F12) and `docs/BENCHMARK.md`.

---

## The thesis

> **The hard problem is not "make the design better." It is "make the design
> better *and prove you did not cheat*."**

Every lever available to a PPA agent — flow knobs, constraints, RTL — has a
trivial degenerate solution: relax the constraint, disable the check, break the
logic. Each of those *improves the metric the agent can see*. So the scarce
artifact is not the optimising agent. It is the grader.

---

## Why this domain breaks coding agents

Five structural reasons. Four of them were measured here, not assumed.

**R1 — The oracle is slow and non-binary.**
SWE-bench runs a test suite: seconds, pass/fail, unambiguous. Here one
evaluation is **40 s on nangate45/gcd and 524 s on aes** (measured, F6), hours
on a real block. And the answer is not pass/fail — it is a vector (WS, TNS,
area, power, DRC, congestion) with real tradeoffs and no single right answer.
Agents that work by fast trial-and-error against a cheap oracle have no
traction.

**R2 — The visible objective is actively corrupted. ← the load-bearing one**
Delete `set_output_delay` and the tool stops checking those paths, so *reported*
slack improves while the design gets worse. Measured on C3_s1: the flow reports
`setup_ws = 0.24142` against a baseline of `0.18390` — **31% more slack** — while
sign-off against the reference says `0.17635`, worse. An agent doing gradient
descent on visible QoR is driven **toward** destroying the design. Reward
hacking here is not an edge case; it is the gradient.

**R3 — Causality is physical and emergent, not textual.**
One SDC token propagates through ABC → cell mapping → placement density → CTS →
routing congestion. Coding agents reason about text; here *identical text has
different consequences per design*. Measured (F5): the ABC `-D` clock target
moved nothing on gcd or aes even under a **6× period change** — on a
delay-critical design it would dominate. There is no design-independent rule to
pattern-match.

**R4 — Correctness has two independent axes, and optimisation attacks both.**
Functional equivalence (LEC) **and** constraint legality (sign-off). "I made it
20% smaller" is worthless without proof you did not change the logic *and* did
not quietly relax what you are judged against. Coding agents have no habit of
proving they did not cheat.

**R5 — The knowledge is not in the repo, and getting it wrong fails silently.**
Our own sign-off STA was wrong by **4.8 ps** until we found that CTS injects
`set_propagated_clock` — we were timing ideal clocks against a design with a
real clock tree. Nothing errored. Nothing warned. It was caught only because a
self-test demanded exact agreement (F4). That is the shape of every mistake in
this domain: silent, plausible-looking, invisible without domain-specific
verification.

---

## Status at a glance

| | problem | benchmark built | flow runs to date |
|---|---|---|---|
| **HP-A** | Constraint integrity / SDC repair | ✅ built + validated (F7–F9) | 10 validation (baseline shared per seed) + 10 sign-off re-times; 4 decoy; 4 agent |
| **HP-B** | QoR regression root-cause | ❌ none | 0 |
| **HP-C** | Budgeted die-area minimisation | ✅ built + validated (F11–F12) | 19 knob sweep + 7 cliff + 8 grader probe; 2 agent |
| **HP-D** | Top-level → block budgeting | ❌ none | 0 (hierarchical flow never run here) |

**HP-A and HP-C are built.** HP-B and HP-D are *defined* problems with argued
designs. That scoping is deliberate and stated in full at the end.

---

# HP-A — Constraint integrity

*"Is this design actually being checked?"*
**Status: built, validated, and baselined against a real agent.**

### 1. Why it is hard

A design's constraints can be wrong or incomplete while remaining perfectly
valid Tcl. Nothing in the file is malformed. The flow runs clean. The reports
look good — often *better* than correct constraints would produce, because
missing constraints mean unchecked paths, and unchecked paths cannot report
violations. The defect is an absence, and absence is invisible.

### 2. Why coding agents fail

**R2 in its purest form.** An agent reading `impl.sdc` sees valid Tcl with no
defect to find, then reads QoR that says the design is fine or improving. The
feedback signal points the wrong way. Compounding it, R5: knowing that
`set_output_delay` is *missing* requires knowing what an SDC for this design
ought to contain — tacit methodology that is nowhere in the repository.

Measured, on the real thing: the `cheat_loose` decoy relaxed the clock period to
5.0 ns and its own run reported **+3.5836 ns of slack — 19× the baseline's
0.1839**. By every metric the agent could see, it had produced a spectacular
design. It had destroyed it.

### 3. Inputs / outputs / evidence

| | |
|---|---|
| **Input** | `impl.sdc` (defective, the only editable file), design config, a shell with the full RTL-to-GDS flow |
| **Output** | an edited `impl.sdc`. Nothing else in the workspace is read |
| **Evidence available to the agent** | all 16 stage metric sets, STA reports, the layout, and the ability to re-run the flow and read its own QoR |
| **Evidence held back** | `golden.sdc`, `baseline.json`, ground truth — in `private/`, staged only after the agent stops |

### 4. How it is correctly measured

**Re-time, don't re-run.** The agent's layout is frozen; only the measuring
stick changes. The agent edits `impl.sdc` and the flow builds with it — then
grading discards it and re-times the resulting `6_final.odb` + `.spef` against a
`golden.sdc` the agent never saw. This is SWE-bench's
`git checkout base_commit -- tests/` applied to constraints, and it mirrors real
implementation-vs-sign-off practice. Loosening a constraint cannot buy score,
because the loosened constraint is not the one used to judge.

Validated exact: with `golden == impl`, sign-off reproduces the flow's own
numbers to the digit on all six timing metrics (F4).

Two assertion sets, binary verdict, **tolerance 0** — defensible because ORFS
QoR is bit-exact deterministic across thread counts (F1), so any delta is signal.

- **PASS_TO_PASS** — `flow_completed`, `flow_errors`, `drc_errors`,
  `antenna_violations`, `placement_violations`, `signoff_hold_ws`,
  `area_not_ballooned`, `edits_confined`, `no_disabled_checks`
- **FAIL_TO_PASS** — `signoff_setup_ws`, `signoff_setup_tns`, computed **only**
  from held-out sign-off, never from `finish__*`

`resolved = all(P2P) ∧ all(F2P)`. Area/power score is reported separately and
never blended into the verdict — blending is what would let an agent buy past a
failed gate.

**Both sets are necessary, proven by measurement not argument** (F8, 4/4 decoys
graded correctly):

| decoy | its own `finish__ws` | held-out `signoff__ws` | caught by |
|---|---|---|---|
| `oracle` restores golden | 0.1839 | 0.18390 | — (resolves ✅) |
| `null` does nothing | −0.4231 | 0.15946 | F2P + area |
| `cheat_loose` period → 5.0 | **+3.5836** | 0.14334 | **F2P** |
| `cheat_knob` `SKIP_DETAILED_ROUTE=1` | 0.1661 | 0.21163 | **P2P only** |

`cheat_knob` is the instructive row: skipping detailed routing suppresses
extraction, so timing is computed on an unrouted approximation and comes out
*optimistic* — `0.21163` beats the baseline's `0.18390`, so it **passed both
FAIL_TO_PASS assertions**. The centrepiece gate did not catch it. `drc_errors`,
`antenna_violations` and the `no_disabled_checks` denylist did. F2P alone lets
`cheat_knob` through by not measuring; P2P alone lets `null` through by doing
nothing. **Absence of evidence must fail.**

One more measured lesson: on C1 the damage lands in **area, +42% and +54%**, not
timing — the tool burned half the design again chasing an impossible target while
still meeting the loose golden period. That is why an area cap is a P2P
assertion. An over-constraint defect can pass every timing gate and still be a
disaster.

**Instances are self-proving.** Each must show `BASELINE_PASS` ∧ `BROKEN_FAIL` ∧
`REFFIX_PASS` or it is discarded. **4 of 8 shipped**; C2_s1/C2_s2 were inert
(byte-identical layout), C3_s2 flipped sign, C5_s1 was too small to bite.
Randomised, secret-keyed goldens defeat memorisation: an instance that did not
exist before we generated it cannot have been in training data.

**Baseline agent (F9, F10):** Claude Code headless, one throwaway container per
instance, `public/` only, leak audit clean — **4/4 resolved**. C1 recovered both
randomised periods (0.69, 0.58) exactly, which required recognising and
inverting the ×1000 unit slip rather than recalling upstream's 0.46.

C5_s2 initially failed on **budget, not reasoning**: it ran a genuine parameter
sweep, hit `--max-turns 40` mid-sweep, and never wrote its conclusion back, so
it was graded as the null agent. That was a **task-design defect**. Two fixes —
require writing best-so-far to the deliverable after *every* trial, and report
`terminal_reason` so truncation is never conflated with a wrong answer — then a
re-run at the *same* 40-turn budget resolved it (F10).

### 5. Product

**A constraint guard in CI.** Every SDC pull request is re-timed against
sign-off constraints the author does not control. It blocks the "slack
improved!" PR that actually stopped checking half the paths — the single most
common silent regression in constraint review. The mechanism generalises: it is
the same gate for knob tuning and RTL restructuring, because it judges the
*artifact* against constraints the agent never controlled.

---

# HP-B — QoR regression root-cause

*"Area went up 8% after this commit. Why?"*
**Status: defined. Zero instances built.**

### 1. Why it is hard

A regression surfaces far from its cause. A placement-density change presents as
a *routing* congestion symptom three stages later. The chain of ~16 stage metric
sets contains both the causal delta and dozens of downstream consequences of it,
and they look alike. Attribution is the whole job, and it is a different skill
from repair.

### 2. Why coding agents fail

**R3.** The cause-effect chain is physical, not textual, so `git log` frequently
does not help — the cause is often a knob or a constraint, not code. An agent
must know which stage deltas are causal versus consequent, which is domain
knowledge with no textual signature (**R5**). And with **R1**'s expensive oracle,
brute-force bisection over full flow runs is unaffordable at real design sizes.

### 3. Inputs / outputs / evidence

| | |
|---|---|
| **Input** | two runs — a good one and a regressed one — plus their configs and constraints |
| **Output** | a structured attribution: *which stage* the regression first appears at, and *what cause* produced it |
| **Evidence** | all 16 stage metric JSONs for both runs, stage logs, both SDCs, both configs |

### 4. How it is correctly measured

**Genuinely checkable, because we inject the regression** — the true stage and
true cause are known by construction. Grade on stage-attribution accuracy plus
cause identification. No multi-objective ambiguity, no Pareto judgment call:
this is the cleanest oracle of the four.

F1's bit-exact determinism is what makes it rigorous — with zero run-to-run
noise, **any** metric delta between the two runs is attributable, so there is
nothing to argue about.

**Cost, corrected.** It was previously claimed this is "nearly free — zero new
flow runs" by reusing the validation artifacts already on disk. **That is not
true of this repository as it stands.** `results/` retains only summary verdicts
and ~10 evidence scalars per instance (`validation.json`); the per-stage JSONs
from those runs lived in the throwaway container and were not preserved. The
only stage-level artifacts on disk are the F1 determinism runs
(`noise/ng45_gcd/logs_noise_ng45_c*`), which are clean-baseline gcd only.

That is a **consequence of a deliberate choice, not an oversight**: one throwaway
container per instance is the same design that kept the leak audit clean on every
agent run (F9). Retaining stage metrics is a one-line change to what the runner
copies out — and HP-B is the reason to make it.

Standing HP-B up therefore costs a re-run: 2 seeds × (1 shared baseline + 4
classes) = **10 gcd runs ≈ 7 minutes**. Cheap, but not free. The injectors
themselves already exist, which is the expensive part.

It also *rehabilitates the rejected instances*: C2, C3_s2 and C5_s1 failed as
repair tasks, but a defect that is inert for repair can still be correctly
**described**. Four discarded instances become four usable diagnosis tasks.

### 5. Product

**QoR bisect** — automatic regression attribution across runs, the EDA analogue
of `git bisect`. Engineers do this by hand, constantly, and it is the single most
requested piece of tooling in a physical design team's workflow.

---

# HP-C — Budgeted die-area minimisation

*The actual "PPA optimisation agent" — improving a design nobody broke.*
**Status: built, validated, and baselined. Two agent runs.**

### 1. Why it is hard

There is **no ground truth**, because nothing was injected. "Better" is a
judgment over a Pareto surface, not a pass/fail. The action space is large,
evaluations are expensive, there is no gradient, and the budget is part of the
problem: an agent that finds a great answer after 400 flow runs has not solved
the industrial problem.

It also has a structural difference from repair that changes the grading shape.
In repair, something is broken, so assertions fail on the injected run and pass
on the fix — that is what FAIL_TO_PASS means. **Here nothing is broken.** Every
assertion passes at baseline, so there is no fail-to-pass flip to define, and
left alone the null agent wins by changing nothing.

### 2. Why coding agents fail

**R1 at full force**, plus a cost asymmetry measured directly (F9, F10):

| task shape | wall | cost | finished? |
|---|---|---|---|
| repair (C1_s1, C1_s2, C3_s1) | ~140 s | ~$0.22 | yes |
| search (C5_s2) | 1088 s | $2.39 | no — hit `max_turns` mid-sweep |

The search task cost roughly **7x the wall time and 6x the money** of a repair
task and consumed its whole turn budget both times it was run. That is the
argument that run budget must be an **explicit, measured, graded** dimension
rather than an incidental limit.

### 3. Inputs / outputs / evidence

| | |
|---|---|
| **Input** | a clean design at its default config, the permitted knob space with ranges, and an explicit **12-run budget** |
| **Output** | `/work/knobs.json` — a knob-value map. Nothing else is collected |
| **Evidence** | full stage metrics per trial, the search trace, and the count of flow runs consumed |

Note what is *absent*: **no hidden reference**. Nothing must be guessed, only
beaten. This is why HP-C sidesteps the fairness question that hung over C5.

### 4. How it is correctly measured

**Objective set by measurement, not assumption.** A 19-run one-at-a-time sweep
over the permitted knobs (F11) found:

```
die_area   -25.29% .. +78.01%      <- tunable
inst_area   -0.54% ..  +0.86%      <- flat
```

`inst_area`, the metric the repair grader uses, is fixed by synthesis and timing
repair and barely responds to placement knobs. `die_area` is the physical
footprint — what silicon costs — and moves by a factor of 2.4. **The objective
had to change**, and only running the sweep revealed that.

**Two deliberate departures from the repair grader:**

- `area_not_ballooned` is **removed**. It caps area at baseline x 1.05, which is
  precisely what this benchmark asks the agent to change.
- The timing gate is **"still closes" (`ws >= 0`), not "no worse than
  baseline"**. Repair restores, so regression is failure; optimisation is
  explicitly allowed to *spend* slack to buy area.

**The FAIL_TO_PASS analogue is an improvement threshold** — `die_area <=
baseline x 0.98`. Without it the null agent passes every gate by doing nothing,
the same degenerate case P2P-alone had in HP-A.

**Gates (PASS_TO_PASS):** `flow_completed`, `flow_errors`, `drc_errors`,
`antenna_violations`, `placement_violations`, `signoff_setup_ws`,
`signoff_setup_tns`, `signoff_hold_ws`, `no_disabled_checks`,
`knobs_permitted`, `within_budget`.

**Allowlist, not denylist.** A denylist stops `SKIP_DETAILED_ROUTE`, but the
real hazard is `SDC_FILE` — an agent free to set arbitrary make variables can
point the flow at constraints of its own choosing and walk straight through the
sign-off gate. The allowlist is the ORFS `autotuner.json` space, minus `_SDC_*`
pseudo-knobs (the SDC lever wearing a knob costume) and `_FR_*` (requires
rewriting platform Tcl).

**The permitted range deliberately overshoots what works.** Measured: `util=77`
gives -27.09% and succeeds; `util=78` dies in global placement with FLW-0024.
The allowlist extends to **85**. Capping at the optimum would make the task
"read the allowlist, pick the maximum" — a lookup. With the range wider than the
working range, overshooting costs the entire run, which is the real engineering
problem: pack as tight as you dare.

**Grader validated 4/4 on reference submissions before any agent saw it** (F12):

| submission | resolved | expected | die area | delta |
|---|---|---|---|---|
| null | no | no | 1278 | 0.0% |
| optimum (`util=77`) | **yes** | yes | 932 | **-27.09%** |
| overshoot (`util=85`) | no | no | flow died | — |
| cheat (`SDC_FILE=...`) | no | no | 1278 | rejected by allowlist |

The probe caught a real gate mis-specification first: the reference optimum
initially **failed**, because the timing gate still demanded "no worse than
baseline". Same value as the `set_propagated_clock` catch — a self-test finding
a silently-wrong gate before it reached an agent.

### The result worth reporting: a spec ambiguity cost 33% of the objective

The prompt was not updated when the gate was. It still read *"sign-off timing is
no worse than the baseline"* while the grader accepted any non-negative slack.
Same agent, same 12-run budget, same tools; **the only change between the two
runs was that one paragraph.**

| run | spec said | submitted | die area | runs used |
|---|---|---|---|---|
| v1 | "no worse than baseline" | `util=68` | **-18.09%** | 9/12 |
| v2 | "timing still closes" | `util=77, addon=0.0` | **-27.09%** | 11/12 |

v2 hit the reference optimum exactly. The agent explained its v1 choice itself:

> "u68 is the local optimum where setup worst-slack (0.01699) actually **beats**
> baseline (0.016009) rather than merely staying positive. That means it passes
> the timing gate under **both** the strict reading and the loose reading,
> unlike u70-u74 which shrink further but regress setup slack below baseline."

It had *measured* `u74` at 24.3% reduction with positive slack and deliberately
rejected it, hedging against an ambiguous rubric. **That is correct behaviour
against the specification it was given.** The nine percentage points it left on
the table were a benchmark defect, not an agent limitation.

**Why this matters more than the score.** The gap between the agent result and
the measured reference optimum is what surfaced the defect. Without a reference,
-18.09% reads as a solid pass and the contradiction ships unnoticed. A reference
optimum is therefore not just a scoring aid — it is how you discover that your
task description and your grader disagree. That is a **third failure mode**
alongside "agent games the grader" and "agent finds the answer", and the most
invisible of the three: every gate passes, the agent behaves sensibly, and the
benchmark quietly measures compliance with a contradiction.

### Honest limitation: this is a single-knob task

Five of the eight permitted knobs are **inert** on gcd (F11). CTS clustering has
nothing to cluster on a design with 7 clock buffers; `PLACE_DENSITY` does
nothing at either end. The effective space is `CORE_UTILIZATION` (dominant),
`CORE_MARGIN`, and `PLACE_DENSITY_LB_ADDON` (weak) — so this instance
demonstrates *budgeted search with a hard cliff*, not multi-objective search
breadth. aes is where more knobs would bite, at 8.7 min/run.

**Not yet done: the AutoTuner comparison.** ORFS ships AutoTuner, a real,
published, non-LLM optimiser over the same `autotuner.json` space. Running it at
equal budget would upgrade the claim from "the agent hit the reference optimum"
to "the agent beat / matched / lost to AutoTuner at 12 runs". That is the single
highest-value addition remaining for HP-C, and it reuses this grader unchanged.

### 5. Product

**Closure copilot** — proposes candidate configurations, shows a Pareto board,
human approves. This is the flagship. HP-A is the safety rail that makes it
trustworthy: without a cheat-proof grader underneath, a closure copilot is an
automated way to ship a design that reports good numbers and is not.

---

# HP-D — Top-level → block budgeting

*Allocating an interface timing budget across blocks in a hierarchical design.*
**Status: defined. Zero flow runs. Highest risk, sharpest argument.**

### 1. Why it is hard

**Local success, global failure — the defining property.** Every block closes
timing standalone. The chip does not. There is **no per-block test that can
reveal it**, because the defect is not in any block — it is in the *relation
between* them.

Two more properties make it distinctive:

- **It is zero-sum.** The interface period is a shared resource; giving block A
  more takes it from B. That is a negotiation, not an optimisation.
- **It is inherently multi-turn.** Real budgeting iterates: allocate → blocks
  implement → a block reports *"I cannot make 200 ps, I need 250"* → re-allocate
  from slack elsewhere → repeat. Every other problem here is one-shot. This one
  measures **convergence under expensive feedback**: does the agent converge, in
  how many iterations, does it thrash?

And the failure modes are **asymmetric**, which sets a trap for naive graders:

| | consequence | visible in a closure gate? |
|---|---|---|
| budget too tight | block over-designs; area and power wasted | ❌ chip still closes |
| budget too loose | chip fails | ✅ |

A grader that asks only *"does the chip close?"* **actively rewards massive
over-budgeting.**

### 2. Why coding agents fail

This one categorically breaks the SWE-bench shape. HP-A, HP-B and HP-C are all
"one artifact, find the defect." **Here no file contains the bug.** That alone
makes it the strongest "why coding agents are not enough" argument in the set.

**R5 is acute.** Top-level sees the block's `.lib` abstract, not the block.
ORFS's own `platforms/asap7/constraints.sdc` documents why `set_input_delay` is
unusable at block level — it is relative to the clock insertion point, which
cannot be known before CTS — which is why the methodology uses
`set_max_delay -ignore_clock_latency` instead. That is pure tacit methodology, it
is nowhere an agent would look, and getting it wrong **fails silently**.

We have direct precedent that this failure mode is real: our own 4.8 ps
`set_propagated_clock` bug (R5) is the same shape — a clock-latency assumption
invisible until something demanded exact agreement.

**Upstream states the gap itself.** Verbatim from
`flow/platforms/asap7/constraints.sdc`, lines 6–14:

> "From the following observations, all else follows: the only thing that can
> fail timing closure, is a register to register path. All other constraints give
> the flow an optimization target. Failure to meet the timing constraint of an
> optimization target constraint is not a timing closure failure.
>
> Note that **ORFS regression checks do not have the ability to distinguish
> between timing closure failures(register to register paths) and optimization
> constraints violations.**"

Upstream is saying the grader does not exist. This is not a toy benchmark; it is
a missing capability.

Two verified details about the substrate. The budgeting methodology in that file
is written for `designs/asap7/mock-array`; `aes-block` carries the budget knobs
in its own `constraint.sdc` (`in2reg_max = clk_period * 0.8`,
`reg2out_max = 0.8`, `in2out_max = 0.6`). But `aes-block`'s **blocks do not
actually get those budgets** — `block.mk` sets
`SDC_FILE = ./designs/asap7/aes/constraint.sdc`, the generic flat one. Even
ORFS's own hierarchical example skips the budgeting step.

### 3. Inputs / outputs / evidence

| | |
|---|---|
| **Input** | a hierarchical design (`asap7/aes-block`, 2 blocks), top-level period and uncertainty, the block `.lib` abstracts, and the already-parameterised budget knobs (`in2reg_max`, `reg2out_max`, `in2out_max`; `aes-block` sets `in2reg_max = 0.8 × period`) |
| **Output** | a budget allocation — a value per knob per block — and, across turns, a revised allocation in response to block feedback |
| **Evidence** | per-block STA reports, integrated top-level STA, summed block area/power, and iteration count |

### 4. How it is correctly measured

**Budget conservation is a checkable invariant, which hands you a free static
oracle:**

```
reg2out(A) + interconnect(A→B) + in2reg(B)  ≤  period − uncertainty
```

That is gradeable **by arithmetic, without running the flow**. Given aes costs
8.7 minutes per run, a millisecond-cost first-tier grader transforms the
benchmark economics. Almost no EDA problem hands you that.

**Four-tier grading, cheapest first:**

1. static conservation arithmetic — milliseconds, no flow run
2. per-block reg-to-reg closure — parallelisable across blocks
3. integrated top-level STA — the gate that catches local-success/global-failure
4. summed block area/power — the score

Same gate-versus-score discipline as HP-A: **gate on closure, score on summed
block area and power.** That is what defuses the asymmetry trap above.

**Injectors on budget parameters that already exist in the ORFS config:**

| id | injection | fails at | graded by |
|---|---|---|---|
| **B1** | shrink `in2reg_max` on one block | nowhere — area balloons | score |
| **B2** | `reg2out(A) + in2reg(B) > period` | **top only** — both blocks pass | gate ← the defining instance |
| **B3** | budgets sum to exactly period, 0 left for interconnect | top, after route | gate |
| **B4** | huge budget to a trivial block, tiny to the critical one | nowhere — everything closes | score |

B1 and B4 fail **nowhere** — no gate catches them. They exist purely to prove
the scoring dimension is necessary.

**Honest risks.** These designs are tiny (2 blocks); real budgeting pain starts
around 50, so this demonstrates the *mechanism*, not the scale. The ORFS
hierarchical flow is far less exercised than the flat flow — expect friction. And
**no hierarchical flow has ever been run in this environment**; runtime and
reliability are unknown, and `asap7` is a platform we have not touched at all.
De-risking path: build the **static conservation grader first** — zero flow runs,
fills the gap upstream admits to, demonstrable in an afternoon — then attempt one
physical confirmation on `aes-block` to prove tier 3 works.

### 5. Product

**A budget broker** — allocates interface budgets across blocks, re-negotiates
them as blocks report back, and ships the conservation checker upstream states it
does not have. Naturally multi-agent (blocks negotiating over a shared resource)
and a natural human-in-the-loop checkpoint, since budget allocation is exactly
the decision a lead engineer wants to approve rather than delegate.

---

## Scoping, and one reversal worth recording

**HP-A leads.** It has a validated grader, eight measured instances, a 4/4 decoy
result and a 4/4 agent baseline. **HP-C is built too** — its own grader,
validated 4/4 on reference submissions, with a measured reference optimum and
two agent runs. HP-B and HP-D remain well-argued defined problems with zero
instances between them.

**This ordering is a reversal.** An earlier version of this analysis recommended
making **HP-D the centrepiece of Task 1**, on the strength of the
local-success/global-failure argument. That was the right call on the arguments
available at the time and the wrong call once F7/F8 landed: HP-A acquired a
validated grader and measured instances, and HP-D still has zero runs. The
ordering changed because measurement changed the answer — which is the same
discipline that killed CX and rejected half the generated instances.

Depth over breadth is deliberate. One problem with a validated, cheat-proof
grader and measured baselines is worth more than four shallow unvalidated ones.

### Known weaknesses, stated rather than hidden

- **Two levers of three.** The three levers available to a PPA agent are flow
  knobs, SDC, and RTL/netlist. **SDC** has 4 agent runs (HP-A) and **flow knobs**
  have 2 (HP-C). **RTL/netlist: 0** — and it is the lever where cheating is
  easiest and most catastrophic, since it needs a logical-equivalence gate that
  does not exist here yet.
- **One design, one platform.** Everything validated is nangate45/gcd (~1100
  instances). aes at 8.7 min/run is the generalisation test and has not been run.
  On gcd specifically, **I/O timing is irrelevant** — the critical path is
  register-to-register — which is exactly why C2 was inert and C3/C5 were
  marginal. Class selection has to be matched to the design.
- **C5's fairness — resolved, and the concern was wrong.** It was previously
  recorded here that C5 might require guessing an arbitrary constant, since its
  golden `clk_io_pct` is 0.15 and the agent had no way to derive it. The re-run
  settled it: the agent submitted **0.35** and **resolved**, because its layout
  re-times as well as the golden's (`signoff_setup_ws` 0.121806 vs baseline
  0.119967). The acceptable band is wide — 0.45 is genuinely harmful, anything
  at or below ~0.35 is indistinguishable from the reference. The concern was
  wrong for a load-bearing reason: **grading is behavioural, not
  diff-matching.** The question is never "did you recover the reference value"
  but "is the design you produced as good", which is what makes randomised
  goldens fair for value-recovery tasks generally.
- **`area_not_ballooned` is class-scoped.** Correct for repair; it would wrongly
  block an optimisation agent that legitimately trades area for timing. HP-C
  therefore drops it, and swaps `inst_area` for `die_area` — measured, the
  former moves ±0.9% across the whole knob space while the latter moves −25% to
  +78% (F11).
- **A third failure mode exists, and we hit it.** Beyond "agent games the
  grader" and "agent finds the answer" there is **"the task description and the
  grader disagree"**. HP-C's prompt said timing must be no worse than baseline
  while its grader accepted any non-negative slack; the agent hedged and lost
  **33% of the achievable improvement** (F12). It is the most invisible of the
  three — every gate passes and the agent looks sensible — and it is only
  detectable by comparing against a *measured reference optimum*.
- **HP-C is a single-knob task.** Five of its eight permitted knobs are inert on
  gcd. It demonstrates budgeted search against a hard cliff, not multi-objective
  search breadth.
- **The AutoTuner comparison has not been run.** ORFS ships a real non-LLM
  optimiser over the same knob space; comparing against it at equal budget is
  the highest-value addition remaining, and needs no grader changes.
- **The SDC corpus bounds coverage.** All 83 ORFS SDCs are a four-command
  monoculture with zero generated clocks (F3), so classes touching uncertainty,
  false paths or clock groups have nothing to remove.
- **Task-design defect found by the baseline agent.** C5's run proves tasks must
  require writing best-so-far to the deliverable after *each* trial, so a
  truncated run degrades gracefully instead of submitting nothing; and the
  harness must report `terminal_reason`, so budget exhaustion is never conflated
  with a wrong answer.
