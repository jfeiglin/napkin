# Readiness audit of `5d9409b`

The auditor's report on `claude/blissful-heisenberg-5me2hn` at `5d9409b`, as the owner received it.
The runnable cases are in `cases-5d9409b/` beside this file (its `README.md` gives each case and the
command that runs them). On `5d9409b` they give 22 failures and 9 passing controls, on macOS and on
Linux.

**I'd hold the broader scenario port.** All **44 cases from the previous audits now pass**, and the
full Linux suites passed **10,547 regular tests and 23,743 deep tests**. I still found a local flow
that silently exceeds its hard capacity and two inventory cases where the latest update changes
whether a run finishes.

## What would block sign-off

| Finding | What was reproduced |
|---|---|
| **A pipe can deliver twice its hard capacity.** | A pipe capped at **1 L/h** starts receiving a **2 L/h** request at hour 0.5. By hour 2 it has delivered **3 L**. The maximum possible is **1.5 L**. `napkin run` exits successfully and prints capacity **1** and actual rate **2** side by side. An explicit solver gives the correct 1.5 L. This also occurred on `8e422da`. |
| **Moving an entire stock can leave the event unable to finish.** | An event starts with 4,000,000 L, receives another ⅔ L, then executes the proposal's own `move batch from batch to this.bulk`. It leaves `1.67e-10 L` behind and fails retirement. The same model emptied the batch and finished on `8e422da`. |
| **An empty event changes whether a refund succeeds.** | A flow transfers **0.05 L** into a million-litre pool. After withdrawing the original million litres, refunding the donor fails. Adding an empty event at hour 0.5 makes the full refund succeed. Both versions finished on `8e422da`. |
| **Naming a formula changes which stage executes.** | With `gap = formula((0.100000024 h + 0 day) - 0.1 h)`, a stage guarded by `this.gap > 0 h` fires. Inlining the identical expression makes it skip. The two spellings agreed on `8e422da`. |
| **Two documented flow controls still fail from scenario text.** | A stage cannot switch an endpoint to `priority(...)` or restore `proportional()`, although the equivalent Python builder case works. Separately, one running event cannot set the first capacity on another occurrence's pipe or endpoint through a reference. Giving it an explicit initial capacity makes the same update work. |

## Evidence and input handling

- **A report can give the right total and lose its sources.** As two event-owned pipes join and
  leave, `sum(stock.outflow.flows.request)` correctly reads **1, 3, 2, 0 L/h**, but credits neither
  pipe's evidence. Reading each request individually credits the right source.
- **A compiled artifact loses citations attached to individual members' field overrides.** A
  source-backed report sums two meters to **5 L** and cites both. Changing one meter's citation
  produces a byte-identical `.napkin` file. A wrapper given only that file cannot recover the
  citation.
- **Two narrower validation issues remain.** An out-of-range JSON input can be accepted when spelled
  `9007199254740993.0` and rejected when spelled `9007199254740993`. The evidence gate also rejects a
  quantity and datum written in the *same unit* when its dimension exponent is `0.1`. None of the 825
  current catalogue datums uses a fractional dimension.

## What held

The piano and reservoir examples held up. Both migration comparisons passed. 12 sampled piano runs
matched their tuning rates and inventory balances, 12 reservoir configurations matched analytical
answers, and the 3,000-place network matched its published totals. The failures above come from
small, independently authored scenarios; no incorrect result was found in either migrated example.

The auditor's recommendation: keep piano and reservoir as accepted examples, and use **hard-cap
enforcement, whole-stock transfers, and identical outcomes with an empty event** as the first three
checks on the next revision.
