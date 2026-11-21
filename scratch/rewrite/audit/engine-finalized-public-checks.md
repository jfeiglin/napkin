# Public execution and migration checks

Candidate `caecf1003c980821a235f264bd10c23d052734e1` passed the public CLI, artifact-only and migration checks against legacy `8488047dbb7eafee1f5582cf59839c6bea0cf8cd`. The migration harness exported both commits and ran each engine in its own process. The piano and reservoir translations used here match the audited `6202824` baseline.

## Current audit and valve results

All 31 audit cases passed. Both the day/hour literal and large-offset guard ran in their named and inline forms. Six additional comparisons forced both valve forms through Component, Sparse and the moving declared solver against the reference interpreter. Each went from 0 to 1 L/h across the opening and delivered 0.5 L at 1 h and 1.5 L at 2 h within the test tolerance. [Audit case results](engine-finalized-audit-cases.csv) · [Valve comparisons](../../../tests/engine/test_valve_allocation.py)

The two valve forms gave identical readings within each method. The opening rates and terminal balances below are the values returned by the engine.

| Valve forms | Method | Rate at 0.49 h (L/h) | Rate at 0.51 h (L/h) | Delivered at 1 h (L) | Delivered at 2 h (L) |
| --- | --- | ---: | ---: | ---: | ---: |
| Explicit pipe capacity and inline `min` | Component and Sparse | 0 | 1 | 0.49999999999999956 | 1.4999999999999984 |
| Explicit pipe capacity and inline `min` | Moving declared solver | 0 | 1 | 0.4999999999999999 | 1.4999999999999996 |
| Explicit pipe capacity and inline `min` | Exact reference | 0 | 1 | 0.5 | 1.5 |

The direct CLI returned the following readings from the audited capacity-valve scenario. It exited 0 with a warning about one value lacking an evidence record.

| Time (h) | Request (L/h) | Capacity (L/h) | Actual (L/h) | Delivered (L) |
| ---: | ---: | ---: | ---: | ---: |
| 0.499 | 0 | 1 | 0 | 0 |
| 0.501 | 2 | 1 | 1 | 0.0010000000000000406 |
| 1 | 2 | 1 | 1 | 0.49999999999999956 |
| 2 | 2 | 1 | 1 | 1.4999999999999984 |

## Public CLI and artifacts

All 242 tests across the commands suite, artifact format, and source/artifact evidence passed. They cover selective histories, cache hits, reordered queries, historical occurrence reads, and the recompile diagnostic for older artifacts. A separate consumer process with only `meters.program` in its working directory read **5 L at 1 h** and returned both source records, `north_meter` (“Northern meter.”) and `south_meter` (“Southern meter.”). The artifact header identifies format 4 and language 0.2.3. [Artifact evidence tests](../../../tests/engine/test_artifact_evidence.py) · [Format tests](../../../tests/program/test_artifact.py)

Public piano compilation and execution both exited 0 with empty diagnostics. The median run reported `tunings_done` of 0, 1461.7687436962908 and 2923.5374873925816 tunings at 0, 4380 and 8760 h.

## Migration comparisons

The median checker accepted both models, including their intermediate readings and terminal outcomes. Piano used `examples/piano_tuners/model.scn` in both versions. Reservoir used legacy `examples/reservoir/model.scn` and candidate `scratch/rewrite/a5/translated/now/examples/reservoir/model.scn`. Each numerical comparison uses the larger of an absolute tolerance of 1e-8 in the stated unit and a relative tolerance of 1e-6. [Checker](../a5/check.py) · [Paired comparison harness](../a5/paired_migrations.py)

With the default reservoir inputs, the public CLI reported water fractions of 0.60, 0.66, 0.70, 0.625, 0.55, 0.49 and 0.40 at 0, 24, 40, 60, 80, 96 and 120 h. Cumulative spill reached 0.50 by 120 h, and risk duration stayed at zero throughout. These values are rounded for display.

| Comparison | Coverage | Maximum absolute legacy–candidate difference |
| --- | --- | --- |
| Piano, 12 distinct legacy productivity draws (seeds 0–11) | At 0, 4380 and 8760 h, 144 comparisons of productivity, due, completed and published totals. Another 24 compare the candidate's actual rate to the legacy balance change over each half-year. | 2.274e-13 tunings/tuner/year in productivity, 6.821e-13 tunings due, 9.095e-13 tunings completed or published, 1.110e-16 tunings/h in realized rate |
| Reservoir, 12 input configurations | At 0, 24, 40, 60, 80, 96 and 120 h, 252 comparisons of water, cumulative spill and risk duration. Inflow was 0.03 or 0.06 fraction/day, spillway was 0.06 or 0.15 fraction/day and risk threshold was 0.6, 0.7 or 0.8 fraction. | 3.331e-16 fraction for water, 7.216e-16 fraction for spill, 5.544e-8 h for risk duration |

The compressed CSV retains all 432 rows with the exact exported readings, including the realized productivity or reservoir inputs, time, unit and analytical expectation. All 252 reservoir rows and 168 piano rows have direct legacy comparisons. The other 12 rows are the candidate's initial piano rates, checked against the analytical rate before the first legacy interval-rate reading. The compressed observations from this run were byte-identical to those from `fc9a9ed`, with SHA-256 `c0861524444e258a9ea171cdbd6176629e951a4b3b6ebafdc85ba89ada718f26`. [Paired and analytical readings](engine-finalized-migration-readings.csv.gz)

Every paired run reached its horizon. Each version also agreed with the analytical solution for each paired input. The candidate's maximum deviations for reservoir water, spill and risk duration were 4.441e-16 fraction, 7.355e-16 fraction and 8.527e-14 h. An independent 24-case suite passed using the candidate sampler's own 12 piano draws and the full analytical reservoir sweep. [Independent analytical tests](../a5/test_port_readiness.py)

Both negative controls exited 1. The wrong output reported 0 tunings against 2923.537487 at 8760 h. The outcome control matched the numeric output but failed the final stage at 8760 h when a move of two tunings exceeded a one-tuning destination capacity. The checker identified the failed terminal outcome. [Wrong output](../a5/translated/wrong/piano_tuners_run/model.scn) · [Horizon failure](../a5/translated/wrong/piano_tuners_outcome/model.scn)

## Reproduction

Run from the candidate checkout with its project environment.

```sh
export PYTHONPATH=. NAPKIN_STORE=off
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
python -m pytest -q -p no:cacheprovider tests/commands tests/program/test_artifact.py \
    tests/engine/test_artifact_evidence.py tests/engine/test_port_occurrence_evidence.py
python -m pytest -q -p no:cacheprovider scratch/rewrite/audit/cases-5d9409b \
    tests/engine/test_valve_allocation.py::test_a_valve_opening_across_its_capacity
python -m napkin run scratch/rewrite/audit/cases-5d9409b/valve --at 0.499h,0.501h,1h,2h \
    --value plant.tap.request,plant.tap.capacity,plant.tap.actual_rate,plant.water --json
python -m napkin compile examples/piano_tuners --json
python -m napkin run examples/piano_tuners --value tunings_done --at 0h,4380h,8760h --json
python -m napkin run scratch/rewrite/a5/translated/now/examples/reservoir --at 0h,24h,40h,60h,80h,96h,120h \
    --value reservoir.water,reservoir.spilled,reservoir.risk_time --json
python scratch/rewrite/a5/paired_migrations.py --candidate caecf1003c980821a235f264bd10c23d052734e1
```
