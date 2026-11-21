# Regular and deep test coverage

The four-worker regular run on `d83a7dd` took 191.340 seconds. It passed 11,625 tests and had one platform skip. Two changes address the 180-second budget.

The independent interpreter reuses the SciPy result for an identical small linear program. The input includes the ordered objective, inequalities, equalities and their right-hand sides. Every unknown has free bounds and the same HiGHS method. The interpreter still assembles each new model and checks its ranks, state, edits and reads. Two regular controls exercise the numerical inputs and compare cached and uncached observations across an edit. A fixed four-seed sample across nine test families measured 1,007 hits and 674 misses. Extrapolating those sample differences to those families gives roughly 34 worker-seconds. The complete-suite clock measures the actual effect. [Oracle implementation](../../../tests/reference/order.py) · [Cache isolation and parity](../../../tests/reference/test_numeric_lp_reuse.py)

Seven combinations introduced during this refactor run in the deep tier. All 39 original node IDs in the two affected tests remain selectable, with 32 in regular and seven in deep. All assertions and inputs are identical. The table gives the exact parameter suffix and the worker time in the `d83a7dd` regular JUnit.

| Test | Parameter suffix | Seconds |
|---|---|---:|
| Capacity | `saturated-at-contact-moving_declared-equation` | 7.589 |
| Capacity | `saturated-at-contact-moving_declared-inflow` | 7.823 |
| Capacity | `saturated-at-contact-moving_declared-outflow` | 7.771 |
| Frozen | `above-MovingDeclared-False` | 3.453 |
| Frozen | `below-MovingDeclared-False` | 3.392 |
| Frozen | `below-MovingDeclared-True` | 2.695 |
| Frozen | `equal-MovingDeclared-True` | 2.668 |

Capacity refers to `test_a_grouped_transfer_respects_the_cap_at_contact_and_the_accepted_prefix`. Regular exercises a saturated pipe on all three moving methods, saturated inflow and outflow on Sparse, and every eligible cap location and declared inequality under limited and sufficient headroom. Each case compares uninterrupted execution, an empty stage and checkpoint restoration. The separate rising-cap matrix also checks the exhausted declared inequality in both continuous and restored runs. [Moving-cap history](../../../tests/engine/test_capacity_headroom_history.py) · [Rising-cap controls](../../../tests/engine/test_moving_placement_capacity.py)

Frozen refers to `test_numerical_leg_respects_the_exact_residual_allowance`. Regular exercises the reciprocal below, equal to and above its allowance on Component and Sparse. Sparse also covers all three with the additional held leg. MovingDeclared exercises the reciprocal at equality and the mixed-leg failure one float above equality. The separate mixed-integral fixture runs all three allowance edges on each of five eligible methods, including MovingDeclared. [Reciprocal controls](../../../tests/engine/test_frozen_numerical_prefix.py) · [Mixed-integral controls](../../../tests/engine/test_frozen_mixed_integrals.py)

The seven cases took 35.391 worker-seconds in total. The generated suite continues to exercise 300 rotated comparisons in regular and 16,000 comparisons over 2,000 seeds in deep.
