# Task 4 — What This Becomes

What the four hard problems turn into with a team of AI engineers and real
resources: one product, four capabilities, built in the order the evidence
supports.

Every mockup below is grounded in numbers this repo actually measured. Where a
screen shows a value, it is a real one.

---

## The product thesis

> **Nobody wants an agent that optimises their chip. They want an agent whose
> results they can sign off on.**

That is not a reframing for the sake of it — it is what the measurements say.
The `cheat_loose` decoy reported **+3.58 ns of slack, 19x the baseline**, and
had destroyed the design. A product that surfaces that number as a win is worse
than no product. A product that catches it is worth paying for even if the agent
underneath is mediocre.

So the thing being built is **not an optimiser with a verification feature**. It
is a **verification substrate that happens to run agents on top**. The agent is
replaceable; the grader is the moat.

### Three failure modes it must defend against

All three were hit in the course of building this, not theorised:

| # | failure | how it presents | defence |
|---|---|---|---|
| 1 | Agent games the metric | slack "improves" 19x while the design gets worse | held-out sign-off |
| 2 | Agent finds the answer | benchmark measures retrieval, not engineering | randomised, secret-keyed references |
| 3 | **Spec and grader disagree** | every gate passes, agent looks sensible, result is quietly wrong | measured reference optimum |

The third is the one nobody builds for, and it cost **33% of the achievable
improvement** in a controlled A/B (F12). It is invisible without a reference to
compare against — which is an argument for shipping the reference optimum as a
product feature, not just a test fixture.

---

## The shape: a PPA review surface, not a chat box

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  gcd · nangate45 · run #2847                    ● 4 gates passed   ⚠ 1 review │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   DIE AREA          POWER            SETUP WS         DRC                    │
│   932 µm²           1.62 mW          +0.011 ns        0                      │
│   ▼ 27.1%           ▼ 0.2%           ▼ 0.005 ns       —                      │
│   ████████████░░░   ██████████████   ███████░░░░░░    ██████████████         │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │  ⚠  Timing slack was SPENT, not preserved.                             │  │
│  │     Baseline +0.016 → now +0.011. Still closes. This is the trade you  │  │
│  │     asked for, but it is a trade. [see path] [reject] [accept]         │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  PROPOSED CHANGE                                    ┌─────────────────────┐  │
│  ────────────────────────────────────────────────   │  SIGN-OFF           │  │
│  CORE_UTILIZATION        55 ──────────────▶ 77      │  ✓ flow completed   │  │
│  PLACE_DENSITY_LB_ADDON  0.20 ────────────▶ 0.00    │  ✓ DRC 0            │  │
│                                                     │  ✓ antenna 0        │  │
│  ⓘ  util 78 fails: FLW-0024 in global placement.    │  ✓ setup WS ≥ 0     │  │
│     This setting is 1 step from the cliff.          │  ✓ hold WS ≥ 0      │  │
│                                                     │  ✓ knobs in policy  │  │
│  SEARCH TRACE           11 of 12 runs · $0.85       │  ✓ budget 11/12     │  │
│  55 ▁ 65 ▃ 75 ▆ 78 ✗ 79 ✗ 80 ✗ 82 ✗ 83 ✗ 85 ✗ 77 █ │  ─────────────────  │  │
│                                       ▲ chosen      │  vs reference: 100% │  │
│                                                     └─────────────────────┘  │
│  [ view layout ]  [ diff constraints ]  [ replay run ]  [ export evidence ]  │
└──────────────────────────────────────────────────────────────────────────────┘
```

Four deliberate choices:

**The trade is called out, not buried.** Slack went from +0.016 to +0.011. Both
pass. A dashboard that shows only green has taught the engineer nothing. The
warning card exists because *spending* slack is legitimate but must be a
decision, not a side effect.

**The failure trace is shown, not hidden.** `78 ✗ 79 ✗ 80 ✗` is the most
informative part of the screen: it tells the engineer where the cliff is, which
is knowledge they keep after the agent is gone.

**"vs reference: 100%"** — the agent found the known optimum. Without this, the
v1 run's −18.09% would have looked like success. This is failure mode 3 rendered
as a UI element.

**Budget and cost are first-class.** `11 of 12 runs · $0.85`. An answer found in
11 runs and the same answer found in 400 are not the same result.

---

## Capability 1 — Constraint Guard  *(from HP-A)*

**Status: the benchmark for this is built and validated. Agent scores 4/4.**

### What it does

Sits in CI. Every pull request that touches an SDC gets its resulting layout
re-timed against sign-off constraints the author does not control.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  PR #412  "tighten IO budget on gcd"                    ✗ BLOCKED         │
├──────────────────────────────────────────────────────────────────────────┤
│  Author reports:   setup WS  0.184 → 0.241   ▲ 31% better                │
│  Sign-off says:    setup WS  0.184 → 0.176   ▼  worse                    │
│                                                                          │
│  ⓘ  This PR deletes set_output_delay. Removing it means those paths are  │
│     no longer checked, which is why the reported number improved.        │
│     35 endpoints became unconstrained.                                   │
│                                                                          │
│  - set_output_delay [expr $clk_period * $clk_io_pct] ...  ← removed      │
│                                                                          │
│  [ show unconstrained endpoints ]   [ override with justification ]      │
└──────────────────────────────────────────────────────────────────────────┘
```

Those numbers are C3_s1, measured.

### Why an engineer would trust it

It does not argue about the constraint file. It re-times the *artifact* against
constraints the author never controlled, which is what sign-off means in
silicon. And it is validated exact: given identical constraints it reproduces
the flow's own numbers to the digit, on every baseline.

### Why it is a product and not a lint rule

A linter checks syntax. This catches the class of defect where the file is
valid, the flow is clean, and the reports are *better than they should be*. The
"slack improved!" PR that stopped checking half the paths is the most common
silent regression in constraint review, and no static tool sees it.

### Scaling path

Same mechanism, more evidence: multi-corner sign-off, per-endpoint attribution,
and the override audit trail. `override with justification` matters — a gate
nobody can override gets disabled within a quarter.

---

## Capability 2 — Closure Copilot  *(from HP-B)*

**Status: the benchmark for this is built and validated. Agent hit the reference
optimum.**

### What it does

Proposes configurations, runs them under budget, and presents a Pareto board for
human approval. The main screen above *is* this capability.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  PARETO BOARD · gcd · 12-run budget                                      │
├──────────────────────────────────────────────────────────────────────────┤
│  die area                                                                │
│  1300 ┤ ●55 (baseline)                                                   │
│  1200 ┤    ●60                                                           │
│  1100 ┤        ●65                                                       │
│  1000 ┤             ●68  ← v1 agent stopped here                         │
│   950 ┤                  ●75                                             │
│   930 ┤                     ★77  ← optimum, v2 agent                     │
│       └──┬─────┬─────┬─────┬─────┬──                                     │
│        0.020 0.016 0.012 0.008  0   setup WS (ns)                        │
│                                  ↑ cliff: 78+ does not build             │
│                                                                          │
│  ⓘ  v1 stopped at 68 because the spec was ambiguous about whether slack  │
│     could be spent. Clarifying one sentence recovered 9 points of area.  │
└──────────────────────────────────────────────────────────────────────────┘
```

### Why an engineer would trust it

Because timing is a **gate, not a score**. The product cannot hand back a design
that traded closure for area, structurally — not because the model was told not
to. And because the search trace is visible: you can see it probe the cliff and
back off.

### Scaling path

The honest limit today is that this is a **single-knob task** — five of eight
permitted knobs are inert on a 1100-cell design. Scaling means bigger designs
where CTS clustering and routing congestion actually bite, multi-objective
Pareto rather than one scalar, and warm-starting from previous runs on similar
blocks.

**The comparator that makes it credible:** ORFS ships **AutoTuner**, a real
non-LLM optimiser over the same knob space. The claim to earn is not "our agent
found −27%" but *"our agent matched AutoTuner in 11 runs and explained why."*
Explanation is the differentiator; a Bayesian optimiser cannot tell you the
cliff is at 78 because of `FLW-0024` in global placement.

---

## Capability 3 — QoR Bisect  *(from HP-C)*

**Status: defined. Not built.** Injectors exist; standing it up costs ~10 gcd
runs (~7 min) to regenerate stage-level artifacts.

### What it does

Answers *"area went up 8% after this commit — why?"* by attributing a regression
to a stage and then to a cause.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  REGRESSION · gcd · run #2801 → #2847        die area ▲ 8.2%             │
├──────────────────────────────────────────────────────────────────────────┤
│  synth      ─────────────  +0.0%   ·                                     │
│  floorplan  ─────────────  +8.1%   ████████  ← first appears here        │
│  place      ─────────────  +8.1%   ████████  (inherited)                 │
│  cts        ─────────────  +8.3%   ████████  (inherited)                 │
│  route      ─────────────  +8.2%   ████████  (inherited)                 │
│                                                                          │
│  ROOT CAUSE (confidence: high)                                           │
│  CORE_UTILIZATION 60 → 55 in config.mk, commit a3f21c                    │
│                                                                          │
│  ⓘ  Synthesis is unchanged, so this is not an RTL or constraint change.  │
│     The delta originates at floorplan and is inherited downstream.       │
│     Everything after floorplan is a consequence, not a cause.            │
└──────────────────────────────────────────────────────────────────────────┘
```

### Why an engineer would trust it

The distinction between *causal* and *inherited* deltas is the entire value, and
it rests on something measured: ORFS QoR is **bit-exact deterministic** (F1), so
there is no run-to-run noise to argue about. Every delta between two runs is
attributable. That is a stronger footing than most regression tooling has.

### Why it is a product

Engineers do this by hand, constantly, and it is pure archaeology. It is the EDA
analogue of `git bisect` — except the cause is usually a knob or a constraint
rather than code, so `git log` does not help.

### Scaling path

Cross-run indexing over a team's entire run history; "what changed between the
last good tapeout candidate and today"; and automatic attribution on every CI
run rather than on request.

---

## Capability 4 — Budget Broker  *(from HP-D)*

**Status: defined. Zero runs. Highest risk, largest ceiling.**

### What it does

Allocates interface timing budgets across blocks in a hierarchical design, and
re-negotiates as blocks report back what they can actually achieve.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  BUDGET · aes-block · period 450 ps                    ⚠ over-allocated  │
├──────────────────────────────────────────────────────────────────────────┤
│  aes_sbox   reg2out  ████████████░░░░░░░░  180 ps   ✓ closes (162 used)  │
│  interconnect        ████░░░░░░░░░░░░░░░░   60 ps   ✓                    │
│  aes_rcon   in2reg   ██████████████████░░  240 ps   ✓ closes (238 used)  │
│                      ─────────────────────────────                       │
│                      allocated 480 ps  >  450 ps budget      ✗ −30 ps    │
│                                                                          │
│  ⚠  Every block closes standalone. The chip does not.                    │
│     No per-block test can detect this.                                   │
│                                                                          │
│  PROPOSED REALLOCATION                                                    │
│  aes_sbox has 18 ps of unused margin → move to aes_rcon                  │
│  aes_sbox 180 → 150   aes_rcon 240 → 240   interconnect 60 → 60 = 450 ✓  │
│                                                                          │
│  [ accept ]  [ re-run blocks ]  [ ask aes_rcon owner ]                   │
└──────────────────────────────────────────────────────────────────────────┘
```

### Why an engineer would trust it

Because the top-tier check is **arithmetic**, not a model output:

```
reg2out(A) + interconnect(A→B) + in2reg(B)  ≤  period − uncertainty
```

That is verifiable by hand in ten seconds, which is exactly the property you
want in the gate a lead engineer signs. The expensive physical confirmation runs
behind it, but the first-tier answer is checkable without trusting anything.

### Why it is the strongest product argument

Upstream ORFS says this capability does not exist. Verbatim, from
`flow/platforms/asap7/constraints.sdc`:

> "ORFS regression checks do not have the ability to distinguish between timing
> closure failures (register to register paths) and optimization constraints
> violations."

And the failure mode is one no single-artifact tool can catch: **every block
passes, the chip fails.** There is no file containing the bug.

### Why it is naturally human-in-the-loop and multi-agent

Interface budget is a **shared, zero-sum resource** — giving block A more takes
it from B. That is a negotiation between block owners, not an optimisation. It
is also the decision a lead engineer most wants to approve rather than delegate,
which makes `ask aes_rcon owner` a real button rather than a mockup flourish.

### Scaling path

Two blocks demonstrates the mechanism; the pain starts around 50. Scaling means
hierarchical budget trees, convergence tracking across iterations (does the
allocation settle or oscillate?), and per-owner notification when a budget they
depend on moves.

---

## The evidence pack — what ships with every result

The PDF asks what an engineer would want before trusting an agent. Concretely,
one export per run:

| artifact | why it is in the pack |
|---|---|
| **Verdict** — every assertion, pass/fail, with numbers | not a score; the actual checks |
| **Sign-off delta** — implementation view vs held-out view | where the lie would be, if there were one |
| **Search trace** — every trial, including failures | the cliff is knowledge the engineer keeps |
| **Diff** — exactly what changed, confined to permitted files | reviewable in seconds |
| **vs reference** — % of known-achievable | catches spec/grader disagreement |
| **Budget + cost** — runs used, dollars | "found in 11 runs" ≠ "found in 400" |
| **Replay command** — pinned commit, exact invocation | reproducible without the product |
| **Leak audit** — what the agent could reach | evidence it solved rather than looked up |
| **Layout images** — congestion, IR drop, worst path | the visual an engineer actually opens |

The replay command matters more than it looks. An evidence pack that only works
inside the product is a lock-in artifact, not a trust artifact.

---

## Build order, and what it costs to be wrong

| phase | capability | why here |
|---|---|---|
| now | Constraint Guard | validated grader; highest trust-per-effort; the safety rail everything else needs |
| next | Closure Copilot | validated grader; needs bigger designs and the AutoTuner comparison to be credible |
| then | QoR Bisect | cheapest to stand up (~7 min of runs); cleanest oracle of the four |
| later | Budget Broker | largest ceiling, highest risk; de-risk with the static conservation checker first, which needs zero flow runs |

Constraint Guard is deliberately first even though Closure Copilot is the
flagship. **Without a cheat-proof grader underneath, a closure copilot is an
automated way to ship a design that reports good numbers and is not.** The order
is a safety argument, not a difficulty ranking.

---

## What would make this fail

Stated plainly, because a product pitch with no failure modes is not a plan:

- **The graders do not survive contact with real designs.** Everything here is
  validated on an 1100-cell design on one platform. aes at 8.7 min/run is the
  first real test and has not been run.
- **Sign-off is not the only correctness axis.** The RTL/netlist lever needs
  logical equivalence checking, which does not exist in this harness yet — and
  it is the lever where cheating is easiest and most catastrophic.
- **Cost.** A search task measured 7x the wall time and 6x the cost of a repair
  task. On a real block at hours per run, that is the business model, not a
  footnote.
- **Gates that fire too often get disabled.** Which is why override-with-
  justification is in the design from the start rather than added after the
  first angry quarter.
