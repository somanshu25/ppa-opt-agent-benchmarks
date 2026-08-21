"""Smoke test: every v1 operator applies to every target design SDC."""

import sys

sys.path.insert(0, "/ppa-bench")

from ppa_bench.injector import inject, V1_CLASSES, InjectionError  # noqa: E402

DESIGNS = [
    ("nangate45", "gcd"),
    ("nangate45", "aes"),
    ("nangate45", "ibex"),
    ("sky130hd", "gcd"),
]
ROOT = "/OpenROAD-flow-scripts/flow/designs"

failures = 0
for platform, design in DESIGNS:
    path = "{}/{}/{}/constraint.sdc".format(ROOT, platform, design)
    try:
        sdc = open(path).read()
    except OSError as exc:
        print("SKIP {}/{}: {}".format(platform, design, exc))
        continue
    for cls in V1_CLASSES + ["CX"]:
        try:
            inj = inject(cls, sdc)
        except InjectionError as exc:
            print("FAIL {:9} {:5} {:3}: {}".format(platform, design, cls, exc))
            failures += 1
            continue
        # The mutation must actually change something, and the golden copy
        # must be preserved verbatim -- the grader depends on both.
        assert inj.sdc != sdc, (cls, platform, design)
        assert inj.golden_sdc == sdc, (cls, platform, design)
        print("ok   {:9} {:5} {:3} {:22} silent={}".format(
            platform, design, cls, inj.name, inj.silent))

print("\nfailures:", failures)
sys.exit(1 if failures else 0)
