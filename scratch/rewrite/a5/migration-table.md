# Migration table: each old construct and its new form

One row for each group of census keys (`census.json`). The first column lists the keys that the row
covers: a name ending in `*` covers every key that starts with it. `table_check.py` checks that each
key of the census, used or never used, falls in a row, and prints the count of uses of each row.

"Mech" says how `translate.py` treats the form: `yes` (it writes the new form), `hand` (it leaves a
`# TODO(hand)` with a draft), `none` (no catalogue use). A form marked PROPOSED had no spelling in
the spec; its ruling is in `FINDINGS.md` (R-A5-NN). "Spec" means the spec gives the spelling. The
new forms are those of the language of now (G0 and the changes after it, in PLAN.md), as M-prep
brought `translate.py` to them (2026-11-19); where a row and the compiler differ, the compiler wins.

## Files, the scenario line, packages

| Keys | Old form | New form or ruling | Mech |
| --- | --- | --- | --- |
| `file.role.*` | first declaration makes a main, a module or a variant | unchanged: `scenario`, `variant`, or a file of templates that `use` names | yes |
| `scenario.line`, `scenario.summary`, `scenario.scope`, `scenario.horizon`, `scenario.library` | `scenario "T"` with `summary`, `scope`, `horizon`, `library` under it | unchanged lines under `scenario "T"`. PROPOSED, R-A5-01 | yes |
| `scenario.timescales*` | `timescales a, b` | unchanged, but each scale is a time (`timescales 30 days`): one that names a value is refused now (`scenario`), so a person writes the time | yes |
| `scenario.resolution` | `resolution D` (longest solver step) | kept with its old meaning until the engine contract names the control (spec, "Numerical scale hints"). PROPOSED, R-A5-01 | yes |
| `variant.*` | `variant "T"` with its own `summary`, `scope` (`horizon`, `resolution`, `timescales`: never used) | unchanged; a variant line overrides the line of the base. PROPOSED, R-A5-03 | yes |
| `use` | `use NAME` | unchanged (spec, "How templates compose") | yes |
| `change` | `change name:` blocks (never used) | unchanged; precedence and conflicts by R-A5-03 | none |

## Things, templates, links

| Keys | Old form | New form or ruling | Mech |
| --- | --- | --- | --- |
| `thing.entity` | `name:` | unchanged | yes |
| `thing.template` | `Template:` | unchanged | yes |
| `thing.instance*` | `name: Template` | unchanged | yes |
| `thing.copies`, `expr.copy` | `name: Template * k`, `copy` | no form in the first version: write the instances, or a table. R-A5-10 | none |
| `thing.table` | `name: Template from "file.csv"` | unchanged, with the spec's `id` column for links (spec, proposed) | none |
| `thing.role*`, `thing.title` | `role R`, `title "…"` | unchanged lines on an entity or a template; a member written by hand has no `title` or `role` now, so the translator keeps them in `notes:` / `titles:` (`roles:`) | yes |
| `thing.sees*` | `sees a, b.c` | none: `sees` left the language (change 15); a wrapper shows any value at a breakpoint | yes |
| `link.declare.one` | `let region: Region` | `region: Region` (a slot that each instance binds). PROPOSED | yes |
| `link.declare.many` | `let regions: [Region]` | `regions: <Region>` (spec collection type) | yes |
| `link.bind.one`, `link.bind.in_instance`, `link.bind.in_thing` | `let region = inland` | `region = inland` | yes |
| `link.bind.list`, `link.bind.empty_list` | `let zones = [a, b]`, `let zones = []` | `zones = <a, b>`, `zones = <>` (spec) | yes |
| `link.bind.template` | `let zones = Zone` | `zones = Zone.instances` (spec) | yes |

## Fields

| Keys | Old form | New form or ruling | Mech |
| --- | --- | --- | --- |
| `field.input.number*` | `input x: u = v in lo to hi` | `input x: u = v in [lo, hi]` (spec) | yes |
| `field.input.number.distribution`, `dist.declaration.*`, `dist.normal.truncated` | `input x = pert(a, b, c) in …` | `input x = pert(a, b, c).draw() in [lo, hi]` (spec, explicit draw); a four-argument `normal` stays truncated | yes |
| `field.input.bool*` | `input flag = true` | unchanged; `: bool` where the old file wrote a type | yes |
| `field.input.text` | `input actor = "The AI"` | unchanged | yes |
| `field.input.named` | input with named values (never used) | `input s: enum[A, B] = A` | none |
| `field.let.fixed*` | `let k = 2 h` | `readonly k = 2 h`. PROPOSED | yes |
| `field.let.formula*` | `let f: u = E` | `readonly f: formula(u) = formula(E)` (spec forms) | yes |
| `field.var.named` | `var s: "a" \| "b" = "a"` | `s: enum[A, B] = A`; members upper case (spec) | yes |
| `field.var.bool` | `var found = false` (never used) | `found: bool = false` | none |
| `field.var.number*` | `var n: u = v [in lo to hi] [size S]` | `n: u = v [in [lo, hi]] [scale S]`; a stock with no range gets `in [0,]` (D8). A state whose start an option sets starts from a new input `n_start`, which the option sets (R-A5-04), unless its start is a calculation (by hand) | yes |
| `type.unit*`, `expr.unit*` | `name: L/h`, `12 h`, `tuner-year` | units with `*` and `/` (D12): `tunings/tuner-year` is `tunings/tuner/year`, `person-hours` is `person * hours`, `h^2` is `h * h`; each part of a composed unit must be a unit of the library | yes |
| `expr.unit.power` | `m^2` (never used) | unchanged | none |

## Flows and shares

| Keys | Old form | New form or ruling | Mech |
| --- | --- | --- | --- |
| `flow`, `flow.plain*` | `flow f: a -> b at R` | `flow f: this.a -> this.b` with `request = formula(R)` and `capacity = formula(R)` under it: the old rate was fixed (D15; S0 D-8) | yes |
| `flow.plain.from_outside`, `flow.plain.to_outside`, `flow.leg.outside` | `-> b`, `a ->` | `SOURCE -> this.b`, `this.a -> SINK` (spec names `SINK`; `SOURCE` PROPOSED) | yes |
| `flow.while` | `… at R while C` | `request = formula(R if C else 0)` | yes |
| `flow.end.other_thing` | `relief.supply -> received` | `relief.supply -> this.received` | yes |
| `flow.legs*`, `flow.leg`, `flow.leg.own_rate`, `flow.leg.in_share` | `flow f at R:` with pairs under it | `flow f:` with a leg `flow name: A -> B` for each pair, each with its `request`; a leg is named by its target store, `owner_target` for another thing's (R-A5-12: rename freely) | yes |
| `share`, `share.proportional`, `flow.in_share`, `flow.plain.in_share`, `flow.legs.in_share` | `share s limit L` | under the store `s`: `outflow.capacity = formula(L)` (spec place; `formula` PROPOSED) | yes |
| `share.order*` | `share s limit L order f, g` | also `outflow.allocation = priority(this.f, this.g)`; a flow with legs is named by the leg that leaves the store | yes |

## Events

| Keys | Old form | New form or ruling | Mech |
| --- | --- | --- | --- |
| `event`, `event.trigger.when`, `event.outcomes.lines`, `event.outcomes.one_written` | `event e when C:` with lines | `e = event():` / `when C:` with `this.e.start()` / `after 0 h:` with the lines (spec) | yes |
| `event.once*` | `once` | `reset when false` in the trigger (spec) | yes |
| `event.trigger.after_when`, `event.after.expression` | `event e after D when C:` | the trigger starts it; the stage is `after D:` | yes |
| `event.trigger.after` | `after D` with no `when` (never used) | `when t >= D:` start, `reset when false` | none |
| `event.after.distribution` | a drawn delay (never used) | `after pert(…).draw():` | none |
| `event.trigger.named_only`, `event.no_lines`, `event.no_record.named_only` | `event e:` that only lines start | `e = event():` with no trigger; started by `this.e.start()` | yes |
| `event.start` | `event start when t >= 0 h:` | unchanged in form; the name `start` is free (an event, not the method) | yes |
| `event.when.*` | a `when` that reads `t`, `count`, `since`, `elapsed`, a crossing | unchanged condition; inclusive crossings only (spec) | yes |
| `event.when.var_comparison.strict` | `when x < k` on a number var | kept when the var is discrete; on a continuous one the new compiler must diagnose (spec, "Monitoring a threshold"). Not checked here | yes |
| `event.while` | `while K` on the header (never used) | no form in the first version. R-A5-10 | none |
| `event.each` | `each W` (never used) | a trigger capture with `reset when W != captured` (spec) | none |
| `event.outcomes.several*`, `outcome`, `outcome.chance.condition`, `outcome.chance.else`, `outcome.chance.none`, `outcome.no_lines` | named outcomes with conditions | a local `outcome: enum[A, B, C] = A`, then in the stage `outcome = A if C1 else B if C2 else C` and `switch outcome:` with a case for each outcome, its text and records under it (a conditional of bare members is no selector: `enum_member`). A case needs an action: an outcome with no line is left for a person | yes |
| `outcome.chance.number`, `event.outcomes.several.by_chance` | outcomes with chances | `switch categorical(A: p, B: q).draw():`, `else` as 1 less the others, each weight a number written in place (D1) | yes |
| `event.choice` | `choice` | a field `forecast = categorical(A: p, B: q)` of the actor, a local `order: enum[A, B] = A`, `order = this.forecast.draw()` and `switch order:` (change 15; the acceptance example `pump_dispatch`): a caller edits `order` at a breakpoint | yes |
| `event.role`, `outcome.role` | `role R` under an event or an outcome | no form: an event and a case have no role now; the translator writes a comment | yes |
| `fn.count.outcome`, `fn.since.outcome` | `count(e.o)`, `since(e.o)` | no form: start an event of its own in that case, and read it. R-A5-10 | hand |
| `text.event*`, `text.outcome*`, `text.event.list` | texts with `{name}` | unchanged: a text keeps its braces as written; the language of now gives them no meaning | yes |

## Lines of events

| Keys | Old form | New form or ruling | Mech |
| --- | --- | --- | --- |
| `stmt.set*`, `stmt.add*` | `x = v`, `x += v` | `this.x = v`, `this.x += v`; a stage reads its own earlier writes (spec): the order of the lines can now change a result | yes |
| `stmt.subtract` | `x -= v` (never used) | unchanged | none |
| `stmt.move*` | `move A from S to D` | unchanged, full paths (spec) | yes |
| `stmt.fire.own`, `stmt.fire.other_thing` | `e`, `thing.e` | `this.e.start()`, `thing.e.start()` | yes |
| `stmt.fire.list` | `list.e` | `this.list.e.start()` (spec, broadcast) | yes |
| `stmt.draws`, `dist.event.normal` | a draw in a line | `normal(…).draw()` (spec) | yes |
| `stmt.reads_delayed`, `fn.delayed` | `delayed(x, D)` (never used) | refused (change 12): a delayed observation is an event that waits and then writes | none |

## Status, asserts, outputs, the report

| Keys | Old form | New form or ruling | Mech |
| --- | --- | --- | --- |
| `status.block`, `status.case*`, `status.block.repeated_rating` | `status rating [when C]` with a text | unchanged (spec) | yes |
| `status.block.no_fallback` | a status whose last case has a condition (never used) | the new compiler should ask for the fallback (spec: "The final unconditional case is the fallback") | none |
| `instance.status` | status lines in an instance (never used) | not in the first version: status belongs to the template | none |
| `assert`, `assert.condition`, `assert.no_within`, `assert.in_thing`, `assert.top` | `assert C` | unchanged; every catalogue use is an input check | yes |
| `assert.sum*`, `assert.within` | `assert a + b is T within TOL` | `assert a + b in [T - TOL, T + TOL]` (spec) | yes |
| `assert.condition.within` | `assert C within TOL` that is no sum (never used) | an error: no `within` (spec) | none |
| `output.top`, `output.thing`, `output.typed`, `output.field` | `output name: u = E`, `output x` | a named value, `name: formula(u) = formula(E) in [0,]`, with its text and records (D10); no `report:` block: the caller selects paths and times | yes |
| `output.cumulative`, `output.set.level` | no `level` / `level` | nothing: a proof says whether a value never falls (`napkin/program/proofs.py`), which the check asks of each value that the old compiler proved cumulative | yes |
| `output.set.signed` | `signed` | the named value gets no `in [0,]` (spec: the interval says whether it can be negative) | yes |
| `output.set.distinct` | `distinct @r` | `@r` on the formula (spec: "An ordinary `@record` on a formula") | yes |
| `output.set.unestimated`, `output.unestimated.*` | `unestimated "Reason"` | no declaration (D4): its label, its reason and its records go into `notes:` / `not_estimated:` | yes |
| `output.set.lag*` | `lag D` | nothing in the model: a caller selects a lag, valid only for a value proved never to fall (D10); the translator keeps the delay in `notes:` / `reporting:` for the publisher | yes |
| `output.set.about`, `output.set.category*`, `output.set.scope` | `about`, `category`, `scope` | no line under a value: they go into `notes:` / `reporting:`, keyed by the value, for the publisher | yes |
| `expr.reads_output` | an output that reads another output | reads the named value | yes |

## Options, runs, instances

| Keys | Old form | New form or ruling | Mech |
| --- | --- | --- | --- |
| `options.group`, `options.option`, `options.option.no_setting` | `options "G":` / `"Option":` | unchanged. PROPOSED, R-A5-04 | yes |
| `options.setting`, `options.setting.thing`, `options.setting.sets.*`, `options.setting.expression` | `thing.field = v @r` | unchanged, full path, a constant of the input's type (D2): a value that is a calculation is left for a person; a state is set through its new input `x_start` | yes |
| `options.setting.template` | `Template.field = v` | `Template.instances.field = v` | yes |
| `options.setting.with_record`, `options.setting.no_record*` | a record or none | a record is required, except on a text. R-A5-05 | yes |
| `options.setting.sets.let.fixed` | an option that sets a `let` (never used) | an error: only an `input` takes an option | none |
| `run`, `run.no_versus`, `run.options*`, `run.text`, `runs.block` | `runs:` / `n = "A" + "B"` | unchanged. PROPOSED, R-A5-04 | yes |
| `run.versus*` | `n = … versus m` | `versus` leaves the model (D9); the translator keeps each pair in `notes:` / `comparisons:` for the publisher | yes |
| `instance.line.value*` | `m = v @r` in an instance | unchanged | yes |
| `instance.line.new_kind*` | `let m: u = E` in an instance | `m = formula(E)`; the template declares `m` a formula. R-A5-07 | yes |
| `instance.line.member_block`, `instance.line.output` | `m:` with new text, `output m` (never used) | no form; text and the report entry belong to the template and `report:` | none |

## Records, notes, texts

| Keys | Old form | New form or ruling | Mech |
| --- | --- | --- | --- |
| `evidence.cite*` | `@name` | unchanged (spec) | yes |
| `evidence.record.named*` | `record n: kind ID "text"` | `record n: kind "text"` with `assumption ID` (or `convention ID`) under it (spec candidate). R-A5-02 | yes |
| `evidence.record.in_place*` | `@kind ID "text"` | `@kind "text"` with the ID line under it. R-A5-02 | yes |
| `evidence.claims_block`, `evidence.claim*` | `claims:` / `E-…` / `datum: key` | unchanged (spec) | yes |
| `evidence.several.*` | two records on one line | unchanged | yes |
| `notes.block`, `note*` | `notes:` with keyed texts | unchanged. PROPOSED, R-A5-02 | yes |
| `text.*` | quoted texts | unchanged, under their declaration (spec) | yes |
| `lines.*` | lines, comments, blank lines | comments kept | yes |

## Functions and expressions

| Keys | Old form | New form or ruling | Mech |
| --- | --- | --- | --- |
| `expr`, `expr.bare_number`, `expr.power`, `expr.t`, `expr.not`, `expr.and_or`, `expr.if_else`, `expr.true_false`, `expr.unreadable` | arithmetic and logic | unchanged | yes |
| `expr.is`, `expr.is_not` | `a is b`, `a is not b` | `a == b`, `a != b` (spec) | yes |
| `expr.named_value` | `"open"` | `OPEN` (spec) | yes |
| `fn.math.*`, `fn.min.scalar*`, `fn.max.scalar*` | `exp`, `clip`, `min(a, b)` … | unchanged | yes |
| `fn.sum.list*` | `sum(link.x)`, `sum(Template.x)` | `sum(this.link.x)`, `sum(Template.instances.x)` (spec) | yes |
| `fn.max.list_with_extra`, `fn.min.list_with_extra` | `max(list.x, v)` | `max(max(list.x), v)`: the extra argument stays a scalar (spec: the empty case of a reduction is open) | yes |
| `fn.min.list`, `fn.max.list`, `fn.count.list`, `fn.any.list`, `fn.all.list` | reductions of a list (never used) | the spec's reductions | none |
| `fn.count.event`, `fn.count.in.*` | `count(e)` | `count(this.e.occurrences)` (spec) | yes |
| `fn.since.event`, `fn.since.in.when` | `since(e) >= d` | `count(this.e.occurrences) > 0 and since(this.e) >= d` (spec) | yes |
| `fn.since.state` | `since(state)` (never used) | `elapsed(this.state)` | none |
| `fn.elapsed*` | `elapsed(state)` | unchanged (spec keeps it) | yes |
| `fn.count.unresolved`, `fn.since.unresolved`, `name.read.unresolved`, `stmt.fire.unresolved` | names the census did not resolve (none) | nothing to migrate | none |
| `dist.keyword_arguments` | `normal(a, b, min=c)` (never used) | positional arguments | none |

## Names

| Keys | Old form | New form or ruling | Mech |
| --- | --- | --- | --- |
| `name.read.own` | `demand` | `this.demand` (spec scope rule) | yes |
| `name.read.via_link` | `utility.service` | `this.utility.service` | yes |
| `name.read.thing_by_name*` | `relief.status` | unchanged: top-level names stay readable. PROPOSED, R-A5-13 | yes |
| `name.read.template_list` | `Utility.unserved` | `Utility.instances.unserved` (spec) | yes |
| `name.declared.*` | members named `status`, `start`, `capacity`, `size` … | allowed, but a value named `status` beside status lines names the display (`status`): the translator renames it `state`; `from`, `to` are reserved | yes |
