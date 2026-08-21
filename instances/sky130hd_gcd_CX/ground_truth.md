# Ground truth: sky130hd_gcd_CX

**Injected defect:** STA-identical. Corrupts ABC -D via textual scrape, silently. MEASURED: no QoR effect on gcd or aes. Documented finding, not a scored instance.

**Reference fix restores:**

```
a bare literal period (1.1) must survive the ORFS scrape
```
