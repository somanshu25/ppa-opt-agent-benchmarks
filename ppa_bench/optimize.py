"""HP-B: budgeted flow-knob optimisation.

A different problem shape from the repair benchmark, and the difference matters
for grading.

In repair, something is broken: assertions fail on the injected run and pass on
the fix, which is what FAIL_TO_PASS means.  Here **nothing is broken**.  The
design starts correct and every assertion passes at baseline, so there is no
fail-to-pass flip to define -- and left alone, the null agent wins by changing
nothing.

So the FAIL_TO_PASS analogue becomes an **improvement threshold**: you must
actually make the design smaller.  PASS_TO_PASS keeps its job of stopping you
from buying that improvement with correctness.

Two deliberate departures from the repair grader:

``area_not_ballooned`` is **removed**.  It caps area at baseline x 1.05, which
    is exactly the thing this benchmark asks the agent to change.
``die_area`` **replaces** ``inst_area`` as the objective.  Measured over the
    permitted knob space on nangate45/gcd, die area moves -25% to +78% while
    instance area moves -0.5% to +0.9% (docs/FINDINGS.md F11). Instance area is
    fixed by synthesis and timing repair; die area is the physical footprint,
    and it is what silicon costs.

Scope, stated rather than implied: on gcd this is close to a **single-knob**
task. Five of the eight permitted knobs are inert on an 1100-cell design.
"""

from __future__ import annotations

from dataclasses import dataclass

from ppa_bench.grader import Assertion, Verdict, _cmp, KNOB_DENYLIST

# Minimum die-area reduction that counts as having done the job. Set from the
# measured range: -25% is reachable with a legal knob setting, so 2% is a low
# bar that still excludes doing nothing. It exists to defeat the null agent,
# not to be the challenge.
DEFAULT_MIN_IMPROVEMENT_PCT = 2.0


@dataclass
class Budget:
    """Flow runs an agent is allowed, and what it actually used.

    Budget is part of the problem statement here, not an incidental limit: the
    measured cost of a search task is roughly 7x a repair task, and both C5
    attempts consumed their entire turn allowance.
    """

    allowed: int
    used: int = 0

    @property
    def exceeded(self) -> bool:
        return self.used > self.allowed


def grade_optimize(instance_id: str,
                   run_qor: dict,
                   run_signoff: dict,
                   baseline_qor: dict,
                   baseline_signoff: dict,
                   completed: bool,
                   knobs_set: set,
                   knob_violations: list,
                   budget: Budget | None = None,
                   min_improvement_pct: float = DEFAULT_MIN_IMPROVEMENT_PCT,
                   tolerance: float = 0.0) -> Verdict:
    """Grade one optimisation attempt."""
    a: list[Assertion] = []

    # ---- PASS_TO_PASS: correctness must survive the optimisation ----------
    a.append(Assertion("flow_completed", "P2P", completed,
                       "flow reached 6_report" if completed
                       else "flow did not finish (over-tightening usually dies "
                            "in global placement)"))
    a.append(_cmp("flow_errors", "P2P", run_qor.get("errors") == 0,
                  run_qor.get("errors"), 0, "=="))
    a.append(_cmp("drc_errors", "P2P", run_qor.get("drc_errors") == 0,
                  run_qor.get("drc_errors"), 0, "=="))
    a.append(_cmp("antenna_violations", "P2P", run_qor.get("antenna_viol") == 0,
                  run_qor.get("antenna_viol"), 0, "=="))
    a.append(_cmp("placement_violations", "P2P", run_qor.get("dpl_violations") == 0,
                  run_qor.get("dpl_violations"), 0, "=="))

    # Timing is a gate, never a score -- scored, an agent would shrink the die
    # until timing collapsed.
    #
    # But the gate is "still closes", NOT "no worse than baseline". Those differ
    # here in a way they do not for repair. A repair is meant to restore the
    # baseline, so regressing timing is failure. An optimisation is explicitly
    # allowed to *spend* slack to buy area -- that is the engineering trade
    # being asked for. Requiring >= baseline would reject the true optimum: on
    # nangate45/gcd, CORE_UTILIZATION=77 gives -27.1% die area at WS +0.011
    # against a baseline WS of +0.016, and a >= baseline gate fails it over
    # 5 ps while the design still closes comfortably.
    for key, label in (("setup_ws", "signoff_setup_ws"),
                       ("setup_tns", "signoff_setup_tns"),
                       ("hold_ws", "signoff_hold_ws")):
        got = run_signoff.get(key)
        if got is None:
            a.append(Assertion(label, "P2P", False, "missing sign-off metric"))
        else:
            a.append(_cmp(label, "P2P", got >= -tolerance, got, -tolerance, ">="))

    banned = knobs_set & KNOB_DENYLIST
    a.append(Assertion("no_disabled_checks", "P2P", not banned,
                       "denylisted knobs set: {}".format(sorted(banned))
                       if banned else "none set"))
    a.append(Assertion("knobs_permitted", "P2P", not knob_violations,
                       "; ".join(knob_violations) if knob_violations
                       else "all knobs within the permitted space"))

    if budget is not None:
        a.append(Assertion("within_budget", "P2P", not budget.exceeded,
                           "{}/{} flow runs used".format(budget.used, budget.allowed)))

    # ---- FAIL_TO_PASS analogue: you must actually improve something -------
    base_die, run_die = baseline_qor.get("die_area"), run_qor.get("die_area")
    if base_die and run_die:
        target = base_die * (1 - min_improvement_pct / 100.0)
        a.append(_cmp("die_area_improved", "F2P", run_die <= target,
                      run_die, target, "<="))
    else:
        a.append(Assertion("die_area_improved", "F2P", False,
                           "missing die area measurement"))

    resolved = all(x.passed for x in a)

    score = {}
    if base_die and run_die:
        score["die_area_delta_pct"] = round(100.0 * (run_die - base_die) / base_die, 3)
    bp, rp = baseline_qor.get("power_total"), run_qor.get("power_total")
    if bp and rp:
        score["power_delta_pct"] = round(100.0 * (rp - bp) / bp, 3)
    bi, ri = baseline_qor.get("inst_area"), run_qor.get("inst_area")
    if bi and ri:
        score["inst_area_delta_pct"] = round(100.0 * (ri - bi) / bi, 3)
    if budget is not None:
        score["runs_used"] = budget.used

    return Verdict(instance_id=instance_id, resolved=resolved,
                   assertions=a, score=score)
