# Readiness findings at 8e422da

Implementation commit `f5ba7db` on `codex/readiness-audit-8e422da` branches from `8e422da` on `claude/blissful-heisenberg-5me2hn`.

The reproductions below were written against the audit descriptions. Expected values come from the declared models, arithmetic, or the reporting rules. The original audit bundle is held by the auditor.

## 1. An unrelated moment and the pump

In `tests/engine/test_audit_switch_departure.py`, the driver starts empty and fills at `2t` L/h. Its level is `t²` L, so it is positive throughout the open interval from 0 to 1 h. An unrestricted 1 L/h pump delivers 0.5 L by the half hour and 1 L by the hour. The baseline reported a 1 L/h request at 0.5 h while delivering zero. Inserting an empty stage at 0.25 h changed the final delivery to 0.75 L on Component. All six combinations of split/unsplit and Component/Sparse/MovingDeclared failed. A truly stationary driver delivered zero on all three.

With a fourth-order driver the baseline delivered zero at 0.5 and 1 h. Splitting a squared-distance tangent at its minimum changed the baseline delivery from 1 L to 0.5 L. With both operands accelerating, the baseline exhausted a 4,000-evaluation budget trying to re-locate a crossing near the beginning of the hour. The fixed quadratic and cubic examples each deliver 1 L.

The first derivative alone could not distinguish staying on the threshold from leaving with zero initial velocity. The shared departure calculation follows the outgoing field when the first derivative is inconclusive. The tests include a chain of initially stationary stores, a small departure from a nonzero inventory, and a squared distance that touches zero then stays positive. The clock-model generator also inserts an unrelated empty event drawn from an independent random stream and compares the existing model’s readings and stopping outcome.

## 2. Settings on an event-local declaration

`tests/language/test_event_local_settings.py` runs both source text and Builder programs. On the baseline the parsed stock drained from 10 L to 8 L and 6 L. With its declared 0.5 L/h outlet it holds 9.5 L and 9 L after one and two hours. A pipe created without a cap should run at 2 L/h for the first hour and 0.5 L/h after the cap is set. Both authoring paths raised `NameError: inf` when the occurrence started.

A value declared inside an event now passes through the same endpoint-declaration completion as an entity value, with the event’s own scope. Plain settings capture values available at their place in entry order. Retained formulas can read later locals. An unbounded initial capacity follows the ordinary initializer path in both setup and occurrence entry. Named controls cover references to the store itself, a priority naming a later pipe, a forward reference in a plain setting that must be refused, and both request and capacity. The generated cases move configured tanks from the existing tank generator into an occurrence and check the hand-worked rates through the text and Builder paths and the interpreter.

## 3. Conservation across transfers and time cuts

`tests/engine/test_mixed_inventory.py` covers both forms of this finding.

- Deposit 0.05 L into 4,000,000 L, remove the principal, refund 0.05 L. The baseline refused the refund at 3 h with a shortfall of 1.86265 × 10⁻¹⁰ L.
- A rounding allowance in the fit check alone cannot recover repeated deposits. After 1,000 deposits of 0.001 L and repayment of 1 L, the baseline allowed another withdrawal of 10⁻⁷ L. After 100 deposits of 0.05 L it refused the 5 L refund, short by 1.86265 × 10⁻⁸ L. These are opposite directions of drift from the same arithmetic.
- The move keeps the signed remainder when it publishes an inventory as a float. Both ends use the same applied quantity. It reuses the existing transaction and checkpoint map and stores an entry only when a remainder exists. The tests exercise fresh and in-place resume, an explicit edit, rollback of a failed stage, continuous inflow, and reaching a physical bound. In the 10-million-litre continuous case an intermediate implementation lost 3 × 10⁻¹⁰ L. The generated round models deposit and recover millilitres in a stock temporarily holding thousands to ten million litres. Baseline seed 5 failed the hand-worked balance.
- The central move-series property found that evaluating each share of a balance in binary before booking it could still reject the last share (seeds 1 and 2). A move now evaluates rational arithmetic on its captured reads and uses the run’s ordinary branch decisions and active comparison tolerance. The existing property’s expectations stayed in place. Ten moves of 0.014 L from 0.14 L exercise the same rule by hand.
- A retired stock with a 0.1 L allowance can receive 0.02 L/h for five hours. On the baseline an empty stage at 1.6 h produced a frozen-stock failure exactly at 6 h. A linear ramp with the same total also failed when split. The tests cover equality and values on either side of the allowance, including a scale of 0.071 L. Incoming and outgoing material are counted separately. Constant rates use exact differences of times. An unrestricted time-polynomial rate on an installed branch uses differences of its exact antiderivative. Other curved and allocated rates are measured on the trajectory and accumulated before the final comparison. The quadrature error estimate adds no inventory allowance. An intermediate numerical implementation accepted the next float above the permitted quadratic mean for some cuts. The two adjacent floats and exact equality agree with the hand integral at all 49 tenth-hour split placements between retirement and the horizon (147 checks).

## 4. The meaning of a compiled expression

`test_two_spellings_of_one_input_refuse_the_lag_of_a_falling_clock` in `tests/engine/test_record_claims.py` reads 0, −1 and −2 h. The baseline certified the clock and applied a lag when one input was written as both `this.x` and `w.x`. The proof evaluator now resolves both spellings to the same input before combining the terms that determine the comparison floor. Distinct members with the same numeric value keep their own identity. The existing gated-plant generator exercises the spelling change. Four of its eight central seeds previously changed the lag decision.

In `tests/language/test_folded_comparisons.py`, `0.00000001 h + 0 day` has a floor of 24 h. Its 10⁻⁸ h value is within the comparison band of zero, giving the initializer 1 h. The baseline compiler folded it to 10 h and rejected the singleton range [1 h, 1 h], even though the engine produced 1 h. The interpreter’s constant arithmetic also returned 10 h. Folding follows the operand scales, including both terms of a sum, through the shared operation rules. Tests cover reversed operand order, a maximum, a lazy conditional and a value outside the band. On the exact edge, the compiler’s rational fold and the runtime’s binary subtraction previously chose opposite branches. The scalar and array evaluators now use the same exact fold for decidable literal comparisons. Tests distinguish a value exactly on the edge from one beyond it in the eighteenth decimal place. They also exercise a changed tolerance and an unused conditional arm. The artifact encodes an exact decimal with its existing quotient of integer literals.

## 5. Checking a cited datum

`test_ninety_nine_hours_cannot_cite_thirty_four_gallons_per_year` and `test_an_unresolvable_cited_unit_names_the_value_claim_and_datum` in `tests/test_check_evidence.py` reproduce the silent pass. On the baseline, the evidence gate produced no diagnostic for the 99 h choice or for an unresolved datum unit. For a library datum the registry now supplies the declared dimension and exact scale of the complete spelling, including a registered quotient whose component names are absent. A comparison that cannot resolve the unit identifies the choice, claim, datum and unit.

All 825 numeric catalogue datums resolved. For the six affected citations I read the value and unit from the legacy model declaration and the referenced datum from its evidence file. I passed each through the rewrite’s evidence gate using its registered dimensions and exact scale. Each passed as written and each was refused with one added to its number.

| Model | Claim | Datum | Authored value |
|---|---|---|---|
| Heat wave blackout | E-ICE2-COSTS | residential_24h | 56.66 USD2025/customer |
| Heat wave blackout | E-ICE2-COSTS | nonresidential_24h | 13,878 USD2025/customer |
| Auburn | E-SC43-AUBURN-AUBURN-SOURCE-CAPACITY | own_source_capacity | 12,055 gal/min |
| Auburn | E-SC43-AUBURN-AUBURN-PURCHASES | purchases_after_2016 | 0 Mgal/yr |
| Austin | E-SC43-AUSTIN-AUSTIN-WATER-SUPPLY | purchased_imported_2023 | 0 gal/yr |
| Cape May | E-SC43-CAPEMAY-CAPE-MAY-NJDEP | contract_limit | 0 Mgal/yr |

## 6. Evidence through a collection

`tests/engine/test_collection_evidence.py` runs each case with a full record and a selected record. A sum of one occurrence credits the same measurement as reading its field directly. Switching a sourced eligibility flag takes a filtered total from 2 to 11 L. Changing a sourced lookup cutoff takes the result from 2 to 9 L. The consulted eligibility fields, cutoff, index and selected measurements receive credit. A composed lookup checks which predicates and branches actually ran. All twelve cases failed on the baseline. The report could omit an occurrence’s measurement or the evidence deciding membership and lookup, even when it displayed the right number.

The proof walk follows collection selectors in their evaluation scopes and occurrence fields on their owners. Reusing a filter’s cached result also reuses its actual consulted fields, so a later reading credits the same evidence.

## Existing expectations

`tests/test_api.py::test_the_run_store_reads_the_same_engine_files_as_before_the_api` now includes `core/literals.py` in the source files hashed by the run store. Both compilation and runtime evaluation depend on this module, so changing its rules must invalidate old cached results.

`tests/engine/test_report_chains.py::test_a_chain_of_named_collections_is_lagged_and_traced_without_recursion` now expects `Tank.rank` in the exercised evidence for both request types and both depths. Every filter in the chain reads the rank to decide membership. The existing expected value of 2 L and lagged value of 1.25 L are unchanged.

`tests/program/test_artifact.py::test_old_language_artifact_requires_recompilation` now requires recompilation of language 0.2.1 artifacts and accepts language 0.2.2. The baseline loaded the old header. The artifact format stays at 3. The language version identifies the corrected evaluation semantics. The existing random generators keep their original models for the same seeds when their new transforms are off.

## Validation

The central suite (`-m "not deep" tests`) passed **10,546** tests in 158.48 s on macOS. Its one platform skip reads Linux process state through `/proc`. The whole deep suite (`-m deep tests`) passed **23,743** tests in 764.67 s, including all the new random transforms. Every named reproduction passed. Ruff lint and format checks passed across `napkin tests tools`.

The three alternating, paired executions of `scratch/rewrite/b1/s5-engine/bench.py 3000 3500 1500` used the same machine, virtual environment and single-threaded BLAS configuration. Times below include model construction, planning, and running with recording.

| Pair | 8e422da total (s) | f5ba7db total (s) | Final / baseline |
|---|---:|---:|---:|
| 1 | 9.1901 | 9.2140 | 1.0026 |
| 2 | 9.3065 | 9.2611 | 0.9951 |
| 3 | 9.3305 | 9.3240 | 0.9993 |

The median paired total-time ratio was **0.9993** against the 1.05 limit. Median phase ratios were 1.0119 for model construction, 0.9992 for planning and 0.9995 for running and recording. All six executions produced 3,163.7587 W at 0 h, 3,083.5128 W at 48 h and the same two solves.

Against `8e422da`, `napkin/engine` changed by **+225 net lines** (310 added, 85 removed over seven files). The full `napkin` package changed by +442 net lines (762 added, 320 removed), and tests by +975 net lines (983 added, eight removed). Counts use `git diff --numstat` on the implementation commit `f5ba7db`.
