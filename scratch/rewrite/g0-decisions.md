# Gate G0: the owner’s decision record (2026-11-18)

Please use this as the owner’s decision record for Gate G0 of the Napkin language rewrite. All 18 numbered rulings and their follow-up questions are settled. Where `rulings.md`, the syntax proposal, or the implementation plan disagree with this handoff, use the decisions below.

The deliverable is one self-contained syntax proposal that explains what a model author writes, what the engine guarantees, why the behavior was chosen, and what the experiments actually established. Keep the repository read-only. Leave implementation steps, agent assignments, and scheduling out of the proposal. Napkin is prerelease and we are refactoring the scenarios, so preserving old syntax is unnecessary. Preserving the meaning of a scenario still matters.

## The language these decisions fit into

Think of the model as scoped values. A quantity can acquire units, bounds, or flow behavior. A distribution exposes `.draw()`. A formula retains a calculation. An event is a typed value with parameters, an explicit `.start(...)` operation, attached triggers, and a collection of occurrences. A provider can own a solver in the same way it owns another value.

Use `name = expression` for a declaration. An ordinary expression captures its value when evaluated. Use `formula(...)` when the calculation should follow its dependencies. `readonly` protects a binding from direct assignment through any reference. A readonly formula can still produce different answers as the model changes.

```text
beans: g = 8
readonly low_on_beans: formula(bool) = formula(this.beans <= 10 g)
```

`beans: g = 8 g` is also valid. Both declarations initialize 8 g. An event binding is readonly by default. Its parameters are part of its type. Inside an invocation, `this` is the receiving entity and bare parameter and local names belong to that invocation. The engine tracks lifecycle facts such as whether an occurrence is active or done. Authors declare a domain-specific `status` only when their model needs one.

## The 18 G0 rulings

**D0 — Solver cost and correctness.** Keep the specified selection order at every model size. Enforce hard constraints, optimize explicit objectives in written order, apply inherited sharing and endpoint preferences, then choose the nearest remaining flow targets and finally the nearest declared references for other unknowns. Give the expensive fairness and final-distance steps budgets. If a step cannot produce an answer within its budget and numerical tolerances, stop with a diagnostic naming the step. Returning a different allocation silently would change the model.

Keep the measurements precise. At 30,000 places, the fairness step alone took 467 linear programs and 128 seconds in one shortage case. A heavier shortage failed partway. At 3,000 places, the final distance step after fairness took 38 seconds in the tested solver. The prototype also matched reference answers on 200 small inequality cases and demonstrated changing flow membership. These results establish specific capabilities and costs. They do not establish that every 30,000-place network finishes within a given time.

**D1 — Chance and actor choice.** Branch on an ordinary value. This is sufficient syntax for a random outcome:

```text
switch categorical(FIXED: 0.7, FAILED: 0.3).draw():
```

Drop the separate `chance(...)` spelling. In `sampled` mode, an executed draw samples. In `median` mode, a numeric distribution returns its median. For a categorical distribution, choose the most likely eligible outcome, taking the first declared eligible outcome on a tie. A reference run uses `median`. Reading a distribution, displaying alternatives, or skipping a branch consumes no draw.

An actor choice is a different source of a value for the same branching construct. **Eligibility and probability are independent.** If a spare pump is available and the automated dispatcher always waits, a human can still send it. If there is no spare, sending it is unavailable to both. `sees` selects observations for human playback. It adds no language-level permission rule for reading or writing model state.

**D2 — Input overrides follow the declared type.** If `repair_time` is a duration, override it with a duration in its admitted range. A scalar override skips the default draw. For example, `uniform(1 h, 3 h).draw()` gives a scalar default. An explicit input range of `[1 h, 12 h]` can admit a 5 h override while retaining that default distribution. If the modeler wants the distribution itself to be configurable, expose a distribution-valued input, override it with a compatible distribution, and call `.draw()` where the model needs the value.

**D3 — Continuously changing rates are valid at any model size.** A rate formula may read a quantity that changes between scheduled events. The prototype’s roughly 150-store threshold was a measurement for one connected component and one implementation. It is not a language limit. A large valid model may take longer or stop with an explicit time, memory, or accuracy failure. Its size must never silently change the equations or freeze a moving rate.

**D4 — Remove `none` as a model value.** If a scenario cannot estimate the number of people continuously without service for a week, explain that in its documentation or evidence and omit the declaration. Daily totals do not establish that the same people were affected each day. There is no need for a placeholder estimate or rules for propagating it through arithmetic.

Empty reductions have ordinary meanings where those exist. `sum` gives zero in the projected unit, `count` gives zero, `any` gives false, and `all` gives true. Reading `min` or `max` of an empty collection fails. A report can explain an unavailable read without introducing a value that participates in the model.

**D5 — Stages commit in deterministic order.** At one timestamp, stages due in the same round commit sequentially. A later stage sees earlier committed direct writes. Starting with 20 g, a stage setting the amount to 8 g followed by another adding 4 g leaves 12 g. Use the established occurrence order for stages due together.

After the round’s writes, starts, and flow membership changes, settle each affected solver once in dependency order and publish its results together. Then evaluate dependent triggers. New consequences can cause another round at the same timestamp. Reading a solver result whose inputs have changed before it settles is an error, including a read through a formula. A stale answer plus a warning is insufficient. Continuous evaluation between moments is a separate matter.

**D6 — Make runaway-run limits configurable.** Provide `max_occurrences`, `max_active`, and `max_rounds`. The proposed starting defaults are 1,000,000 starts of one event, 100,000 simultaneously active occurrences, and 1,000 rounds at one timestamp. These are protective defaults that a run can configure. When a limit is reached, identify the limit and the relevant event, waiting occurrence, or gate so the author can distinguish legitimate scale from a loop.

**D7 — A finished occurrence is a stable record.** Keep its identity, parameters, locals, and final formula results. A formula that read 14 at finish still reads 14 later. If a formula could not be evaluated at finish, preserve the reason and let the occurrence finish normally. For example, a formula asking how long it has been since a repair can be unavailable because no repair has started. A report can display that reason. A model read of the frozen field raises the recorded error. A later repair cannot retroactively change the answer.

**D8 — One-sided bounds and `scale`.** Allow either bound to be omitted. Use an empty side in examples, such as `in [0,]` for a nonnegative quantity with no upper bound. Finite endpoints are inclusive. A quantity declared without a range is unbounded, so a migrated physical inventory that must stay nonnegative needs its lower bound written explicitly. Rename the numerical hint `size` to `scale`. A scale helps numerical calculation and imposes no physical bound.

**D9 — The scenario owns comparisons and publication.** One engine invocation produces one trajectory from one effective configuration, run mode, seed where applicable, and set of controller choices. Named configurations can stay in the model. A scenario that wants a comparison runs the engine twice and compares the records in its own wrapper. Remove `versus`. There is no required repository publisher, comparison manifest, featured pair, or shared reporting convention. To share weather across two policies, the wrapper can supply the same weather realization to both. Equal seeds alone need not keep later draws aligned once the policies take different branches.

**D10 — Any named value can be reported.** The caller selects paths and times. Remove `output`, output flags, `cumulative` markers, and the model-level `report:` block. A live aggregate is simply:

```text
unserved_volume = formula(sum(Utility.instances.unserved))
```

Keep authored labels, descriptions, event cards, menu lines, evidence, and status text with the model. A status display has text per case because two cases can share the same state and need different explanations. A reporting lag is a caller-selected transformation that requires proof the value never falls. A delayed observation that influences a player’s decision belongs in the model. Drop the `distinct`, `unestimated`, `level`, and `signed` measurement clauses. Ordinary evidence, documentation, interval bounds, and compiler proofs cover their purposes.

**D11 — Allow `if` and `else` inside a stage.** A stage can run several actions and conditionally perform one of them. `after D when C:` still expresses a guard on the entire timed stage. An ordinary Boolean branch should not require a two-case `switch`.

**D12 — Units use ordinary multiplication and division.** `48 h/2` and `48 h / 2` both equal `24 h`. There is no unit named `h/2`. Write compound dimensions with `*` and `/`. For example, `(3 person) * (2 year)` gives `6 person * year`. Multiplication is what allows the compiler to derive and check the result’s dimension. Migrate hyphenated unit products accordingly.

**D13 — Pass a quantity for an amount and an entity for access to its fields.** An event parameter `amount: L` receives a value. If the caller passes the tank’s current 8 L, withdrawing from the parameter cannot debit the tank. An event that must withdraw from that particular tank takes a typed tank entity and uses its `.water` field. There is no new `stock` value type or `ref` keyword. A quantity acquires source or sink behavior through its use as a flow endpoint.

**D14 — Ordinary event-local initializers run in written order.** This includes plain initializers on an occurrence’s declared flow. A plain `request = left / (2 h)` requires `left` to have been initialized above it. A retained `formula(left / (2 h))` may refer to a later declaration because it evaluates on read. Model-level setup keeps its dependency ordering.

**D15 — A request is soft and capacity is hard.** A request contributes a service preference. A higher-ranked objective can make an allocation above that request useful, subject to every hard constraint. If a consumer physically cannot accept more than it asks for, set its capacity to the request too. When the request varies, use a live formula for that capacity. A plain assignment captures only the value at initialization. Always distinguish requested, permitted, and actual rates in examples.

**D16 — Retire the old machinery while preserving useful proof results.** Retire the second reading of the rules and whole-run pickles. Use the run record for histories and traces. Express the old `Partition` numeric checks with ordinary assertions. Reduce the old comparison tool to the checks on names, values, and traces that are useful for verifying migration.

Keep conservative reachability information for an effective configuration, including conclusions the compiler can establish through finite event or enum-state transitions. “This event cannot fire with the plant closed” and “this event could have fired but did not fire in this run” answer different questions. A trace establishes only the latter observation. Preserve proof metadata for callers and evidence displays. Physically pruning execution work is a separate optimization whose value can be measured.

**D17 — Correct the water scenario example.** `unserved_rate` can fall to zero when service returns. `unserved_volume` accumulates the unmet rate and retains the loss already incurred. If service returns at hour 5, the volume reported at hour 6 still includes the water missed through hour 5. This is a correction to that example. Other model authors can define an instantaneous shortfall when that is what they mean.

## Flow, solver, and event decisions needed to apply those rulings

**Put a rule on the value that has the information to express it.** A directed flow sees its source and sink and exposes its `actual_rate`. The supplying value gains `outflow`, the receiving value gains `inflow`, and each endpoint sees its incident flows. Put a pipe’s capacity on the pipe and a tank’s combined outlet capacity or sharing rule on the tank’s `outflow`. `SOURCE` supplies an external resource and `SINK` absorbs it, with the connection determining the resource unit. Ordinary local transfers need no explicit solver declaration.

**Share locally by default.** Suppose 1 L/h reaches a junction. Two pipes each request 1 L/h. One serves A and the other feeds a second junction with equal requests from B and C. The first junction sends half down each pipe. A receives ½ L/h, B receives ¼ L/h, and C receives ¼ L/h. Adding C changes B’s share. A’s share stays the same. If a provider promises equal service to all three recipients, put that objective on the provider’s solver.

**Use one owner for a coordinated decision.** A generic `solver` can coordinate flow rates or other numeric values, such as staff hours. Keep `inputs`, `solve_for`, `constraints`, and optional `objective` distinct so a reader can tell what is known, what the solver chooses, and why it chooses an answer. Respect bounds and hard constraints already declared on participating values. When two explicit provider solvers would separately choose rates that compete for the same binding hard resource, give the joint decision to one coordinating solver. Ordinary flows sharing a constrained endpoint can still use its local allocation rule.

**Keep the two-bottleneck example.** Three consumers each request 6 W, with `a + b <= 4 W` and `b + c <= 5 W`. Default equal-priority fair sharing gives `(2, 2, 3) W`. Putting `minimize(sum(unmet))` first gives `(4, 0, 5) W`. The second allocation delivers more in total and leaves B entirely unserved. A later fairness preference cannot undo an earlier objective. This example explains a consequential modeling choice that a single bottleneck cannot show.

**Keep the three flow forms distinct.** A directed flow exposes its actual rate. A reversible route has one signed actual rate and exposes directional legs in endpoint collections. Name the appropriate leg in `priority(...)`. Both ends of a reversible route must be able to supply and receive, which rules out `SOURCE`, `SINK`, and a receive-only tally. A flow with several simultaneous legs gives each leg its own full-service request and actual rate and gives the parent one `served_fraction`. Thus legs requesting 4 L/h and 8 Wh/h at half service deliver 2 L/h and 4 Wh/h. Each rate keeps its unit. A zero-request leg transfers zero. A `[0, 0]` junction must balance total inflow and outflow at each instant.

**Endpoint collections describe the present. Occurrences preserve history.** A run can add both flows and occurrences. An entity-owned flow stays connected for the entity’s lifetime, even when closed or starved. An occurrence-owned flow joins its endpoint collections at the start and leaves them together at finish. Its key is never reused. Through the finished occurrence, the flow keeps its endpoints and final request and capacity, and reads zero actual rate. A finished multi-leg flow also reads zero served fraction. This keeps yesterday’s frozen 2 L/h request out of today’s demand sum. A transfer that should continue after an event finishes belongs on the entity, where the event can enable it. A finishing occurrence must account for material in its own store by draining or moving it before normal completion.

**Use the same collection operations throughout.** Entity instances, table rows, flows, and occurrences share one typed collection abstraction. `where` preserves keys, `by(field)` gives the same members a new key, and projection carries the originating keys. That is why `customers.by(rank).delivery` can rank the projected flows. Equal priority ranks are legitimate. Flag duplicate file keys in a keyed view used for `.at(...)`, where the tie affects which row is read. `.at(x)` uses the greatest key at or below `x`, in compatible units. An empty lookup or a read below the first key fails when evaluated. `count(c)` counts members, `count(c.done)` counts true flags, and `count(c.amount)` on a numeric field is a type error. Give table rows stable IDs and route columns names such as `origin` and `destination` so reordering rows preserves the named transfers.

**Allow writes to live occurrences.** A dispatch event can update a writable `crew_size` on a particular running repair. Mark the field `readonly` if direct assignment should be forbidden. There is no special “only this invocation may write” rule. Finished occurrences are frozen. Likewise, `readonly` on an inventory forbids direct assignment, including `+=` and `-=`, while a declared flow or checked `move` can still transfer material and record it.

**Fire triggers when their condition first becomes true.** A trigger belongs to its bound event. For a supported continuous condition, including one that reads a solved value, find the first qualifying crossing even between scheduled events. A tank starting at 11 L and draining at 1 L/h reaches `water <= 10 L` at hour 1. A discrete condition is checked on committed changes. If the engine cannot certify the first crossing, diagnose it so the author can choose a supported threshold or an explicit inspection schedule. Silent polling would change the event time.

**A human prompt pauses one atomic stage.** If a stage draws a value, queues a child start, and then asks a player to choose, preserve that draw and the pending choice. The child becomes visible when the stage commits. Resuming or replaying applies the answer and commits the effects exactly once. The prompt must never produce a second draw, child, or transfer.

Please carry these decisions through the examples, diagnostics, acceptance cases, and “open questions” text as well as the main prose. A reader should get the same answer from the worked model as from the language rules. Keep prototype results identified as measurements, and keep performance work separate from settled author-visible behavior.
