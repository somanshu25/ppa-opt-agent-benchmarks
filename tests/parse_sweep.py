"""Summarise the clock-period sweep used to pick the randomisation range.

An instance is only usable if its baseline is clean, so this reports the two
things that decide that: does timing close, and is the layout DRC-clean.
"""

import json
import os
import sys

sys.path.insert(0, "/ppa-bench")
from ppa_bench.metrics import parse_run  # noqa: E402

WORK = "/OpenROAD-flow-scripts/flow"
periods = sys.argv[1:] or ["0.46", "0.50", "0.55", "0.60", "0.65", "0.70"]

print("{:>8} {:>10} {:>10} {:>9} {:>8} {:>5} {:>7}".format(
    "period", "setup_ws", "setup_tns", "area", "power", "drc", "verdict"))
print("-" * 64)

for p in periods:
    variant = "rand_p" + p
    log_dir = os.path.join(WORK, "logs", "nangate45", "gcd", variant)
    if not os.path.isdir(log_dir):
        print("{:>8} {:>10}".format(p, "(missing)"))
        continue
    try:
        rec = parse_run(WORK, "nangate45", "gcd", variant)
    except Exception as exc:  # noqa: BLE001
        print("{:>8} parse error: {}".format(p, exc))
        continue

    q = rec.qor
    if not rec.completed or q.get("setup_ws") is None:
        print("{:>8} {:>10}  (still running, last stage {})".format(
            p, "-", rec.last_stage))
        continue

    # BASELINE_PASS: the flow finished, timing closes, and the layout is clean.
    # Without positive slack there is no headroom for an injected defect to
    # show up as a *degradation* rather than as more of an existing violation.
    clean = (
        rec.completed
        and q["setup_ws"] >= 0
        and q["drc_errors"] == 0
        and q["errors"] == 0
    )
    print("{:>8} {:>+10.5f} {:>+10.4f} {:>9.1f} {:>8.5f} {:>5} {:>7}".format(
        p, q["setup_ws"], q["setup_tns"], q["inst_area"],
        (q["power_total"] or 0) * 1000, q["drc_errors"], "PASS" if clean else "fail"))
