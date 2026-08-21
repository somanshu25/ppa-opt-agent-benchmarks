# Ground truth: nangate45_gcd_C3_s2

**Sampled golden:** period=0.580 io_pct=0.150 seed=2

**Injected defect:** implementation-run slack IMPROVES; only golden-SDC signoff degrades

**Reference fix restores:**

```
set_output_delay [expr $clk_period * $clk_io_pct] -clock $clk_io_name [all_outputs]
```
