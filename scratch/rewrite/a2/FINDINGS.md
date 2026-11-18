# A2 findings: reference semantics

> DRAFT. The rules below are decided. Examples, numbers and the coverage table are TODO until the
> tests run. See `STATE.md` for where the work stands.

## 1. Summary

TODO.

## 2. What was done

TODO: scripts and how to run each.

## 3. Results

TODO: coverage table for the 31 cases.

## 4. Rulings

Each rule is the default of one switch in `ref/model.py` (`Rules`); the alternative is the other
value. TODO: the example of each, with what both give, from `cases/test_rulings.py`.

### R-A2-01: The order of simultaneous starts and of due stages  [owner]
Rule: Starts register in the order in which their `.start` statements ran: stages in commit order, then trigger firings by receiver and declaration. Stages due in one round commit by the age of their occurrence, the older first.
Alternative: Stages commit in the order in which they were scheduled.
Example: TODO
Recommendation: TODO

### R-A2-02: The members of a start on a collection  [owner]
Rule: The members start in the key order of the collection as addressed; equal keys in creation order.
Alternative: Creation order, whatever key `by` gave.
Example: TODO
Recommendation: TODO

### R-A2-03: Conflicting writes from two stages of one round  [owner]
Rule: Stages of a round commit one after the other. A later stage reads what an earlier one wrote. The last `=` wins and `+=` adds up.
Alternative: Every stage reads the state from the start of the round; two different `=` to one value fail the run.
Example: TODO
Recommendation: TODO

### R-A2-04: Reset cycles  [owner]
Rule: A trigger may fire again at the same time after its reset. A run allows a fixed number of rounds at one time (100). Beyond it the run fails and names the triggers that fired again and again.
Alternative: A second firing of one trigger at one time fails the run at once.
Example: TODO
Recommendation: TODO

### R-A2-05: Setup order  [owner]
Rule: Setup is round zero. Starting values in dependency order; the statements of the setup scope commit as one stage; rates and solvers settle; then triggers get their first check.
Alternative: The starts of the setup scope run to rest before the first trigger check.
Example: TODO
Recommendation: TODO

### R-A2-06: `none` in arithmetic, in a comparison and in a reduction  [owner]
Rule: `none` propagates through arithmetic, ordering comparisons and reductions. `==` and `!=` test for absence. A decision that receives `none` fails the run and names the value.
Alternative: Any arithmetic or ordering on `none` fails the run at once.
Example: TODO
Recommendation: TODO

### R-A2-07: `min` and `max` over nothing  [owner]
Rule: `none`. A scalar beside the collection takes part, so `max(0 L, c.x)` over nothing is `0 L`.
Alternative: A run error where it is evaluated.
Example: TODO
Recommendation: TODO

### R-A2-08: `elapsed` after several writes in one stage  [owner]
Rule: The clock restarts only when the committed value differs from the value before the stage.
Alternative: Every write that changes the value restarts it, also a change that the same stage undoes.
Example: TODO
Recommendation: TODO

### R-A2-09: A read with zero delay inside a stage  [owner]
Rule: `delayed(x, 0 h)` reads the committed value: not what the stage itself has written.
Alternative: It reads what `x` reads.
Example: TODO
Recommendation: TODO

### R-A2-10: What stays readable on a finished occurrence  [owner]
Rule: Everything, frozen at the finish: arguments, locals, formulas (as values), `started`, `done`, `active`. A local store reads its final amount, which the retirement rule makes zero.
Alternative: Only the built-in fields and plain declared locals; arguments, stores and formulas fail.
Example: TODO
Recommendation: TODO

### R-A2-11: A saved reference to an occurrence  [owner]
Rule: It pins the identity. A later start does not change what it names.
Alternative: It is the lookup, read again at each use.
Example: TODO
Recommendation: TODO

### R-A2-12: A flow with legs that two endpoints rank differently  [owner]
Rule: A claim is decided after every claim that some endpoint ranks ahead of it. Claims whose ranks contradict each other share a tier.
Alternative: The claim takes the last position that any endpoint gives it.
Example: TODO
Recommendation: TODO

### R-A2-13: The budget for occurrences that never finish  [owner]
Rule: Waiting for ever is legal. The budget is on the occurrences of one bound event that run at once (1000); the message names the event, the count, the time and the gate of the oldest.
Alternative: No budget.
Example: TODO
Recommendation: TODO

### R-A2-14: Where a human choice pauses  [owner]
Rule: Inside the stage, before its commit. Nothing of the stage is visible while the run waits; the answer replays the stage.
Alternative: The stage commits what it did before the choice.
Example: TODO
Recommendation: TODO

### R-A2-15: Where an `assert` on state is checked  [owner]
Rule: After every round, just after every moment, and at each contact with its boundary between moments.
Alternative: After every round only.
Example: TODO
Recommendation: TODO

### R-A2-16: An invalid history read that a report asks for  [owner]
Rule: A report reads the record after the run. An invalid read shows as unavailable, with the reason.
Alternative: The read happens in the run and fails it.
Example: TODO
Recommendation: TODO

### R-A2-17: The key of each draw  [technical]
Rule: The seed, the site of the draw in the model, and its owner: the entity, or the occurrence, or the firing.
Alternative: The position of the draw in one stream.
Example: TODO
Recommendation: TODO

### R-A2-18: An opening balance from outside  [owner]
Rule: What a store holds when it first becomes a store is recorded as an opening balance from outside.
Alternative: A store of an occurrence must start empty.
Example: TODO
Recommendation: TODO

TODO: rulings for `move` on readonly, forward references of locals and flows, the retirement rule, a
stale result read across stages, and the flow scale across dimensions.

## 5. Not covered

TODO.
