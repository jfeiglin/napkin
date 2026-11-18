# Parse report

`make_report.py` makes this file again. Nothing here is written by hand.

- Python 3.13.18; `napkin` from `/home/user/napkin-base` (the base commit).
- Load of the machine when this ran (1, 5, 15 min): 3.01, 3.42, 2.65.
- Corpus: 30 corpus files are the blocks of the spec, byte for byte.
- Time to parse the 27 files of the corpus (276 lines), best of three runs: 4.9 ms.

## The blocks of the spec

Each fenced `text` block of `spec.md` is one file. `Stands in` is the place where its lines
stand: most blocks of the spec are fragments (`corpus/MANIFEST.tsv`).

| File | Spec lines | Stands in | Result | What the tree holds |
| --- | --- | --- | --- | --- |
| `01-grinder.scn` | 42-47 | file | parsed | 1 entities, 2 values, 1 events, 1 stages, 1 assignments |
| `02-range-and-assert.scn` | 69-73 | members | parsed | 1 values, 1 asserts |
| `03-collection-literals.scn` | 87-88 | members | parsed | 2 values |
| `04-formulas.scn` | 104-106 | members | parsed | 3 values |
| `05-reportable-bindings.scn` | 114-115 | file | parsed | 2 values |
| `06-status-cases.scn` | 125-133 | file | parsed | 1 entities, 1 values, 3 status cases |
| `07-none-and-record.scn` | 143-149 | file | parsed | 2 values, 1 records |
| `08-input-draw.scn` | 159-159 | members | parsed | 1 values |
| `09-tank-clinic.scn` | 171-177 | file | parsed | 2 entities, 1 values, 2 properties, 1 flows |
| `10-local-allocation.scn` | 236-247 | file | parsed | 3 entities, 1 values, 4 properties, 2 flows |
| `11-network.scn` | 269-318 | file | parsed | 1 entities, 3 templates, 3 tables, 17 values, 2 properties, 1 events, 1 triggers, 1 stages, 3 flows, 1 solvers, 1 objectives, 1 assignments, 1 starts, 1 resets |
| `12-staffing.scn` | 380-394 | file | parsed | 1 entities, 4 values, 1 solvers, 2 unknowns, 1 objectives |
| `13-water-electricity.scn` | 404-445 | file | parsed | 6 entities, 7 values, 4 properties, 5 flows, 1 solvers, 4 objectives |
| `14-provider-limit.scn` | 455-482 | file | parsed | 3 entities, 6 values, 4 properties, 2 flows, 1 solvers, 3 objectives |
| `15-record-delivery.scn` | 506-510 | file | parsed | 1 entities, 1 values, 1 events, 1 stages, 1 assignments |
| `16-switch.scn` | 522-528 | event | parsed | 1 events, 1 stages, 1 assignments, 2 starts, 1 switches |
| `17-broadcast.scn` | 536-537 | event | parsed | 1 events, 1 stages, 1 starts |
| `18-inspect.scn` | 557-567 | members | parsed | 1 events, 3 stages, 1 gates, 1 assignments, 2 starts |
| `19-trigger.scn` | 593-602 | members | parsed | 1 values, 1 events, 1 triggers, 1 stages, 2 assignments, 1 starts, 1 resets |
| `20-clock-trigger.scn` | 608-614 | members | parsed | 1 events, 1 triggers, 1 stages, 1 assignments, 1 starts, 1 resets |
| `21-repair.scn` | 640-643 | members | parsed | 1 events, 1 stages, 1 assignments, 1 starts |
| `22-legs.scn` | 657-661 | members | parsed | 2 properties, 3 flows |
| `23-reserve-delivery.scn` | 687-695 | members | parsed | 1 values, 1 properties, 1 events, 1 stages, 1 gates, 1 flows, 1 moves |
| `24-reserve-at-outset.scn` | 701-713 | members | parsed | 1 values, 2 properties, 1 events, 2 stages, 1 gates, 1 flows, 1 assignments, 1 moves |
| `25-changing-rate.scn` | 721-727 | members | parsed | 2 values, 1 properties, 1 events, 1 gates, 1 flows |
| `26-diff.scn` | 739-741 | file | parsed | 3 values |
| `27-record-claims.scn` | 763-766 | file | parsed | 1 records |

27 of 27 files parse.

The 3 `csv` blocks are in `corpus/data/` (`places.csv`, `readings.csv`, `routes.csv`). The parser reads the line that names a table (`sites: Place from "places.csv"`); it does not read the table. The headers of two of them hold a unit after a colon (`supply_limit: W`), as the present tables do.

### The same block in another place

A block is read where it stands. This table shows what each of the other two places says for it:
the place of a line is part of its meaning.

| File | file | members | event |
| --- | --- | --- | --- |
| `01-grinder.scn` | parsed (its place) | refused, line 1 | refused, line 1 |
| `02-range-and-assert.scn` | parsed | parsed (its place) | refused, line 1 |
| `03-collection-literals.scn` | parsed | parsed (its place) | parsed |
| `04-formulas.scn` | parsed | parsed (its place) | parsed |
| `05-reportable-bindings.scn` | parsed (its place) | parsed | parsed |
| `06-status-cases.scn` | parsed (its place) | refused, line 1 | refused, line 1 |
| `07-none-and-record.scn` | parsed (its place) | refused, line 7 | refused, line 7 |
| `08-input-draw.scn` | parsed | parsed (its place) | refused, line 1 |
| `09-tank-clinic.scn` | parsed (its place) | refused, line 1 | refused, line 1 |
| `10-local-allocation.scn` | parsed (its place) | refused, line 1 | refused, line 1 |
| `11-network.scn` | parsed (its place) | refused, line 1 | refused, line 1 |
| `12-staffing.scn` | parsed (its place) | refused, line 1 | refused, line 1 |
| `13-water-electricity.scn` | parsed (its place) | refused, line 1 | refused, line 1 |
| `14-provider-limit.scn` | parsed (its place) | refused, line 1 | refused, line 1 |
| `15-record-delivery.scn` | parsed (its place) | refused, line 1 | refused, line 1 |
| `16-switch.scn` | refused, line 1 | refused, line 1 | parsed (its place) |
| `17-broadcast.scn` | refused, line 1 | refused, line 1 | parsed (its place) |
| `18-inspect.scn` | refused, line 1 | parsed (its place) | refused, line 1 |
| `19-trigger.scn` | refused, line 1 | parsed (its place) | refused, line 1 |
| `20-clock-trigger.scn` | refused, line 1 | parsed (its place) | refused, line 1 |
| `21-repair.scn` | refused, line 1 | parsed (its place) | refused, line 1 |
| `22-legs.scn` | refused, line 1 | parsed (its place) | parsed |
| `23-reserve-delivery.scn` | refused, line 1 | parsed (its place) | refused, line 1 |
| `24-reserve-at-outset.scn` | refused, line 1 | parsed (its place) | refused, line 1 |
| `25-changing-rate.scn` | refused, line 1 | parsed (its place) | refused, line 1 |
| `26-diff.scn` | parsed (its place) | parsed | parsed |
| `27-record-claims.scn` | parsed (its place) | refused, line 1 | refused, line 1 |

## The notation that the spec shows inline

`corpus/inline.txt`, one piece on each line. An expression is shown as a tree in brackets;
a line is shown as the nodes of its tree.

154 of 154 pieces parse (91 expression, 22 declaration, 12 statement, 6 type, 6 step, 6 trigger, 4 range, 4 setup, 3 objective).

| Spec line | Kind | Notation | What the parser gives |
| ---: | --- | --- | --- |
| 17 | declaration | `beans: g = 8` | `Declare name=beans type=g value=8` |
| 18 | expression | `Route.instances` | `Route.instances` |
| 19 | statement | `grinder.refill.start(50 g)` | `Start call=grinder.refill.start(50 g)` |
| 29 | expression | `grinder.beans` | `grinder.beans` |
| 29 | expression | `grinder.refill` | `grinder.refill` |
| 32 | expression | `grinder.refill.occurrences.at(t).status` | `(member (method grinder.refill.occurrences at t) status)` |
| 33 | expression | `pump.fill.actual_rate` | `pump.fill.actual_rate` |
| 34 | expression | `tank.water.outflow.flows` | `tank.water.outflow.flows` |
| 35 | expression | `provider.charging` | `provider.charging` |
| 35 | expression | `clinic.staffing` | `clinic.staffing` |
| 50 | declaration | `beans: g = 8 g` | `Declare name=beans type=g value=8 g` |
| 50 | expression | `low_on_beans` | `low_on_beans` |
| 54 | type | `bool` | `WordType bool` |
| 54 | type | `enum[OPEN, CLOSED]` | `EnumType enum[OPEN, CLOSED]` |
| 54 | expression | `1 if ready else 0` | `(if ready 1 0)` |
| 54 | expression | `OPEN` | `(case OPEN)` |
| 56 | declaration | `water = 20 L` | `Declare name=water value=20 L` |
| 58 | expression | `clinic.water` | `clinic.water` |
| 58 | expression | `supply.initial_water` | `supply.initial_water` |
| 64 | expression | `2 * this.delay` | `(mul 2 this.delay)` |
| 66 | range | `[lo, hi]` | `Range [lo, hi]` |
| 66 | expression | `x in [lo, hi]` | `(within x lo hi)` |
| 76 | range | `[x, x]` | `Range [x, x]` |
| 76 | declaration | `ok = (samples.draw() in [lo, hi])` | `Declare name=ok value=(samples.draw() in [lo, hi])` |
| 76 | statement | `ok = (samples.draw() in [lo, hi])` | `Assign target=ok op== value=(samples.draw() in [lo, hi])` |
| 76 | expression | `lo <= x and x < hi` | `(and (compare lo le x) (compare x lt hi))` |
| 78 | expression | `max(0, need - use_rate)` | `(call max 0 (sub need use_rate))` |
| 80 | expression | `48 h / 2` | `(div (q 48 h) 2)` |
| 84 | type | `<T>` | `CollectionType <T>` |
| 84 | expression | `grinder.refill.occurrences` | `grinder.refill.occurrences` |
| 84 | expression | `water.outflow.flows` | `water.outflow.flows` |
| 91 | expression | `routes.limit` | `routes.limit` |
| 91 | statement | `machines.repair.start()` | `Start call=machines.repair.start()` |
| 91 | expression | `count(c)` | `(call count c)` |
| 91 | expression | `count(c.done)` | `(call count c.done)` |
| 91 | expression | `count(c.amount)` | `(call count c.amount)` |
| 91 | expression | `sum(c.amount)` | `(call sum c.amount)` |
| 93 | expression | `Route.instances.where(destination == this)` | `(method Route.instances where (compare destination eq this))` |
| 93 | expression | `Place.instances.where(critical)` | `(method Place.instances where critical)` |
| 93 | expression | `customers.by(rank).delivery` | `(member (method customers by rank) delivery)` |
| 95 | expression | `c.at(x)` | `(method c at x)` |
| 95 | expression | `Reading.instances.by(hour).at(t).factor` | `(member (method (method Reading.instances by hour) at t) factor)` |
| 95 | expression | `tiers.by(threshold).at(volume).price` | `(member (method (method tiers by threshold) at volume) price)` |
| 97 | expression | `Machine.instances` | `Machine.instances` |
| 101 | type | `formula(bool)` | `FormulaType formula(bool)` |
| 101 | expression | `formula(expression)` | `(formula expression)` |
| 109 | type | `formula(T)` | `FormulaType formula(T)` |
| 118 | expression | `Utility.instances` | `Utility.instances` |
| 118 | expression | `reservoir.spilled` | `reservoir.spilled` |
| 138 | declaration | `net_change: L = 0 in [-20, 20]` | `Declare name=net_change type=L value=0 range=[-20, 20]` |
| 154 | expression | `normal(2, 3)` | `(call normal 2 3)` |
| 154 | expression (derived) | `repair_times.mean` | `repair_times.mean` |
| 154 | expression (derived) | `repair_times.std` | `repair_times.std` |
| 154 | expression (derived) | `repair_times.draw()` | `(method repair_times draw)` |
| 180 | expression | `clinic.delivery.capacity` | `clinic.delivery.capacity` |
| 180 | expression | `clinic.delivery.request` | `clinic.delivery.request` |
| 180 | statement | `tank.water = 10 L` | `Assign target=tank.water op== value=10 L` |
| 182 | declaration | `flow name: source -> sink` | `FlowDecl name=name kind=directed source=source sink=sink` |
| 182 | setup | `clinic.delivery.request = 3 L/h` | `Property path=clinic.delivery.request value=3 L/h` |
| 184 | declaration | `flow link: west.water <-> east.water` | `FlowDecl name=link kind=reversible source=west.water sink=east.water` |
| 184 | expression | `link.actual_rate` | `link.actual_rate` |
| 188 | expression | `west.water.outflow.flows` | `west.water.outflow.flows` |
| 188 | expression | `east.water.inflow.flows` | `east.water.inflow.flows` |
| 188 | expression | `link.forward` | `link.forward` |
| 188 | expression | `max(link.actual_rate, 0 L/h)` | `(call max link.actual_rate (q 0 L/h))` |
| 189 | expression | `link.backward` | `link.backward` |
| 189 | expression | `max(-link.actual_rate, 0 L/h)` | `(call max (neg link.actual_rate) (q 0 L/h))` |
| 191 | expression | `priority(link.forward, backup)` | `(call priority link.forward backup)` |
| 191 | expression | `west.water.outflow` | `west.water.outflow` |
| 206 | expression | `main.sink` | `main.sink` |
| 206 | expression | `sum(water.outflow.flows.actual_rate)` | `(call sum water.outflow.flows.actual_rate)` |
| 206 | expression | `water.outflow.actual_rate` | `water.outflow.actual_rate` |
| 214 | expression | `count(deliver.occurrences)` | `(call count deliver.occurrences)` |
| 214 | expression | `count(tank.water.outflow.flows)` | `(call count tank.water.outflow.flows)` |
| 214 | expression | `sum(tank.water.outflow.flows.request)` | `(call sum tank.water.outflow.flows.request)` |
| 214 | expression | `tank.water.outflow.actual_rate` | `tank.water.outflow.actual_rate` |
| 221 | expression | `deliver.occurrences.at(t).pipe.request` | `(member (member (method deliver.occurrences at t) pipe) request)` |
| 225 | declaration | `capacity = 0 L/h` | `Declare name=capacity value=0 L/h` |
| 225 | declaration | `request = 0 L/h` | `Declare name=request value=0 L/h` |
| 225 | declaration | `capacity = none` | `Declare name=capacity value=none` |
| 229 | range | `[0, 0]` | `Range [0, 0]` |
| 229 | declaration | `remaining: L = amount` | `Declare name=remaining type=L value=amount` |
| 231 | declaration (derived) | `flow through: SOURCE -> SINK` | `FlowDecl name=through kind=directed source=SOURCE sink=SINK` |
| 250 | expression | `priority(a, b)` | `(call priority a b)` |
| 252 | expression | `proportional()` | `(call proportional)` |
| 252 | expression | `priority(customers.by(rank).delivery)` | `(call priority (member (method customers by rank) delivery))` |
| 254 | setup | `clinic.water.inflow.request = 6 L/h` | `Property path=clinic.water.inflow.request value=6 L/h` |
| 254 | setup | `clinic.water.inflow.allocation = priority(main, backup)` | `Property path=clinic.water.inflow.allocation value=priority(main, backup)` |
| 254 | setup | `main.capacity = 4 L/h` | `Property path=main.capacity value=4 L/h` |
| 254 | declaration | `inflow.request = formula(max(0 L, 15 L - this.water) / (2 h))` | `Property path=inflow.request value=formula(max(0 L, 15 L - this.water) / (2 h))` |
| 260 | declaration | `routes = Route.instances` | `Declare name=routes value=Route.instances` |
| 260 | expression | `routes.carried.actual_rate` | `routes.carried.actual_rate` |
| 262 | range | `[0 W, 10 W]` | `Range [0 W, 10 W]` |
| 353 | objective | `minimize(sum(places.where(critical).unmet))` | `Objective direction=minimize value=sum(places.where(critical).unmet)` |
| 353 | objective | `minimize(sum(places.unmet))` | `Objective direction=minimize value=sum(places.unmet)` |
| 362 | expression | `links.junction_clinic.carried` | `links.junction_clinic.carried` |
| 362 | expression | `links.garden_junction.carried` | `links.garden_junction.carried` |
| 368 | expression | `a + b <= 4 W` | `(compare (add a b) le (q 4 W))` |
| 368 | expression | `b + c <= 5 W` | `(compare (add b c) le (q 5 W))` |
| 368 | declaration | `unmet = formula(max(0 W, this.use.request - this.use.actual_rate))` | `Declare name=unmet value=formula(max(0 W, this.use.request - this.use.actual_rate))` |
| 373 | objective | `minimize(sum(consumers.unmet))` | `Objective direction=minimize value=sum(consumers.unmet)` |
| 375 | expression | `a + b + c <= 9 W - b` | `(compare (add (add a b) c) le (sub (q 9 W) b))` |
| 397 | expression | `clinic.staffing.care` | `clinic.staffing.care` |
| 397 | expression | `clinic.staffing.outreach` | `clinic.staffing.outreach` |
| 448 | expression | `pump.power.actual_rate` | `pump.power.actual_rate` |
| 448 | expression | `pump.fill.actual_rate` | `pump.fill.actual_rate` |
| 485 | expression | `formula(min(6 W, (10 Wh - this.energy) / (1 h)))` | `(formula (call min (q 6 W) (div (sub (q 10 Wh) this.energy) (q 1 h))))` |
| 493 | declaration | `level = 0 in [-30, 30]` | `Declare name=level value=0 range=[-30, 30]` |
| 503 | declaration | `refill = event(amount: g):` | `EventDecl name=refill params=[amount: g]` |
| 503 | declaration | `readonly refill = event(amount: g):` | `EventDecl name=refill modifier=readonly params=[amount: g]` |
| 513 | statement | `tank.record_delivery.start(20 L)` | `Start call=tank.record_delivery.start(20 L)` |
| 519 | type | `enum[REPAIR, RESUME]` | `EnumType enum[REPAIR, RESUME]` |
| 540 | statement | `this.machines.repair.start()` | `Start call=this.machines.repair.start()` |
| 546 | expression | `this.water` | `this.water` |
| 546 | expression | `this.customer.water` | `this.customer.water` |
| 548 | declaration | `doubled = amount * 2` | `Declare name=doubled value=amount * 2` |
| 554 | expression | `this.staffing.care` | `this.staffing.care` |
| 572 | step | `until C` | `Gate condition=C` |
| 572 | step | `after 0 h:` | `Stage delay=0 h` |
| 574 | statement | `move batch from batch to this.supply` | `Move amount=batch source=batch destination=this.supply` |
| 574 | statement | `this.repair_succeeded.start()` | `Start call=this.repair_succeeded.start()` |
| 582 | step | `after D when C:` | `Stage delay=D guard=C` |
| 582 | step | `after 2 h when this.water < 10 L:` | `Stage delay=2 h guard=this.water < 10 L` |
| 583 | step | `when C:` | `Trigger condition=C` |
| 583 | trigger | `reset when C` | `Reset kind=when value=C` |
| 584 | step | `when this.water <= 10 L:` | `Trigger condition=this.water <= 10 L` |
| 605 | trigger | `reset when false` | `Reset kind=when value=false` |
| 605 | statement | `grinder.refill.start(20 g)` | `Start call=grinder.refill.start(20 g)` |
| 619 | trigger | `shift = this.shift` | `Capture name=shift value=this.shift` |
| 619 | trigger | `reset when this.shift != shift` | `Reset kind=when value=this.shift != shift` |
| 619 | trigger | `ready_at = t + 3 h` | `Capture name=ready_at value=t + 3 h` |
| 619 | trigger | `reset when t >= ready_at and this.water >= 12 L` | `Reset kind=when value=t >= ready_at and this.water >= 12 L` |
| 628 | expression | `count(grinder.refill.occurrences)` | `(call count grinder.refill.occurrences)` |
| 629 | expression | `count(grinder.refill.occurrences.done)` | `(call count grinder.refill.occurrences.done)` |
| 630 | expression | `any(grinder.refill.occurrences.active)` | `(call any grinder.refill.occurrences.active)` |
| 632 | expression | `since(grinder.refill)` | `(call since grinder.refill)` |
| 635 | expression | `count(grinder.refill.occurrences) > 0` | `(compare (call count grinder.refill.occurrences) gt 0)` |
| 648 | expression | `count(this.service_restored.occurrences) > 0 and since(this.service_restored) >= 3 h` | `(and (compare (call count this.service_restored.occurrences) gt 0) (compare (call since this.service_restored) ge (q 3 h)))` |
| 652 | expression | `this.supply.outflow.capacity` | `this.supply.outflow.capacity` |
| 664 | expression | `formula(this.crew.pace_now)` | `(formula this.crew.pace_now)` |
| 664 | expression | `restore.served_fraction` | `restore.served_fraction` |
| 664 | expression | `restore.labor.actual_rate` | `restore.labor.actual_rate` |
| 664 | expression | `restore.work.actual_rate` | `restore.work.actual_rate` |
| 666 | expression | `restore.actual_rate` | `restore.actual_rate` |
| 716 | statement | `delivery.request = speeds.draw()` | `Assign target=delivery.request op== value=speeds.draw()` |
| 732 | statement | `tank.receive.start(20 L, 5 L/h, 5 L/h^2)` | `Start call=tank.receive.start(20 L, 5 L/h, 5 L/h^2)` |
| 736 | expression | `y.diff(z)` | `(method y diff z)` |
| 736 | expression | `this.pressure` | `this.pressure` |
| 744 | declaration | `x = 2 * z` | `Declare name=x value=2 * z` |
| 748 | declaration | `assert repair_threshold < failure_threshold @policy` | `Check condition=repair_threshold < failure_threshold evidence=[@policy]` |
| 791 | statement | `move amount from source to destination` | `Move amount=amount source=source destination=destination` |
| 795 | expression | `sites.clinic` | `sites.clinic` |
| 829 | declaration | `weekly_unserved: people = none @no_cohorts` | `Declare name=weekly_unserved type=people value=none evidence=[@no_cohorts]` |
| 859 | expression | `4 <= x + y <= 6` | `(compare 4 le (add x y) le 6)` |

## The notation that the parser refuses

`corpus/refused.txt`: notation of the present compiler that the spec quotes, candidates that
the rulings leave out, and what the rules of FINDINGS.md refuse. Each piece must be refused
with a message that holds the part written in the file.

72 of 72 pieces are refused with their message.

| From | Kind | Notation | Message |
| --- | --- | --- | --- |
| spec 80 | expression | `48 h/2` | the unit h is followed by /: a unit ends at a space, a comma, a closing bracket or a colon. Write a space on each side of an operator that follows a unit: 48 h / 2 |
| spec 97 | declaration | `let machines = Machine` | let is no longer a word of the language: a value is `name = value`, and a calculation that follows its inputs is `name = formula(...)` |
| spec 97 | expression | `machines.2` | a dot is followed by the name of a member: a row of a table is named by its id |
| spec 750 | declaration | `assert tank.gate is "closed"` | equality is == and inequality is !=: `is` is no longer a word of the language |
| spec 752 | declaration | `assert 1 + 1 is 2.05 within 0.1` | equality is == and inequality is !=: `is` is no longer a word of the language |
| spec 752 | declaration | `assert true within undefined_name` | there is no `within`: a tolerance is a closed interval, assert x in [lo, hi] |
| spec 791 | statement | `move(source, destination, amount)` | a move has one form: move amount from source to destination |
| spec 572 | step | `at T:` | there is no `at T:` step in this version: a step waits a duration, `after D:` |
| spec 750 | declaration | `assert initially tank.gate == CLOSED` | there is no `assert initially` in this version: assert over the inputs that give the start |
| rule | expression | `a < b > c` | a chain of comparisons points one way, as in lo <= x < hi: join the others with `and` |
| rule | expression | `a == b == c` | a chain of comparisons points one way, as in lo <= x < hi: join the others with `and` |
| rule | expression | `<a + b>` | a collection literal lists its members between < and >, as in <a, b>: a member with an operator needs brackets, and a comparison with < has a value on its left |
| rule | expression | `<a, b` | a collection literal lists its members between < and >, as in <a, b>: a member with an operator needs brackets, and a comparison with < has a value on its left |
| rule | expression | `[a, b]` | an interval stands after `in`: x in [lo, hi]. A collection is written <a, b> |
| rule | expression | `c[1]` | a value has no index: a member of a collection is read by its key, c.at(key) |
| rule | statement | `ok = x in [lo, hi]` | to keep the result of a membership test, put the whole test in brackets: ok = (x in [lo, hi]) |
| rule | declaration | `ok = a if x in [lo, hi] else b` | to keep the result of a membership test, put the whole test in brackets: ok = (x in [lo, hi]) |
| rule | expression | `a < b in [lo, hi]` | a membership test is not chained with a comparison: put one of them in brackets |
| rule | expression | `x not in [lo, hi]` | there is no `not in`: write not (x in [lo, hi]) |
| rule | expression | `x in lo` | in is followed by a closed interval: x in [lo, hi] |
| rule | declaration | `delay: h = 3 in [0, 1] in [0, 2]` | nothing more belongs on this line |
| rule | expression | `a <-> b` | <-> joins the two ends of a flow (`flow name: source <-> sink`): it is no part of an expression |
| rule | expression | `a -> b` | -> joins the two ends of a flow (`flow name: source -> sink`): it is no part of an expression |
| rule | declaration | `flow f: SINK -> a` | SOURCE stands on the left of -> and SINK on the right |
| rule | declaration | `flow f: SOURCE <-> a` | a reversible route joins two stocks: SOURCE and SINK stand at an end of a -> flow |
| rule | expression | `x = y` | one = on a line: equality inside an expression is == |
| rule | declaration | `x = y = z` | one = on a line: equality inside an expression is == |
| rule | expression | `3 h-2 h` | the unit h is followed by -: a unit ends at a space, a comma, a closing bracket or a colon. Write a space on each side of an operator that follows a unit: 48 h / 2 |
| rule | expression | `3 L/h*2` | the unit L/h is followed by *: a unit ends at a space, a comma, a closing bracket or a colon. Write a space on each side of an operator that follows a unit: 48 h / 2 |
| rule | expression | `48h` | 48h: a unit follows its number after one space, as in 48 h |
| rule | expression | `3  h` | 3 h: a unit follows its number after exactly one space, and two values need an operator between them |
| rule | expression | `x ^ 2` | a power of a value is a ** b; ^ writes the power of a unit, such as 5 m^2 |
| rule | type | `L//h` | L//h is not a unit: a unit is names joined by / (divide) and - (multiply), each with an optional whole power, as in L/h^2 |
| old | expression | `100 {item}/h` | { is not a part of the language: a unit takes no text parameter: each field of a template has one dimension |
| rule | declaration | `Beans: g = 8` | the name of a value starts with a small letter: a capital starts a template or a member of an enum |
| rule | declaration | `gate: enum[open, closed] = open` | a member of an enum starts with a capital letter: OPEN |
| rule | declaration | `from: Place` | from is a word of the language and names nothing else |
| rule | declaration | `this = 3` | this is a word of the language and names nothing else |
| rule | expression | `formula(bool)` | bool is a word of the language, not a value |
| rule | expression | `SOURCE` | SOURCE is an end of a flow, not a value: flow name: SOURCE -> stock |
| rule | expression | `x.to` | to is a word of the language and names no member |
| rule | declaration | `job = this.repair.start()` | .start(...) starts an occurrence and gives no value: write it on a line of its own in a stage or in a trigger |
| rule | expression | `twice(x)` | twice(...) is not a function of the language |
| rule | expression | `c.first()` | .first(...) is not an operation of the language: the operations are .at, .by, .diff, .draw, .start, .where |
| rule | expression | `minimize(x)` | minimize(...) ranks the answers of a solver: it stands in its objective section |
| rule | expression | `c.where(this.x == y)` | inside where, a field of the member stands alone or on the left of a comparison, and the right side is read in the enclosing scope: where(critical), where(destination == this) |
| rule | expression | `c.by(this.rank)` | by takes one field of the member, which gives the key: by(rank) |
| rule | declaration | `this.beans += 3` | a change (+=, -=) belongs to a stage of an event: here a property gets its starting value |
| rule | declaration | `after 0 h:` | after belongs to the body of an event: name = event(...): |
| rule | step | `status ok when this.done` | a status display belongs to an entity. An event declares a field for its progress: status: enum[WEIGHING, ADDED] = WEIGHING |
| rule | step | `this.beans += amount` | an action belongs inside a stage of the event: after 0 h: |
| rule | step | `until this.ready:` | until C is a gate with no body: the next step goes on when C holds |
| rule | step | `after 2 h when this.safe` | a stage is `after D:` or `after D when C:` with its actions under it |
| rule | statement | `after 0 h:` | a timing step stands at the level of the event, outside the stages and their branches |
| rule | statement | `x: h = 2 h` | a stage declares no value: declare a local at the start of the event, before its timing steps, and assign to it here |
| rule | statement | `if this.safe:` | a stage has no `if` line: guard the stage (`after D when C:`) or branch with `switch` |
| rule | statement | `this.beans` | a line of a stage assigns (`x = v`, `x += v`, `x -= v`), starts an event (`e.start(...)`), moves (`move A from S to D`) or branches (`switch E:`) |
| rule | trigger | `this.beans += 3` | the body of a trigger captures values (`name = value`), starts its event (`this.event.start(...)`) and ends with its reset; a change of state belongs to a stage of the event |
| rule | setup | `flow f: a -> b` | a flow belongs to an entity or to an event: write it under one |
| rule | setup | `refill = event():` | an event belongs to an entity or to a template: declare it under one |
| rule | expression | `"a \n b"` | in a text, a backslash writes a quote (\") or a backslash (\\), and nothing else |
| rule | expression | `"open` | the text has no closing quote |
| rule | expression | `a +` | the line ends with +: an expression goes on to the next row only inside brackets: ( … ) |
| rule | declaration | `x = 3 "label"` | a text stands on a line of its own, under the line that it describes |
| old | declaration | `var dosing: "normal" &#124; "tampered" = "normal"` | &#124; is not a part of the language: named values are an enum now: enum[OPEN, CLOSED] |
| old | declaration | `input find_time = 6 h in 1 h to 24 h` | in is followed by a closed interval: x in [lo, hi] |
| old | declaration | `event find once when since(plant.dosing) >= find_time:` | an event is a value now: name = event(parameters): with its steps under it |
| old | declaration | `flow drain: tank -> basin at 10 L/h while valve is "open"` | the line of a flow holds its two ends: its rate and its limit are `request = ...` and `capacity = ...` on lines under it |
| old | declaration | `status failed when dosing is "tampered"` | equality is == and inequality is !=: `is` is no longer a word of the language |
| old | declaration | `output unsafe_water: L = plant.unsafe_drunk` | output is no longer a word of the language: any named value can be reported: name the calculation with an ordinary binding |
| old | declaration | `share basin limit 3 L/h order pump_a, pump_b` | share is no longer a word of the language: sharing belongs to the endpoint: `outflow.allocation = priority(a, b)` under the stock |
| old | declaration | `let zones = [near, middle]` | let is no longer a word of the language: a value is `name = value`, and a calculation that follows its inputs is `name = formula(...)` |

## The hunt for ambiguities

`ambiguities.md` has the 10 items of the brief with their grammar rules and 117 cases; 117 are as `hunt.py` writes them.

## The checks

`check.py`. Each check is behind a claim of FINDINGS.md.

| Check | Result |
| --- | --- |
| `test_copied_pieces` | SyntaxProblem, Token, Line, fold and tree are the text of lex.py at the base commit |
| `test_catalogue_tokens` | 23 present files, 6960 logical lines: 6813 give the same tokens, 147 differ for 3 known reasons |
| `test_corpus` | 27 blocks of the spec parse |
| `test_inline` | 154 pieces of inline notation parse |
| `test_refused` | 72 pieces are refused, each with its message |
| `test_hunt` | 117 cases of the ambiguity hunt are as written |
| `test_round_trip_corpus` | 337 expressions of the corpus read back from their text to the same node |
| `test_round_trip_random` | 3000 random trees (21094 nodes) read back from their text to the same node, in both places |
| `test_core` | 16 expressions go through the unit rules and the evaluator of napkin.core with the expected unit and value; 3 are refused by its unit rules |
| `test_catalogue_expressions` | 2956 expressions of the present models are the same node by today's route and by the new parser |
| `test_python_keywords` | a name that Python keeps (`class`) evaluates in napkin.core (function and program); `expr.limited` and `expr.read` refuse it, because they read the text again with `ast` |

### The present models, token by token

The new tokenizer against the present one (`lex.py` at the base commit), on each of the 6960 logical lines of the 23 present model files. 6813 lines give the same tokens.

| Lines | Why they differ | First place |
| ---: | --- | --- |
| 83 | differs: `size` after a bare number (`= 0.6 size 1`) is read as its unit | `examples/reservoir/model.scn:19` |
| 40 | refused: `&#124;` between named values (`"a" &#124; "b"`), now `enum[A, B]` | `examples/reservoir/model.scn:22` |
| 24 | refused: a flow with one end left out (`-> tally`, `stock ->`), now `SOURCE` and `SINK` | `scenarios/cyber_learning_loop/model.scn:1358` |

## The census of the present models

`census_names.py`: 23 files; wrote census.json and census.md. See `census.md`.
