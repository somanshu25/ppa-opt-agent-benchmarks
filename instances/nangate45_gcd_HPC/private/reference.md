# Reference optimum (analysis only, not used in grading)

Measured by sweep on nangate45/gcd:

| CORE_UTILIZATION | die area | delta | ws | drc |
|---|---|---|---|---|
| 55 (default) | 1278 | 0.00% | +0.01601 | 0 |
| 75 | 955 | -25.29% | +0.01040 | 0 |
| 77 | 932 | **-27.09%** | +0.01101 | 0 |
| 78+ | FAIL | - | - | FLW-0024 in global placement |

Best legal setting is CORE_UTILIZATION=77. The permitted range extends to 85 so the optimum is interior and overshooting costs the run.

Five of the eight permitted knobs are inert on this design; see docs/FINDINGS.md F11.
