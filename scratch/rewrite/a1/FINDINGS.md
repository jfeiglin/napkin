# A1: notation and types. Findings

## 1. Summary

- The notation of the spec parses. All 27 `text` blocks of the spec parse, and so do all 154 pieces of inline notation. 72 pieces that must be refused are refused, each with its message. The 13 whole models in `models/` parse.
- With one rule for each of the 10 kinds of ambiguity in the brief, no reading is ambiguous: 117 cases in `ambiguities.md`. The place decides `<`, `=`, `in`, `status` and `when`. The first letter decides between an enum member and a value. A unit is one word after one space.
- No present model breaks on the reserved words. 147 of 6960 present lines tokenize differently, for 3 known reasons (section 3).
- `types.md` gives a first type system: 10 written types and 12 made by declarations, who reads and writes each, 11 inference rules, and 6 places where a declaration gives a literal its unit.
- 32 rulings (section 4). The ones with most weight: unit grammar (R-A1-01), `.request` takes a rate or a formula (R-A1-16), object parameters are entity references only (R-A1-21), triggers have no names (R-A1-25), and draws keep the support as their range (R-A1-19).
- **No type checker ran.** `typecheck.py` was not written. The rules of `types.md` were applied to the 13 models by hand. One model fails: `13-reports` uses the unit `people`, which `models/units.json` does not declare.

## 2. What was done

Run everything from `scratch/rewrite/a1/`, with `PY="env PYTHONPATH=/home/user/napkin-base /home/user/napkin/.venv/bin/python"`.

| Script | What it does | Run |
| --- | --- | --- |
| `extract_corpus.py` | copies each `text` and `csv` block of the spec into `corpus/`; `--check` proves they are byte for byte | `$PY extract_corpus.py --check` |
| `parser.py` | tokenizer, precedence parser, lines and blocks | `$PY parser.py corpus/`; `$PY parser.py --expr 'a < -b'`; `$PY parser.py --tree --context stage FILE` (contexts: `file`, `members`, `event`, `stage`) |
| `hunt.py` | writes `ambiguities.md` | through `make_report.py` |
| `census_names.py` | names, units and notation of the 23 present models, with the present parser | through `make_report.py` |
| `check.py` | 11 checks | `$PY -m pytest check.py --confcutdir=. --rootdir=. -p no:cacheprovider` |
| `make_report.py` | runs all of these and writes `parse_report.md`, `ambiguities.md`, `census.md`, `census.json` | `$PY make_report.py` (11 s) |

Also: `models/` holds the 13 models, `rulings/` holds the parser examples of the rulings below, and `types.md` holds the type system.

The first agent wrote the corpus, the parser, the hunt, the census and the checks. It was stopped before it wrote this file, `types.md` or a checker. Its draft of the rulings was lost. The second agent wrote `types.md`, this file and `rulings/`. The rulings follow the "Decisions taken" of `STATE.md`, and they keep the ruling numbers that `parser.py`, `hunt.py`, `corpus/refused.txt` and `census_names.py` already cite. No decision of the first agent was changed.

## 3. Results

From `make_report.py`, run on 2026-11-18 (load 3.01, 3.42, 2.65). The results are in `parse_report.md`.

| What | Result |
| --- | --- |
| spec blocks (`corpus/*.scn`) | 27 of 27 parse; 3 csv blocks; byte for byte |
| inline notation (`corpus/inline.txt`) | 154 of 154 parse |
| notation to refuse (`corpus/refused.txt`) | 72 of 72 refused with their message |
| ambiguity cases (`ambiguities.md`) | 117 of 117 as written |
| models (`models/*.scn`) | 13 of 13 parse (`$PY parser.py models/`) |
| parse time of the corpus, 276 lines | 4.9 ms, best of three |
| round trip: expression text to node to text | 337 corpus expressions; 3000 random trees (21094 nodes) |
| present expressions, today's route against the new parser | 2956 of 2956 give the same node |
| present lines, old tokenizer against the new one | 6813 of 6960 give the same tokens |
| present names that the reserved list breaks | none (`census.md`) |
| present units outside the unit grammar of R-A1-01 | none: 1289 uses after a number, 931 in a type |
| `check.py` | 11 of 11 pass |
| type rules on the 13 models | by hand only (`types.md` section 9): 12 pass, `13-reports` fails on `people` |

The 147 present lines that tokenize differently have three causes:

- 83 lines have a clause word after a bare number (`= 0.6 size 1`). The new tokenizer reads `size` as a unit. If brief A5 keeps such clauses, their words must be reserved (R-A1-08).
- 40 lines use `|` between named states. That is now `enum[A, B]`.
- 24 lines are flows with one end left out. That end is now `SOURCE` or `SINK`.

Not verified: no type rule ran as code. The unit dimensions in `types.md` section 9 were worked by hand. The timings are from one loaded machine.

## 4. Rulings

Each `rulings/` file runs as `$PY parser.py --tree --context CONTEXT rulings/FILE`, with the context that the ruling names (`members` where none is named).

### R-A1-01: Unit arithmetic  [owner]
Rule: A unit is one word after its number and exactly one space. Its grammar is `factor (('/' | '-') factor)*`, with `factor := NAME ['^' ['-'] DIGITS]`. `-` multiplies and binds tighter than `/`. The word must end at a space, `,`, `)`, `]`, `:` or the end of the line. An operator that touches a unit is refused, with a message to add spaces. `^` is used only inside a unit, and `**` raises a value to a power. A number, a space and a name always make a quantity. `48h` is refused in the parser, not the tokenizer: the claim IDs of the catalogue need number and name tokens. `{item}/h` is dropped, because the catalogue uses it 0 times. This is the regex of `napkin/model/types.py:31` with a fixed end.
Alternative: Read the unit like an operand, so that `48 h/2` means `(48 h)/2`, and make `*` the product of units in place of `-`.
Example: `$PY parser.py --expr '48 h/2'` refuses the input and says to write `48 h / 2`. The alternative gives 24 h. `$PY parser.py --expr '3 person-years'` gives one unit under the rule. The alternative breaks the 19 declared units and 125 uses that hold `-` (census).
Recommendation: Take the rule. It changes no present model (0 units outside the grammar), and it removes the one silent difference that the spec names: today `48 h / 2` and `48 h/2` parse differently.

### R-A1-02: `<...>` beside comparisons, and the arrows  [owner]
Rule: The place decides. Where a value starts, `<` opens a collection. After a value, `<` compares. After a colon, `<` opens a type. The members of a literal are paths with no operator, so the first `>` closes the literal. A chain of comparisons points one way. A line may end with `>`. `->` and `<->` are tokens by longest match and stand only in a flow line. `<-` is no token, so `a<-b` is `a < -b`.
Alternative: Use other brackets for literals, such as `{a, b}`, and keep `<` for comparisons only.
Example: `count(<a, b>) > 0` gives `(compare (call count (collection a b)) gt 0)`. `a < b > c` is refused under the rule, and the alternative reads it as a chain of comparisons. `$PY parser.py --expr '<a + b, c>'` is refused under the rule ("a member with an operator needs brackets"). The alternative needs no such message (ambiguities.md item 1).
Recommendation: Keep the spec's `<...>`. The catalogue has 0 chains of comparisons, so the one-way rule costs nothing. The spec already writes `<T>` for the type.

### R-A1-03: A trailing `in [lo, hi]`: a range, or a membership test  [owner]
Rule: After the `=` of a declaration, an `in` outside brackets starts the range. After the `=` of an assignment it is refused, and membership needs brackets there. Everywhere else `in` is the membership test. It binds as a comparison, never chains, and has no `not in`.
Alternative: Read a stage's `ok = x in [lo, hi]` as membership, as Python does.
Example: In a stage, `ok = samples.draw() in [lo, hi]` is refused with "put the whole test in brackets". The alternative stores a bool there, while the same text in a declaration stores a number with a range. ambiguities.md item 2 has both rows.
Recommendation: Refuse. One text then means one thing in every place.

### R-A1-04: Capital letters, and enum names with no expected type  [owner]
Rule: A name with a capital first letter is a template (before a dot) or an enum member (with no dot after it). A value's name starts with a small letter. A bare member takes its enum from the expected type, in the places that `types.md` section 3 lists. With no expected type it is an error that names the fix: `gate = OPEN` gets "declare the type: gate: enum[OPEN, CLOSED] = OPEN".
Alternative: Search every enum in scope, and accept the member when exactly one enum has it.
Example: `gate = OPEN` parses (`Declare name=gate value=OPEN`). The rule refuses it in the checker. The alternative accepts it until a second enum with `OPEN` is added anywhere, and then the same line fails.
Recommendation: Take the rule. Adding a declaration should never break a distant line. The census finds no present name that the case rule breaks.

### R-A1-05: Boolean expressions have their own type  [owner]
Rule: `bool` is a type, separate from numbers. Arithmetic on a bool is an error. `count(c.done)` is the one reduction that counts bools. A numeric reading is written `1 if ready else 0`.
Alternative: Treat a bool as the numbers 0 and 1, as the present compiler does.
Example: `bad = this.safe + 1` parses. The rule refuses it: "a bool is no number: write (1 if this.safe else 0) + 1". The alternative gives 2.
Recommendation: Take the rule, which is the spec's recommendation (spec:54). `count(c.amount)` is already an error under the spec, and a bool type is the same discipline.

### R-A1-06: A complete type specification: named states, text, references, unit conversion  [owner]
Rule: The rule is `types.md` sections 1 to 3. An enum compares only with members of the same enum. Text has `==` and `!=` and nothing else. A reference compares by identity, and its links are fixed during the run (R-A1-30). Units convert by scale within one dimension. A bounded number exposes its range as `.lower` and `.upper`.
Alternative: Two enums with the same members are one type, and text is ordered.
Example: Take `a: enum[OPEN, SHUT]`, `b: enum[OPEN, SHUT]` and `same = (this.a == this.b)`. The rule refuses the comparison of two enum types. The alternative compares the member names and gives a bool.
Recommendation: Take the rule. Named states are the domain's, and a match of names by accident is an error.

### R-A1-07: Wrapped clauses, escaped quotes, trailing comments  [owner]
Rule: A `#` outside a text ends the row, and the comment stays with its row for the formatter. A text can go on over rows that are indented deeper. In a text, `\"` and `\\` are the only escapes. An expression goes on to the next row only inside `(` or `[`. A declaration's `in [lo, hi]` and its `@record` can each stand on a row of their own under it.
Alternative: Let a line go on after a trailing operator (`a +` at the end), and allow the escapes of Python.
Example: `total = a +` with `b` on the next row is refused ("an expression goes on to the next row only inside brackets"). The alternative joins the two rows. `"a \n b"` is refused under the rule, and the alternative makes it a line break (ambiguities.md item 10).
Recommendation: Take the rule. No present text holds a backslash or a `#`, so nothing changes. The tokenizer never has to guess whether a `<` at the end of a row opens a bracket.

### R-A1-08: The reserved words  [owner]
Rule: `RESERVED` in `parser.py:43` is the list: `true false none this t SOURCE SINK and or not if else in is from to when after until reset switch move assert flow record readonly input formula event solver enum bool`. Contextual words (`status`, the ratings, the solver sections, the record kinds, `minimize`, `maximize`) stay valid names, and the next token decides. Function names are not reserved, because `name(` is a call. `text` and `number` are type words and can still name a value. If brief A5 keeps a clause after a bare number (`size`, `scale`), it must reserve that clause word, or the word is read as a unit.
Alternative: Reserve all of Python's keywords as well, as the present resolver does.
Example: `to = 3` is refused under the rule ("to is a word of the language"). A field `class` is valid under the rule and refused under the alternative. The census finds 0 present names that either list breaks. `test_python_keywords` shows that `class` evaluates in `napkin.core`, but `expr.limited` refuses it.
Recommendation: Take the rule. The evaluator of the rewrite must then not read model text back through Python's `ast`.

### R-A1-09: Name shadowing and built-in member names  [owner]
Rule: There is no shadowing. Within one invocation, parameters, locals, flows and trigger captures have distinct names. A field may share a name with a function or a unit. A declared name that equals a built-in member of its owner's type is an error, and only then: an event local `done` clashes with the occurrence's `done`, but an entity field `done` is valid. Inside `where(...)` and `by(...)`, a bare name on the left is a field of the member. If the member has no such field, that is an error, and the name does not fall back to the enclosing scope.
Alternative: An inner name hides an outer one, and a member field falls back to a name of the enclosing scope.
Example: Inside an event, `critical: bool = true` and then `Place.instances.where(critical)` on a template with no `critical` field. The rule refuses the filter. The alternative filters on the local and selects every place.
Recommendation: Take the rule. The census shows 7 built-in names that present models declare (`done`, `start`, `capacity`, ...). The rule keeps all of them valid, because their owners have no such built-in member.

### R-A1-10: `.start(...)` gives no value, and no handle  [owner]
Rule: `.start(...)` is a statement in a stage or in a trigger, and it gives no value. An occurrence is reached through `e.occurrences`, with `.at(t)` for the newest one. There is no stable handle in v1.
Alternative: `job = this.repair.start()` keeps a reference to that occurrence.
Example: `job = this.repair.start()` is refused ("starts an occurrence and gives no value": `corpus/refused.txt` line 66). The alternative stores a reference. It would then need rules for the start being discarded when the stage fails (spec:554) and for pinning (open item 66).
Recommendation: No handle in v1. The occurrence exists only once the stage commits, so a handle would name something that may never exist.

### R-A1-11: `this` always designates the owning entity  [owner]
Rule: `this` is the receiving entity in a member initializer, in an event of that entity, in its stages and locals, and in its triggers. It never changes when a link is followed or when another entity starts the event. Bare names are the invocation's own. In setup there is no `this`.
Alternative: `this` is the occurrence inside an event body.
Example: In `refill`, `this.beans += amount` writes the grinder's beans, and `status = ADDED` writes the occurrence's field (models/01). Under the alternative, `this.beans` is an error, because an occurrence has no `beans`.
Recommendation: Take the rule. The spec's examples are all written that way.

### R-A1-12: A `run` path in source  [owner]
Rule: There is no `run` path in v1, and `run` is not reserved. Time is `t`. The mode and the seed are the wrapper's (spec:803), and the model cannot read them.
Alternative: Make `run` reserved, with `run.mode`, `run.seed` and `run.horizon`.
Example: `x = run.seed` (`rulings/r12-run.scn`) parses. With no entity named `run`, the resolver refuses it. Under the alternative, a model could branch on the mode, and a median run would then differ from a sampled run by more than its draws.
Recommendation: No path. A model that reads its mode breaks the contract that a run produces one trajectory from its configuration.

### R-A1-13: A distribution argument inherits a unit from its role  [owner]
Rule: The value arguments of a constructor (min, mode, max, mean, sd, median) take the declared unit, but only when the constructor, or the constructor with `.draw()`, is the whole initializer of a declaration that names a unit. The shape arguments (`gsd`, `a`, `b`, `p`) are dimensionless.
Alternative: Every argument writes its unit.
Example: `input repair_time: h = uniform(1, 3).draw()` (`rulings/r13-bare-args.scn`) is 1 to 3 hours under the rule. Under the alternative it is an error: "1 has no unit".
Recommendation: Take the rule. It is the same convenience as `beans: g = 8`, and it stops at the same edge: inside a larger expression, a bare number stays dimensionless.

### R-A1-14: `after D` with no colon is a wait with no action  [owner]
Rule: `after D` on a line of its own waits for `D` and does nothing. `after D:` needs a body.
Alternative: An event that only takes time writes an empty stage, such as `after 2 h:` with `pass`.
Example: `rulings/r14-wait.scn` parses (`Stage delay=2 h`). `rulings/r14-empty-stage.scn` (`after 2 h:` with nothing under it) is refused ("a stage has its lines under it"). The alternative needs a new word, `pass`.
Recommendation: Take the rule. models/11 needs it 3 times, for events that are only counted.

### R-A1-15: A writable `formula(T)` binding takes another formula, never a scalar  [owner]
Rule: In a stage, `x = formula(...)` may replace a writable `formula(T)` binding with another `formula(T)`. A scalar `x = 3 L/h` and `x += ...` are type errors on it. A `readonly` formula is never replaced.
Alternative: A scalar assignment turns the binding into a stored value.
Example: Take `rate: formula(L/h) = formula(this.water / (2 h))` and, in a stage, `this.rate = 3 L/h`. The rule refuses it: "rate keeps a formula: write formula(3 L/h)". The alternative silently stops following the water.
Recommendation: Take the rule, which is the spec's recommendation (spec:109). The kind of a binding never changes.

### R-A1-16: A property that takes a stored rate or a live formula: `.request`  [owner]
Rule: The type of `.request` (and of `.capacity`) on flows, legs and endpoints is written `rate | formula(rate)`, where `rate` is the flow's dimension. A scalar stores a rate. A `formula(...)` installs a live rate. An assignment in a stage may switch between the two. Only built-in properties have this type in v1, and a model cannot declare it.
Alternative: `.request` is always a `formula(rate)`, and a scalar is lifted to a constant formula.
Example: Take `delivery.request = this.speeds.draw()` in one stage (models/12) and `delivery.request += 1 L/h` in a later one. Under the rule the first stores a rate, so the `+=` adds to it. Under the alternative the property holds a formula, so the `+=` is refused (R-A1-15).
Recommendation: Take the rule. It is what the spec says the property does (spec:109), and the author reads the kind of the value at the line that sets it.

### R-A1-17: Copying a formula, and when a replacement is valid  [owner]
Rule: There is no operator that copies a definition. `formula(this.draining)` makes a live formula that reads `draining`, and it follows later replacements of it. To copy the definition, the author writes the expression again. A replacement is valid when it has the same result type, is pure, adds no cycle, and reads no local that dies before the binding (spec:550).
Alternative: `formula(f)` of a bare formula binding copies its current definition.
Example: Take `copy = formula(this.draining)`, then a stage sets `this.draining = formula(0 L/h)`. Under the rule, `copy` reads 0 L/h. Under the alternative, `copy` keeps the old drain.
Recommendation: Take the rule. One meaning of `formula(...)` (keep this calculation) is enough, and `.diff` (spec:744) follows replacements in the same way.

### R-A1-18: Distribution constructors, `.mean`, `.std`, `.draw()`  [owner]
Rule: The constructors are the present families with their parameter order (`napkin/distributions.py:34`): `uniform(min, max)`, `triangular(min, mode, max)`, `pert(min, mode, max)`, `loguniform(min, max)`, `normal(mean, sd)`, `normal(mean, sd, min, max)`, `lognormal(median, gsd)`, `lognormal(median, gsd, min, max)`, `beta(a, b)`, `bernoulli(p)` and `categorical(A: p, B: q)`. Their types are `distribution(U)`, `distribution(bool)` and `distribution(enum)`. `.mean`, `.std`, `.lower` and `.upper` are read-only, consume no draw, and report the moments and the support of the distribution as written, truncation included (spec:785). `.draw()` is not allowed in a formula.
Alternative: Name the parameters at the call (`normal(mean = 2 h, sd = 0.5 h)`), with no positions.
Example: `$PY parser.py --expr 'normal(2 h, 0.5 h).draw()'` parses. Under the rule it is a draw of an unbounded normal (R-A1-19). The present compiler refuses a normal with no bounds.
Recommendation: Take the positional rule. It is the present order, the catalogue uses it, and it gives a 2-argument `normal`.

### R-A1-19: Unbounded and transformed draws, fixed defaults, overrides, correlations  [owner]
Rule: A draw has the support of its distribution as its range, when no range is written. For an `input` with a range, that range must contain the support (spec:162), so an unbounded `normal` needs a 4-argument form or no range. A transformed draw (`clip(x.draw(), lo, hi)`, `2 * x.draw()`) is an ordinary expression, and its range is what the declaration writes. A fixed default is a plain value. An override is a number, never a distribution, in v1. Correlations are not in the first version, and the message is: "draws are independent: share one stored draw to tie two values".
Alternative: Admit a distribution-valued override, which replaces the descriptor before any draw.
Example: `input repair_time = uniform(1 h, 3 h).draw()`, overridden with `5 h`, is refused: 5 h is outside the range [1 h, 3 h]. Overridden with `uniform(2 h, 4 h)`, it is refused under the rule ("an override is a number") and accepted under the alternative.
Recommendation: Take the rule for v1. A distribution-valued override belongs to the wrapper of an experiment (spec:803).

### R-A1-20: A leg is named in `priority(...)` as `link.forward`  [owner]
Rule: `priority(...)` takes directed flows, the legs `link.forward` and `link.backward`, the named legs of an activity (`restore.labor`), or a projection of those. Each must be incident in the endpoint's direction. A bare reversible `link` is an error, and so is a leg that runs the wrong way.
Alternative: A bare `link` stands for the one leg of it that is incident at that endpoint.
Example: On `west.water.outflow`, `priority(link, backup)` (`rulings/r20-bare-link.scn` parses it) is refused under the rule: "name the leg: link.forward". The alternative picks `link.forward` at `west` and `link.backward` at `east`, so the same text has two meanings.
Recommendation: Take the spec's proposed rule (spec:191).

### R-A1-21: Object parameters: a stock, against a copy of its value  [owner]
Rule: A parameter whose type is a unit (`amount: L`) is a copy of a value. It has no storage identity: it cannot be the end of a flow or of a `move` (spec:229). A parameter whose type is a template (`target: Tank`) is a reference to that entity. Its fields are reached and written as `target.water`, and a flow or `move` can use them. v1 has no reference to a single field.
Alternative: A spelling such as `source: stock L` that passes one stored field by reference.
Example: In `fill = event(target: Tank)`, the stage line `target.water += 2 L` writes the tank (`rulings/r21-object-param.scn`). With `fill = event(level: L)`, the line `move 2 L from level to this.store` is refused ("level is a copy and holds no stock") under the rule. The alternative makes `level: stock L` work.
Recommendation: Take the rule. It needs no new type word, and an entity reference already says which stock is meant.

### R-A1-22: The spelling of `switch`, and a Boolean shorthand  [owner]
Rule: The spelling is `switch` with one case per member, an optional `else:`, and the selector read once. A bool selector takes `true:` and `false:` cases. A stage has no `if` statement: a single condition is the stage guard `after D when C:` or a `switch`.
Alternative: Add an `if C:` and `else:` block statement in stages.
Example: `rulings/r22-switch-bool.scn` (context `stage`) parses, with the cases `true:` and `else:`. `rulings/r22-if.scn` (context `stage`) is refused ("a stage has no `if` line"). The alternative accepts it.
Recommendation: Take the rule for v1. One branch form keeps the A2 rules on evaluation order in one place, and `if` can be added later without breaking a model.

### R-A1-23: Forward references in local formulas, and flows that read later locals  [owner]
Rule: The locals of an invocation initialize in written order. A plain initializer, and the property initializer of a declared flow, may read only names declared above it. A retained `formula(...)` may name a later local or flow of the same invocation, because it is read only after entry is complete. No local is read before the invocation has initialized.
Alternative: Formulas also follow written order.
Example: `flow delivery: batch -> this.customer.water`, with `request = formula(left / (2 h))` under it and `left: L = amount` declared below the flow. The rule accepts the formula. A plain `request = left / (2 h)` in the same place is refused ("left is declared below"). The alternative refuses both.
Recommendation: Take the rule. When the engine first reads a formula at entry is brief A2's, and the rule needs only that the read comes after entry.

### R-A1-24: Short-lived names inside a stage  [owner]
Rule: These are not in the first version. A stage declares no name. A value needed by several lines is a local declared at the start of the event and assigned in the stage. The message is "a stage declares no value: declare a local at the start of the event, before its timing steps, and assign to it here".
Alternative: A `name = expression` that names nothing declared makes a name that lives until the end of the stage.
Example: `rulings/r24-stage-name.scn` (context `event`) has `gap = this.need - this.water` in a stage. The parser reads it as an assignment, and the resolver refuses `gap` as undeclared. The alternative makes `gap` a temporary. The same misspelling of a declared local then makes a temporary too, and nothing reports it.
Recommendation: Take the rule. The spec makes a misspelled target an error (spec:39), and temporaries would undo that.

### R-A1-25: Triggers: names, how many, which events they start  [owner]
Rule: A trigger has no name, and nothing can read or write it. An event may have several triggers, each with its own state. A trigger starts only its own event, one or more times in its body.
Alternative: Named triggers (`low = when C:`) that a report can read, which can start any event of the receiver.
Example: `rulings/r25-two-triggers.scn` parses: two triggers on one event. In `rulings/r25-other-event.scn`, the trigger of `alarm` starts `this.cool`. It is refused ("a trigger starts its own event"). The alternative accepts it. A start of `cool` then has no trigger of its own, which breaks "a trigger belongs to its event" (spec:588).
Recommendation: Take the rule. To start another event, a trigger starts its own event, and that event's stage starts the other one.

### R-A1-26: The syntax and reads of a flow with legs  [owner]
Rule: `flow name:` with no ends holds two or more nested `flow leg: a -> b`, each with its own `request` and optional `capacity`. The parent has only the read-only `.served_fraction`, in [0, 1]. Each leg is a directed flow for reads, for `.flows` membership and for `priority`. The parent takes no property line.
Alternative: Let the parent carry one `capacity` that limits the common fraction.
Example: `rulings/r26-parent-capacity.scn` puts `capacity = 1` under the parent, and the parser refuses it. The message is only "this line does not belong here"; it should name the rule. In `rulings/r26-reads.scn`, `x = this.restore.actual_rate` parses, and the checker refuses it ("read a leg, or restore.served_fraction": spec:666).
Recommendation: Take the rule, which is the spec's proposed syntax (spec:657). Improve the parser's message.

### R-A1-27: `move(source, destination, amount)` as a shorthand  [owner]
Rule: There is one form, `move amount from source to destination`. The call form is refused, with its own message.
Alternative: Accept both forms.
Example: `rulings/r27-move-call.scn` (context `stage`) holds `move(a, b, 3 L)`. It is refused ("a move has one form: move amount from source to destination"). The alternative accepts it, and the reader must then know the order of the arguments to know which end is debited.
Recommendation: Keep one form. The words `from` and `to` say which end is debited.

### R-A1-28: A table row named by position, and the `id` column  [owner]
Rule: A row is named by its `id` cell as `table.id_value`, as in `sites.clinic`. An `id` is nonempty and unique in its table, and a link must name exactly one row. A row has no name by position in v1. The `id` column is not a field of the template. It is independent of the numeric key of `by`, `at` and `priority`.
Alternative: Use `sites.2` for the second row, as the present `machines.2`.
Example: `routes.csv` holds `origin = sites.junction`, and `rulings/r28-row-by-id.scn` (context `file`) parses it. If the rows of `places.csv` are sorted again, the rule still finds `junction`, but `sites.1` names another row under the alternative.
Recommendation: Take the spec's proposed spelling (spec:795). A position breaks when someone edits the file.

### R-A1-29: Where a collection declares a reusable key; duplicate members in a literal  [owner]
Rule: A key is given where it is used, by `c.by(field)`. A binding can keep the keyed view, as in `ranked = this.customers.by(rank)`, and the view keeps its key. A collection type declares no key. In a literal, the same path written twice, or two paths that setup resolves to one entity, is an error at setup.
Alternative: Declare the key in the type, `<Customer by rank>`, and drop the second member of a duplicate in silence.
Example: `pumps: <Pump> = <this.primary, this.primary>` (`rulings/r29-duplicate.scn`) parses, and the checker refuses it ("a collection holds distinct members: this.primary is written twice"). Under the alternative, `count(this.pumps)` is 1.
Recommendation: Take the rule. A keyed binding already makes the key reusable. A member dropped in silence changes counts.

### R-A1-30: Links are fixed during the run  [owner]
Rule: A field whose type is a template (a link) is set by its initializer, by a table, or by a `change`. No stage can assign to it.
Alternative: A writable link can be reassigned in a stage.
Example: Take `Route` with `origin: Place` and a stage line `this.origin = sites.garden`. The rule refuses it. Under the alternative, the flow `carried`, whose ends are fixed for its lifetime (spec:182), keeps the old place, while `this.origin.level` reads the new one.
Recommendation: Take the rule. The spec filters on "links ... fixed for each member" (spec:93), and fixed links keep flow ends and filters true.

### R-A1-31: The fields of an occurrence are read-only outside it  [owner]
Rule: Only its own invocation writes an occurrence's parameters, locals and declared fields, by bare name. Every other scope reads them, for example `refill.occurrences.at(t).status`, and cannot write them.
Alternative: Any resolvable path can write them, as for entity fields (spec:546).
Example: The stage line `this.refill.occurrences.at(t).status = ADDED` on the grinder is refused under the rule. Under the alternative it changes the progress of a refill from outside, so that the running refill's own `status = ADDED` no longer marks its own stage.
Recommendation: Take the rule. An occurrence is the record of one start, and only that start can write it.

### R-A1-32: How an author asserts that two links name distinct instances  [owner]
Rule: The author writes `assert this.primary != this.backup` over the links. Links are fixed (R-A1-30), so setup checks it once.
Alternative: Use a type word such as `distinct(primary, backup)`.
Example: A station with `primary = first_pump` and `backup = first_pump`. Under the rule, the assert fails at setup with its message. The alternative refuses the declarations with a built-in message. They differ only when no assert is written: then the rule accepts the station.
Recommendation: Take the rule. It needs no new word. `!=` on references compares identity (R-A1-06), and a literal `<this.primary, this.backup>` is refused for a duplicate anyway (R-A1-29).

### The open items that A1 owes, and their rulings

| Item | Ruling | Item | Ruling |
| --- | --- | --- | --- |
| 2 | R-A1-05 | 23 | R-A1-23 (A2 rules on the time of the first read) |
| 3 | R-A1-06, types.md | 24 | R-A1-24 |
| 4 | R-A1-12 | 29 | R-A1-25 |
| 5 | R-A1-11 | 31 | R-A1-26 |
| 6 | R-A1-13 | 42 | R-A1-27 |
| 7 | R-A1-01 | 43 | R-A1-08 |
| 8 | R-A1-07 | 44 | R-A1-28 |
| 11 | R-A1-15 | 49 | R-A1-09, R-A1-04, R-A1-17 |
| 12 | R-A1-16, R-A1-17 | 50 | R-A1-29 |
| 14 | R-A1-18 | 53 | R-A1-10 |
| 15 | R-A1-19 | 64 | R-A1-32 |
| 16 | R-A1-20 | brief: `<...>` | R-A1-02 |
| 20 | R-A1-21 | brief: trigger names | R-A1-25 |
| 21 | R-A1-22 | found | R-A1-03, R-A1-14, R-A1-30, R-A1-31 |

## 5. Not covered

- **No type checker ran.** `typecheck.py` was not written, for lack of usage. The rules of `types.md` were applied to the 13 models by hand, and no seeded error was tried. `check.py` does not test types.
- The parser refuses some of the examples above. Others parse, and their refusal belongs to a checker that does not exist yet: R-A1-04, 05, 09, 12, 15, 17, 19, 20, 21, 23, 24, 26 (`actual_rate`), 29, 30, 31, 32.
- `models/13-reports.scn` uses `people`, which `models/units.json` lacks. `.diff` (open item 35) is out of scope.
- Left to other briefs: `none` in arithmetic (A2, item 67); when an `assert` or a range on mutable state is checked (A2); the record syntax and clause words such as `size` (A5).
- The parser message for a property under the parent of a flow with legs is weak (R-A1-26). It was not changed.
