# Monte Carlo recording request

Revision `e2a24f2258cd5a747f3bb78661ef4c3e80cd992f`, with a clean engine and reference. All models use two synthetic counters and a uniform scalar draw. Each standalone sample uses the study's selected counter, cutoff, piece budget and actual sample seed.

| Check | Failed | Passed |
| --- | ---: | ---: |
| Direct central selection, ten fixed samples and two-piece control | 9 | 6 |
| `p5/request/0` through `p5/request/299` | 264 | 36 |

The selected counter starts at 7 and at hour 1 becomes 8 if a draw exceeds 0.5. The median stays at 7, which fits one piece. When the incoming configuration selected the other counter, the central report returned two unavailable readings. Full recording exhausted its budget at hour 0, before a sample ran. With the correct central selection, fixed samples 0, 1, 3, 4, 5 and 7 exhausted a one-piece budget in standalone runs. The study gave all ten samples a fresh default budget and reported success for each. The other four standalone samples fit. All ten samples fit the two-piece control. The family varies the counter, threshold, opening and change, initial request, budget, and three sample seeds.
