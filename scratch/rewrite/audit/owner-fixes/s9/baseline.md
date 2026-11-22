## S9 dense stock bounds on macOS

At clean engine and reference revision `ca5a6749ffe3c88ea65d8d9a97f3f2d4bccfeaca`, the two families produced 213 failing and 387 passing seed IDs. The [complete baseline](baseline.jsonl.gz) contains the generated source for each unsuccessful variant. The straight-line controls use the exact reference. The continuously varying signed routes use independently integrated, clipped quadratics, including both tanks and the extrema of their recorded pieces.

| Family | Failed IDs | Passed IDs | Observations |
| --- | ---: | ---: | --- |
| Reversible, seeds 0–299 | 199 | 101 | Sparse produced incorrect dense trajectories on 110 plain and 107 empty-event variants. Component stopped 67 plain and 68 empty-event runs. MovingDeclared exhausted the 1,500-trial budget in 6 plain and 5 empty-event runs. The budget counts actual integrated-rate evaluations per spelling and records the last accepted time and stock levels. |
| Simultaneous bounds, seeds 0–299 | 14 | 286 | Every seed exercised Family, Lines and held Declared both with and without an empty event. Of the 43 seeds that also exercised Sparse, 14 violated both stock bounds on the uncut run. Inserting an empty event changed both readings. |

The [original two-tank example](authored-reversible.scn) passed the headline Sparse reads here. In [seed 4](reversible-lower.scn), the second tank instead reached −0.3125 L at 1 h and finished at 0.9375 L instead of 1.25 L. [Seed 2](reversible-upper.scn) exercises an upper bound. The Component equivalent of the original example posts the first 2 L transfer correctly, then produces a negative dense value while the second tank rests on its floor before reversal. [Model](component-first-bound.scn) and [trial and posting trace](component-first-bound.log.gz).

The 12 direct Radau regressions produced ten failures and two passing controls. Both the lower and upper excursions cross at 1/8 and return at 3/16 of a step whose endpoints are inside. Earlier guards and earlier comparison cutoffs correctly won. [Pytest output](radau-baseline.log.gz).

The [source and diagnostics for all 146 stopped or budget-limited variants](stopped-models.jsonl.gz) identify their generated seed, spelling and source digest. All occurred in the reversible family. The simultaneous family completed all of its runs. [Minimized models and their individual outcomes](stops.md).
