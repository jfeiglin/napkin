# Short bends in a uniform-lag report

At ee36192d068884c5ab348bcb5306525022b6a9b9, 134 of 300 seeds failed under both full and selective recording. The raw report and an independent integral of the raw reads agreed with the analytic results in all 300 seeds. In 132 seeds the stored history also missed one or more sampled interior values. In the other two, seeds 220 and 265, all sampled history values agreed but the integrated lag still differed. The straight-line control passed throughout.

In the [seed-zero model](bend.scn), credit rises from 0.51 L at 0.51 h to 0.53 L at 0.52 h and then stays level until 0.53 h. The stored history gave 0.52 L at the peak, and the lagged report gave 0.5 L for a window whose analytic mean is 0.5001 L. This direct test also fails on b433a4d710b10ff10c858edeae01cce72a6afcc2.

The [complete ledger](baseline.jsonl.gz) retains the 166 passing controls and the full models and numerical differences for the 134 failures.
