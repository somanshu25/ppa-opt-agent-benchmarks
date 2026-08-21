# Ground truth: nangate45_gcd_C5_s2

**Sampled golden:** period=0.580 io_pct=0.150 seed=2

**Injected defect:** clk_io_pct 0.15 -> 0.45; flow still passes all gates

**Reference fix restores:**

```
set clk_io_pct 0.15
```
