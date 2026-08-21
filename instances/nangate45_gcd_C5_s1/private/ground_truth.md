# Ground truth: nangate45_gcd_C5_s1

**Sampled golden:** period=0.690 io_pct=0.210 seed=1

**Injected defect:** clk_io_pct 0.21 -> 0.45; flow still passes all gates

**Reference fix restores:**

```
set clk_io_pct 0.21
```
