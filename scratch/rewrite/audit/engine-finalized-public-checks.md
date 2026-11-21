# Public execution and migration checks

Candidate `89bda575521c9d88c20d9f05f3e6caeb55571374` passed the public CLI, artifact-only and migration checks against legacy `8488047dbb7eafee1f5582cf59839c6bea0cf8cd`. The migration harness exported both commits and ran each engine in its own process. The piano and reservoir translations used here match the audited `6202824` baseline.

## Public CLI and artifacts

All 242 tests across the commands suite, artifact format, and source/artifact evidence passed. They cover selective histories, cache hits, reordered queries, historical occurrence reads, and the recompile diagnostic for older artifacts. A separate consumer process with only `meters.program` in its working directory read **5 L at 1 h** and returned both source records, `north_meter` (“Northern meter.”) and `south_meter` (“Southern meter.”). The artifact header identifies format 4 and language 0.2.3. [Artifact evidence tests](../../../tests/engine/test_artifact_evidence.py) · [Format tests](../../../tests/program/test_artifact.py)

Public piano compilation and execution both exited 0 with empty diagnostics. The median run reported `tunings_done` of 0, 1461.7687436962908 and 2923.5374873925816 tunings at 0, 4380 and 8760 h.

## Migration comparisons

The median checker accepted both models, including their intermediate readings and terminal outcomes. Piano used `examples/piano_tuners/model.scn` in both versions. Reservoir used legacy `examples/reservoir/model.scn` and candidate `scratch/rewrite/a5/translated/now/examples/reservoir/model.scn`. Each numerical comparison uses the larger of an absolute tolerance of 1e-8 in the stated unit and a relative tolerance of 1e-6. [Checker](../a5/check.py) · [Paired comparison harness](../a5/paired_migrations.py)

| Comparison | Coverage | Maximum absolute legacy–candidate difference |
| --- | --- | --- |
| Piano, 12 distinct legacy productivity draws (seeds 0–11) | At 0, 4380 and 8760 h, 144 comparisons of productivity, due, completed and published totals. Another 24 compare the candidate's actual rate to the legacy balance change over each half-year. | 2.274e-13 tunings/tuner/year in productivity, 6.821e-13 tunings due, 9.095e-13 tunings completed or published, 1.110e-16 tunings/h in realized rate |
| Reservoir, 12 input configurations | At 0, 24, 40, 60, 80, 96 and 120 h, 252 comparisons of water, cumulative spill and risk duration. Inflow was 0.03 or 0.06 fraction/day, spillway was 0.06 or 0.15 fraction/day and risk threshold was 0.6, 0.7 or 0.8 fraction. | 3.331e-16 fraction for water, 7.216e-16 fraction for spill, 5.544e-8 h for risk duration |

Every paired run reached its horizon. Each version also agreed with the analytical solution for each paired input. The candidate's maximum deviations for reservoir water, spill and risk duration were 4.441e-16 fraction, 7.355e-16 fraction and 8.527e-14 h. An independent 24-case suite passed using the candidate sampler's own 12 piano draws and the full analytical reservoir sweep. [Independent analytical tests](../a5/test_port_readiness.py)

Both negative controls exited 1. The wrong output reported 0 tunings against 2923.537487 at 8760 h. The outcome control matched the numeric output but failed the final stage at 8760 h when a move of two tunings exceeded a one-tuning destination capacity. The checker identified the failed terminal outcome. [Wrong output](../a5/translated/wrong/piano_tuners_run/model.scn) · [Horizon failure](../a5/translated/wrong/piano_tuners_outcome/model.scn)

## Reproduction

Run from the candidate checkout with its project environment.

```sh
export PYTHONPATH=. NAPKIN_STORE=off
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
python -m pytest -q -p no:cacheprovider tests/commands tests/program/test_artifact.py \
    tests/engine/test_artifact_evidence.py tests/engine/test_port_occurrence_evidence.py
python -m napkin compile examples/piano_tuners --json
python -m napkin run examples/piano_tuners --value tunings_done --at 0h,4380h,8760h --json
python scratch/rewrite/a5/paired_migrations.py --candidate 89bda575521c9d88c20d9f05f3e6caeb55571374
```
