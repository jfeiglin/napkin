# Reporting lag and observed decreases

All 300 seeds failed at f28abb4d1b21daae8d3277e583b7cc5bdb2882e1. All three named seed-zero tests also failed against the archived engine at b433a4d710b10ff10c858edeae01cce72a6afcc2. Each seeded run compares the raw readings, the program's monotonicity proof, and the report's lag decision.

| Seed-zero reading | Physical readings in L | Baseline lag decision |
| --- | --- | --- |
| Minimum of two bins | 2 → 6 → 2 | Granted |
| Maximum of the same bins | 10 → 6 → 10 | Granted |
| Fixed-time occurrence lookup | 10 → 2 → 2 | Granted |
| First of two overlapping occurrence stocks | 10 → 10 → 6 | Granted |

Every seed reproduced all four unsound grants. The bin sum stayed at 12 L in seed zero. Lag was correctly granted for the conserved sum, the minimum of two increasing receipt tallies, and the count of starts. The late start after the fixed cutoff left the selected reading unchanged. The overlap model checks that the second stock received exactly what the first stock lost.

The [complete ledger](baseline.jsonl.gz) contains the source hashes, models and all observed proof and report mismatches. The three representative models are [bin transfers](minimum.scn), [fixed cutoff](cutoff.scn) and [overlapping stocks](overlap.scn).
