# The hunt for ambiguities

`hunt.py` makes this file. Each case is checked against what `hunt.py` writes for it.
A case that the parser refuses shows `refused:` and the message.

## 1. `<` and `>`: a comparison, the brackets of a collection, a type

Grammar:

```text
comparison := sum ( ('<' | '<=' | '>' | '>=' | '==' | '!=') sum )*     a chain points one way
primary    := '<' [ path (',' path)* [','] ] '>'                        a collection literal
type       := '<' type '>'                                               after a colon only
path       := primary ( '.' NAME [ '(' arguments ')' ] )*
```

The place decides. Where a value starts, `<` opens a collection. After a value, `<` compares. After the colon of a declaration, `<` opens a type. Inside a collection literal each member is a path with no operator, so the first `>` closes it. A chain of comparisons must point one way, so no chain looks like a pair of brackets.

| Where | Input | What the parser gives |
| --- | --- | --- |
| expression | `low < high` | `(compare low lt high)` |
| expression | `<this.primary, this.backup>` | `(collection this.primary this.backup)` |
| expression | `<>` | `(collection)` |
| expression | `count(<a, b>) > 0` | `(compare (call count (collection a b)) gt 0)` |
| expression | `<a, b>.where(critical)` | `(method (collection a b) where critical)` |
| expression | `lo <= x < hi` | `(compare lo le x lt hi)` |
| expression | `a < b > c` | refused: a chain of comparisons points one way, as in lo <= x < hi: join the others with `and` |
| expression | `<a + b, c>` | refused: a collection literal lists its members between < and >, as in <a, b>: a member with an operator needs brackets, and a comparison with < has a value on its left |
| expression | `<(a if c else b), d>` | `(collection (if c a b) d)` |
| declaration | `pumps: <Pump> = <this.primary, this.backup>` | `Declare name=pumps type=<Pump> value=<this.primary, this.backup>` |
| declaration | `idle: <Pump>= <>` | `Declare name=idle type=<Pump> value=<>` |
| declaration | `ready = low < high` | `Declare name=ready value=low < high` |
| type | `<<Pump>>` | `CollectionType <<Pump>>` |

- A line can now end with `>` (`idle: <Pump> = <>`). The present tokenizer refuses a line that ends with an operator (`lex.py:203`); the rule keeps every other operator.
- `<Pump>= <>` has no space before `=`, so the tokenizer reads `>=`. Where a type closes, the parser reads it as `>` and then `=`.
- The tokenizer cannot know that `<` opens a bracket. So a collection literal goes on to the next row only inside `( ... )`, as any expression does.
- The parser reads `<<Pump>>`, a collection of collections. The type rules refuse it (types.md).

## 2. A trailing `in [lo, hi]`: a range, against a membership test

Grammar:

```text
declaration := [modifier] NAME [':' type] ['=' value] ['in' interval] evidence*
value       := expression with no `in` outside brackets
comparison  := sum 'in' interval                    in an assert, a guard, or inside brackets
interval    := '[' expression ',' expression ']'
```

After the `=` of a declaration, an `in` outside brackets ends the value and starts the range. After the `=` of an assignment it is refused, because the two readings differ. Everywhere else `in` is the membership test. It binds as a comparison and never chains.

| Where | Input | What the parser gives |
| --- | --- | --- |
| declaration | `ok = samples.draw() in [lo, hi]` | `Declare name=ok value=samples.draw() range=[lo, hi]` |
| declaration | `ok = (samples.draw() in [lo, hi])` | `Declare name=ok value=(samples.draw() in [lo, hi])` |
| declaration | `care: h in [0 h, available]` | `Declare name=care type=h range=[0 h, available]` |
| declaration | `assert total in [initial - tolerance, initial + tolerance]` | `Check condition=total in [initial - tolerance, initial + tolerance]` |
| statement | `ok = (samples.draw() in [lo, hi])` | `Assign target=ok op== value=(samples.draw() in [lo, hi])` |
| statement | `ok = samples.draw() in [lo, hi]` | refused: to keep the result of a membership test, put the whole test in brackets: ok = (x in [lo, hi]) |
| declaration | `ok = a if x in [lo, hi] else b` | refused: to keep the result of a membership test, put the whole test in brackets: ok = (x in [lo, hi]) |
| declaration | `ok = max(0, x) in [0, 5]` | `Declare name=ok value=max(0, x) range=[0, 5]` |
| declaration | `ok = (x in [0, 5]) in [0, 1]` | `Declare name=ok value=(x in [0, 5]) range=[0, 1]` |
| expression | `not x in [lo, hi]` | `(not (within x lo hi))` |
| expression | `a + b in [lo, hi] and ready` | `(and (within (add a b) lo hi) ready)` |
| expression | `a < b in [lo, hi]` | refused: a membership test is not chained with a comparison: put one of them in brackets |
| expression | `x not in [lo, hi]` | refused: there is no `not in`: write not (x in [lo, hi]) |
| step | `after 2 h when this.water in [0 L, 10 L]:` | `Stage delay=2 h guard=this.water in [0 L, 10 L]` |

- The first two cases differ by one pair of brackets and give different models: a number with a range, or a yes/no. The spec agrees this rule. The type check catches the slip only when the declaration writes `: bool` (a bool has no range).
- The range can stand on a line of its own under the declaration (`corpus/02-range-and-assert.scn`).

## 3. `->` and `<->`, against a comparison with a minus sign

Grammar:

```text
tokens      := '<->' | '->' | '<=' | '<' | '-' | ...        the longest one that matches; `<-` is no token
flow        := 'flow' NAME ':' end ('->' | '<->') end
end         := 'SOURCE' | 'SINK' | NAME ('.' NAME)*
```

An arrow stands only between the two ends of a flow line, and an end is a path, never an expression. In an expression `<`, `-` and `>` in a row never make sense as an arrow: `-` needs a value after it, and `>` starts none. So the longest match is safe.

| Where | Input | What the parser gives |
| --- | --- | --- |
| expression | `a < -b` | `(compare a lt (neg b))` |
| expression | `a<-b` | `(compare a lt (neg b))` |
| expression | `a>-b` | `(compare a gt (neg b))` |
| expression | `a<->b` | refused: <-> joins the two ends of a flow (`flow name: source <-> sink`): it is no part of an expression |
| expression | `a -> b` | refused: -> joins the two ends of a flow (`flow name: source -> sink`): it is no part of an expression |
| expression | `a - > b` | refused: a value is missing before > |
| declaration | `flow link: west.water <-> east.water` | `FlowDecl name=link kind=reversible source=west.water sink=east.water` |
| declaration | `flow fill: SOURCE -> tank.water` | `FlowDecl name=fill kind=directed source=SOURCE sink=tank.water` |
| declaration | `flow f: a.x -> b.at(t).y` | refused: an end of a flow is the path of a stored quantity, SOURCE or SINK: it holds no call |
| declaration | `flow f: a <-> SINK` | refused: a reversible route joins two stocks: SOURCE and SINK stand at an end of a -> flow |

## 4. Unit arithmetic

Grammar:

```text
quantity := NUMBER ' ' unit                         exactly one space
unit     := factor ( ('/' | '-') factor )*          no space inside; '-' multiplies and binds tighter than '/'
factor   := NAME [ '^' ['-'] DIGITS ]
after a unit: a space, ',' , ')' , ']' , ':' or the end of the line
power    := path [ '**' signed ]                    `^` only inside a unit
```

A unit is one word that follows its number after one space. Inside the word `/` divides, `-` multiplies and `^` is a whole power. The word must end at a space, a comma, a closing bracket or a colon: an operator directly after a unit is refused. A number, a space and a name is always a quantity; a reserved word is never a unit.

| Where | Input | What the parser gives |
| --- | --- | --- |
| expression | `48 h / 2` | `(div (q 48 h) 2)` |
| expression | `48 h/2` | refused: the unit h is followed by /: a unit ends at a space, a comma, a closing bracket or a colon. Write a space on each side of an operator that follows a unit: 48 h / 2 |
| expression | `5 L/h^2` | `(q 5 L/h^2)` |
| expression | `0.5 Wh/L` | `(q 0.5 Wh/L)` |
| expression | `this.water / (2 h)` | `(div this.water (q 2 h))` |
| expression | `this.water / 2 h` | `(div this.water (q 2 h))` |
| expression | `10 L / 5 L/h` | `(div (q 10 L) (q 5 L/h))` |
| expression | `x ** 2` | `(pow x 2)` |
| expression | `x ^ 2` | refused: a power of a value is a ** b; ^ writes the power of a unit, such as 5 m^2 |
| expression | `(2 m) ** 2` | `(pow (q 2 m) 2)` |
| expression | `2 m^2` | `(q 2 m^2)` |
| expression | `3 person-years` | `(q 3 person-years)` |
| expression | `3 person - years` | `(sub (q 3 person) years)` |
| expression | `3 h-2 h` | refused: the unit h is followed by -: a unit ends at a space, a comma, a closing bracket or a colon. Write a space on each side of an operator that follows a unit: 48 h / 2 |
| expression | `2 g` | `(q 2 g)` |
| expression | `2 * g` | `(mul 2 g)` |
| expression | `2 if c else 3 h` | `(if c 2 (q 3 h))` |
| expression | `48h` | refused: 48h: a unit follows its number after one space, as in 48 h |
| expression | `1e-3 s^-1` | `(q 0.001 s^-1)` |
| type | `L/h^2` | `UnitType L/h^2` |
| type | `tunings/tuner-year` | `UnitType tunings/tuner-year` |
| type | `g` | `NameType g` |
| step | `after 0.5 h:` | `Stage delay=0.5 h` |

- `2 g` is 2 grams also when a value `g` is in scope; `2 * g` multiplies by that value. The spec itself has a field `hour` beside the unit `hour` of the prelude.
- A quantity is one value: `x / 2 h` is `x / (2 h)`, as today. The formatter writes the brackets.

## 5. `=`: a declaration or an assignment, against `==`

Grammar:

```text
declaration := NAME [':' type] '=' value ...        in an entity, at the start of an event, in `inputs:`, at the top level
property    := path '=' value                       under a value or a flow, or by its full path
assignment  := path ('=' | '+=' | '-=') value       in a stage
capture     := NAME '=' value                       in the body of a trigger
comparison  := sum '==' sum                         inside any expression
```

The place of the line decides what `name = value` does. A line has one `=`. Inside an expression equality is `==`, and a second `=` is refused with that message.

| Where | Input | What the parser gives |
| --- | --- | --- |
| declaration | `up = true` | `Declare name=up value=true` |
| statement | `up = true` | `Assign target=up op== value=true` |
| trigger | `shift = this.shift` | `Capture name=shift value=this.shift` |
| setup | `clinic.delivery.request = 3 L/h` | `Property path=clinic.delivery.request value=3 L/h` |
| declaration | `same = a == b` | `Declare name=same value=a == b` |
| declaration | `same = a = b` | refused: one = on a line: equality inside an expression is == |
| expression | `a = b` | refused: one = on a line: equality inside an expression is == |
| statement | `this.beans += amount` | `Assign target=this.beans op=+= value=amount` |
| declaration | `this.beans += amount` | refused: a change (+=, -=) belongs to a stage of an event: here a property gets its starting value |
| statement | `x: h = 2 h` | refused: a stage declares no value: declare a local at the start of the event, before its timing steps, and assign to it here |
| expression | `a is b` | refused: equality is == and inequality is !=: `is` is no longer a word of the language |

- A misspelled target of an assignment is an error of the resolver, not of the parser: in a stage `name = value` never declares.

## 6. Bare enum members, with and without an expected type

Grammar:

```text
NAME of a value            := [a-z_][A-Za-z0-9_]*
NAME of a template or case := [A-Z][A-Za-z0-9_]*
primary := CASE                 a capital word with no dot after it: a member of an enum
         | TEMPLATE '.' NAME    a capital word before a dot: a template (`Route.instances`)
```

The first letter decides. A word with a capital first letter and no dot after it is a member of an enum; before a dot it is a template. A name of a value starts with a small letter. So `OPEN` can never be a field, and the parser gives it a node of its own (`case`). Which enum it belongs to is the type checker's: it needs an expected type (R-A1-04).

| Where | Input | What the parser gives |
| --- | --- | --- |
| expression | `this.gate == OPEN` | `(compare this.gate eq (case OPEN))` |
| expression | `this.gate == open` | `(compare this.gate eq open)` |
| declaration | `gate: enum[OPEN, CLOSED] = OPEN` | `Declare name=gate type=enum[OPEN, CLOSED] value=OPEN` |
| declaration | `gate = OPEN` | `Declare name=gate value=OPEN` |
| expression | `OPEN if ready else CLOSED` | `(if ready (case OPEN) (case CLOSED))` |
| expression | `Route.instances` | `Route.instances` |
| declaration | `Gate: enum[OPEN, CLOSED] = OPEN` | refused: the name of a value starts with a small letter: a capital starts a template or a member of an enum |
| declaration | `gate: enum[open, closed] = open` | refused: a member of an enum starts with a capital letter: OPEN |
| type | `enum[OPEN, OPEN]` | refused: an enum lists each member once: OPEN is written twice |

- `gate = OPEN` parses. With no declared type the checker has no enum for `OPEN` and refuses it.
- The census finds no present name of a value with a capital first letter, and no template with a small one (census.md).

## 7. `status`: a field of an occurrence, against the status display

Grammar:

```text
status case := 'status' RATING ['when' expression] evidence*      RATING := ok | degraded | failed | inactive
declaration := 'status' (':' | '=') ...                           `status` is a name here
```

`status` is not reserved. The second token decides: a name after `status` makes a case of the status display, and `:` or `=` makes `status` a name. A status display belongs to an entity, so the body of an event refuses a case.

| Where | Input | What the parser gives |
| --- | --- | --- |
| declaration | `status ok when this.work_state == DONE` | `StatusCase rating=ok condition=this.work_state == DONE` |
| declaration | `status degraded` | `StatusCase rating=degraded` |
| step | `status: enum[WEIGHING, ADDED] = WEIGHING` | `Declare name=status type=enum[WEIGHING, ADDED] value=WEIGHING` |
| statement | `status = ADDED` | `Assign target=status op== value=ADDED` |
| expression | `grinder.refill.occurrences.at(t).status` | `(member (method grinder.refill.occurrences at t) status)` |
| declaration | `status: enum[UP, DOWN] = UP` | `Declare name=status type=enum[UP, DOWN] value=UP` |
| step | `status ok when this.done` | refused: a status display belongs to an entity. An event declares a field for its progress: status: enum[WEIGHING, ADDED] = WEIGHING |
| declaration | `status fine when this.done` | refused: a status case rates ok, degraded, failed or inactive |
| declaration | `status ok = 3` | refused: one = on a line: equality inside an expression is == |

- An entity can have a field `status` and a status display. The field is read as `clinic.status`. How a report names the display is brief A5's.
- The parser also refuses a case that follows the case with no condition: that one is the last.

## 8. `when`: the guard of a stage, a trigger, a reset

Grammar:

```text
stage   := 'after' expression ['when' expression] ':' actions      on one line, then the block
wait    := 'after' expression                                      no colon, no block: a wait with no action
gate    := 'until' expression                                      no colon, no block
trigger := 'when' expression ':' captures* starts+ [reset]
reset   := 'reset' ('when' expression | 'after' expression)       the last line of a trigger
```

The first word of the line decides: `after` starts a step, `when` starts a trigger, `reset` ends a trigger. `when` is reserved, so the duration before it ends there. A guard does not go on to a row of its own, so a `when` under `after D` is never a guard.

| Where | Input | What the parser gives |
| --- | --- | --- |
| step | `after delay when this.safe:` | `Stage delay=delay guard=this.safe` |
| step | `when this.low_on_beans:` | `Trigger condition=this.low_on_beans` |
| trigger | `reset when false` | `Reset kind=when value=false` |
| trigger | `reset after 3 h` | `Reset kind=after value=3 h` |
| step | `after 2 h` | `Stage delay=2 h` |
| step | `after x if c else y when ready:` | `Stage delay=x if c else y guard=ready` |
| step | `after 2 h when this.safe` | refused: a stage is `after D:` or `after D when C:` with its actions under it |
| step | `until this.ready:` | refused: until C is a gate with no body: the next step goes on when C holds |
| statement | `when this.safe:` | refused: a timing step stands at the level of the event, outside the stages and their branches |
| step | `reset when false` | refused: reset is the last line of a trigger (`when C:`) |
| trigger | `reset when a<br>reset after 3 h` | refused: reset is the last line of a trigger, and a trigger has one |

- `after 2 h` with no colon is a wait with no action. The spec has no such line; without it an event that only takes time needs an empty stage (R-A1-14).

## 9. `formula(bool)` where a type stands, `formula(expression)` where a value stands

Grammar:

```text
type    := 'formula' '(' type ')'              after the colon of a declaration or of a parameter
primary := 'formula' '(' expression ')'        where a value stands
```

The colon and the `=` of the declaration decide: a type stands after the colon, a value after the `=`. `formula` and `bool` are reserved, so `formula(bool)` where a value stands is refused. A unit and a value can share a name: the place says which one is meant.

| Where | Input | What the parser gives |
| --- | --- | --- |
| declaration | `ready: formula(bool) = formula(this.water >= this.minimum)` | `Declare name=ready type=formula(bool) value=formula(this.water >= this.minimum)` |
| declaration | `rate: formula(L/h) = formula(this.water / (2 h))` | `Declare name=rate type=formula(L/h) value=formula(this.water / (2 h))` |
| declaration | `twice: formula(g) = formula(g)` | `Declare name=twice type=formula(g) value=formula(g)` |
| declaration | `ready = formula(bool)` | refused: bool is a word of the language, not a value |
| declaration | `ready: formula(this.water >= 2 L) = true` | refused: this is a word of the language, not a type |
| type | `formula(formula(bool))` | `FormulaType formula(formula(bool))` |
| expression | `formula` | refused: formula keeps a calculation: formula(expression) |

- The parser reads `formula(formula(bool))`. The type rules refuse it (types.md).

## 10. Comments, `#` in a text, escaped quotes, wrapped clauses

Grammar:

```text
row      := tokens ['#' comment]                  a `#` outside a text ends the row
text     := '"' ( any character but " and \ | '\"' | '\\' )* '"'     it can go on over rows that are indented deeper
logical line := one row, or more rows while '(' or '[' is open
wrapped clauses of a declaration: `in [lo, hi]` and `@record` on rows of their own under it
```

The tokenizer reads a text to its closing quote before it looks for `#`, so a `#` inside a text is a character of the text. A backslash writes a quote or a backslash, and nothing else. An expression goes on to the next row only inside round or square brackets.

| Where | Input | What the parser gives |
| --- | --- | --- |
| declaration | `x = 3  # a note` | `Declare name=x value=3` |
| expression | `"a # b"` | `"a # b"` |
| expression | `"say \"hi\""` | `"say \"hi\""` |
| expression | `"C:\\data"` | `"C:\\data"` |
| expression | `"a \n b"` | refused: in a text, a backslash writes a quote (\") or a backslash (\\), and nothing else |
| declaration | `delay: h = 3<br>    in [0.5, 12]  # hours<br>    @timing` | `Declare name=delay type=h value=3 range=[0.5, 12] evidence=[@timing]` |
| declaration | `total = sum(  # all of them<br>    a,<br>    # the second<br>    b<br>)` | `Declare name=total value=sum(a, b)` |
| declaration | `total = a +<br>    b` | refused: the line ends with +: an expression goes on to the next row only inside brackets: ( … ) |
| declaration | `note = "one<br>    two"` | `Declare name=note value="one two"` |
| declaration | `x = 3 # in [0, 5]` | `Declare name=x value=3` |

- The tokenizer keeps each comment with its row (`Line.trailing`), for the formatter.
- No text of the present models holds a backslash or a `#` (census.md), so the two escapes change no present text.
