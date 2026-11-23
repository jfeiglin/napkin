# The compiler

The compiler reads a model and gives the program that the engine runs. This page follows the chain
from the text to the program. It names the module and the function of each step, what each step
gives, and how each step refuses a model. The words **model**, **package**, **variant**, **entity**,
**template**, **value**, **input**, **flow**, **run**, **configuration**, **record** and **path** have
the meanings of [the terms](language/README.md#terms).

The paths on this page are relative to `napkin/`, unless they start with `docs/`, `tests/` or
`tools/`. The modules of this page are internal. The public API is the list of names in
[python-api.md](python-api.md).

## Contents

1. [The chain](#the-chain)
2. [The two entry points](#the-two-entry-points)
3. [Packages, modules and variants](#packages-modules-and-variants)
4. [Lex, parse and format](#lex-parse-and-format)
5. [Declare](#declare)
6. [Lower](#lower)
7. [The program](#the-program)
8. [The builder: the second authoring path](#the-builder-the-second-authoring-path)
9. [Diagnostics](#diagnostics)
10. [The evidence gate](#the-evidence-gate)
11. [The configuration of a run](#the-configuration-of-a-run)
12. [The model hash](#the-model-hash)
13. [Proofs over a program](#proofs-over-a-program)
14. [The artifact](#the-artifact)

## The chain

Each step is one function. It takes one form of the model and gives the next form.

```text
files -> logical lines -> tree -> declared model -> program -> Compiled
```

| Step | Module and function | What it gives |
| --- | --- | --- |
| 1. Find the files | `model/language/modules.py`, `files(path)` | The files of the model, in the order of reading |
| 2. Lex | `model/language/lex.py`, `lines(text)` and `tree(found)` | The logical lines and their tokens |
| 3. Parse | `model/language/parse.py`, `parse(text)` | A tree: a `File` of `model/language/nodes.py` |
| 4. Declare | `model/semantic.py`, `declare(tree, units, tables_reader, files)` | A `DeclaredModel`: names resolved, types and units checked |
| 5. Lower | `model/lowering.py`, `lower(declared)` | A `Program` of `program/parts.py`, checked by `program/check.py` and `model/solvers.py` |
| 6. Report | `lowering.reports`, `support.unsupported`, `support.cited_data` | The warnings, which refuse nothing |
| 7. Locate | `lowering.side_table(declared, program, file)` | The side table: the place, the label, the evidence and the title of each part |
| 8. Identify | `model/identity.py`, `model_hash(declared, program, base)` | The model hash |
| 9. Configure | `compile.default_run(declared)`, then `model/runs.py`, `configuration(...)` | The configuration of the default run, or of a named run under an edit document |

`model/compile.py` joins the steps. Its result is a `Compiled`
([The two entry points](#the-two-entry-points)). The engine reads only the program and a
configuration ([docs/engine/README.md](engine/README.md)).

The parser resolves no name. The declared model knows nothing of the engine. The program holds no
text and no place in a file. Each step owns its own decisions, and no later step makes them again.

## The two entry points

| Function | Input | Use |
| --- | --- | --- |
| `model.compile.load_scenario(path, *, run=None, edits=None)` | A package folder, its `model.scn`, or the `model.scn` of a variant | The commands and the public API (`napkin.load_scenario`) |
| `model.compile.compile_text(text, units, file='', tables=None, *, run=None, edits=None)` | One text, with its table of units | Tests and short scripts |

`compile_text` reads no prelude and no library: the model has the units of `units` only. A unit is
`{'L': {'volume': 1}}` (a dimension) or `{'days': ({'time': 1}, 24)}` (a dimension and a scale). The
argument `tables` gives the text of each table that the model names, as `{'places.csv': text}`.

```python
from napkin.model.compile import compile_text

UNITS = {'L': {'volume': 1}, 'h': {'time': 1}}
TEXT = '''\
scenario "A tank"
    horizon 4 h

tank:
    readonly water: L = 8 L in [0 L, 20 L]

clinic:
    flow delivery: tank.water -> SINK
        capacity = 5 L/h
        request = 3 L/h
'''
model = compile_text(TEXT, UNITS)
print([item.code for item in model.reports])  # ['no_record']
```

Both functions give a `Compiled` (`model/compile.py`):

| Field | What it holds |
| --- | --- |
| `declared` | The `DeclaredModel` (`model/semantic.py`) |
| `program` | The `Program` (`program/parts.py`) |
| `configuration` | The configuration of the run that `run` and `edits` chose: the default run when both are None. None for a text with no horizon |
| `base` | The configuration of the default run: a median run to the horizon of the scenario line, with `resolution` as the longest step |
| `reports` | The warnings: each a `Problem` that refuses nothing ([Diagnostics](#diagnostics)) |
| `model_hash` | The model hash ([The model hash](#the-model-hash)) |
| `table` | The side table (`program/artifact.py`, `SideTable`). No hash covers it |

`Compiled.configure(run=None, edits=None, options=None)` gives the configuration of another run of
the same model ([The configuration of a run](#the-configuration-of-a-run)).
`Compiled.artifact()` gives the program with its side table ([The artifact](#the-artifact)).

`load_scenario` refuses a file that does not exist with `FileNotFoundError`. It refuses a model with
`LanguageError`, which holds every problem that it found. A problem of the library (`units.json`,
`evidence/`, `vocabulary.json`) is a `ModelError` (`model/ir.py`). A scenario line with no horizon is
the problem `scenario`, because a package needs a default run.

## Packages, modules and variants

A package is a folder. `paths.py` names its files, and `model/language/modules.py` reads them.

```text
clinic/
    model.scn                 the main file: it starts with `scenario "Title"`
    parts/staff.scn           a module: `use parts.staff` reads it
    units.json                units of the package (optional)
    evidence/                 sources, claims and assumptions of the library (optional)
    style.toml                the picture (docs/draw.md); the compiler never reads it
    roles.toml                who plays each part, for the wrapper (docs/draw.md)
    variants/
        winter/model.scn      a variant: it starts with `variant "Title"`
```

The first declaration of a file gives its role (`modules.role_of`):

| First declaration | Role | Where it is |
| --- | --- | --- |
| `scenario "Title"` | The main file | `<package>/model.scn` |
| `variant "Title"` | A variant | `<package>/variants/<name>/model.scn` |
| Any other line | A module | Any other `.scn` file of the package |

These are the three files of a package that compiles:

```scn
scenario "A clinic"
    summary "Patients wait, and the staff treats them."
    horizon 10 days
    scope "One clinic."

use parts.staff

clinic:
    "The clinic."
    waiting: people = 200 people in [0,] scale 200 people @guess
        "Patients who wait"
    treated: people = 0 people in [0,] scale 200 people @guess
        "Patients treated"
    flow treat: this.waiting -> this.treated @guess
        request = formula(staff.pace)

record guess: assumption "An example value."
```

The module `parts/staff.scn`:

```scn
staff:
    "The staff of the clinic."
    input pace: people/day = 15 people/day in [0 people/day, 50 people/day] @guess
        "Patients that the staff treats in a day"
```

The variant `variants/winter/model.scn`:

```scn
variant "Winter"
    horizon 20 days

change staff:
    pace = 10 people/day @guess
```

These rules apply to the files of one model:

1. `use a.b` names the module `<package>/a/b.scn`. The compiler reads no file of another package.
2. A variant reads the main file of its package first.
3. Each file comes after the modules that it uses, in the order of its `use` lines. The entry file
   comes last. The compiler reads each module once, also when two files use it.
4. The compiler parses each file alone. It numbers the lines of a file after the lines of the file
   before it, so each problem names its own file and line (`semantic.Files`).
5. The files make one model under one scenario line (`compile.merged`). Each line that a variant
   writes under its `variant` line replaces the same line of the main file: `summary`, `horizon`,
   `scope` or `resolution`. The title becomes `Title: Variant`, here `A clinic: Winter`.
6. A variant reads the library of its package. A `library` line in a variant is the problem
   `scenario`.
7. A `change` line of a variant gives an entity, a template or a member of an earlier file a new
   value or a new link. Two changes of one value are an error.

A problem in a module names the module, as in this output of `napkin compile`:

```text
parts/staff.scn:3:30: error: pace is declared people/day, and its initializer is people [unit]
```

The units of a model come from four places, in this order (`model/library.py`,
`load_library`):

1. the prelude, `std/units.json`, which every model has (`h`, `day`, `week`, `month`, `year`,
   `person`, `people`, `fraction` and others);
2. the library that the main file names with `library "PATH"` (`vocabulary.json` in that folder);
3. the `units.json` and the `evidence/` folder of the package;
4. for a variant, the `units.json` and the `evidence/` folder of the variant.

A unit or an entry of the evidence (a source, a claim, an assumption) is in one place only, and no
file can define a name of the prelude again. A table (`sites: Place from "places.csv"`) is a CSV file of the package folder
(`model/language/tables.py`).

`package.py`, `load_package(path)`, compiles every model of a package. A package with no variants
gives `{package: model}`. A package with variants gives `{package:variant: model}` for each variant,
in name order. A problem of the main file shows once, not once for each variant.

## Lex, parse and format

**The lexer** (`model/language/lex.py`) gives the logical lines of a text.

- A logical line is one row of the file, or more rows while a bracket `(` or `[` or a text is open.
- Each level of indent is four spaces. A tab is the problem `tab`, and another indent is the problem
  `indent`.
- A `#` outside a text starts a comment to the end of its row. The lexer keeps the comments, so the
  formatter can write them again.
- A text is in double quotes. Its only escapes are `\"` and `\\`. A row break inside a text reads as
  a space, and an empty row as one line break.
- Each token records if a space comes before it. The parser uses this to read an ID such as
  `A-TIMING` and the unit after a number. The lexer reads no unit.

**The parser** (`model/language/parse.py`, `parse(text)`) gives one tree for one text. It reads the
form of each line and resolves no name. It stops at the first line that it cannot read, with a
`SyntaxProblem` that names the form that the line must have.

- Expressions bind from the loosest: `a if C else b`; `or`; `and`; `not`; a comparison or
  `x in [lo, hi]`; `+ -`; `* /`; a sign; `**`; a dot; a value.
- After the `=` of a declaration, an `in` outside brackets starts the range. After the `=` of an
  assignment, the parser refuses it, so one text has one meaning.
- A number with a name one space after it is a quantity. Its unit continues through `*` and `/`
  while the next factor is a bare name. So `48 h/2` stops before the `2`.
- A name with a capital first letter is a template or a member of an enum. The name of a value
  starts with a small letter.
- The parser refuses by name a word that the language no longer has, with the code `retired` and
  the form to write now ([docs/language/changes.md](language/changes.md)).

**The tree** (`model/language/nodes.py`) has one frozen dataclass for each kind of expression, type
and line. The place in the file and the layout (comments, empty rows) take no part in equality. So
`parse(write(tree)) == tree`.

**The formatter** (`model/language/format.py`, `format_text(text)`) writes a tree again in the
language's own layout. It writes four spaces for each level and one logical line on one row. It
writes only the brackets that the order of the operations needs. A formatted text does not change
when the formatter reads it again. `napkin fmt` is this function ([cli.md](cli.md#napkin-fmt)).

## Declare

`model/semantic.py`, `declare(tree, units, tables_reader=None, files=())`, gives the
`DeclaredModel`. It resolves each name, and checks each type and each unit. It collects every problem
and raises one `LanguageError` with all of them. The module docstring of `semantic.py` is the full
list of its rules. The main rules are these:

| Subject | Rule |
| --- | --- |
| Types and units | The model declares a type (`water: L`), or the type comes from the initializer. `+`, `-`, a comparison, `min`, `max`, `clip` and both sides of `if ... else` need one dimension. `*` and `/` make the dimension of their result |
| Quantities | A quantity is its dimension and its exact scale, never its spelling. A written number is the exact decimal of its token. So `[6 h, 1 day]` runs from 6 h to 24 h |
| Unit runs | After a number, a name is a unit while the library has a unit of that name. The first name that is no unit ends the run |
| Members and links | A template is the schema of its members. An entity is the template of its one member. A link names one member, fixed for the run |
| Cycles | The members' own connections give the order of the values. A cycle is the problem `cycle`, with its chain: `a reads b reads a` |
| Flows and routes | A flow ends at `SOURCE`, `SINK` or a stored number. A route (`<->`) joins two stocks. Its legs are `forward` and `backward` |
| Events | Stages, gates and triggers are steps in order. A plain initializer of an event local reads only what is above it |
| Writes | An input, a link, an event and the ends of a flow are fixed for the run. `readonly` refuses `=`, `+=` and `-=`. No statement assigns what the run computes |
| Lifetimes | A formula that a stage installs reads only what lives at least as long as its place |
| Draws | A draw stands where a value is captured once. A formula and a condition that is read again make no draw |
| Solvers | `solve_for` names stored numbers, rates and served fractions, and new unknowns |
| Options and runs | An option sets inputs only, by their full paths, each with a constant of the input's type |
| Status displays | The first case whose condition holds gives the rating and the text. The last case has no condition |

Each declared part has a stable path, for example `tank.water`, `Place.level` or `sites.clinic`. The
program gives the same path to the part as its `origin`. A report or a trace uses the origin to find
the label and the evidence of the part.

## Lower

`model/lowering.py`, `lower(declared)`, writes the declared model as a program. It uses the builder
of `program/build.py`, the same builder that tests use
([The builder](#the-builder-the-second-authoring-path)).

1. Each template becomes a template of the program. Each entity becomes a template of one member.
2. Each member that the model writes by hand becomes a member with its own values and links. The
   rows of a table go to `Builder.table`, which keeps the rows in the order of their ids. So a
   reordered CSV file gives the same program.
3. The values and the assertions of the top level go to the root. The setup's starts go to
   `Builder.setup`.
4. `Builder.finish` gives each part its origin and each draw its site. It then runs the checker,
   `program/check.py`, `check(program)`.
5. `model/solvers.py`, `problems(program)`, checks what each solver says about what it determines.

A refusal of step 4 or 5 becomes a `Problem` at the line of the declared part that it names. So a
model text and a program that a test builds have one set of rules.

## The program

The program (`program/`) is the one contract between the compiler and the engine. It imports nothing
of napkin but `napkin.core`.

| Module | What it holds |
| --- | --- |
| `program/parts.py` | Frozen dataclasses for the whole language: units, enums, templates, values, flows, events, solvers, status displays, assertions, members and the `Program` |
| `program/refs.py` | What an expression reads: a `Path` from a start (`THIS`, `ROOT`, `ITEM`, `Named`, `Local`, a collection) through named steps, and the reads that the language writes as calls |
| `program/config.py` | The configuration: inputs, mode, seed, limits, budgets, numerical settings and the request |
| `program/record.py` | The record of a run: histories of pieces, the trace and the manifest |
| `program/check.py` | The checker and the resolver of paths |
| `program/build.py` | The builder |
| `program/canonical.py` | The canonical bytes of a program and of a configuration, and `decode`, which reads them back |
| `program/artifact.py` | The program as a file, with its side table and its versions |
| `program/checkpoint.py` | A run stopped at a breakpoint, as data |
| `program/reach.py` | Which events can start, and which values each named state can take |
| `program/proofs.py` | That a value never falls, and what a value reads |

A program holds no text. Each part carries its `origin`, never a line number. A number type names
its unit by its spelling (`L/h`), and the program's table of units gives each spelling its dimension
and its exact scale. Time is in hours.

**Canonical bytes** (`program/canonical.py`). Two builds of one model give equal bytes. A change of a
number, a unit, a name or the structure gives other bytes. Each value has a tag and a length
before it. Nothing depends on the identity of an object, the order of a dictionary or the
process. The run store keys a run by these bytes ([cli.md](cli.md#the-run-store)).

## The builder: the second authoring path

`program/build.py` is a short Python API that makes programs. Tests use it, and
`model/lowering.py` uses it. A program that the builder makes and a model text that means the same
give the same canonical bytes. This script prints `True`:

```python
from napkin.model.compile import compile_text
from napkin.program.build import SINK, Builder, flow, q, value
from napkin.program.canonical import program_bytes

UNITS = {'L': {'volume': 1}, 'h': {'time': 1}}

b = Builder(UNITS)
tank = b.entity('tank', value('water', 'L', 8, lower=0, upper=20, readonly=True))
b.entity('clinic', flow('delivery', tank.water, SINK, capacity=q(5, 'L/h'), request=q(3, 'L/h')))
built = b.finish()

TEXT = '''\
scenario "A tank"
    horizon 4 h

tank:
    readonly water: L = 8 L in [0 L, 20 L]

clinic:
    flow delivery: tank.water -> SINK
        capacity = 5 L/h
        request = 3 L/h
'''
print(program_bytes(built) == program_bytes(compile_text(TEXT, UNITS).program))
```

The builder gives handles for expressions: `this`, `local`, `item`, `root`, `t`, a member from
`entity`, `member`, `named` or a table, `q(number, unit)` and `call(name, ...)`. The part
constructors (`value`, `input_`, `link`, `flow`, `route`, `legs`, `event`, `after`, `until`, `when`,
`solver`, `status`, `assertion` and others) make the dataclasses of `program/parts.py`.

`Builder.finish()` gives each part its origin from its place (`grinder.refill.step[0].do[1]`), each
draw its site (`<origin>.draw[0]`) and each flow with no unit the unit of its ends per hour. Then it
runs `check.check`. A program that breaks a rule raises `ProgramError`. Each of its `diagnostics` has
a `code`, a `part` (the origin) and a `message`:

```python
from napkin.program.build import SINK, Builder, flow, q, value
from napkin.program.check import ProgramError

b = Builder({'L': {'volume': 1}, 'h': {'time': 1}})
tank = b.entity('tank', value('water', 'L', 8, lower=0, upper=20))
b.entity('clinic', flow('delivery', tank.wter, SINK, request=q(3, 'L/h')))
try:
    b.finish()
except ProgramError as error:
    for item in error.diagnostics:
        print(item.code, item.part, item.message)
# unknown_name clinic.delivery `tank.wter`: 'wter' names nothing
```

`check.py` is the only place that states what an engine can rely on. The front end refuses most
problems earlier, with its own message at the line. The checker refuses the same problems in a
program that the builder makes. Its codes are in the module docstring of `program/check.py`. They
include `unknown_name`, `unknown_unit`, `duplicate_name`, `range`, `kind`, `link_unset`, `no_value`,
`two_writers`, `readonly_write`, `fixed_write`, `result_write`, `assign_value`, `flow_end`,
`parameter_end`, `route_end`, `flow_units`, `move_end`, `formula_draws`, `trigger_start`,
`local_order`, `solve_for`, `priority_item`, `enum_member`, `distribution`, `collection`,
`duplicate_literal`, `where_live`, `status_fallback` and `arguments`.

## Diagnostics

A diagnostic of the front end is a `Problem` (`model/language/problems.py`): its `code`, its
`message`, its `line`, its `column` and its `file`. The code names the rule. A test and a caller read
the code and not the message.

- The lexer and the parser raise `SyntaxProblem` at the first line that they cannot read.
- `declare` and `lower` collect every problem and raise one `LanguageError`. Its `problems` hold
  each `Problem`, and `codes` gives their codes in order.
- A warning is a `Problem` in `Compiled.reports`. It refuses nothing.

The commands write one diagnostic on one line: `file:line:column: error: message [code]`, or
`warning:` for a warning ([cli.md](cli.md#diagnostics-and-exit-codes)). These lines come from
`napkin compile`:

```text
broken/model.scn:10:37: error: + needs one dimension on both sides: people/day and people [unit]
broken/model.scn:10:31: error: service has no rat; did you mean rate? [unknown_name]
norec/model.scn:10: warning: service.rate: an input rests on no record: cite one (@name) or write one under it [no_record]
```

The codes come from these steps. The lists name the common codes. The module of each step has the
full list. A word or a form that the language no longer has gives `retired` or a code of its own,
with the form to write now. [docs/language/changes.md](language/changes.md) lists each one.

| Step | Module | Codes |
| --- | --- | --- |
| Files | `model/language/modules.py` | `use`, `module`, `scenario` |
| Lex | `model/language/lex.py` | `tab`, `indent`, `bracket`, `text`, `number` |
| Parse | `model/language/parse.py` | `syntax`, `reserved`, `retired`, `layout`, `route_end` |
| Tables | `model/language/tables.py` | `table` |
| Declare | `model/semantic.py` | `unknown_name`, `type`, `unit`, `range`, `cycle`, `link`, `property`, `flow_end`, `move_end`, `fixed_write`, `readonly_write`, `result_write`, `formula_draws`, `local_order`, `lifetime`, `draw`, `distribution`, `arguments`, `status` |
| Check | `program/check.py` | See [The builder](#the-builder-the-second-authoring-path) |
| Solvers | `model/solvers.py` | `solver_form`, `nonlinear`, `participant`, `two_solvers` |
| Runs and edits | `model/runs.py` | `run`, `schema`, `model_hash`, `reference`, `input`, `value`, `bool`, `unit`, `meeting` |
| Warnings | `model/support.py`, `program/check.py` | `no_record`, `datum`, `equal_keys`, `below_first_key` |

The warnings refuse nothing:

| Code | What it says |
| --- | --- |
| `no_record` | A part rests on no evidence ([The evidence gate](#the-evidence-gate)) |
| `datum` | A value differs from the datum that its evidence cites, or the compiler cannot fix its number |
| `equal_keys` | Two members of a keyed view that `.at(...)` reads have equal keys |
| `below_first_key` | A lookup can read below the first key at a known lower bound |

## The evidence gate

`model/support.py` holds the owner's evidence rule. Each part of a model shows its support: a
citation `@name` of a `record` declaration, or a line `@kind "explanation"` under it
([docs/language/evidence.md](language/evidence.md)). `support.unsupported` gives the warning
`no_record` for each of these parts when it has no evidence:

- an input, but a text input;
- a stored number or yes/no of an entity, a template or the top level. A yes/no with no evidence of
  its own takes the evidence of its entity;
- an event that acts at a time, with a stage or a trigger;
- a case of a status display. A case with no evidence of its own takes the evidence of its entity;
- an assertion;
- a number, a yes/no or a distribution that a member written by hand gives as its own value;
- a column of a table that holds such values. Its evidence is in the header of the column
  (`base_need: W @survey`).

A text, a member of an enum, a link, a collection and a formula need no evidence. A value that an
option or a `change` sets is different: with no evidence, it is an error, not a warning.

`support.cited_data` checks a value whose evidence cites a datum of a claim (`datum: key`). The
value must be that number, in dimension and scale, read exactly. So `0.1 day` is the datum 2.4 h. A
difference gives the warning `datum` with both numbers. A value that the compiler cannot fix (a
draw, a read of another value) also gives `datum`.

A model with these warnings still compiles and runs. `napkin compile` lists each warning. Each other
command writes one line that counts the `no_record` warnings. The catalogue checker,
`tools/check.py`, refuses a package with a `no_record` or `datum` warning.

## The configuration of a run

`model/runs.py`, `configuration(declared, base, run, edits, options, model_hash)`, gives the
configuration of one run. `Compiled.configure(run, edits, options)` calls it.

- `base` is the default run: a median run to the horizon, with `resolution` as the longest step.
- `run` names a named run of the model. Its options give their inputs their values.
- `edits` is the edit document ([cli.md](cli.md#the-edit-document)). The compiler checks it whole,
  in every run of the model, before any run takes its values.
- `options` makes a combination of options that no named run names.

An option or an edit configures a run of one program. A variant or a `change` changes the model, so
it has a program of its own.

## The model hash

`model/identity.py`, `model_hash(declared, program, base)`, names one revision of what a model
computes. It covers:

- the canonical bytes of the program;
- the options and the named runs that set its inputs;
- the horizon and the numerical settings of its default run;
- the version of the language, `LANGUAGE_VERSION`.

It covers no label: no text, title, menu line, note or `record` declaration, and not the places of
the lines, the comments or the names of the files. So a corrected label or a moved line keeps the
hash, and a saved edit document stays valid. An edit document names the model hash of its revision
(`model_hash`).

## Proofs over a program

Two modules prove facts about a program under one configuration. Each conclusion has its reason. No
run uses them to change its work.

- `program/reach.py`, `reach(program, configuration)`, finds which events can start and which values
  each named state can take. It is conservative: "cannot start" is proved, "can start" says only that
  nothing rules it out. `napkin draw --run` uses it to leave out the events that cannot start.
- `program/proofs.py`, `never_falls(program, configuration, key)`, proves that a value never falls
  over a run. A lag of a report needs this proof. `reads(program, configuration, key)` gives the parts
  that a value can read, for the evidence trail of a report.

For the named run `standard` of `examples/incident_response_tempo`, `reach` gives these conclusions
for two of its events:

```text
attack.attempt True | its trigger attack.attempt.when[0] can fire
queue.recover False | nothing that can happen starts it: no start of the setup, no trigger whose condition can hold, no statement that can run
```

## The artifact

`program/artifact.py` keeps a compiled program in a file. A fresh process loads the file and runs it
without the parser. The file holds the canonical bytes of the program and of its side table:

```text
napkin program 4               the name of the format and FORMAT_VERSION
language 0.2.3                 LANGUAGE_VERSION
program <size> <sha256>        the program's canonical bytes, and their digest
<the program's bytes>
table <size>                   the side table's canonical bytes
<the table's bytes>
```

- `FORMAT_VERSION` (4) names the layout and the dataclasses of the file. It goes up with each change
  of a dataclass, a field added, removed, renamed or moved included.
- `LANGUAGE_VERSION` (`0.2.3`) names what a program means. It goes up with each change of what a
  program computes. The model hash covers it.
- A loader reads only its own format and language. It refuses any other by name, and the remedy is
  to compile the model again.

`ArtifactError` has these codes: `not_a_program`, `format_version`, `language_version` and `damaged`.

**The side table** (`SideTable`) maps each part that has an origin to its `Location`. A location
holds the kind and the name of the part, and its file, line and column. It also holds the label (the
first text under the part), the evidence and the title.
The kinds at which a run can stop are `event`, `stage`, `gate`, `trigger`, `assign`, `move`, `start`,
`if`, `switch` and `case` (`EXECUTABLE`). No hash covers the side table: a new label changes the
table and keeps the program's bytes.

**The identity** of a program is its digest (`Artifact.digest`), the SHA-256 of its canonical bytes.
A checkpoint names its program by this digest.

```python
import napkin
from napkin.program import artifact

model = napkin.load_scenario('examples/piano_tuners')
model.artifact().save('tuners.program')

loaded = artifact.load('tuners.program')
record = napkin.run(loaded.program, model.configuration)
print(napkin.read(record, loaded.program, ['tunings_done'], [8760])[0].values)  # (2923.537487392582,)
```

The artifact holds no configuration. A caller gives one: `Compiled.configuration`, or a
`Configuration` of `program/config.py`.
