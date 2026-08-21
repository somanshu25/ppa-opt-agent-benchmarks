# Ground truth: nangate45_aes_C3

**Injected defect:** implementation-run slack IMPROVES; only golden-SDC signoff degrades

**Reference fix restores:**

```
set_output_delay [expr $clk_period * $clk_io_pct] -clock $clk_io_name [all_outputs]
```
