# Napkin engine audit at 5d9409b

Tested the remote branch `claude/blissful-heisenberg-5me2hn` at `5d9409bcacf3da6381cd7bdc23c1a934dc583091`. The comparison revision was `8e422da`. The tests run small authored models through the compiler, runner, artifact loader, evidence gate or CLI. Each assertion describes the expected public behavior. Several parameterizations are passing controls.

Run them from the root of the checkout:

```sh
.venv/bin/python -B -m pytest -q tests/audit
```

The smallest hard-cap example is also a standalone scenario in `valve/`:

```sh
.venv/bin/napkin run tests/audit/valve --at 1h,2h \
    --value plant.tap.request,plant.tap.capacity,plant.tap.actual_rate,plant.water
```

The CLI exits successfully and prints these values at the audited tip.

| Value | 1 h | 2 h |
| --- | ---: | ---: |
| Requested, L/h | 2 | 2 |
| Capacity, L/h | 1 | 1 |
| Actual, L/h | 2 | 2 |
| Water, L | 1 | 3 |

At 2 h the pipe has been open for 1.5 hours. Its maximum possible delivery is 1.5 L.

## Flow rates and inventory

- **test_gate_capacity.py** — A 1 L/h pipe receives a 2 L/h request after hour 0.5. It must have delivered 1.5 L at hour 2. The local run delivers 3 L on both revisions and reports a 2 L/h actual rate alongside its 1 L/h capacity. An explicit solver gives 1.5 L. The clock-only example works as expected when the same hard cap is placed on the receiving endpoint. No precision near the switching instant can account for the extra 1.5 L.
- **test_flow_refund.py** — A flow whose rate rises from 0 to 0.1 L/h delivers 0.05 L over one hour. After withdrawing its starting inventory, the pool must be able to refund the donor's loss. At a million litres, an empty event at hour 0.5 decides whether the 0.05 L refund succeeds at the audited tip. Both versions of that model finish on the previous revision. At ten million litres the ramp case already failed on the previous revision. A constant-rate control succeeds. Reassigning that same constant formula at hour 0.25 can make it fail.
- **test_move_all.py** — An event-local store starts at 4,000,000 L and receives another 2/3 L. The documented `move batch from batch to this.bulk` leaves about 1.67e-10 L, preventing the event from finishing. The previous revision emptied the store and completed the event.

## Scenario authoring

- **test_stage_allocation.py** — A stage changes the priority on a stock with two competing requests or restores proportional sharing. All four text models are rejected at compile time. They cover stores on an entity and stores on an occurrence. The repository has a passing builder-level counterpart in `tests/engine/test_occurrences.py`. The specification describes restoring proportional service in `scratch/rewrite/spec.md` and describes allocation changes taking effect when rates are shared again.
- **test_indirect_capacity.py** — One running event sets the capacity of another running event's flow or stock endpoint at hour 1. A shorthand reference fails during setup, and a fully spelled lookup raises an uncaught `Outside` exception. Declaring an initial 5 L/h capacity makes all four controls work. The tank then reads 10, 8 and 7.5 L at 0, 1 and 2 hours.
- **test_guards_and_edits.py**, formula tests — Naming the quantity in a guarded stage flips whether the stage executes. In the day/hour example the inline guard skips and the named guard fires at the audited tip. In the large-offset subtraction example the inline guard fires and the named guard skips. On the previous revision the two spellings agreed in each case. These models use only literal arithmetic, with no moving stock or solver.
- **test_guards_and_edits.py**, CLI tests — With a closed maximum of 9007199254740992, an explicit JSON edit of 9007199254740993 is refused while 9007199254740993.0 is accepted. The same disagreement occurs just above 0.6 between a bare JSON number and a supported quantity string. It occurs on both revisions.

## Evidence

- **test_live_flow_evidence.py** — Two event-owned pipes join and leave a stock. The sum of the requests on its currently connected flows reads 1, 3, 2 and 0 L/h in chronological order. The source for each active request is absent from the sum's evidence trail under both full and selective recording. Reading the individual requests credits their sources.
- **test_compiled_evidence.py** — Two members override a template's meter reading and cite their respective sources. The source-backed total is 5 L and credits both. Changing one source description leaves the compiled artifact, including its side table, byte-identical. A consumer of the compiled file alone cannot recover this member-level citation. The numeric total survives.
- **test_fractional_unit_evidence.py** — A value of 1 in a registered unit and a cited datum of 1 in that same unit are diagnosed as different dimensions when the dimension exponent is 0.1. The 0.5 control passes. Both pass at the previous revision. No current catalogue datum uses fractional dimensions.

On the audited revision, the 31 cases in this bundle yielded 22 failed assertions and nine passing controls. These are independently authored scenarios. The separate migration checks for the piano and reservoir examples passed.
