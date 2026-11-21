# Paired migration results at 31b07b0

Piano and reservoir passed against legacy `8488047dbb7eafee1f5582cf59839c6bea0cf8cd` on candidate `31b07b0b11502e9ae43c1a944a8983975d37920d`. All runs finished at their horizons. The standard migration checker also passed both median models at their intermediate times and rejected both negative controls. Both checkers use `max(1e-8, 1e-6 × max(|old|, |new|))` in the compared quantity's unit. [Paired harness](../a5/paired_migrations.py) · [Migration checker](../a5/check.py)

## Piano

For each seed from 0 through 11, the legacy sampler drew one productivity from the authored PERT distribution in `examples/piano_tuners/model.scn`. The candidate ran its `examples/piano_tuners/model.scn` in sampled mode with the same realized input in tunings per tuner-year. All 12 draws were distinct. At 0, 4,380 and 8,760 h the model versions agreed exactly on productivity, tunings due, tunings completed and the public `tunings_done` output. The candidate's actual tuning rate in tunings/h also agreed exactly with the realized rate calculated from the legacy change in completed tunings over each half-year. That gives 144 point comparisons and 24 interval-rate comparisons. The largest difference from the closed-form result across either version's completed or due balances was 4.55e-13 tunings.

The independent candidate tests separately drew from the candidate's own sampler for the same 12 seeds and compared its stock levels, public output and actual rate against each draw's closed form. [Independent controls](../a5/test_port_readiness.py)

## Reservoir

The legacy entry was `examples/reservoir/model.scn`. The candidate entry was `scratch/rewrite/a5/translated/now/examples/reservoir/model.scn`. The sweep combined inflows of 0.03 and 0.06 fraction/day, spillway rates of 0.06 and 0.15 fraction/day, and risk thresholds of 0.6, 0.7 and 0.8 fraction. Both engines accepted all 12 combinations. At 0, 24, 40, 60, 80, 96 and 120 h, all 252 paired comparisons passed, covering both gate-opening times. Water and cumulative spill followed the two piecewise-linear segments, and risk time equaled their combined duration at or above the threshold.

| Maximum absolute difference | Legacy versus candidate | Legacy versus analytical | Candidate versus analytical |
| --- | ---: | ---: | ---: |
| Water, fraction of capacity | 6.11e-16 | 4.44e-16 | 6.66e-16 |
| Spilled, fraction of capacity | 9.44e-16 | 7.22e-16 | 1.03e-15 |
| Risk time, h | 5.54e-8 | 5.54e-8 | 1.42e-13 |

## Negative controls and reproduction

The migration checker returned exit 1 for a piano translation with the wrong final `tunings_done` value. It also returned exit 1 for the fixture whose numeric outputs match but whose run fails at 8,760 h. The separate candidate sampled-piano and analytical-reservoir suite passed all 24 cases. [Wrong-output fixture](../a5/translated/wrong/piano_tuners_run/model.scn) · [Horizon-failure fixture](../a5/translated/wrong/piano_tuners_outcome/model.scn)

The command extracts the two committed versions into temporary directories and starts separate Python processes for them. The final JSON gives the maximum absolute error for each comparison and output in its stated unit.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python \
    scratch/rewrite/a5/paired_migrations.py --candidate 31b07b0
```
