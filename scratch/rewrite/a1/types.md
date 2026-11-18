# A first type system for the rewrite

This file proposes the types that a checker needs to check a model of the rewrite. It rests on
`scratch/rewrite/spec.md` (cited as `spec:LINE`) and on the parse trees of `parser.py`. The 13
models in `models/` are the examples; each rule names one where it can. The rulings that this file
uses are in `FINDINGS.md` (`R-A1-NN`).

No checker of these rules has run (FINDINGS.md, "Not covered"). Each rule below was applied by hand
to the 13 models; section 9 lists what that found.

## 1. The words of a type

A type is written after the colon of a declaration, of an event parameter, or of a solver unknown.
The parser reads all of these forms (`parser.py --context members`, ambiguities.md item 9).

| Written | Type | Example |
| --- | --- | --- |
| `bool` | Boolean | `safe: bool = true` (models/11) |
| `enum[A, B, ...]` | named states, members with a capital first letter | `action: enum[REPAIR, RESUME] = REPAIR` (models/11) |
| a unit, such as `L`, `L/h`, `L/h^2`, `crew_h` | number of that unit's dimension | `water: L = 12` |
| `number`, `fraction`, `ratio` | dimensionless number | `share: fraction = 0.5` |
| `duration` | number of dimension time (as today, `napkin/model/types.py:22`) | |
| `text` | quoted text | |
| `formula(T)` | a kept calculation whose result has type `T` | `ready: formula(bool) = ...` (models/02) |
| `distribution(U)` | a distribution of numbers in unit `U` (R-A1-18) | `speeds: distribution(L/h) = uniform(1 L/h, 3 L/h)` |
| `<T>` | collection of members of type `T` | `pumps: <Pump> = <...>` (models/02) |
| a template name, such as `Pump` | a reference (a link) to an entity of that template | `origin: Place` (models/06) |

A range is not a type of its own. `in [lo, hi]` after the initializer, or on a row under it, adds a
closed interval to a number binding (section 4).

The checker refuses these written forms, which the parser reads:

- `<<Pump>>`: a collection holds entities, flows, legs or occurrences, never collections.
- `formula(formula(T))`: a formula of a formula. Reading a formula gives its value (section 5).
- `formula(<T>)`: a collection is already live when it comes from `instances`, `occurrences` or
  `flows`, and a literal is fixed (R-A1-29).
- `enum` members written twice, or with a small first letter (the parser refuses these already).

The author never writes the other types. They come from the declaration that makes the value:

| Made by | Type |
| --- | --- |
| `flow name: a -> b` | directed flow of dimension `dim(a)/time` (or `dim(b)/time` when `a` is `SOURCE`) |
| `flow name: a <-> b` | reversible route; `a` and `b` have one dimension |
| `flow name:` with nested `flow` legs | activity with legs; each leg is a directed flow of its own dimension |
| a number field that a flow or a `move` names as an end | store: the number type plus `.outflow` and `.inflow` |
| `name = event(p: T, ...):` | event with that signature, bound to its receiver |
| `when C:` inside an event | trigger of that event (R-A1-25) |
| a start of an event | occurrence of that event |
| `name = solver:` | solver of its receiver |
| `priority(...)`, `proportional()` | allocation |
| `Template.instances`, `e.occurrences`, `s.outflow.flows` | collections |
| `name: Template from "file.csv"` | table: a collection `<Template>` whose rows can also be named by `id` (R-A1-28) |
| `name: Template` at the top level | one instance of `Template` (models/02 `first_pump: Pump`) |

## 2. Numbers, dimensions and units

- A unit has a dimension and a scale (`models/units.json`; the prelude gives `h`, the counts and the
  dimensionless `fraction` and `ratio`). A dimension is a vector of whole powers of base
  dimensions.
- A number type is its dimension. The unit that a declaration writes is the unit in which the
  author reads and writes it; `L/h` and `m^3/day` are one type and convert (spec:56).
- A field of a template has one dimension in every instance (spec:56). A table column whose header
  names a unit of another dimension is an error at setup.
- Arithmetic: `+`, `-`, `min`, `max`, `clip`, `abs` and comparisons need one dimension on each side,
  and convert. `*` and `/` multiply and divide dimensions. `a ** n` needs a dimensionless `a`, or a
  constant whole `n`. `sqrt` needs even powers. `exp`, `ln`, `expm1`, `log1p` and `erf` need a
  dimensionless argument and give one.
- `t` is the time of the run: dimension time, read-only, readable everywhere, also in a formula.
- `since(e)` and `elapsed(x)` have dimension time. `delayed(x, d)` has the type of `x`.
- A rate of a flow has the dimension of its stored end divided by time. `models/08`: the store
  `battery.energy` is in `Wh`, so `battery.charge.capacity = 1 W` is a rate of that store, and
  `motor.actual_rate == fill.actual_rate * (0.5 Wh/L)` balances `Wh/h` with `L/h * Wh/L`.
- `SOURCE` and `SINK` have no dimension of their own. The other end gives it. A `SOURCE -> SINK`
  flow takes it from its first rate initializer that has a unit (spec:231); with none it is an
  error.

## 3. Bool, enum, text, none

- **bool** is a type of its own (R-A1-05). `and`, `or`, `not`, a trigger's `when`, `until`, a
  stage guard, `assert`, `where(...)` and `any`/`all` need a bool. A bool is no number:
  `count(c.done)` is the only reduction that counts bools; `1 if ready else 0` writes the number.
- **enum** values compare with `==` and `!=` only, and only with members of the same enum. Two
  enums with the same member names are two types. A bare member (`OPEN`) takes its enum from the
  expected type (R-A1-04): the declared type of the binding, the other side of `==`/`!=`, the
  selector of a `switch`, the target of an assignment, an event parameter, or the other branch of
  `if ... else`. With none, it is an error: `gate = OPEN` with no type.
- **text** is a value: `==` and `!=`, no order, no arithmetic, no range, never a key. A text
  parameter is a copy (spec:515). A text under a declaration is its label, not a value (spec:122).
- **none** is the absent value. It needs a declared type at its binding: `weekly_unserved: people
  = none` (models/13), and it is the value that clears an optional property: `capacity = none`
  (models/12). What `none` does in arithmetic is brief A2's (open item 67).

## 4. Ranges

- `in [lo, hi]` belongs to a number binding: a field, an input, a local, a solver unknown. Both
  ends are included, `lo <= hi` (spec:76). On a bool, enum, text, formula, collection or reference
  it is an error.
- The ends are expressions of the binding's dimension, evaluated once when the binding
  initializes: `batch: L = 0 L in [0 L, amount]` (models/12) takes `amount` of that invocation. A
  solver unknown's domain is read at each solve: `care: h in [0 h, available]` (models/07).
- The range of an `input` is the set of overrides that the input admits. The range of a stored
  quantity is an inventory bound that flows and `move` honor (spec:229). On a formula binding the
  range is a check of each value it gives, as an `assert`; when the engine checks it is brief A2's.
- `x.draw()` has the support of its distribution as its range, when no range is written
  (spec:162, R-A1-19).

## 5. Formulas

- `formula(e)` has the type `formula(T)` where `T` is the type of `e`. The body is pure: no
  `.draw()`, no `.start(...)`, no assignment, no cycle (spec:109).
- Reading a formula binding in an ordinary expression gives a `T`: `captured = this.draining`
  stores a rate. Reading it inside another `formula(...)` keeps it live: `formula(this.draining)`
  follows the binding, also when the binding is given another formula later (R-A1-17).
- A declared scalar type with a formula initializer is an error, with the fix: `rate: L/h =
  formula(...)` gets "write `rate: formula(L/h) = formula(...)`". The one exception is a property
  that takes a rate or a formula (R-A1-16).
- A writable `formula(T)` binding takes another `formula(T)` in a stage, never a `T`, and never
  `+=` (R-A1-15).
- A formula that names a local of an invocation can be installed only where that invocation
  outlives it: on its own locals and flows (models/12 `receive`), never on a field of the entity
  (spec:550).

## 6. Who reads and who writes

The scopes that read and write are:

- **setup**: the top level of a file, which declares entities, instances and tables and wires them
  (`clinic.delivery.request = 3 L/h`);
- **member initializer**: the declaration of a field, link, formula, flow, event or solver of an
  entity, run once when the run starts, in dependency order (spec:58);
- **stage**: the body of `after D:` of an invocation, which runs at its time;
- **trigger**: the body of `when C:` of an event, for one receiver;
- **solver**: the four sections of a solver;
- **formula**: the body of a `formula(...)`, read only;
- **caller**: a report or an experiment outside the run, read only.

"Read" means readable from every scope that can name the value by a path (`this...`, a link, an
admitted argument, a top-level name in setup). "Write" lists who can change it during the run.
Setup and an `input` override always set the starting value of what the table calls configurable.

| Type | Read | Written by | Not writable |
| --- | --- | --- | --- |
| bool, enum, text, number field | the value; a number with a range also `.lower`, `.upper` (R-A1-06) | its initializer; an assignment in any stage, through any reference (`=`, and `+=`/`-=` for a number); a solver's `solve_for` for a number | `readonly`: no assignment through any path; `input`: fixed after setup (spec:39) |
| store (a number field that a flow or `move` names) | as a number field, and `.outflow`, `.inflow` | as a number field; flows; `move` (also on `readonly`, spec:791) | proposed here: an assignment out of the inventory bound fails the run and clips nothing (the spec says this only of `move`, spec:791; brief A2 rules on execution) |
| `formula(T)` | reading gives `T` | a stage, with another `formula(T)`, unless `readonly` (R-A1-15) | a scalar, `+=` |
| distribution | `.mean`, `.std`, `.draw()` (R-A1-18) | a stage, with another distribution of its dimension, unless `readonly` | `.draw()` in a formula |
| reference (link) to an entity | the entity's fields, events, flows, solver; `==` and `!=` by identity | setup and `change` only (R-A1-30) | any stage |
| `<T>` | `.where`, `.by`, `.at`, a projection `.f`, the reductions, a broadcast `.start(...)` | a stage, with another `<T>`, unless `readonly` | a projection is no value of its own and is never stored (spec:91) |
| directed flow | `.source`, `.sink`, `.actual_rate` | `.capacity` (rate or `none`), `.request` (rate or `formula(rate)`, R-A1-16): initializer, setup, any stage | `.actual_rate`; the ends |
| reversible route | signed `.actual_rate`, `.forward`, `.backward` | `.capacity`, signed `.request` | the legs' fields |
| leg view `link.forward` | `.source`, `.sink`, `.actual_rate`, `.request` (the positive part) | none | all |
| activity with legs | `.served_fraction` (fraction in [0, 1]); each leg as a directed flow | each leg's `.request` and `.capacity` | the parent has no `.request`, `.capacity`, `.actual_rate` (spec:666) |
| `s.outflow`, `s.inflow` | `.flows` (`<flow>` of incident legs), `.actual_rate` (sum) | `.capacity`, `.request`, `.allocation` | `.flows`, `.actual_rate` |
| allocation | nothing | as the property `.allocation` | |
| event | `.occurrences: <occurrence>`, `since(e)`; `.start(args)` as a statement (R-A1-10) | nobody: the binding is read-only | the binding |
| trigger | nothing (R-A1-25) | nobody | |
| occurrence | `started` (time), `done`, `active` (bool), its parameters, its declared locals and flows | its own invocation, by bare name (models/01 `status = ADDED`) | every other scope (R-A1-31) |
| solver | its declared unknowns, as `clinic.staffing.care`; its input names inside its sections | nobody during the run; the solver writes its `solve_for` targets | unknowns, from any other scope |
| template | `.instances: <Template>` | nobody | |
| `t` | time | the engine | |

Each scope sees these names without a path:

| Scope | Bare names | `this` |
| --- | --- | --- |
| setup | top-level entities, instances, tables, records | none |
| member initializer | none of the entity's fields (they are `this.x`), the built-ins | the entity |
| event body, its locals, flows and stages | the invocation's parameters and locals, the event's own flows | the receiver (R-A1-11) |
| trigger | its own captures, in written order | the receiver |
| solver section | its inputs, its own unknowns | the owning entity |
| `where(...)`, `by(...)` | the member's fields on the left of a comparison; the enclosing scope on the right (spec:93) | the enclosing entity |

## 7. The type of an initializer

The checker infers the type of `name = e` from `e`, and checks it against the declared type when
there is one. In order:

1. A literal number with no unit: the declared unit if the declaration names one and the literal
   is the whole initializer, or a sign and the literal (`beans: g = 8`, `delay: h = 3`). Else
   dimensionless: `inspections = 0`, `input factor = 1`, `level = 0 in [-30, 30]` (models/06, 11).
   `beans: g = 4 * 2` is an error: `4 * 2` is dimensionless.
2. A quantity, `20 L`: its unit's dimension. With a declared unit, the dimensions must agree and the
   value is converted.
3. `true`, `false`: bool. A text: text. `none`: needs a declared type.
4. A bare member of an enum: the declared enum; with no declared type it is an error (R-A1-04).
5. A path: the type of the value it names. `primary = first_pump` is a `Pump` (models/02).
   Reading a formula gives its result type (section 5).
6. `formula(e)`: `formula(type of e)`.
7. A constructor of a distribution: `distribution(U)` with `U` from its arguments (R-A1-18).
   `.draw()` of it: a number in `U`, with the support as its range.
8. A collection literal `<a, b>`: `<T>` where `T` is the one type of the members, which are paths;
   two templates in one literal are an error. `<>` needs a declared `<T>` (spec:84). The same path
   twice is an error (R-A1-29).
9. `Template.instances`: `<Template>`. `e.occurrences`: `<occurrence of e>`. `s.outflow.flows`:
   `<flow>`. `c.where(p)`, `c.by(f)`: the type of `c`. `c.at(x)`: `T`. `c.f`: a projection of the
   type of `f`, which only a reduction, `solve_for`, `priority(...)` or a broadcast `.start` takes.
10. An expression: by section 2 and 3. `a if C else b` needs one type in both branches.
11. `event(...)` and `solver:` make their own types; `x = this.refill` is an error: an event and a
    solver are bound where they are declared, and no other binding holds one.

A declaration with a type and no initializer is a link of a template (`origin: Place`, set by
setup or by a table), an instance at the top level, or a solver unknown. A stored number with no
initializer is an error, as the spec says: "An annotation ... by itself supplies no initial value
for stored state" (spec:56).

Event parameters always declare a type (spec:56). An argument is checked against it at the call:
`this.deliver.start(20 L, 1 h)` (models/12).

## 8. Where a literal gets its unit from the declaration

A bare number gets a unit from its context only in these places. Everywhere else a bare number is
dimensionless, and `2 * this.delay` multiplies by 2 (spec:64).

| Place | Example | Unit |
| --- | --- | --- |
| the whole initializer of a declaration with a unit | `beans: g = 8` | `g` |
| an end of the range of a declaration | `water: L = 12 in [0, 20]`; `input delay: h = 3 in [0.5, 12]` | the binding's unit, declared or inferred |
| an end of a solver unknown's domain | `care: h in [0, available]` | `h` |
| a bare zero beside a value of known unit, in `+`, `-`, a comparison, `min`, `max`, `clip`, `if ... else` | `max(0, need - use)` (spec:78) | the other operand's |
| the value arguments of a distribution that is the whole initializer of a declaration with a unit | `input repair_time: h = uniform(1, 3).draw()` | `h` (R-A1-13) |
| a cell of a table | `places.csv` column `supply_limit: W` | the header's unit, else the field's |

These do not give a unit, and the checker says so with the fix: a property of a flow
(`capacity = 5` gets "a rate needs its unit: 5 L/h"), an assignment in a stage (`this.beans = 8`),
an argument of a start (`this.refill.start(50)`), and a literal inside a larger expression. The
bare zero is the exception in each of them.

## 9. The 13 models under these rules

Applied by hand, not by a program.

| Model | What the rules give |
| --- | --- |
| 01-grinder | `beans` is `g`; `low_on_beans` is `formula(bool)`; the trigger's condition reads it as a bool; `status = ADDED` takes its enum from the local. Passes. |
| 02-station | `primary`, `backup` are `Pump`; the literal is `<Pump>`; `captured` is `L/h`; `repair_time` is `h` in `[1 h, 12 h]`, which contains the support `[1 h, 3 h]`. Passes. The `assert` reads mutable state: when it is checked is A2's. |
| 03-crew | `DONE`, `WORKING` take the enum of `work_state` from `==`. Passes. |
| 04-tank-clinic | `tank.water` is a `readonly` store; the flow may drain it. Passes. |
| 05-allocation | `priority(hospital.delivery, garden.delivery)`: both flows leave `reservoir.water`. Passes. |
| 06-network | `level` is dimensionless; `power` is `Wh`; the routes' `carried.actual_rate` is `Wh/h` = `W`, and `pull * (level - level)` is `W`. Passes. |
| 07-staffing | `outreach_minimum` is `formula(h)`; the unknowns are `h`. Passes. |
| 08-water-electricity | the balance of `Wh/h` and `L/h * Wh/L` holds. Passes. |
| 09-provider-limit | all rates are `W`. Passes. |
| 10-record-delivery | Passes. |
| 11-plant | `repair_times` is `distribution(h)`; the broadcast argument is `h` and matches `Machine.repair(duration: h)`. `inspections` is dimensionless and `+= 1` keeps it so. Passes. |
| 12-depot | `crew_h` and `work_unit` legs each have their own unit; `delivery.request = this.speeds.draw()` gives a rate to a property that takes a rate or a formula; `rate_change * (t - started_at)` is `L/h^2 * h`. Passes. |
| 13-reports | **Fails**: `people` is no unit of `models/units.json`. `dy_dz = y.diff(z)` uses `.diff`, which is out of scope (open item 35); the checker would refuse it with that message. |
