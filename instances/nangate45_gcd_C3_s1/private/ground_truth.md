# Ground truth: nangate45_gcd_C3_s1

**Sampled golden:** period=0.690 io_pct=0.210 seed=1

**Injected defect:** implementation-run slack IMPROVES; only golden-SDC signoff degrades

**Reference fix restores:**

```
set_output_delay [expr $clk_period * $clk_io_pct] -clock $clk_io_name [all_outputs]
```
