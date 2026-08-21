# Ground truth: nangate45_gcd_C2_s1

**Sampled golden:** period=0.690 io_pct=0.210 seed=1

**Injected defect:** implementation-run slack IMPROVES; only golden-SDC signoff degrades

**Reference fix restores:**

```
set_input_delay [expr $clk_period * $clk_io_pct] -clock $clk_io_name $non_clock_inputs
```
