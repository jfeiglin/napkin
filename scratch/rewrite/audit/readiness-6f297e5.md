# Napkin scenario-port readiness audit

The reviewed branch is `claude/blissful-heisenberg-5me2hn` at `6f297e56718dfd5885abd661c3f92c15bd708f02`. The previous audit used `8b3a01a`. The migration checker compares against the pre-rewrite engine at `8488047dbb7eafee1f5582cf59839c6bea0cf8cd`.

## Porting decision

The default piano and reservoir comparisons pass. A supported reservoir configuration loses 80 hours of reported risk. That gives the first planned port a concrete acceptance blocker. The finished-occurrence and solver cases below also produce successful runs with incorrect inventory. Source translation and inspection can proceed independently. Scenario results, interactive replay and published evidence need their respective checks before acceptance.

## Reproductions

Run these external tests from the reviewed checkout using its development environment. Replace the directory argument if the bundle was extracted elsewhere.

```sh
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 NAPKIN_STORE=off .venv/bin/python -B -m pytest -p no:cacheprovider --tb=short -q /workspace/napkin-audit-6f297e5
```

The assertions express the expected result. A failure reproduces the finding. The reservoir test loads the draft already present in the checkout. Evidence fixtures and cache tests work in private temporary directories. No scenario port is needed to run any case.

| Finding | Expected and observed | Where to look in the checkout |
|---|---|---|
| Reservoir at the risk threshold | Start at 0.6. Take in 0.06 of capacity per day. Open at 0.7 and release 0.06 per day. At hour 40 the level reaches 0.7 and stays there. The model uses `water >= risk`, so it should count the final 80 h. Old engine 80.0000000055 h. New engine 0 h at maximum steps of 1 h and 0.15 h. Its trace opens the gate at 39.9999999653 h and its water then holds near 0.69999999991. The tally stays off and the report contains no near-tie entry. Eleven of twelve hand-calculated reservoir input combinations passed for remaining water, cumulative spill and hours at risk. | `test_reservoir.py`, `scratch/rewrite/a5/translated/now/examples/reservoir/model.scn:38` and `:50` |
| Writes after an occurrence finishes | A stock retired empty at 0.5 h. A later 0.02 L/h flow added 20 L. Separately, 100 moves of 0.02 L added 2 L. The large declared upper bound of 1 billion L gives this stock a 0.1 L tolerance. An amount tolerance applied separately to each move or to a rate cannot guarantee that the frozen amount stays fixed. The handoff explicitly requires a named failure for any nonzero transfer. | `test_frozen.py`, `napkin/engine/timeline/occurrences.py:374` and `:404` |
| Solver transfers inventory on an idle route | A supply asks for 30 million L/h and is capped at 10 million L/h. The shortfall is identical under either route choice. The solver finds a zero rate for the idle route. When the engine publishes the answer, it permits 1 L/h, and the sending stock falls from 10 to 9 L in one hour. The same arithmetic reproduces with a 30 MW request, a 10 MW cap and 1 W on the idle route. | `test_distance.py`, `napkin/engine/solve/solver.py:339` |
| Reporting a capacity first set during a run | An unbounded drain serves 2 L/h. At hour 1 an event sets its cap to 1 L/h and the actual flow correctly falls to 1 L/h. At hour 2 the Python report says the capacity is infinite, CLI text displays zero, and JSON raises an exception. The same case reproduces for an endpoint. A declared initial capacity of 5 L/h changed to 1 L/h records correctly. | `test_capacity.py`, `scratch/rewrite/HANDOFF.md:183`, `napkin/engine/timeline/record.py:194` |
| Cached replay accepts the wrong breakpoint time | Record the same edit at hour 2 and hour 3 using two different inputs. Replaying the hour-3 log against the hour-2 configuration correctly fails on an empty cache. Prime the cache with the valid hour-2 replay and the invalid hour-3 replay returns success. This matters for the interactive water scenario. | `test_cache.py`, `napkin/store.py:401`, `napkin/session.py:234` |
| Provider cannot allocate two boundary flows | The language permits `SOURCE -> SINK` with a unit-bearing rate. Each of two flows requests 6 L/h and the provider's solver names both rates and caps their sum at 8 L/h. The expected result is 4 L/h each. The model compiles, then the engine refuses the first rate when constructing the run. | `test_boundary.py`, `scratch/rewrite/spec.md:254`, `napkin/engine/timeline/plan.py:1446` |
| Occurrence lifecycle fields fail direct reporting | Direct reads of `.started`, `.active` and `.done` give the expected values, but `.started` loses its hour unit. Reporting any of the three, including from the CLI, raises `KeyError`. A named model formula reading the start time reports 1.5 h correctly. | `test_builtins.py`, `napkin/engine/timeline/record.py:964`, `napkin/engine/report.py:413` |
| Frozen formula loses evidence | An occurrence's formula reads a measured 1 L input. The report still shows 1 L at and after completion, but its evidence changes from reached to possible, with a message saying the report holds no value there. | `test_evidence.py`, `napkin/engine/timeline/record.py:1343`, `napkin/engine/report.py:451` |
| Exact decimal evidence in JSON | Given the JSON datum 34.0000000000000001 h, the evidence gate accepts 34 h and rejects the exact value as unequal. Model-source decimal handling passed. The JSON reader rounds the claim before comparison. None of the 825 numeric claim datums inspected in the committed catalogue loses digits in this way. | `test_evidence.py`, `napkin/model/load.py:36`, `napkin/model/support.py:218` |

## Checker and test results

- The external regression bundle gives 16 failures and 11 passes on this commit. Ten passes are the prior regressions and the eleventh is the initially finite capacity control. Several failures test the same defect through different paths.
- The migration checker’s 14 outcome tests passed. It accepted the default piano at 0, 4380 and 8760 h and the default reservoir at 0, 24, 40, 60, 96 and 120 h. It rejected a piano that silently zeroed its tunings and a run that failed at its horizon despite preserving its numeric output.
- Ruff check and format check passed for `napkin/`, `tests/` and `tools/`.

## Fixes verified

- All ten public regression cases from `8b3a01a` now pass. The previous simple idle-route case, normal-sized frozen-stock transfer, escaping event formula, report-order dependence, root collection reduction, reversed stage interval, long lag chain, constant-expression evidence and short-budget cache cases are covered in `test_previous.py`.
- The model grammar rejects former entity, template, member, event and case role declarations. The translator puts actor metadata in `roles.toml` and diagram roles in `style.toml`. The starter generated a model and stylesheet that compiled, ran and drew a diagram. Adapting the catalogue publisher and water UI to those files belongs to the port.
- The round rule works in local and declared sharing. Two overlapping flows went from 4/0 to 2/2 to 0/4 L/h. A stage could read the incoming allocation, and an `after 0 h` stage saw the next allocation at the same clock time. Saved checkpoints reproduced the overlap results.
- Unedited run-cache reuse respects horizon, history selection, and history budget. Changing only key order reuses the cache and reports the caller's order. The previous exhausted-budget case now returns a terminal failure before handing out a later breakpoint.
- Top-level collection aliases, 300- and 1,100-link formula chains with reporting lag, endpoint rates, distribution moments and declared solver values agreed between direct reads and reports in the exercised cases. A runtime-reversed interval in a solver stopped at the relevant moment.
- Text near-tie reporting grouped the five most frequent source/kind pairs and reported the omitted count. JSON retained all nine individual records in the test. The handoff separately documents a deferred case for a service split decided between moments.

## Secondary limitations

- Compiled programs still declare language version `0.1.0` across the change to round semantics. An artifact compiled once at `e529a1f` failed at hour 1 on that version for reading a rate in the same stage as a request change. Identical bytes loaded at `6f297e5` ran through hour 3 and correctly returned the incoming 2 L/h and next-round 6 L/h. The header does not distinguish those meanings, contrary to `napkin/program/artifact.py:31`. This concerns reuse of prerelease binaries. A freshly compiled scenario on this commit has the agreed semantics.

- A one-piece history budget correctly reports exhaustion at hour 1, yet the engine processes all ten hours of scheduled moments before returning it. This is a work/resource issue. `history_budget_work.py` shows both the public stop time and the moments the engine processed.
- The public `load_scenario` example passes a folder. It raises `IsADirectoryError`, although the entry filename and CLI directory path work. The starter points to the old language guide that still teaches model roles. A backslash in a starter title also exposes escaping trouble, and a file occupying the requested `variants` directory can leave a partially written starter. These affect author onboarding.
- The checked-in migration drafts for IV, heat, cyber and the water variants still have name, unit or endpoint diagnostics. They are inputs to the planned translation work. This audit compiled the existing drafts and did not translate them or run those catalogue scenarios end to end.
