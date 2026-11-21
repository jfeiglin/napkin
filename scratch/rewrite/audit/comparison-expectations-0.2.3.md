# Comparison expectations for language 0.2.3

The audit baseline is `6202824`. Published commit `677eeba` implements the owner's change 29 ruling. An authored literal contributes zero tolerance floor, even through a named formula or a unit conversion. The numeric band remains `max(rtol, atol_factor) × max(floor, |a|, |b|)`. The default factor in these cases is `1e-9`. The tables give expected results before and after the ruling. [Owner ruling](../PLAN.md#changes-after-g0)

## Changed assertions

In `test_naming_a_formula_preserves_the_guard`, each expected Boolean applies independently to the named stage and the inline stage. [Audit case](cases-5d9409b/test_guards_and_edits.py)

| Guard operand compared with zero | Previous expectation | 0.2.3 expectation | Arithmetic |
| --- | --- | --- | --- |
| `(0.100000024 h + 0 day) - 0.1 h` | False | True | The exact gap is 0.000000024 h. Its band against zero is 2.4e-17 h. |
| `1000000000.00000005 h - 1000000000 h` | True | True | The exact gap is 0.00000005 h. Its band against zero is 5e-17 h. The named reading also retains that gap. |

A further regression names just the first operand of the large subtraction and compares the residual with a declared input of 1e-8 h. The engine previously read zero and returned False in this form. Both spellings now read 5e-8 h and return True, in agreement with the reference interpreter. A vectorized case binds each row to a different named operand and checks that only rows taking the branch resolve its operands. [Literal operand tests](../../../tests/language/test_folded_comparisons.py)

The following six rows of `test_a_mixed_unit_initializer_keeps_its_value_in_a_singleton_range` select the 10 h initializer when their operand exceeds zero. Each row checks the compiled singleton range, the run, and the reference interpreter. [Initializer tests](../../../tests/language/test_folded_comparisons.py)

| Operand | Previous initializer | 0.2.3 initializer | Arithmetic |
| --- | --- | --- | --- |
| `0.00000001 h + 0 day` | 1 h | 10 h | 1e-8 h exceeds its 1e-17 h band. |
| `0 day + 0.00000001 h` | 1 h | 10 h | The reversed sum has the same gap and band. |
| `max(0.00000001 h, 0 day)` | 1 h | 10 h | The maximum is 1e-8 h. |
| `(0.00000001 h + 0 day) if true else (1 h / 0)` | 1 h | 10 h | The selected arm supplies 1e-8 h. The division stays unevaluated. |
| `(0.100000024 h + 0 day) - 0.1 h` | 1 h | 10 h | 2.4e-8 h exceeds its 2.4e-17 h band. |
| `((0.100000024 h + 0 day) if true else this.unused) - 0.1 h` | 1 h | 10 h | The selected arm gives the same 2.4e-8 h difference. |

The remaining three rows still select 10 h. Their exact positive gaps are 0.00000003 h, 0.0000000240001 h, and 0.000000024000000001 h.

`test_literal_gap_uses_the_active_factor_for_scalar_and_array_reads` compares `0.100000024 h + 0 day` directly with `0.1 h`. At factor `1e-9`, its 2.4e-8 h gap exceeds its 1.00000024e-10 h relative band. The final row below repeats the first factor after the evaluation cache was used. [Scalar and array tests](../../../tests/language/test_folded_comparisons.py)

| Factor in evaluation order | Previous result | 0.2.3 result |
| --- | --- | --- |
| 1e-9 | False | True |
| 5e-10 | True | True |
| 1e-9, repeated | False | True |

The replacement factor-sensitivity control compares `1 h + 0 day > 0.999999999 h`. That gap is exactly 1e-9 h. On the same three factors its expected results are False, True, False. At threshold `0.999999998999999999 h`, the gap is 1.000000001e-9 h, strictly outside the closed default band.

The capacity-split trace at hour 1 formerly expected a gap of 5.551115123125783e-17 L/h for the authored sum `0.1 L/h + 0.2 L/h` against a claim of 0.3 L/h. The expected gap is now zero because the literal sum rounds once to 0.3 L/h. An additional control captures the first term as a declared value and computes the capacity from that reading. Its gap remains 5.551115123125783e-17 L/h. Both runs must record the same stage, round, comparison and near-tie. [Capacity-split trace tests](../../../tests/engine/test_near_tie_kinds.py)

## Generated expectations and unit equivalence

The independent scalar walk previously gave every literal a unit-sized floor. It now assigns zero to literal-only expressions, including powers. For example, `1e-300 == 0` becomes False and a membership interval spanning `[1e-300, 0]` is reversed. The independent simulation interpreter separately implements the same rule for literal arithmetic, named or inline formulas, and an empty sum. Captured quantities retain their declared scale. The existing random-expression assertions still compare execution with those independent calculations. [Scalar walk](../../../tests/core/reference.py) · [Reference interpreter](../../../tests/reference/evaluate.py)

The unit-respelling generator now specifies the same physical scale for each named numeric value in both texts, including the squared unit for the square. At 5e-10 L the guard comparing an input with zero reads True with either the default litre scale or an explicit 1000 mL scale. Deliberately giving it the default 1 mL scale yields False. [Unit controls](../../../tests/model/test_units.py)

In the port corpus, respelling both receiving stores as mL also changed the implicit scales of `tap.request`, `ramp.actual_rate`, and their generated inflow fields from 1 L/h to 1 mL/h. The unit transform now respells the move-only stock declarations and all stock initializers, while keeping receiving store declarations in L and explicit pipe capacity literals in L/h. A control compares the canonical scale of every concrete named field across litres, millilitres, text and the builder, including both valve forms and named demands. The expected physical readings are the same. [Generated unit control](../../../tests/engine/test_port_invariance.py)

## Verification

The 400 generated solver unit comparisons now also compare the physical scale of every runtime name across L, mL and kL. Stock and parameter scales are explicit, and the builder fixes the flow unit that supplies implicit endpoint scales. All existing expected readings and failure times were retained. A separate new control compares a 5e-11 L/h reading against zero. With scale 1 L/h the guard stays false, and with scale 1 mL/h it becomes true. The 27 analytical split controls retain the three actual flow units. [Solver unit fixtures](../../../tests/engine/test_published_answers.py)

On the isolated language build `2cc0d0a` (its two patches were published as `677eeba` and `6749516`), the deep selector below passed 74 tests in 3.96 s with 2,223 cases deselected. It exercised 60 event-local settings seeds (12 through 71), ten relation cases covering five magnitudes on the engine and reference interpreter, and four powers. Other selected directories contributed regular coverage.

```sh
PYTHONPATH=. NAPKIN_STORE=off python -m pytest -m deep -q \
  tests/core tests/language tests/model tests/reference \
  tests/engine/test_comparison_bands.py tests/engine/test_reduction_scales.py tests/test_check_evidence.py
```

The earlier audit reported all 44 retained cases passing on `5d9409b`. The linked 31-case bundle covers the newer findings. The earlier repair report identifies the auditor as the holder of the original bundle, and the prior audit names an external `/workspace/napkin-audit-6f297e5` directory for its 27-case predecessor. Searches across the local repository's reachable Git history, ignored worktrees and audit archives, and the remote audit branch listings found the reports and reconstruction tests. The owner waived the candidate rerun of these 44. The reported count of 44 is a historical observation from the audited baseline. [Auditor's 44-case result](readiness-5d9409b.md) · [Earlier repair report](readiness-fixes-8e422da.md) · [External bundle instructions](readiness-6f297e5.md)


## Compiled evidence and cache identity

- `tests/program/test_artifact.py` now requires format 4 (previously 3) and language 0.2.3 (previously 0.2.2). Scoped evidence adds a field to the wire format. The language change identifies the corrected comparisons. Loading a file with either older header must produce the existing recompile diagnostic.
- `tests/test_api.py::test_the_run_store_reads_the_same_engine_files_as_before_the_api` now includes `engine/continuous/transfers.py`. Its accepted-prefix arithmetic affects the physical record and changes to the file must invalidate a cached run.
