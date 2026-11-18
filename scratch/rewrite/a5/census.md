# Census of the catalogue at the base commit

Made by `census.py` with the old parser at `/home/user/napkin-base` (commit 8488047). Every count is of parsed nodes. No count comes from a text pattern.

Files: 23. Lines: 10185. Keys counted: 358.

Columns: the two `examples/` models; `cyber_learning_loop`; `heat_wave_blackout`; 
`iv_fluid_shortage`; `water_controls_wipe/water.scn`; its main `model.scn`; its 16 variants together.
"Where" gives up to three places, as `file:line`.

## Forms that the language has and the catalogue never uses

- `thing.copies`: `name: Template * k`, and so `copy` in an expression
- `thing.table`: `name: Template from "file.csv"`
- `change`: `change name:` blocks
- `event.each`: `each W` windows
- `event.while`: `while K` on the header of an event
- `event.after.distribution`: a drawn delay, `after pert(...)`
- `event.trigger.after`: `after D` with no `when`
- `fn.delayed`: `delayed(x, D)`
- `fn.count.list`: `count(list.flag)`
- `fn.any.list`: `any(list.flag)`
- `fn.all.list`: `all(list.flag)`
- `fn.min.list`: `min(list.x)`
- `fn.max.list`: `max(list.x)`
- `fn.min.list_with_extra`: `min(list.x, v)`
- `fn.since.state`: `since(state)` of a named state
- `name.read.unresolved`: a name that this census did not resolve
- `fn.since.unresolved`: `since()` whose argument this census did not resolve
- `fn.count.unresolved`: `count()` whose argument this census did not resolve
- `stmt.fire.unresolved`: a line that names an event this census did not resolve
- `expr.unreadable`: an expression that the old reader does not read alone
- `fn.count.outcome`: `count(e.o)` of one outcome
- `output.set.lag.uniform`: `lag uniform(a, b)`
- `output.set.lag.mixture`: `lag mixture(...)`
- `field.input.named`: an input with named values
- `field.var.bool`: a yes/no state, `var found = false`
- `expr.copy`: `copy`
- `expr.unit.power`: a unit with a power, `m^2`
- `dist.declaration.bernoulli`: `bernoulli(p)`
- `dist.declaration.categorical`: `categorical(...)`
- `dist.keyword_arguments`: a distribution with arguments by name, `normal(a, b, min=c)`
- `stmt.subtract`: `x -= v`
- `stmt.reads_delayed`: a line that reads `delayed`
- `text.event.list`: a list of texts on an event
- `assert.condition.within`: `assert C within TOL` that is no sum
- `instance.line.member_block`: `m:` with new text or records in an instance
- `instance.line.output`: `output m` in an instance
- `instance.status`: `status` lines in an instance
- `variant.horizon`: a variant with a `horizon` of its own
- `variant.resolution`: a variant with a `resolution` of its own
- `variant.timescales`: a variant with `timescales` of its own
- `options.setting.sets.let.fixed`: an option that sets a `let`
- `note.value.list`: a note whose value is a list
- `status.block.no_fallback`: a status whose last line has a condition

## Files and lines

| Key | What it counts | Total | examples | cyber | heat | iv | water.scn | water main | 16 variants | Where |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `file.role.main` | Files whose first declaration makes them a main | 6 | 2 | 1 | 1 | 1 |  | 1 |  | examples/piano_tuners:1, examples/reservoir:1 |
| `file.role.module` | Files whose first declaration makes them a module | 1 |  |  |  |  | 1 |  |  | water/water.scn:1 |
| `file.role.variant` | Files whose first declaration makes them a variant | 16 |  |  |  |  |  |  | 16 | water/variants/asheville:1, water/variants/auburn:1 |
| `lines.blank` | Empty lines | 531 | 6 | 46 | 68 | 33 | 98 |  | 280 |  |
| `lines.comment` | Comment lines | 149 | 2 | 49 | 41 | 30 | 10 | 1 | 16 |  |
| `lines.logical` | Logical lines: a line with what its brackets and texts carry on | 6960 | 74 | 2158 | 1342 | 717 | 1022 | 5 | 1642 |  |
| `lines.physical` | Lines of the file | 10185 | 84 | 3199 | 1917 | 1137 | 1431 | 7 | 2410 |  |

## The scenario line, variants, modules

| Key | What it counts | Total | examples | cyber | heat | iv | water.scn | water main | 16 variants | Where |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `scenario.horizon` | `horizon …` under the scenario line | 6 | 2 | 1 | 1 | 1 |  | 1 |  | examples/piano_tuners:4, examples/reservoir:5 |
| `scenario.library` | `library …` under the scenario line | 4 |  | 1 | 1 | 1 |  | 1 |  | cyber_learning_loop:13, heat_wave_blackout:14 |
| `scenario.line` | `scenario "Title"` | 6 | 2 | 1 | 1 | 1 |  | 1 |  | examples/piano_tuners:2, examples/reservoir:2 |
| `scenario.resolution` | `resolution …` under the scenario line | 1 |  | 1 |  |  |  |  |  | cyber_learning_loop:11 |
| `scenario.scope` | `scope …` under the scenario line | 6 | 2 | 1 | 1 | 1 |  | 1 |  | examples/piano_tuners:5, examples/reservoir:6 |
| `scenario.summary` | `summary …` under the scenario line | 5 | 2 | 1 | 1 | 1 |  |  |  | examples/piano_tuners:3, examples/reservoir:3 |
| `scenario.timescales` | `timescales a, b` under the scenario line | 2 |  | 1 | 1 |  |  |  |  | cyber_learning_loop:10, heat_wave_blackout:11 |
| `scenario.timescales.values` | The values that `timescales` lists | 5 |  | 3 | 2 |  |  |  |  | cyber_learning_loop:10, heat_wave_blackout:11 |
| `use` | `use NAME`: a module of the package | 1 |  |  |  |  |  | 1 |  | water:7 |
| `variant.line` | `variant "Title"` | 16 |  |  |  |  |  |  | 16 | water/variants/asheville:2, water/variants/auburn:2 |
| `variant.scope` | `scope …` under the variant line | 16 |  |  |  |  |  |  | 16 | water/variants/asheville:5, water/variants/auburn:5 |
| `variant.summary` | `summary …` under the variant line | 16 |  |  |  |  |  |  | 16 | water/variants/asheville:3, water/variants/auburn:3 |

## Things

| Key | What it counts | Total | examples | cyber | heat | iv | water.scn | water main | 16 variants | Where |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `instance.line.new_kind` | `input m = v` / `let m: u = E` in an instance: a new kind of value for a member | 40 |  | 39 |  |  | 1 |  |  | cyber_learning_loop:1685, cyber_learning_loop:1979 |
| `instance.line.new_kind.let.fixed` | … that makes the member a let.fixed | 6 |  | 6 |  |  |  |  |  | cyber_learning_loop:2042, cyber_learning_loop:2043 |
| `instance.line.new_kind.let.formula` | … that makes the member a let.formula | 34 |  | 33 |  |  | 1 |  |  | cyber_learning_loop:1685, cyber_learning_loop:1979 |
| `instance.line.value` | `m = v  @r` in an instance: a new value for a member | 346 |  | 53 | 9 |  | 4 |  | 280 | cyber_learning_loop:826, cyber_learning_loop:830 |
| `instance.line.value.no_record` | … with no record of its own (a text value needs none) | 47 |  |  |  |  | 2 |  | 45 | water/variants/asheville:13, water/variants/asheville:32 |
| `instance.line.value.sets.input.bool` | … of a member that is a input.bool | 13 |  | 13 |  |  |  |  |  | cyber_learning_loop:1632, cyber_learning_loop:1636 |
| `instance.line.value.sets.input.number` | … of a member that is a input.number | 285 |  | 40 | 8 |  | 2 |  | 235 | cyber_learning_loop:826, cyber_learning_loop:830 |
| `instance.line.value.sets.input.text` | … of a member that is a input.text | 47 |  |  |  |  | 2 |  | 45 | water/variants/asheville:13, water/variants/asheville:32 |
| `instance.line.value.sets.let.fixed` | … of a member that is a let.fixed | 1 |  |  | 1 |  |  |  |  | heat_wave_blackout:990 |
| `link.bind.empty_list` | `let regions = []`: a list of no things | 43 |  |  |  |  |  |  | 43 | water/variants/asheville:11, water/variants/asheville:12 |
| `link.bind.in_instance` | A link bound in an instance (or a change block) | 118 |  |  | 9 |  | 2 |  | 107 | heat_wave_blackout:1083, heat_wave_blackout:1086 |
| `link.bind.in_thing` | A link bound in a thing made without a template, or in a template | 4 |  |  | 4 |  |  |  |  | heat_wave_blackout:703, heat_wave_blackout:704 |
| `link.bind.list` | `let zones = [near, middle]`: a link to a list of things | 13 |  |  | 4 |  |  |  | 9 | heat_wave_blackout:703, heat_wave_blackout:704 |
| `link.bind.one` | `let region = inland`: a link to one thing | 64 |  |  | 9 |  |  |  | 55 | heat_wave_blackout:1083, heat_wave_blackout:1086 |
| `link.bind.template` | `let zones = Zone`: the list of the instances of a template | 2 |  |  |  |  | 2 |  |  | water/water.scn:503, water/water.scn:511 |
| `link.declare.many` | `let regions: [Region]`: a slot for a list of things | 3 |  |  |  |  | 3 |  |  | water/water.scn:79, water/water.scn:80 |
| `link.declare.one` | `let region: Region`: a slot for one thing, which each instance binds | 7 |  |  | 3 |  | 4 |  |  | heat_wave_blackout:999, heat_wave_blackout:1094 |
| `thing.entity` | `name:`: a thing made without a template | 45 | 3 | 11 | 14 | 12 | 5 |  |  | examples/piano_tuners:7, examples/reservoir:8 |
| `thing.instance` | `name: Template`: an instance of a template | 110 |  | 17 | 16 |  | 2 |  | 75 | cyber_learning_loop:824, cyber_learning_loop:828 |
| `thing.instance.bare` | … with no line under it | 2 |  |  | 2 |  |  |  |  | heat_wave_blackout:200, heat_wave_blackout:981 |
| `thing.role` | `role R` under a thing | 59 | 2 | 15 | 20 | 12 | 10 |  |  | examples/piano_tuners:7, examples/reservoir:37 |
| `thing.role.adversary` | `role adversary` | 4 |  | 1 | 1 | 1 | 1 |  |  | cyber_learning_loop:839, heat_wave_blackout:540 |
| `thing.role.clinician` | `role clinician` | 2 |  |  | 1 |  | 1 |  |  | heat_wave_blackout:909, water/water.scn:634 |
| `thing.role.community` | `role community` | 9 |  |  | 6 | 2 | 1 |  |  | heat_wave_blackout:181, heat_wave_blackout:782 |
| `thing.role.contractor` | `role contractor` | 1 |  |  | 1 |  |  |  |  | heat_wave_blackout:496 |
| `thing.role.effects_program` | `role effects_program` | 1 |  | 1 |  |  |  |  |  | cyber_learning_loop:1513 |
| `thing.role.environment` | `role environment` | 12 | 1 | 2 | 5 | 3 | 1 |  |  | examples/piano_tuners:7, cyber_learning_loop:15 |
| `thing.role.military_planners` | `role military_planners` | 1 |  | 1 |  |  |  |  |  | cyber_learning_loop:697 |
| `thing.role.operator` | `role operator` | 17 | 1 | 7 | 1 | 5 | 3 |  |  | examples/reservoir:37, cyber_learning_loop:39 |
| `thing.role.other_states` | `role other_states` | 1 |  | 1 |  |  |  |  |  | cyber_learning_loop:2059 |
| `thing.role.researchers` | `role researchers` | 1 |  | 1 |  |  |  |  |  | cyber_learning_loop:1687 |
| `thing.role.responder` | `role responder` | 8 |  | 1 | 3 | 1 | 3 |  |  | cyber_learning_loop:530, heat_wave_blackout:698 |
| `thing.role.utility` | `role utility` | 2 |  |  | 2 |  |  |  |  | heat_wave_blackout:359, heat_wave_blackout:656 |
| `thing.sees` | `sees a, b.c`: the thing is an actor | 1 | 1 |  |  |  |  |  |  | examples/reservoir:37 |
| `thing.sees.fact.value` | A fact that an actor sees: a value | 1 | 1 |  |  |  |  |  |  | examples/reservoir:37 |
| `thing.template` | `Template:`: a template | 15 |  | 4 | 6 |  | 5 |  |  | cyber_learning_loop:697, cyber_learning_loop:1513 |
| `thing.title` | `title "…"` under a thing | 90 |  | 11 | 6 | 1 | 3 |  | 69 | cyber_learning_loop:17, cyber_learning_loop:42 |

## Fields

| Key | What it counts | Total | examples | cyber | heat | iv | water.scn | water main | 16 variants | Where |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `field.input.bool` | `input flag = true`: a yes/no input | 18 |  | 14 | 1 | 1 | 2 |  |  | cyber_learning_loop:56, cyber_learning_loop:182 |
| `field.input.bool.typed` | … with its type written (`name: unit = …`) | 14 |  | 14 |  |  |  |  |  | cyber_learning_loop:56, cyber_learning_loop:182 |
| `field.input.number` | `input x = 6 h in 1 h to 24 h`: a number input | 281 | 7 | 127 | 79 | 23 | 45 |  |  | examples/piano_tuners:10, examples/piano_tuners:14 |
| `field.input.number.distribution` | A `input x = 6 h in 1 h to 24 h`: a number input whose value is a distribution | 1 | 1 |  |  |  |  |  |  | examples/piano_tuners:10 |
| `field.input.number.range` | … with a range, `in low to high` | 281 | 7 | 127 | 79 | 23 | 45 |  |  | examples/piano_tuners:10, examples/piano_tuners:14 |
| `field.input.number.type_from_value` | … with no type: the unit of its value gives it | 115 | 3 |  | 58 | 18 | 36 |  |  | examples/piano_tuners:10, examples/piano_tuners:14 |
| `field.input.number.typed` | … with its type written (`name: unit = …`) | 166 | 4 | 127 | 21 | 5 | 9 |  |  | examples/reservoir:10, examples/reservoir:13 |
| `field.input.text` | `input actor = "The AI"`: a text value | 7 |  | 1 | 1 | 1 | 4 |  |  | cyber_learning_loop:844, heat_wave_blackout:553 |
| `field.let.fixed` | `let k = 2 h`: a value that never changes | 28 |  | 11 | 9 | 5 | 3 |  |  | cyber_learning_loop:82, cyber_learning_loop:1714 |
| `field.let.fixed.type_from_value` | … with no type: the unit of its value gives it | 13 |  |  | 6 | 5 | 2 |  |  | heat_wave_blackout:140, heat_wave_blackout:268 |
| `field.let.fixed.typed` | … with its type written (`name: unit = …`) | 15 |  | 11 | 3 |  | 1 |  |  | cyber_learning_loop:82, cyber_learning_loop:1714 |
| `field.let.formula` | `let f: unit = a * b`: a formula | 461 |  | 343 | 50 | 18 | 50 |  |  | cyber_learning_loop:31, cyber_learning_loop:34 |
| `field.let.formula.typed` | … with its type written (`name: unit = …`) | 461 |  | 343 | 50 | 18 | 50 |  |  | cyber_learning_loop:31, cyber_learning_loop:34 |
| `field.var.named` | `var s: "a" \| "b" = "a"`: a named state | 40 | 1 | 3 | 13 | 10 | 13 |  |  | examples/reservoir:22, cyber_learning_loop:76 |
| `field.var.number` | `var n: unit = 0 …`: a number that changes (a stock, a tally or a number state) | 149 | 5 | 37 | 47 | 23 | 37 |  |  | examples/piano_tuners:20, examples/piano_tuners:22 |
| `field.var.number.no_range_no_size` | A number var with no range and no size | 14 |  |  |  |  | 14 |  |  | water/water.scn:150, water/water.scn:152 |
| `field.var.number.range` | … with a range, `in low to high` | 36 |  | 33 | 3 |  |  |  |  | cyber_learning_loop:74, cyber_learning_loop:78 |
| `field.var.number.size` | … with a `size` hint | 135 | 5 | 37 | 47 | 23 | 23 |  |  | examples/piano_tuners:20, examples/piano_tuners:22 |
| `field.var.number.start_expression` | A number var whose start value is an expression of other values | 53 | 1 | 30 | 10 | 7 | 5 |  |  | examples/piano_tuners:20, cyber_learning_loop:74 |
| `field.var.number.typed` | … with its type written (`name: unit = …`) | 149 | 5 | 37 | 47 | 23 | 37 |  |  | examples/piano_tuners:20, examples/piano_tuners:22 |

## Flows and shares

| Key | What it counts | Total | examples | cyber | heat | iv | water.scn | water main | 16 variants | Where |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `flow` | Flows, of every form | 134 | 4 | 58 | 32 | 15 | 25 |  |  | examples/piano_tuners:24, examples/reservoir:33 |
| `flow.end.other_thing` | An end of a flow in another thing, `relief.supply -> received` | 65 |  | 44 | 6 | 5 | 10 |  |  | cyber_learning_loop:478, cyber_learning_loop:478 |
| `flow.in_share` | A flow that drains a var with a `share` | 74 |  | 39 | 18 | 8 | 9 |  |  | cyber_learning_loop:473, cyber_learning_loop:475 |
| `flow.leg` | A pair of a flow with several pairs | 104 |  | 91 | 4 | 2 | 7 |  |  | cyber_learning_loop:477, cyber_learning_loop:478 |
| `flow.leg.in_share` | A pair of a flow with several pairs that drains a var with a `share` | 70 |  | 61 | 4 | 1 | 4 |  |  | cyber_learning_loop:477, cyber_learning_loop:478 |
| `flow.leg.outside` | A pair with one end outside the model | 39 |  | 39 |  |  |  |  |  | cyber_learning_loop:1358, cyber_learning_loop:1359 |
| `flow.leg.own_rate` | A pair with a rate of its own, `c -> d at other_rate` | 67 |  | 65 |  | 1 | 1 |  |  | cyber_learning_loop:478, cyber_learning_loop:482 |
| `flow.legs` | `flow name at RATE:` with its pairs under it: pairs that move by one fraction | 32 |  | 26 | 2 | 1 | 3 |  |  | cyber_learning_loop:475, cyber_learning_loop:479 |
| `flow.legs.in_share` | A flow with several pairs, one of which drains a var with a `share` | 29 |  | 23 | 2 | 1 | 3 |  |  | cyber_learning_loop:475, cyber_learning_loop:479 |
| `flow.legs.pairs2` | … with that many pairs | 13 |  | 8 | 2 | 1 | 2 |  |  | cyber_learning_loop:475, cyber_learning_loop:479 |
| `flow.legs.pairs3` | … with that many pairs | 12 |  | 11 |  |  | 1 |  |  | cyber_learning_loop:495, cyber_learning_loop:505 |
| `flow.legs.pairs4` | … with that many pairs | 1 |  | 1 |  |  |  |  |  | cyber_learning_loop:1473 |
| `flow.legs.pairs5` | … with that many pairs | 1 |  | 1 |  |  |  |  |  | cyber_learning_loop:1445 |
| `flow.legs.pairs6` | … with that many pairs | 2 |  | 2 |  |  |  |  |  | cyber_learning_loop:1419, cyber_learning_loop:1452 |
| `flow.legs.pairs7` | … with that many pairs | 3 |  | 3 |  |  |  |  |  | cyber_learning_loop:1427, cyber_learning_loop:1436 |
| `flow.plain` | `flow name: a -> b at RATE`: one pair | 102 | 4 | 32 | 30 | 14 | 22 |  |  | examples/piano_tuners:24, examples/reservoir:33 |
| `flow.plain.from_outside` | `flow name: -> b at RATE`: from outside the model | 36 | 2 | 10 | 8 | 3 | 13 |  |  | examples/reservoir:33, examples/reservoir:35 |
| `flow.plain.in_share` | A flow of one pair that drains a var with a `share` | 45 |  | 16 | 16 | 7 | 6 |  |  | cyber_learning_loop:473, cyber_learning_loop:485 |
| `flow.plain.store_to_store` | `flow name: a -> b at RATE`: between two vars | 50 | 2 | 6 | 22 | 11 | 9 |  |  | examples/piano_tuners:24, examples/reservoir:34 |
| `flow.plain.to_outside` | `flow name: a -> at RATE`: out of the model | 16 |  | 16 |  |  |  |  |  | cyber_learning_loop:126, cyber_learning_loop:286 |
| `flow.while` | `… while C`: a flow that moves only while a condition holds | 6 | 1 |  |  | 2 | 3 |  |  | examples/reservoir:34, iv_fluid_shortage:345 |
| `share` | `share VAR limit RATE [order f, g]` | 31 |  | 15 | 8 | 4 | 4 |  |  | cyber_learning_loop:483, cyber_learning_loop:514 |
| `share.order` | A share with `order f, g`: the named flows first, in order | 3 |  |  |  | 2 | 1 |  |  | iv_fluid_shortage:536, iv_fluid_shortage:743 |
| `share.order.flows2` | … that names that many flows | 2 |  |  |  | 2 |  |  |  | iv_fluid_shortage:536, iv_fluid_shortage:743 |
| `share.order.flows4` | … that names that many flows | 1 |  |  |  |  | 1 |  |  | water/water.scn:371 |
| `share.proportional` | A share with no `order`: in proportion to what each flow asks | 28 |  | 15 | 8 | 2 | 3 |  |  | cyber_learning_loop:483, cyber_learning_loop:514 |

## Events

| Key | What it counts | Total | examples | cyber | heat | iv | water.scn | water main | 16 variants | Where |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `event` | Events, of every form | 100 | 1 | 8 | 34 | 27 | 30 |  |  | examples/reservoir:44, cyber_learning_loop:130 |
| `event.after.expression` | `after D`: a delay that reads a value | 4 |  |  | 1 | 1 | 2 |  |  | heat_wave_blackout:575, iv_fluid_shortage:262 |
| `event.choice` | `choice` under an event: an actor chooses its outcome | 1 | 1 |  |  |  |  |  |  | examples/reservoir:44 |
| `event.no_lines` | An event with no line under it: it changes nothing, and others read it | 13 |  | 1 | 5 | 3 | 4 |  |  | cyber_learning_loop:1510, heat_wave_blackout:428 |
| `event.no_record.named_only` | An event of the form named_only with no record on its line | 2 |  |  |  | 1 | 1 |  |  | iv_fluid_shortage:618, water/water.scn:407 |
| `event.once` | `once`: the event triggers at most once in a run | 37 | 1 | 3 | 16 | 11 | 6 |  |  | examples/reservoir:44, cyber_learning_loop:130 |
| `event.once.after_when` | `once` with the trigger form after_when | 4 |  |  | 1 | 1 | 2 |  |  | heat_wave_blackout:575, iv_fluid_shortage:262 |
| `event.once.when` | `once` with the trigger form when | 33 | 1 | 3 | 15 | 10 | 4 |  |  | examples/reservoir:44, cyber_learning_loop:130 |
| `event.outcomes.lines` | An event with its lines under it: the one outcome `done` | 79 |  | 6 | 27 | 22 | 24 |  |  | cyber_learning_loop:130, cyber_learning_loop:133 |
| `event.outcomes.one_written` | An event with one outcome written by its name, `done C:` | 1 |  |  |  |  | 1 |  |  | water/water.scn:69 |
| `event.outcomes.several` | An event with two outcomes or more | 7 | 1 | 1 | 2 | 2 | 1 |  |  | examples/reservoir:44, cyber_learning_loop:678 |
| `event.outcomes.several.by_chance` | … with a chance that is a number or an expression | 1 | 1 |  |  |  |  |  |  | examples/reservoir:44 |
| `event.outcomes.several.by_condition` | … whose chances are all conditions (and `else`): the model decides | 6 |  | 1 | 2 | 2 | 1 |  |  | cyber_learning_loop:678, heat_wave_blackout:575 |
| `event.outcomes.several.n2` | … with that many outcomes | 5 | 1 | 1 | 1 | 2 |  |  |  | examples/reservoir:44, cyber_learning_loop:678 |
| `event.outcomes.several.n3` | … with that many outcomes | 2 |  |  | 1 |  | 1 |  |  | heat_wave_blackout:575, water/water.scn:291 |
| `event.role` | `role R` under an event | 10 |  |  | 4 | 2 | 4 |  |  | heat_wave_blackout:416, heat_wave_blackout:490 |
| `event.start` | `event start when t >= 0 h:`: the start of the model | 4 |  | 1 | 1 | 1 | 1 |  |  | cyber_learning_loop:1510, heat_wave_blackout:590 |
| `event.trigger.after_when` | `event e after D when C:`: it fires D after it triggers | 4 |  |  | 1 | 1 | 2 |  |  | heat_wave_blackout:575, iv_fluid_shortage:262 |
| `event.trigger.named_only` | `event e:` with no `when`: it triggers only when a line names it | 12 |  |  | 3 | 6 | 3 |  |  | heat_wave_blackout:1075, heat_wave_blackout:1151 |
| `event.trigger.when` | `event e when C:`: it triggers each time C becomes true | 84 | 1 | 8 | 30 | 20 | 25 |  |  | examples/reservoir:44, cyber_learning_loop:130 |
| `event.when.reads_count` | A `when` that reads `count()` | 6 |  |  | 1 | 2 | 3 |  |  | heat_wave_blackout:522, iv_fluid_shortage:249 |
| `event.when.reads_elapsed` | A `when` that reads `elapsed()` | 4 |  |  |  |  | 4 |  |  | water/water.scn:335, water/water.scn:487 |
| `event.when.reads_since` | A `when` that reads `since()` | 31 |  | 1 | 19 | 6 | 5 |  |  | cyber_learning_loop:133, heat_wave_blackout:177 |
| `event.when.reads_t` | A `when` that reads the time `t` | 9 |  | 5 | 1 | 2 | 1 |  |  | cyber_learning_loop:130, cyber_learning_loop:137 |
| `event.when.var_comparison.inclusive` | A `when` that compares a number var by `<=` or `>=` | 20 | 1 | 4 | 4 | 6 | 5 |  |  | examples/reservoir:44, cyber_learning_loop:137 |
| `event.when.var_comparison.strict` | A `when` that compares a number var by `<` or `>` | 4 |  |  | 3 |  | 1 |  |  | heat_wave_blackout:416, heat_wave_blackout:416 |
| `outcome` | Outcomes written by their name | 17 | 2 | 2 | 5 | 4 | 4 |  |  | examples/reservoir:47, examples/reservoir:50 |
| `outcome.chance.condition` | An outcome whose chance is a condition, `done mode is "x" and ready:` | 8 |  | 1 | 3 | 2 | 2 |  |  | cyber_learning_loop:679, heat_wave_blackout:578 |
| `outcome.chance.else` | `name else:`: 1 less the other chances | 7 | 1 | 1 | 2 | 2 | 1 |  |  | examples/reservoir:50, cyber_learning_loop:684 |
| `outcome.chance.none` | An outcome with no chance: the chance 1 | 1 |  |  |  |  | 1 |  |  | water/water.scn:70 |
| `outcome.chance.number` | An outcome whose chance is a number, `open 1:` | 1 | 1 |  |  |  |  |  |  | examples/reservoir:47 |
| `outcome.no_lines` | An outcome with no line: it changes nothing | 8 | 1 |  | 3 | 2 | 2 |  |  | examples/reservoir:50, heat_wave_blackout:584 |
| `outcome.role` | `role R` under an outcome | 5 |  |  | 3 | 2 |  |  |  | heat_wave_blackout:584, heat_wave_blackout:587 |
| `stmt.add` | `x += v` in an event | 21 |  | 5 | 4 |  | 12 |  |  | cyber_learning_loop:140, cyber_learning_loop:681 |
| `stmt.add.expression` | … whose value is an expression (it reads the values from before the outcome) | 18 |  | 3 | 4 |  | 11 |  |  | cyber_learning_loop:140, cyber_learning_loop:683 |
| `stmt.add.other_thing` | … whose target is a value of another thing | 2 |  |  | 2 |  |  |  |  | heat_wave_blackout:582, heat_wave_blackout:583 |
| `stmt.add.target.var.number` | … whose target is a var.number | 21 |  | 5 | 4 |  | 12 |  |  | cyber_learning_loop:140, cyber_learning_loop:681 |
| `stmt.draws` | A line of an event that draws from a distribution | 1 |  | 1 |  |  |  |  |  | cyber_learning_loop:139 |
| `stmt.fire.list` | `list.e`: a line that fires the event of each member of a list | 3 |  |  | 3 |  |  |  |  | heat_wave_blackout:774, heat_wave_blackout:775 |
| `stmt.fire.other_thing` | `thing.e`: a line that fires an event of another thing | 4 |  |  |  | 4 |  |  |  | iv_fluid_shortage:118, iv_fluid_shortage:119 |
| `stmt.fire.own` | `e`: a line that fires an event of the same thing | 8 |  |  |  | 4 | 4 |  |  | iv_fluid_shortage:362, iv_fluid_shortage:366 |
| `stmt.move` | `move A from S to D` | 8 |  |  | 4 | 4 |  |  |  | heat_wave_blackout:608, heat_wave_blackout:1076 |
| `stmt.move.other_thing` | A move with an end in another thing | 2 |  |  | 1 | 1 |  |  |  | heat_wave_blackout:608, iv_fluid_shortage:257 |
| `stmt.set` | `x = v` in an event | 95 | 1 | 10 | 27 | 25 | 32 |  |  | examples/reservoir:49, cyber_learning_loop:132 |
| `stmt.set.expression` | … whose value is an expression (it reads the values from before the outcome) | 3 |  | 3 |  |  |  |  |  | cyber_learning_loop:139, cyber_learning_loop:677 |
| `stmt.set.other_thing` | … whose target is a value of another thing | 21 | 1 |  | 6 | 12 | 2 |  |  | examples/reservoir:49, heat_wave_blackout:423 |
| `stmt.set.target.var.named` | … whose target is a var.named | 87 | 1 | 5 | 24 | 25 | 32 |  |  | examples/reservoir:49, cyber_learning_loop:132 |
| `stmt.set.target.var.number` | … whose target is a var.number | 8 |  | 5 | 3 |  |  |  |  | cyber_learning_loop:139, cyber_learning_loop:677 |

## Status, asserts, outputs

| Key | What it counts | Total | examples | cyber | heat | iv | water.scn | water main | 16 variants | Where |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `assert` | `assert` lines | 38 |  | 3 | 16 | 9 | 10 |  |  | cyber_learning_loop:1806, cyber_learning_loop:1809 |
| `assert.condition` | `assert C`: a condition | 21 |  | 3 | 9 | 7 | 2 |  |  | cyber_learning_loop:1806, cyber_learning_loop:1809 |
| `assert.in_thing` | `assert` under a thing | 20 |  | 3 | 7 | 2 | 8 |  |  | cyber_learning_loop:1806, cyber_learning_loop:1809 |
| `assert.no_within` | `assert` with no `within` | 21 |  | 3 | 9 | 7 | 2 |  |  | cyber_learning_loop:1806, cyber_learning_loop:1809 |
| `assert.sum` | `assert a + b is T within TOL`: a sum of number vars | 17 |  |  | 7 | 2 | 8 |  |  | heat_wave_blackout:441, heat_wave_blackout:443 |
| `assert.sum.list_term` | A term of a sum that names a list, `Zone.held` | 2 |  |  |  |  | 2 |  |  | water/water.scn:686, water/water.scn:686 |
| `assert.sum.terms2` | … with that many terms (5: five or more) | 10 |  |  | 3 |  | 7 |  |  | heat_wave_blackout:443, heat_wave_blackout:653 |
| `assert.sum.terms3` | … with that many terms (5: five or more) | 4 |  |  | 1 | 2 | 1 |  |  | heat_wave_blackout:441, iv_fluid_shortage:660 |
| `assert.sum.terms5` | … with that many terms (5: five or more) | 3 |  |  | 3 |  |  |  |  | heat_wave_blackout:1077, heat_wave_blackout:1153 |
| `assert.top` | `assert` at the top level | 18 |  |  | 9 | 7 | 2 |  |  | heat_wave_blackout:1229, heat_wave_blackout:1232 |
| `assert.within` | `assert … within TOL` | 17 |  |  | 7 | 2 | 8 |  |  | heat_wave_blackout:441, heat_wave_blackout:443 |
| `output.cumulative` | An estimated output with no `level`: the file says it is cumulative | 35 | 3 | 2 | 10 | 16 | 4 |  |  | examples/piano_tuners:26, examples/reservoir:28 |
| `output.field` | `output x` under a thing: its field `x` is an output | 9 | 2 |  |  | 6 | 1 |  |  | examples/reservoir:28, examples/reservoir:32 |
| `output.set.about` | `about "…"` under an output | 21 |  |  | 6 | 5 | 10 |  |  | heat_wave_blackout:465, heat_wave_blackout:1276 |
| `output.set.category` | `category word` under an output | 19 |  | 3 | 8 | 3 | 5 |  |  | cyber_learning_loop:2284, cyber_learning_loop:2288 |
| `output.set.category.casualties` | `category casualties` | 6 |  | 1 | 3 | 1 | 1 |  |  | cyber_learning_loop:2288, heat_wave_blackout:1294 |
| `output.set.category.deaths` | `category deaths` | 5 |  | 1 | 2 | 1 | 1 |  |  | cyber_learning_loop:2284, heat_wave_blackout:1270 |
| `output.set.category.exposure` | `category exposure` | 2 |  |  | 1 |  | 1 |  |  | heat_wave_blackout:468, water/water.scn:798 |
| `output.set.category.loss` | `category loss` | 6 |  | 1 | 2 | 1 | 2 |  |  | cyber_learning_loop:2292, heat_wave_blackout:1322 |
| `output.set.distinct` | `distinct  @r`: the people that it adds are different people | 9 |  |  | 5 | 1 | 3 |  |  | heat_wave_blackout:740, heat_wave_blackout:1283 |
| `output.set.lag.fixed` | `lag` of kind fixed | 2 |  |  |  | 2 |  |  |  | iv_fluid_shortage:723, iv_fluid_shortage:728 |
| `output.set.level` | `level`: the output can fall | 85 |  | 59 | 15 | 3 | 8 |  |  | cyber_learning_loop:2089, cyber_learning_loop:2092 |
| `output.set.scope` | `scope "…"` under an output | 54 |  |  | 20 | 19 | 15 |  |  | heat_wave_blackout:402, heat_wave_blackout:406 |
| `output.set.signed` | `signed`: the output can be below zero | 3 |  | 1 | 1 |  | 1 |  |  | cyber_learning_loop:2141, heat_wave_blackout:1402 |
| `output.set.unestimated` | `unestimated "Reason"`: an output with no estimate | 11 |  | 3 | 4 |  | 4 |  |  | cyber_learning_loop:2287, cyber_learning_loop:2291 |
| `output.thing` | `output name: unit = E` under a thing | 19 |  |  | 12 | 7 |  |  |  | heat_wave_blackout:400, heat_wave_blackout:404 |
| `output.top` | `output name: unit = E` at the top level | 102 | 1 | 64 | 16 | 6 | 15 |  |  | examples/piano_tuners:26, cyber_learning_loop:2089 |
| `output.typed` | An output with its unit written | 121 | 1 | 64 | 28 | 13 | 15 |  |  | examples/piano_tuners:26, cyber_learning_loop:2089 |
| `output.unestimated.level` | An unestimated output with `level` | 1 |  |  | 1 |  |  |  |  | heat_wave_blackout:1402 |
| `output.unestimated.no_level` | An unestimated output with no `level` | 10 |  | 3 | 3 |  | 4 |  |  | cyber_learning_loop:2284, cyber_learning_loop:2288 |
| `status.block` | Things with `status` lines | 34 |  | 1 | 13 | 11 | 9 |  |  | cyber_learning_loop:667, heat_wave_blackout:173 |
| `status.block.repeated_rating` | A status with two cases of one rating and different texts | 12 |  |  | 7 | 4 | 1 |  |  | heat_wave_blackout:350, heat_wave_blackout:408 |
| `status.case` | `status rating [when C]` lines | 101 |  | 3 | 43 | 28 | 27 |  |  | cyber_learning_loop:667, cyber_learning_loop:669 |
| `status.case.fallback` | A status line with no condition | 34 |  | 1 | 13 | 11 | 9 |  |  | cyber_learning_loop:671, heat_wave_blackout:175 |
| `status.case.rating.degraded` | `status degraded …` | 22 |  | 1 | 10 | 2 | 9 |  |  | cyber_learning_loop:669, heat_wave_blackout:175 |
| `status.case.rating.failed` | `status failed …` | 27 |  |  | 11 | 11 | 5 |  |  | heat_wave_blackout:354, heat_wave_blackout:410 |
| `status.case.rating.inactive` | `status inactive …` | 12 |  | 1 | 5 | 2 | 4 |  |  | cyber_learning_loop:671, heat_wave_blackout:747 |
| `status.case.rating.ok` | `status ok …` | 40 |  | 1 | 17 | 13 | 9 |  |  | cyber_learning_loop:667, heat_wave_blackout:173 |
| `status.case.when` | A status line with `when C` | 67 |  | 2 | 30 | 17 | 18 |  |  | cyber_learning_loop:667, cyber_learning_loop:669 |

## Options and runs

| Key | What it counts | Total | examples | cyber | heat | iv | water.scn | water main | 16 variants | Where |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `options.group` | `options "Group":` | 20 |  | 10 | 2 | 3 | 4 |  | 1 | cyber_learning_loop:2297, cyber_learning_loop:2310 |
| `options.option` | `"Option":` under a group | 52 |  | 27 | 9 | 7 | 8 |  | 1 | cyber_learning_loop:2298, cyber_learning_loop:2301 |
| `options.option.no_setting` | An option that sets nothing: the values as the file writes them | 18 |  | 9 | 2 | 3 | 4 |  |  | cyber_learning_loop:2298, cyber_learning_loop:2328 |
| `options.setting` | `thing.field = v` in an option | 108 |  | 33 | 20 | 17 | 36 |  | 2 | cyber_learning_loop:2304, cyber_learning_loop:2305 |
| `options.setting.expression` | … whose value is an expression | 3 |  |  |  | 3 |  |  |  | iv_fluid_shortage:877, iv_fluid_shortage:881 |
| `options.setting.no_record` | … with no record (the old compiler asks for none) | 4 |  | 1 | 1 | 1 | 1 |  |  | cyber_learning_loop:2314, heat_wave_blackout:1453 |
| `options.setting.no_record.input.text` | … with no record, on a input.text | 4 |  | 1 | 1 | 1 | 1 |  |  | cyber_learning_loop:2314, heat_wave_blackout:1453 |
| `options.setting.sets.input.bool` | … that sets a input.bool | 11 |  | 7 | 2 |  |  |  | 2 | cyber_learning_loop:2334, cyber_learning_loop:2335 |
| `options.setting.sets.input.number` | … that sets a input.number | 87 |  | 25 | 16 | 12 | 34 |  |  | cyber_learning_loop:2304, cyber_learning_loop:2305 |
| `options.setting.sets.input.text` | … that sets a input.text | 4 |  | 1 | 1 | 1 | 1 |  |  | cyber_learning_loop:2314, heat_wave_blackout:1453 |
| `options.setting.sets.var.named` | … that sets a var.named | 3 |  |  | 1 | 1 | 1 |  |  | heat_wave_blackout:1470, iv_fluid_shortage:885 |
| `options.setting.sets.var.number` | … that sets a var.number | 3 |  |  |  | 3 |  |  |  | iv_fluid_shortage:877, iv_fluid_shortage:881 |
| `options.setting.template` | `Template.field = v`: every instance of a template | 14 |  |  | 3 |  | 10 |  | 1 | heat_wave_blackout:1457, heat_wave_blackout:1458 |
| `options.setting.thing` | `thing.field = v`: one thing | 94 |  | 33 | 17 | 17 | 26 |  | 1 | cyber_learning_loop:2304, cyber_learning_loop:2305 |
| `options.setting.with_record` | … with a record | 104 |  | 32 | 19 | 16 | 35 |  | 2 | cyber_learning_loop:2304, cyber_learning_loop:2305 |
| `run` | `name = "Option" + "Option"` lines of `runs:` | 36 |  | 12 | 11 | 7 | 5 |  | 1 | cyber_learning_loop:2418, cyber_learning_loop:2421 |
| `run.no_versus` | A run with no `versus` | 25 |  | 7 | 7 | 6 | 4 |  | 1 | cyber_learning_loop:2418, cyber_learning_loop:2424 |
| `run.options2` | A run that names that many options (8: eight or more) | 21 |  |  | 11 | 6 | 4 |  |  | heat_wave_blackout:1475, heat_wave_blackout:1476 |
| `run.options3` | A run that names that many options (8: eight or more) | 3 |  |  |  | 1 | 1 |  | 1 | iv_fluid_shortage:912, water/variants/washington_dc:165 |
| `run.options7` | A run that names that many options (8: eight or more) | 10 |  | 10 |  |  |  |  |  | cyber_learning_loop:2418, cyber_learning_loop:2421 |
| `run.options8` | A run that names that many options (8: eight or more) | 2 |  | 2 |  |  |  |  |  | cyber_learning_loop:2448, cyber_learning_loop:2451 |
| `run.text` | A run with its text under it | 19 |  | 12 | 4 | 1 | 1 |  | 1 | cyber_learning_loop:2418, cyber_learning_loop:2421 |
| `run.versus` | A run with `versus other`: a comparison | 11 |  | 5 | 4 | 1 | 1 |  |  | cyber_learning_loop:2421, cyber_learning_loop:2436 |
| `run.versus.baselines` | Distinct runs that a `versus` names | 7 |  | 2 | 3 | 1 | 1 |  |  |  |
| `runs.block` | `runs:` blocks | 5 |  | 1 | 1 | 1 | 1 |  | 1 | cyber_learning_loop:2417, heat_wave_blackout:1474 |

## Notes

| Key | What it counts | Total | examples | cyber | heat | iv | water.scn | water main | 16 variants | Where |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `note` | Notes: `key: value` lines under `notes:` | 163 |  | 7 | 34 | 14 | 29 |  | 79 | cyber_learning_loop:2456, cyber_learning_loop:2457 |
| `note.depth.max` | The deepest nesting of notes (a maximum, not a sum) | 2 |  | 2 | 2 | 2 | 2 |  | 2 |  |
| `note.top.benchmark` | The top-level note `benchmark:` | 1 |  |  | 1 |  |  |  |  | heat_wave_blackout:1559 |
| `note.top.counterfactual` | The top-level note `counterfactual:` | 3 |  |  | 1 | 1 | 1 |  |  | heat_wave_blackout:1572, iv_fluid_shortage:945 |
| `note.top.decisive` | The top-level note `decisive:` | 4 |  | 1 | 1 | 1 | 1 |  |  | cyber_learning_loop:2468, heat_wave_blackout:1579 |
| `note.top.exposure` | The top-level note `exposure:` | 2 |  |  | 1 |  | 1 |  |  | heat_wave_blackout:1537, water/water.scn:957 |
| `note.top.limitations` | The top-level note `limitations:` | 20 |  | 1 | 1 | 1 | 1 |  | 16 | cyber_learning_loop:2460, heat_wave_blackout:1523 |
| `note.top.premises` | The top-level note `premises:` | 4 |  | 1 | 1 | 1 | 1 |  |  | cyber_learning_loop:2456, heat_wave_blackout:1492 |
| `note.top.reachability` | The top-level note `reachability:` | 2 |  |  | 1 |  | 1 |  |  | heat_wave_blackout:1551, water/water.scn:973 |
| `note.top.verification` | The top-level note `verification:` | 19 |  |  | 1 | 1 | 1 |  | 16 | heat_wave_blackout:1539, iv_fluid_shortage:933 |
| `note.value.none` | A note whose value is nothing: it holds notes | 46 |  | 2 | 5 | 3 | 4 |  | 32 | cyber_learning_loop:2456, cyber_learning_loop:2460 |
| `note.value.number` | A note whose value is a number | 4 |  |  | 4 |  |  |  |  | heat_wave_blackout:1562, heat_wave_blackout:1563 |
| `note.value.text` | A note whose value is a text | 113 |  | 5 | 25 | 11 | 25 |  | 47 | cyber_learning_loop:2457, cyber_learning_loop:2461 |
| `note.with_evidence` | A note that cites or holds a record | 51 |  | 3 | 5 |  | 12 |  | 31 | cyber_learning_loop:2461, cyber_learning_loop:2464 |
| `notes.block` | `notes:` blocks | 20 |  | 1 | 1 | 1 | 1 |  | 16 | cyber_learning_loop:2456, heat_wave_blackout:1492 |

## Evidence

| Key | What it counts | Total | examples | cyber | heat | iv | water.scn | water main | 16 variants | Where |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `evidence.cite` | `@name`: a named record cited at a line | 1922 | 7 | 868 | 332 | 153 | 294 |  | 268 | examples/piano_tuners:20, examples/piano_tuners:22 |
| `evidence.cite.on.assert` | `@name` on a assert | 37 |  | 3 | 15 | 9 | 10 |  |  | cyber_learning_loop:1806, cyber_learning_loop:1809 |
| `evidence.cite.on.distinct` | `@name` on a distinct | 9 |  |  | 5 | 1 | 3 |  |  | heat_wave_blackout:740, heat_wave_blackout:1283 |
| `evidence.cite.on.event` | `@name` on a event | 103 | 1 | 8 | 30 | 32 | 32 |  |  | examples/reservoir:44, cyber_learning_loop:130 |
| `evidence.cite.on.field` | `@name` on a field | 906 | 2 | 550 | 169 | 47 | 138 |  |  | examples/piano_tuners:20, examples/piano_tuners:22 |
| `evidence.cite.on.flow` | `@name` on a flow | 165 | 4 | 85 | 31 | 17 | 28 |  |  | examples/piano_tuners:24, examples/reservoir:33 |
| `evidence.cite.on.flow pair` | `@name` on a flow pair | 3 |  |  | 2 |  | 1 |  |  | heat_wave_blackout:1065, heat_wave_blackout:1210 |
| `evidence.cite.on.instance line` | `@name` on a instance line | 335 |  | 92 | 5 |  | 3 |  | 235 | cyber_learning_loop:826, cyber_learning_loop:830 |
| `evidence.cite.on.note` | `@name` on a note | 46 |  | 3 | 1 |  | 11 |  | 31 | cyber_learning_loop:2463, cyber_learning_loop:2465 |
| `evidence.cite.on.option line` | `@name` on a option line | 99 |  | 32 | 17 | 13 | 35 |  | 2 | cyber_learning_loop:2304, cyber_learning_loop:2305 |
| `evidence.cite.on.outcome` | `@name` on a outcome | 6 |  |  | 2 | 2 | 2 |  |  | heat_wave_blackout:578, heat_wave_blackout:643 |
| `evidence.cite.on.output` | `@name` on a output | 121 |  | 65 | 27 | 13 | 16 |  |  | cyber_learning_loop:2089, cyber_learning_loop:2092 |
| `evidence.cite.on.share` | `@name` on a share | 30 |  | 15 | 7 | 4 | 4 |  |  | cyber_learning_loop:483, cyber_learning_loop:515 |
| `evidence.cite.on.status` | `@name` on a status | 4 |  |  | 1 | 2 | 1 |  |  | heat_wave_blackout:350, iv_fluid_shortage:140 |
| `evidence.cite.on.thing` | `@name` on a thing | 58 |  | 15 | 20 | 13 | 10 |  |  | cyber_learning_loop:15, cyber_learning_loop:39 |
| `evidence.claim` | A claim listed under a record | 821 |  | 104 | 124 | 75 | 118 |  | 400 | cyber_learning_loop:2486, cyber_learning_loop:2487 |
| `evidence.claim.datum` | `datum: key` under a claim | 142 |  |  | 31 |  |  |  | 111 | heat_wave_blackout:30, heat_wave_blackout:43 |
| `evidence.claims_block` | `claims:` under a record | 417 |  | 58 | 83 | 36 | 53 |  | 187 | cyber_learning_loop:2481, cyber_learning_loop:2511 |
| `evidence.record.in_place` | `@kind [ID] "explanation"` under a line | 152 | 12 |  | 80 | 58 | 2 |  |  | examples/piano_tuners:13, examples/piano_tuners:16 |
| `evidence.record.in_place.id` | A record in place with an ID | 83 |  |  | 38 | 44 | 1 |  |  | heat_wave_blackout:26, heat_wave_blackout:194 |
| `evidence.record.in_place.kind.assumption` | A record in place of kind `assumption` | 76 | 9 |  | 24 | 42 | 1 |  |  | examples/piano_tuners:13, examples/piano_tuners:16 |
| `evidence.record.in_place.kind.identity` | A record in place of kind `identity` | 23 | 3 |  | 10 | 9 | 1 |  |  | examples/piano_tuners:28, examples/reservoir:27 |
| `evidence.record.in_place.kind.source` | A record in place of kind `source` | 24 |  |  | 24 |  |  |  |  | heat_wave_blackout:41, heat_wave_blackout:47 |
| `evidence.record.in_place.kind.source_transfer` | A record in place of kind `source_transfer` | 29 |  |  | 22 | 7 |  |  |  | heat_wave_blackout:26, heat_wave_blackout:32 |
| `evidence.record.in_place.on.assert` | A record in place on a assert | 3 |  |  | 1 | 2 |  |  |  | heat_wave_blackout:1268, iv_fluid_shortage:788 |
| `evidence.record.in_place.on.event` | A record in place on a event | 29 |  |  | 13 | 16 |  |  |  | heat_wave_blackout:426, heat_wave_blackout:430 |
| `evidence.record.in_place.on.field` | A record in place on a field | 85 | 11 |  | 46 | 28 |  |  |  | examples/piano_tuners:13, examples/piano_tuners:16 |
| `evidence.record.in_place.on.flow` | A record in place on a flow | 3 |  |  | 3 |  |  |  |  | heat_wave_blackout:434, heat_wave_blackout:437 |
| `evidence.record.in_place.on.instance line` | A record in place on a instance line | 4 |  |  | 4 |  |  |  |  | heat_wave_blackout:204, heat_wave_blackout:213 |
| `evidence.record.in_place.on.note` | A record in place on a note | 5 |  |  | 4 |  | 1 |  |  | heat_wave_blackout:1495, heat_wave_blackout:1501 |
| `evidence.record.in_place.on.option line` | A record in place on a option line | 6 |  |  | 2 | 4 |  |  |  | heat_wave_blackout:1459, heat_wave_blackout:1471 |
| `evidence.record.in_place.on.outcome` | A record in place on a outcome | 3 |  |  |  | 3 |  |  |  | iv_fluid_shortage:254, iv_fluid_shortage:268 |
| `evidence.record.in_place.on.output` | A record in place on a output | 8 | 1 |  | 5 | 2 |  |  |  | examples/piano_tuners:28, heat_wave_blackout:473 |
| `evidence.record.in_place.on.share` | A record in place on a share | 1 |  |  | 1 |  |  |  |  | heat_wave_blackout:778 |
| `evidence.record.in_place.on.thing` | A record in place on a thing | 5 |  |  | 1 | 3 | 1 |  |  | heat_wave_blackout:548, iv_fluid_shortage:149 |
| `evidence.record.named` | `record name: kind [ID] "explanation"` | 516 | 3 | 144 | 85 | 35 | 62 |  | 187 | examples/piano_tuners:30, examples/reservoir:53 |
| `evidence.record.named.id` | A named record with an ID | 387 |  | 129 | 68 | 26 | 49 |  | 115 | cyber_learning_loop:2471, cyber_learning_loop:2474 |
| `evidence.record.named.kind.assumption` | A named record of kind `assumption` | 368 | 1 | 127 | 52 | 25 | 48 |  | 115 | examples/reservoir:54, cyber_learning_loop:2471 |
| `evidence.record.named.kind.convention` | A named record of kind `convention` | 4 |  | 1 | 1 | 1 | 1 |  |  | cyber_learning_loop:3198, heat_wave_blackout:1897 |
| `evidence.record.named.kind.identity` | A named record of kind `identity` | 48 | 2 | 15 | 15 | 6 | 10 |  |  | examples/piano_tuners:30, examples/reservoir:53 |
| `evidence.record.named.kind.source` | A named record of kind `source` | 74 |  |  | 2 |  |  |  | 72 | heat_wave_blackout:1588, heat_wave_blackout:1672 |
| `evidence.record.named.kind.source_transfer` | A named record of kind `source_transfer` | 22 |  | 1 | 15 | 3 | 3 |  |  | cyber_learning_loop:2984, heat_wave_blackout:1676 |
| `evidence.several.on.assert` | A assert with two records or more (cited or in place) | 2 |  |  |  | 2 |  |  |  | iv_fluid_shortage:785, iv_fluid_shortage:795 |
| `evidence.several.on.event` | A event with two records or more (cited or in place) | 27 |  |  | 8 | 17 | 2 |  |  | heat_wave_blackout:491, heat_wave_blackout:524 |
| `evidence.several.on.field` | A field with two records or more (cited or in place) | 50 |  | 15 | 29 | 5 | 1 |  |  | cyber_learning_loop:345, cyber_learning_loop:350 |
| `evidence.several.on.flow` | A flow with two records or more (cited or in place) | 33 |  | 26 | 2 | 2 | 3 |  |  | cyber_learning_loop:473, cyber_learning_loop:475 |
| `evidence.several.on.option line` | A option line with two records or more (cited or in place) | 1 |  |  |  | 1 |  |  |  | iv_fluid_shortage:886 |
| `evidence.several.on.outcome` | A outcome with two records or more (cited or in place) | 2 |  |  |  | 2 |  |  |  | iv_fluid_shortage:251, iv_fluid_shortage:265 |
| `evidence.several.on.output` | A output with two records or more (cited or in place) | 7 |  | 1 | 4 | 1 | 1 |  |  | cyber_learning_loop:2288, heat_wave_blackout:737 |
| `evidence.several.on.status` | A status with two records or more (cited or in place) | 1 |  |  |  | 1 |  |  |  | iv_fluid_shortage:140 |
| `evidence.several.on.thing` | A thing with two records or more (cited or in place) | 7 |  |  | 2 | 4 | 1 |  |  | heat_wave_blackout:346, heat_wave_blackout:540 |

## Texts

| Key | What it counts | Total | examples | cyber | heat | iv | water.scn | water main | 16 variants | Where |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `text.assert` | The text of a assert | 38 |  | 3 | 16 | 9 | 10 |  |  | cyber_learning_loop:1807, cyber_learning_loop:1810 |
| `text.braces.other_thing` | Braces that name a text value of another thing | 2 |  |  |  |  | 2 |  |  | water/water.scn:342, water/water.scn:348 |
| `text.event` | The text of a event | 72 | 1 | 7 | 28 | 14 | 22 |  |  | examples/reservoir:45, cyber_learning_loop:131 |
| `text.event.braces` | A text of a event with a name in braces | 20 |  |  | 1 | 1 | 18 |  |  | heat_wave_blackout:591, iv_fluid_shortage:285 |
| `text.field` | The text of a field | 833 | 13 | 535 | 90 | 45 | 150 |  |  | examples/piano_tuners:12, examples/piano_tuners:15 |
| `text.flow` | The text of a flow | 108 |  | 58 | 24 | 12 | 14 |  |  | cyber_learning_loop:125, cyber_learning_loop:129 |
| `text.outcome` | The text of a outcome | 17 | 2 | 2 | 5 | 4 | 4 |  |  | examples/reservoir:48, examples/reservoir:51 |
| `text.outcome.braces` | A text of a outcome with a name in braces | 6 |  |  | 1 | 2 | 3 |  |  | heat_wave_blackout:579, iv_fluid_shortage:252 |
| `text.output` | The text of a output | 121 | 1 | 64 | 28 | 13 | 15 |  |  | examples/piano_tuners:27, cyber_learning_loop:2090 |
| `text.share` | The text of a share | 12 |  |  | 8 |  | 4 |  |  | heat_wave_blackout:777, heat_wave_blackout:1067 |
| `text.status` | The text of a status | 101 |  | 3 | 43 | 28 | 27 |  |  | cyber_learning_loop:668, cyber_learning_loop:670 |
| `text.thing` | The text of a thing | 156 | 3 | 32 | 22 | 12 | 12 |  | 75 | examples/piano_tuners:8, examples/reservoir:9 |

## Functions and expressions

| Key | What it counts | Total | examples | cyber | heat | iv | water.scn | water main | 16 variants | Where |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `dist.declaration.pert` | `pert(...)` written in a declaration | 1 | 1 |  |  |  |  |  |  | examples/piano_tuners:10 |
| `dist.event.normal` | `normal(...)` written in an event: drawn at each firing | 1 |  | 1 |  |  |  |  |  | cyber_learning_loop:139 |
| `dist.normal.truncated` | `normal` with bounds: four arguments | 1 |  | 1 |  |  |  |  |  | cyber_learning_loop:139 |
| `expr` | Expressions, of every place | 2954 | 43 | 1251 | 630 | 284 | 463 | 1 | 282 | examples/piano_tuners:4, examples/piano_tuners:10 |
| `expr.and_or` | `and` / `or` | 113 |  | 9 | 49 | 26 | 29 |  |  | cyber_learning_loop:130, cyber_learning_loop:673 |
| `expr.bare_number` | A number with no unit, `0.3` | 1033 | 13 | 660 | 187 | 50 | 107 |  | 16 | examples/reservoir:16, examples/reservoir:16 |
| `expr.if_else` | A conditional value, `a if C else b` | 99 | 1 | 41 | 15 | 15 | 27 |  |  | examples/reservoir:35, cyber_learning_loop:84 |
| `expr.is` | Equality, `a is b` | 213 | 1 | 11 | 80 | 54 | 67 |  |  | examples/reservoir:34, cyber_learning_loop:84 |
| `expr.is_not` | Inequality, `a is not b` | 19 |  |  | 7 | 11 | 1 |  |  | heat_wave_blackout:626, heat_wave_blackout:643 |
| `expr.named_value` | A named value or a text in quotes, `"open"` | 417 | 3 | 21 | 127 | 100 | 121 |  | 45 | examples/reservoir:22, examples/reservoir:34 |
| `expr.not` | `not` | 8 |  | 1 | 5 |  | 2 |  |  | cyber_learning_loop:689, heat_wave_blackout:391 |
| `expr.power` | A power, `a ** b` | 32 |  | 30 | 2 |  |  |  |  | cyber_learning_loop:658, cyber_learning_loop:733 |
| `expr.reads_output` | An output that reads another output by its name | 13 |  |  | 8 | 5 |  |  |  | heat_wave_blackout:1294, heat_wave_blackout:1294 |
| `expr.t` | The time, `t` | 17 |  | 11 | 3 | 2 | 1 |  |  | cyber_learning_loop:31, cyber_learning_loop:31 |
| `expr.true_false` | `true` or `false` | 42 |  | 34 | 3 | 1 | 2 |  | 2 | cyber_learning_loop:56, cyber_learning_loop:182 |
| `expr.unit` | A number with its unit, `12 h` | 1289 | 24 | 409 | 294 | 118 | 224 | 1 | 219 | examples/piano_tuners:4, examples/piano_tuners:10 |
| `expr.unit.product` | A unit that is a product, `tuner-year` | 62 | 5 | 36 | 15 |  | 5 |  | 1 | examples/piano_tuners:10, examples/piano_tuners:10 |
| `expr.unit.quotient` | A unit that is a quotient, `L/h` | 404 | 11 | 116 | 36 | 37 | 81 |  | 123 | examples/piano_tuners:10, examples/piano_tuners:10 |
| `fn.count.event` | `count(e)` of an event | 9 |  |  | 3 | 2 | 4 |  |  | heat_wave_blackout:514, heat_wave_blackout:522 |
| `fn.count.in.status when` | `count()` read in a status when | 3 |  |  | 2 |  | 1 |  |  | heat_wave_blackout:514, heat_wave_blackout:899 |
| `fn.count.in.when` | `count()` read in a when | 6 |  |  | 1 | 2 | 3 |  |  | heat_wave_blackout:522, iv_fluid_shortage:249 |
| `fn.elapsed` | `elapsed(state)`: the time since a named state last changed | 4 |  |  |  |  | 4 |  |  | water/water.scn:335, water/water.scn:487 |
| `fn.elapsed.in.when` | `elapsed()` read in a when | 4 |  |  |  |  | 4 |  |  | water/water.scn:335, water/water.scn:487 |
| `fn.math.abs` | `abs()` | 4 |  |  | 2 | 2 |  |  |  | heat_wave_blackout:1232, heat_wave_blackout:1235 |
| `fn.math.clip` | `clip()` | 27 |  | 15 | 9 |  | 3 |  |  | cyber_learning_loop:31, cyber_learning_loop:34 |
| `fn.math.erf` | `erf()` | 14 |  | 14 |  |  |  |  |  | cyber_learning_loop:744, cyber_learning_loop:744 |
| `fn.math.exp` | `exp()` | 46 |  | 36 | 10 |  |  |  |  | cyber_learning_loop:31, cyber_learning_loop:31 |
| `fn.math.expm1` | `expm1()` | 3 |  | 3 |  |  |  |  |  | cyber_learning_loop:1836, cyber_learning_loop:1839 |
| `fn.math.ln` | `ln()` | 28 |  | 28 |  |  |  |  |  | cyber_learning_loop:90, cyber_learning_loop:163 |
| `fn.math.sqrt` | `sqrt()` | 23 |  | 23 |  |  |  |  |  | cyber_learning_loop:658, cyber_learning_loop:740 |
| `fn.max.list_with_extra` | `max(list.x, v)`: a list and a further argument | 2 |  | 2 |  |  |  |  |  | cyber_learning_loop:663, cyber_learning_loop:665 |
| `fn.max.scalar` | `max(a, b, ...)` of scalars | 108 |  | 79 | 16 | 4 | 9 |  |  | cyber_learning_loop:31, cyber_learning_loop:34 |
| `fn.max.scalar.args2` | `max` with that many arguments (4: four or more) | 107 |  | 79 | 16 | 3 | 9 |  |  | cyber_learning_loop:31, cyber_learning_loop:34 |
| `fn.max.scalar.args3` | `max` with that many arguments (4: four or more) | 1 |  |  |  | 1 |  |  |  | iv_fluid_shortage:565 |
| `fn.min.scalar` | `min(a, b, ...)` of scalars | 30 |  | 18 | 2 | 3 | 7 |  |  | cyber_learning_loop:264, cyber_learning_loop:373 |
| `fn.min.scalar.args2` | `min` with that many arguments (4: four or more) | 29 |  | 18 | 2 | 3 | 6 |  |  | cyber_learning_loop:264, cyber_learning_loop:373 |
| `fn.min.scalar.args4` | `min` with that many arguments (4: four or more) | 1 |  |  |  |  | 1 |  |  | water/water.scn:573 |
| `fn.since.event` | `since(e)` of an event | 30 |  | 1 | 19 | 5 | 5 |  |  | cyber_learning_loop:133, heat_wave_blackout:177 |
| `fn.since.in.when` | `since()` read in a when | 31 |  | 1 | 19 | 6 | 5 |  |  | cyber_learning_loop:133, heat_wave_blackout:177 |
| `fn.since.outcome` | `since(e.o)` of one outcome of an event | 1 |  |  |  | 1 |  |  |  | iv_fluid_shortage:105 |
| `fn.sum.list` | `sum(list.x)` over a list link or a template | 52 |  | 21 | 6 |  | 25 |  |  | cyber_learning_loop:157, cyber_learning_loop:159 |
| `fn.sum.list.link` | `sum(link.x)`: over a list link | 13 |  |  | 6 |  | 7 |  |  | heat_wave_blackout:728, heat_wave_blackout:728 |
| `fn.sum.list.template` | `sum(Template.x)`: over every instance of a template | 39 |  | 21 |  |  | 18 |  |  | cyber_learning_loop:157, cyber_learning_loop:159 |
| `type.unit` | A type written as a unit, `name: L/h = …` | 910 | 10 | 582 | 148 | 59 | 111 |  |  | examples/piano_tuners:20, examples/piano_tuners:22 |
| `type.unit.product` | A type whose unit is a product, `person-days` | 64 |  | 53 | 7 |  | 4 |  |  | cyber_learning_loop:72, cyber_learning_loop:82 |
| `type.unit.quotient` | A type whose unit is a quotient | 200 | 2 | 147 | 6 | 15 | 30 |  |  | examples/reservoir:10, examples/reservoir:13 |

## Names

| Key | What it counts | Total | examples | cyber | heat | iv | water.scn | water main | 16 variants | Where |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `name.declared.active` | A member or a thing named `active`, a word that the new language uses itself | 1 |  | 1 |  |  |  |  |  | cyber_learning_loop:192 |
| `name.declared.as.event` | A event whose name is a word of the new language | 4 |  | 1 | 1 | 1 | 1 |  |  | cyber_learning_loop:1510, heat_wave_blackout:590 |
| `name.declared.as.field` | A field whose name is a word of the new language | 23 | 2 | 5 | 5 | 6 | 5 |  |  | examples/piano_tuners:22, examples/reservoir:10 |
| `name.declared.as.flow` | A flow whose name is a word of the new language | 2 |  |  |  | 1 | 1 |  |  | iv_fluid_shortage:496, water/water.scn:673 |
| `name.declared.capacity` | A member or a thing named `capacity`, a word that the new language uses itself | 3 |  | 1 |  |  | 2 |  |  | cyber_learning_loop:232, water/water.scn:431 |
| `name.declared.done` | A member or a thing named `done`, a word that the new language uses itself | 1 | 1 |  |  |  |  |  |  | examples/piano_tuners:22 |
| `name.declared.draw` | A member or a thing named `draw`, a word that the new language uses itself | 1 |  |  |  |  | 1 |  |  | water/water.scn:673 |
| `name.declared.inflow` | A member or a thing named `inflow`, a word that the new language uses itself | 1 | 1 |  |  |  |  |  |  | examples/reservoir:10 |
| `name.declared.priority` | A member or a thing named `priority`, a word that the new language uses itself | 1 |  | 1 |  |  |  |  |  | cyber_learning_loop:260 |
| `name.declared.proportional` | A member or a thing named `proportional`, a word that the new language uses itself | 1 |  | 1 |  |  |  |  |  | cyber_learning_loop:56 |
| `name.declared.request` | A member or a thing named `request`, a word that the new language uses itself | 1 |  |  |  |  | 1 |  |  | water/water.scn:658 |
| `name.declared.size` | A member or a thing named `size`, a word that the new language uses itself | 1 |  | 1 |  |  |  |  |  | cyber_learning_loop:708 |
| `name.declared.start` | A member or a thing named `start`, a word that the new language uses itself | 4 |  | 1 | 1 | 1 | 1 |  |  | cyber_learning_loop:1510, heat_wave_blackout:590 |
| `name.declared.status` | A member or a thing named `status`, a word that the new language uses itself | 13 |  |  | 5 | 6 | 2 |  |  | heat_wave_blackout:147, heat_wave_blackout:376 |
| `name.declared.use` | A member or a thing named `use`, a word that the new language uses itself | 1 |  |  |  | 1 |  |  |  | iv_fluid_shortage:496 |
| `name.read.own` | A name of a member of the thing itself, written bare (`demand`) | 1995 | 9 | 1259 | 340 | 118 | 269 |  |  | examples/piano_tuners:20, examples/piano_tuners:24 |
| `name.read.template_list` | A member of every instance of a template, by its name (`Utility.unserved`) | 41 |  | 23 |  |  | 18 |  |  | cyber_learning_loop:157, cyber_learning_loop:159 |
| `name.read.thing_by_name` | A member of another thing, read by that thing's name (`relief.status`) | 1007 | 2 | 602 | 263 | 112 | 28 |  |  | examples/piano_tuners:26, examples/reservoir:44 |
| `name.read.thing_by_name.in_event` | A member of another thing, read by that thing's name (`relief.status`), in a trigger or a line of an event | 92 | 1 | 1 | 54 | 23 | 13 |  |  | examples/reservoir:44, cyber_learning_loop:139 |
| `name.read.via_link` | A name read through a link of the thing (`utility.service`, `buys.rate`) | 35 |  |  | 14 |  | 21 |  |  | heat_wave_blackout:728, heat_wave_blackout:728 |

## What the old compiler makes of each model

One row for each entry file, from `build_model`. The counts are of the compiled model, with each instance of a template written out. "Stock", "tally" and "number state" are what the compiler found for each number var (`Quantity.kind`: `stock`, `cumulative`, `variable`). The trigger kinds are those of `Trigger.kind`.

| Model | Things | Inputs | Stocks | Tallies | Number states | Named states | Formulas | Flows | in a share | Shares (order / proportional) | Flows with legs | Rules | discrete / timer / crossing / face | Outputs | cumulative / level | Proved cumulative | Unestimated | Sum checks | Runs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `examples/piano_tuners` | 1 | 3 | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 0 / 0 | 0 | 0 | 0 / 0 / 0 / 0 | 1 | 1 / 0 | 1 | 0 | 0 | 1 |
| `examples/reservoir` | 2 | 4 | 1 | 2 | 0 | 1 | 0 | 2 | 0 | 0 / 0 | 0 | 1 | 0 / 0 / 1 / 0 | 2 | 2 / 0 | 2 | 0 | 0 | 1 |
| `cyber_learning_loop` | 28 | 237 | 46 | 6 | 6 | 3 | 756 | 154 | 107 | 0 / 33 | 26 | 8 | 2 / 6 / 0 / 0 | 64 | 5 / 59 | 2 | 3 | 0 | 12 |
| `heat_wave_blackout` | 30 | 112 | 41 | 50 | 12 | 13 | 96 | 72 | 60 | 0 / 22 | 6 | 40 | 16 / 20 / 4 / 0 | 37 | 21 / 16 | 18 | 4 | 13 | 11 |
| `iv_fluid_shortage` | 12 | 29 | 10 | 13 | 0 | 10 | 18 | 13 | 8 | 2 / 2 | 1 | 27 | 13 / 8 / 6 / 0 | 19 | 16 / 3 | 16 | 0 | 2 | 7 |
| `water` | does not build alone: ModelError: evidence/sources/sc43_bea2026_cagdp2_ak: Local record is not used by this scenario; evidence/sources/sc43_bea2026_cagdp2_ca: Local record is not used by this scenario; evidence/sources/sc43_bea2026_ca | | | | | | | | | | | | | | | | | | |
| `water/variants/asheville` | 10 | 54 | 11 | 22 | 6 | 14 | 45 | 17 | 10 | 1 / 4 | 3 | 34 | 15 / 14 / 5 / 0 | 16 | 8 / 8 | 4 | 4 | 9 | 5 |
| `water/variants/auburn` | 10 | 54 | 11 | 22 | 6 | 14 | 45 | 17 | 10 | 1 / 4 | 3 | 34 | 15 / 14 / 5 / 0 | 16 | 8 / 8 | 4 | 4 | 9 | 5 |
| `water/variants/austin` | 10 | 54 | 11 | 22 | 6 | 14 | 45 | 17 | 10 | 1 / 4 | 3 | 34 | 15 / 14 / 5 / 0 | 16 | 8 / 8 | 4 | 4 | 9 | 5 |
| `water/variants/camden` | 10 | 54 | 11 | 22 | 6 | 14 | 45 | 17 | 10 | 1 / 4 | 3 | 34 | 15 / 14 / 5 / 0 | 16 | 8 / 8 | 4 | 4 | 9 | 5 |
| `water/variants/cape_may` | 11 | 78 | 16 | 35 | 11 | 22 | 73 | 30 | 18 | 2 / 4 | 6 | 52 | 28 / 16 / 8 / 0 | 16 | 8 / 8 | 4 | 4 | 12 | 5 |
| `water/variants/clayton` | 10 | 54 | 11 | 22 | 6 | 14 | 45 | 17 | 10 | 1 / 4 | 3 | 34 | 15 / 14 / 5 / 0 | 16 | 8 / 8 | 4 | 4 | 9 | 5 |
| `water/variants/el_dorado` | 12 | 81 | 17 | 38 | 11 | 22 | 77 | 32 | 19 | 2 / 4 | 6 | 53 | 28 / 16 / 9 / 0 | 16 | 8 / 8 | 4 | 4 | 13 | 5 |
| `water/variants/jackson` | 10 | 54 | 11 | 22 | 6 | 14 | 45 | 17 | 10 | 1 / 4 | 3 | 34 | 15 / 14 / 5 / 0 | 16 | 8 / 8 | 4 | 4 | 9 | 5 |
| `water/variants/jamestown` | 17 | 113 | 24 | 57 | 16 | 30 | 125 | 49 | 29 | 3 / 4 | 9 | 73 | 41 / 18 / 14 / 0 | 16 | 8 / 8 | 4 | 4 | 18 | 5 |
| `water/variants/juneau` | 10 | 54 | 11 | 22 | 6 | 14 | 45 | 17 | 10 | 1 / 4 | 3 | 34 | 15 / 14 / 5 / 0 | 16 | 8 / 8 | 4 | 4 | 9 | 5 |
| `water/variants/lehigh` | 12 | 81 | 17 | 38 | 11 | 22 | 77 | 32 | 19 | 2 / 4 | 6 | 53 | 28 / 16 / 9 / 0 | 16 | 8 / 8 | 4 | 4 | 13 | 5 |
| `water/variants/los_angeles` | 10 | 54 | 11 | 22 | 6 | 14 | 45 | 17 | 10 | 1 / 4 | 3 | 34 | 15 / 14 / 5 / 0 | 16 | 8 / 8 | 4 | 4 | 9 | 5 |
| `water/variants/lumberton` | 10 | 54 | 11 | 22 | 6 | 14 | 45 | 17 | 10 | 1 / 4 | 3 | 34 | 15 / 14 / 5 / 0 | 16 | 8 / 8 | 4 | 4 | 9 | 5 |
| `water/variants/minot` | 12 | 81 | 17 | 35 | 11 | 22 | 77 | 31 | 18 | 2 / 4 | 6 | 53 | 28 / 16 / 9 / 0 | 16 | 8 / 8 | 4 | 4 | 13 | 5 |
| `water/variants/richmond` | 10 | 54 | 11 | 22 | 6 | 14 | 45 | 17 | 10 | 1 / 4 | 3 | 34 | 15 / 14 / 5 / 0 | 16 | 8 / 8 | 4 | 4 | 9 | 5 |
| `water/variants/washington_dc` | 23 | 173 | 38 | 92 | 26 | 46 | 197 | 82 | 48 | 5 / 4 | 15 | 113 | 67 / 22 / 24 / 0 | 16 | 8 / 8 | 4 | 4 | 28 | 6 |

### The outputs that the old compiler proved cumulative

`check.py` lists these for a translation. The new compiler must prove that each of them never falls.

- examples/piano_tuners: `tunings_done`
- examples/reservoir: `reservoir.risk_time.output`, `reservoir.spilled.output`
- cyber_learning_loop: `capabilities_burned`, `total_attacks`
- heat_wave_blackout: `casualties`, `confined_65_to_74.deaths`, `confined_75_and_over.deaths`, `confined_under_65.deaths`, `deaths`, `device_admissions`, `device_users_65_to_74.admissions`, `device_users_65_to_74.deaths`, `device_users_75_and_over.admissions`, `device_users_75_and_over.deaths`, `device_users_under_65.admissions`, `device_users_under_65.deaths`, `places.admissions`, `residents_65_to_74.deaths`, `residents_75_and_over.deaths`, `residents_under_65.deaths`, `supply.resident_hours`, `thermal_exposure`
- iv_fluid_shortage: `fluid_sent_elsewhere`, `high_risk_patients.casualties`, `high_risk_patients.deaths`, `high_risk_patients.rescued.output`, `high_risk_patients.serious_survivors`, `high_risk_patients.unresolved.output`, `manufacturer.hours_out.output`, `manufacturer.output_loss`, `other_care_reserve.deficit.output`, `other_care_reserve.shortage_days`, `people_needing_courses`, `procedure_loss`, `release_work_done`, `resuscitation_patients.unserved.output`, `resuscitation_reserve.deficit.output`, `timely_courses`
- water/variants/asheville and 15 more: `hospital_hours_constrained`, `person_days_lost`, `rework_caused`, `unserved_volume`

### Other keys of the compiled models, summed over the entry files

| Key | Sum |
| --- | ---: |
| `allocation.priority` | 28 |
| `allocation.proportional` | 121 |
| `check.input` | 68 |
| `check.state` | 2 |
| `computed` | 1946 |
| `coupling` | 111 |
| `coupling.flows` | 287 |
| `entity` | 260 |
| `entity.actor` | 1 |
| `flow` | 668 |
| `flow.in_allocation` | 426 |
| `flow.outside_to_store` | 61 |
| `flow.store_to_outside` | 50 |
| `flow.store_to_store` | 557 |
| `label` | 206 |
| `mode` | 331 |
| `outcome.cumulative` | 173 |
| `outcome.lag` | 2 |
| `outcome.nonnegative` | 361 |
| `outcome.proven_cumulative` | 103 |
| `outcome.status.estimated` | 308 |
| `outcome.status.unestimated` | 71 |
| `outcome.stock` | 206 |
| `parameter` | 1532 |
| `partition` | 202 |
| `quantity.cumulative` | 587 |
| `quantity.stock` | 338 |
| `quantity.variable` | 164 |
| `quantity.with_maximum` | 54 |
| `quantity.with_size` | 734 |
| `rule` | 813 |
| `rule.choice` | 1 |
| `rule.delay` | 44 |
| `rule.each` | 0 |
| `rule.extras` | 1 |
| `rule.keep` | 0 |
| `rule.named` | 93 |
| `rule.once` | 150 |
| `rule.outcomes1` | 781 |
| `rule.outcomes2` | 5 |
| `rule.outcomes3` | 27 |
| `rule.trigger.crossing` | 134 |
| `rule.trigger.crossing.op.<=` | 133 |
| `rule.trigger.crossing.op.>=` | 1 |
| `rule.trigger.discrete` | 401 |
| `rule.trigger.timer` | 278 |

