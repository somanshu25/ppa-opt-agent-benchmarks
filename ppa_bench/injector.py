"""SDC defect injectors.

Each operator takes a clean ORFS ``constraint.sdc`` and returns a mutated copy
plus the ground truth needed to grade a repair.  The operator set is chosen
from the corpus survey (``survey/``): 48 of 83 ORFS SDCs are the same
four-command template, so every operator here targets one of
``create_clock`` / ``set_input_delay`` / ``set_output_delay`` /
``set_clock_latency``.  Mutations that remove uncertainty, false paths or
generated clocks are deliberately absent -- those commands are near-nonexistent
in the corpus and there would be nothing to remove.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Injection:
    """A mutated SDC plus everything the grader and validator need."""

    class_id: str
    name: str
    sdc: str                      # the mutated (broken) SDC text
    golden_sdc: str               # the reference SDC, held out from the agent
    description: str              # shown to the agent as the task
    ground_truth: str             # what the reference fix restores
    expect_degrades: list[str]    # canonical QoR fields expected to worsen
    silent: bool = False          # True if the implementation run looks *better*
    notes: str = ""
    meta: dict = field(default_factory=dict)


class InjectionError(RuntimeError):
    """Raised when an operator cannot apply to the given SDC."""


def _require(pattern: str, text: str, what: str) -> re.Match:
    m = re.search(pattern, text, flags=re.M)
    if not m:
        raise InjectionError("cannot inject: " + what + " not found in SDC")
    return m


# --------------------------------------------------------------------------
# C1 -- clock period unit slip
# --------------------------------------------------------------------------

def c1_unit_slip(sdc: str, factor: float = 1000.0) -> Injection:
    """Write the clock period in the wrong unit (ns read as ps, or vice versa).

    Ground truth is unambiguous -- there is exactly one right answer -- which
    makes this the calibration instance of the suite.
    """
    m = _require(r"^set\s+clk_period\s+(\S+)", sdc, "set clk_period")
    orig = float(m.group(1))
    slipped = orig / factor
    broken = sdc[: m.start(1)] + repr(slipped) + sdc[m.end(1):]
    return Injection(
        class_id="C1",
        name="unit_slip",
        sdc=broken,
        golden_sdc=sdc,
        description=(
            "The clock period in this SDC appears to be wrong. The design is "
            "being over-constrained and QoR has collapsed. Diagnose and fix "
            "the constraint file."
        ),
        ground_truth="set clk_period " + m.group(1),
        expect_degrades=["setup_ws", "setup_tns", "inst_area", "power_total"],
        notes="period {} -> {} (divided by {})".format(orig, slipped, factor),
        meta={"original_period": orig, "broken_period": slipped},
    )


# --------------------------------------------------------------------------
# C2 / C3 -- missing I/O constraints
# --------------------------------------------------------------------------

def _drop_command(sdc: str, command: str) -> tuple[str, str]:
    """Remove every line invoking ``command``; return (new_sdc, removed_text)."""
    kept, removed = [], []
    for line in sdc.splitlines(keepends=True):
        target = removed if re.match(r"^\s*" + command + r"\b", line) else kept
        target.append(line)
    if not removed:
        raise InjectionError("cannot inject: no " + command + " in SDC")
    return "".join(kept), "".join(removed)


_INCOMPLETE_PROMPT = (
    "This SDC is incomplete: some timing paths in the design are not being "
    "checked at all. Identify what is missing and restore it."
)


def c2_missing_input_delay(sdc: str) -> Injection:
    """Delete ``set_input_delay``, leaving input paths unconstrained.

    This is the most interesting class in the suite: with input paths
    unconstrained the *implementation* run reports better slack while the
    design is genuinely worse.  Only sign-off STA against the held-out golden
    SDC exposes it, which is precisely the gate this benchmark exists to
    justify.
    """
    broken, removed = _drop_command(sdc, "set_input_delay")
    return Injection(
        class_id="C2",
        name="missing_input_delay",
        sdc=broken,
        golden_sdc=sdc,
        description=_INCOMPLETE_PROMPT,
        ground_truth=removed.strip(),
        expect_degrades=["signoff_setup_ws", "signoff_setup_tns"],
        silent=True,
        notes="implementation-run slack IMPROVES; only golden-SDC signoff degrades",
    )


def c3_missing_output_delay(sdc: str) -> Injection:
    """Delete ``set_output_delay`` -- the output-side twin of C2."""
    broken, removed = _drop_command(sdc, "set_output_delay")
    return Injection(
        class_id="C3",
        name="missing_output_delay",
        sdc=broken,
        golden_sdc=sdc,
        description=_INCOMPLETE_PROMPT,
        ground_truth=removed.strip(),
        expect_degrades=["signoff_setup_ws", "signoff_setup_tns"],
        silent=True,
        notes="implementation-run slack IMPROVES; only golden-SDC signoff degrades",
    )


# --------------------------------------------------------------------------
# C5 -- over-constrained I/O budget
# --------------------------------------------------------------------------

def c5_io_overconstrain(sdc: str, new_pct: float = 0.45) -> Injection:
    """Inflate the I/O timing budget so the core is squeezed for no reason.

    Nothing breaks -- the flow completes and signoff passes.  The design is
    simply worse: more area and power spent meeting a budget nobody asked for.
    Tests QoR judgment rather than defect repair, so it is graded on score
    rather than on a gate.
    """
    m = _require(r"^set\s+clk_io_pct\s+(\S+)", sdc, "set clk_io_pct")
    orig = float(m.group(1))
    if new_pct <= orig:
        raise InjectionError("new clk_io_pct must exceed the original")
    broken = sdc[: m.start(1)] + str(new_pct) + sdc[m.end(1):]
    return Injection(
        class_id="C5",
        name="io_overconstrain",
        sdc=broken,
        golden_sdc=sdc,
        description=(
            "This design meets timing and passes signoff, but its QoR is worse "
            "than it needs to be. Find the constraint that is costing area and "
            "power without buying anything, and improve it."
        ),
        ground_truth="set clk_io_pct " + m.group(1),
        expect_degrades=["inst_area", "power_total", "utilization"],
        notes="clk_io_pct {} -> {}; flow still passes all gates".format(orig, new_pct),
        meta={"original_pct": orig, "broken_pct": new_pct},
    )


# --------------------------------------------------------------------------
# CX -- semantically-null rewrite that is not actually null
# --------------------------------------------------------------------------

def cx_expr_period(sdc: str) -> Injection:
    """Rewrite the period as a Tcl expression -- valid SDC, identical to STA.

    ORFS scrapes the period out of the SDC *textually*
    (``scripts/variables.mk``) and forwards it to ABC as ``-D``.  An
    ``[expr ...]`` form defeats that regex and ABC silently receives the
    literal string ``[expr``.  Confirmed end-to-end; nothing errors or warns.

    Shipped as a *probe*, never as a scored instance.  Measured on both gcd and
    aes, the corrupted ABC ``-D`` changes synthesis by exactly nothing -- even a
    6x period change leaves area and cell count bit-identical (see
    docs/FINDINGS.md).  So this is a real silent-corruption channel with no
    demonstrated QoR consequence, which makes it a good finding and a bad
    benchmark task.  Kept so the negative result stays reproducible.
    """
    m = _require(r"^set\s+clk_period\s+(\S+)", sdc, "set clk_period")
    val = m.group(1)
    broken = sdc[: m.start(1)] + "[expr " + val + "]" + sdc[m.end(1):]
    return Injection(
        class_id="CX",
        name="expr_period_rewrite",
        sdc=broken,
        golden_sdc=sdc,
        description="Tidy up this SDC. Do not change what it means.",
        ground_truth="a bare literal period (" + val + ") must survive the ORFS scrape",
        expect_degrades=[],
        silent=True,
        notes=(
            "STA-identical. Corrupts ABC -D via textual scrape, silently. "
            "MEASURED: no QoR effect on gcd or aes. Documented finding, not a "
            "scored instance."
        ),
    )


OPERATORS = {
    "C1": c1_unit_slip,
    "C2": c2_missing_input_delay,
    "C3": c3_missing_output_delay,
    "C5": c5_io_overconstrain,
    "CX": cx_expr_period,
}

# Classes shipped as scored v1 instances (CX is a probe, see above).
V1_CLASSES = ["C1", "C2", "C3", "C5"]


def inject(class_id: str, sdc: str, **kwargs) -> Injection:
    """Apply one operator by class id."""
    if class_id not in OPERATORS:
        raise InjectionError("unknown injector class " + repr(class_id))
    return OPERATORS[class_id](sdc, **kwargs)
