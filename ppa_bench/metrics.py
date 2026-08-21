"""Parse OpenROAD-flow-scripts run artifacts into a canonical QoR record.

ORFS writes one flat JSON per flow stage into
    <work>/logs/<platform>/<design>/<variant>/<stage>.json
Every key is already stage-prefixed (``synth__``, ``detailedplace__``,
``finish__`` ...), so merging the stage files is a plain dict union.  This
module does that union and then projects it onto the small set of metrics the
benchmark actually grades on.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, asdict, field

# Stage order matters only for reporting; the union itself is collision-free
# because ORFS prefixes every key with its stage name.
STAGE_ORDER = [
    "1_synth", "2_1_floorplan", "2_2_floorplan_macro", "2_3_floorplan_tapcell",
    "2_4_floorplan_pdn", "3_1_place_gp_skip_io", "3_2_place_iop", "3_3_place_gp",
    "3_4_place_resized", "3_5_place_dp", "4_1_cts", "5_1_grt", "5_2_route",
    "5_3_fillcell", "6_1_fill", "6_report",
]

# Canonical QoR projection: friendly name -> ORFS metric key.
QOR_KEYS = {
    "setup_ws":       "finish__timing__setup__ws",
    "setup_tns":      "finish__timing__setup__tns",
    "hold_ws":        "finish__timing__hold__ws",
    "hold_tns":       "finish__timing__hold__tns",
    "fmax":           "finish__timing__fmax",
    "clock_skew":     "finish__clock__skew__setup",
    "power_total":    "finish__power__total",
    "power_leakage":  "finish__power__leakage__total",
    "inst_area":      "finish__design__instance__area",
    "inst_count":     "finish__design__instance__count",
    "die_area":       "finish__design__die__area",
    "core_area":      "finish__design__core__area",
    "utilization":    "finish__design__instance__utilization",
    "nets":           "finish__design__nets",
    "drv_setup_viol": "finish__timing__drv__setup_violation_count",
    "drv_hold_viol":  "finish__timing__drv__hold_violation_count",
    "errors":         "finish__flow__errors__count",
    "warnings":       "finish__flow__warnings__count",
    "wirelength":     "detailedroute__route__wirelength",
    "antenna_viol":   "detailedroute__antenna__violating__nets",
    "synth_area":     "synth__design__instance__area__stdcell",
    "dpl_violations": "detailedplace__design__violations",
    # buffers inserted to repair timing -- the tell-tale of an over-constrained SDC
    "repair_buffers": "finish__design__instance__count__class:timing_repair_buffer",
    "repair_buf_area": "finish__design__instance__area__class:timing_repair_buffer",
}

# Metrics where a larger value is better (used by the scorer).
HIGHER_IS_BETTER = {"setup_ws", "setup_tns", "hold_ws", "hold_tns", "fmax"}


@dataclass
class RunRecord:
    """One flow run: where it came from, whether it finished, and its QoR."""

    platform: str
    design: str
    variant: str
    completed: bool
    last_stage: str | None
    qor: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)

    def to_dict(self, include_raw: bool = False) -> dict:
        d = asdict(self)
        if not include_raw:
            d.pop("raw")
        return d


def merge_stage_json(log_dir: str) -> tuple[dict, list[str]]:
    """Union every ``*.json`` in a run's log directory.

    Returns the merged metrics and the list of stages that produced JSON, in
    flow order.  Unknown/extra stage files are appended after the known ones so
    nothing is silently dropped.
    """
    if not os.path.isdir(log_dir):
        raise FileNotFoundError(log_dir)

    present = {
        os.path.splitext(f)[0]: os.path.join(log_dir, f)
        for f in os.listdir(log_dir)
        if f.endswith(".json")
    }
    ordered = [s for s in STAGE_ORDER if s in present]
    ordered += sorted(s for s in present if s not in STAGE_ORDER)

    merged: dict = {}
    for stage in ordered:
        with open(present[stage]) as fh:
            try:
                merged.update(json.load(fh))
            except json.JSONDecodeError:
                # A stage killed mid-write leaves truncated JSON; treat the
                # stage as absent rather than failing the whole parse.
                continue
    return merged, ordered


def _drc_errors(merged: dict) -> int | None:
    """Final detailed-route DRC count.

    ORFS records one ``__iter:N`` key per routing iteration; the graded number
    is the last iteration's, not the first.
    """
    if "detailedroute__route__drc_errors" in merged:
        return merged["detailedroute__route__drc_errors"]
    iters = [
        (int(m.group(1)), v)
        for k, v in merged.items()
        if (m := re.fullmatch(r"detailedroute__route__drc_errors__iter:(\d+)", k))
    ]
    return max(iters)[1] if iters else None


def parse_run(work_home: str, platform: str, design: str, variant: str = "base") -> RunRecord:
    """Build a RunRecord from an ORFS work tree."""
    log_dir = os.path.join(work_home, "logs", platform, design, variant)
    merged, stages = merge_stage_json(log_dir)

    qor = {name: merged.get(key) for name, key in QOR_KEYS.items()}
    qor["drc_errors"] = _drc_errors(merged)

    # "Completed" means the finish stage wrote its report -- the same condition
    # ORFS itself uses to declare the flow done.
    completed = "6_report" in stages and merged.get("finish__timing__setup__ws") is not None

    return RunRecord(
        platform=platform,
        design=design,
        variant=variant,
        completed=completed,
        last_stage=stages[-1] if stages else None,
        qor=qor,
        raw=merged,
    )


def load_metrics_file(path: str) -> dict:
    """Load a merged-metrics JSON previously written by :func:`dump_run`."""
    with open(path) as fh:
        return json.load(fh)


def dump_run(record: RunRecord, path: str) -> None:
    """Persist a run (canonical QoR + full merged metrics) as JSON."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        json.dump(record.to_dict(include_raw=True), fh, indent=2, sort_keys=True)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Parse an ORFS run into canonical QoR")
    ap.add_argument("work_home")
    ap.add_argument("platform")
    ap.add_argument("design")
    ap.add_argument("variant", nargs="?", default="base")
    ap.add_argument("-o", "--out")
    args = ap.parse_args()

    rec = parse_run(args.work_home, args.platform, args.design, args.variant)
    print(json.dumps(rec.to_dict(), indent=2, sort_keys=True))
    if args.out:
        dump_run(rec, args.out)
