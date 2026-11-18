# The compiler

The compiler reads the model file of a package and makes the model that the engine runs. It works in
five steps. Each step is a function: it takes one form of the model and gives the next form.

```text
.scn text -> syntax tree -> resolved model -> flat structures -> resolved run -> engine
```

This page is the contract of each step: its modules, its input, its output, what it guarantees and
how it fails. It then describes the typed expressions, the lowering and the analysis, and follows
three features from the file to the structure. [language.md](language.md) says how a file writes a
model. [engine.md](engine.md) says what a run does with a structure, and
[python-api.md](python-api.md) what a program reads. [extending.md](extending.md) lists what to change
for each kind of new feature.

The paths on this page are relative to `napkin/`. The modules of this page are internal: the public
API is the list of names in [python-api.md](python-api.md).

## Contents

1. [The chain](#the-chain)
2. [Typed expressions](#typed-expressions)
3. [The contract of an operation](#the-contract-of-an-operation)
4. [The consumers](#the-consumers)
5. [The lowering](#the-lowering)
6. [The analysis](#the-analysis)
7. [Three features from the file to the structure](#three-features-from-the-file-to-the-structure)
8. [What is not here yet](#what-is-not-here-yet)

## The chain

| Step | Function | What it gives |
| --- | --- | --- |
| 1. Text to syntax tree | `front.load(path)` in `model/language/front.py` | A `File` of `model/language/nodes.py` |
| 2. Syntax tree to resolved model | `resolve(file, library, files)` in `model/language/resolve.py` | A `Scenario` of `model/semantic.py` |
| 3. Resolved model to flat structures | `Builder` in `model/lower/builder.py`, then `structure_facts` in `model/analysis/structure.py` | One structure for each set of start-state options: a `Structure` of `model/structure.py` |
| 4. Structure to resolved run | `Model.resolve(run, values)` in `model/model.py` | A `Resolved` of `model/structure.py` |
| 5. Resolved run to engine | `simulate(rs, library, settings)` in `engine/runtime.py` | A trajectory |

`napkin.load_scenario(path)` does steps 1 to 3. It also does step 4 for each run of the model as its
files write it. Its functions are `front.build` and `front.compile_file`, then `finish` of
`model/model.py`. A study does step 4 again with its edits, and then step 5
([engine.md](engine.md#the-study)).

**How a step fails.** Steps 1 to 4 raise `ModelError` (`model/ir.py`). Its `diagnostics` are a list of
dicts, each with a `code`, a `path`, a `message` and a `severity`. The `path` is the place of the part
in the file, such as `clinic/report/when:`. The function `located` of `model/model.py` adds the `line`,
the `column` and the `file` of that place. It reads them from the line map of the syntax tree.

The examples of diagnostics on this page come from the model of
[the last section](#three-features-from-the-file-to-the-structure), with one line changed for each.
They leave the `file` out.

### 1. From the text to the syntax tree

- **Modules.** `model/language/lex.py` reads the lines and the tokens. `parse.py` is the parser,
  `nodes.py` has the nodes, `modules.py` reads the files of one model, and `tables.py` reads the
  table of a set of instances ([language.md](language.md), §2.3).
- **Input.** The path of a model file: the main file of a package, or the file of a variant.
- **Output.** `front.load(path)` gives `(file, files)`, and `file` is one `File`. It holds the
  scenario line, the things, the top-level checks and outputs, the options, the runs, the notes and
  the records. Each list is in the order of the file. `files` gives the file of each line when the
  model has several files; else it is `{}`. `front.read(text, origin)` gives the `File` of one text.

The step guarantees these things:

- Each node has its `place` and its `line`. A place is a tuple that is unique in the file, such as
  `('clinic', 'report', 'when:')`. `File.lines` gives the line of each place, and `File.columns` its
  column.
- The parser reads only the form of each line. It gives no meaning to a name.
- An expression stays the list of its tokens (`Expr`).
- A model of several files is one `File`. `modules.read` merges the files: each file after the files
  that it uses, and the entry file last ([language.md](language.md), §2.12).

The step fails in two ways:

- A line that the language does not write raises `SyntaxProblem` (`model/language/lex.py`). The front
  end makes it a `ModelError` with the code `syntax` and an empty path. The diagnostic has the line,
  and the column when the problem has one.
- A problem of the files of a model has the code `modules`. Examples are a module that is missing, a
  circle of `use` lines, and a variant outside its `variants/<name>/` folder.

```text
{'code': 'syntax', 'path': '', 'message': 'a tab is not allowed: each level of nesting is four spaces', 'severity': 'error', 'line': 21}
```

The model hash covers the meaning of this tree: each node by its fields, and each expression by its
tokens. It covers no line, place or column (`identity` of `model/language/evidence.py`). It also
covers the units that the model uses, the records that it reaches and the version of the language
([python-api.md](python-api.md#the-model)).

### 2. From the syntax tree to the resolved model

- **Modules.** `model/language/resolve.py` is the resolver. `model/language/expressions.py` has the
  grammar of an expression. `model/semantic.py` has the records of the resolved model, and
  `model/resolved.py` the typed nodes of a resolved expression. `model/meaning.py` checks the options
  and the runs, and `model/runs.py` makes the table of the runs.
- **Input.** The `File`, the library and `files`.
- **Output.** `resolve(file, library, files)` gives `(scenario, resolver)`. `scenario` is a `Scenario`:
  the resolved model, which the code calls the semantic model. It holds each entity with its values,
  flows, shares, events, checks and status, and then the outputs, the options and the runs.
  `front.compile_file` then makes the table of the runs from it (`Runs.from_scenario`). The table
  holds the value of each input in each run.

The step guarantees these things:

- A template makes no entity. Each instance is one entity, and each copy of a set is one entity
  (`name.1`, `name.2`). An instance has the members of its template, in the template's order, with
  its own changes.
- Each number `var` has its kind: a stock, a tally or a number state ([language.md](language.md),
  §2.4).
- Each event has its `rank`, which starts with the line of the event in the model. The rank orders the
  events of one moment.
- Each name of each expression is resolved, or it is a `Problem` with its message (below).
- The checks of `model/meaning.py` hold: the menu of the options, the runs, and no value that the
  options of two groups set.

**An expression.** `Resolver.expression` gives an `Expression` of `model/semantic.py`. It has three
fields: `written` (how the file writes it), `node` (its typed nodes with its names resolved) and
`where` (its place). The resolver makes it in three steps:

1. `expressions.tree(tokens)` writes the tokens as Python text and reads that text with `ast`. Each
   name of the file becomes a placeholder. `is` becomes `==`, and `12 h` becomes `q(12, 'h')`.
2. `Resolver.resolve_tree` puts a resolved leaf in the place of each placeholder.
3. `resolved.of_tree` gives the typed nodes of that tree, which the `Expression` keeps. Python's
   tree is only the resolver's working form. A call with arguments by name is one typed node, a
   `Named` (below). A part that the language does not have is a `Foreign` node, which keeps Python's
   tree of that part: for example `(a, b)`, or a call of something that is no name. The target of a
   line (`x = v`) and the ends of a move are the resolver's own records (`semantic.Ref`), not nodes.

A resolved expression is a tree of the nodes of `core/expr.py`
([Typed expressions](#typed-expressions)), with five kinds of leaf from `model/resolved.py`:

| Leaf | What it is |
| --- | --- |
| `Ref` | A value: member `member` of entity `entity`, or an output of the scenario when `entity` is None. `written` is the name as the file writes it. |
| `EventRef` | An event: its `key` (`entity.event`) and `ending`, the outcome that the name names, or None. |
| `Terms` | The members of a list: one `Ref` for each entity of a list link, or for each copy of a set. `written` is the name of the list as the file writes it. |
| `Word` | `true` or `false`. |
| `Problem` | A part that the resolver cannot read, with its `message`. |

A call keeps the name of its function as the file writes it. The name can be `sum`, `since`,
`delayed`, a distribution or a function of the engine. The value of a line of an outcome (`x = v`)
and the amount of a move (`move A from S to D`) are typed nodes too.

A call with arguments by name is a `Named` node of `model/resolved.py`. A distribution is written
that way: `normal(a, b, min=c)`. `resolved.named(function, args, named)` makes the node. It has
three fields:

| Field | What it is |
| --- | --- |
| `function` | The name of the function. |
| `args` | The nodes of the arguments by position. |
| `named` | One pair of a name and a node for each argument by name, in the order in which they are written. |

- Two such calls with the same fields are one object. The order of the arguments by name is a part
  of the identity.
- The parts of the node (`children`) are the arguments by position, then the arguments by name.
- `resolved.breadth_first` gives an argument by name one level deeper than an argument by position.
  That is its level in Python's tree of the call, so the walk keeps the order of `ast.walk`.
- The typing gives a `Named` of a distribution or of `delayed` to the event that reads it
  (`Typing.fired`). It refuses a `Named` of any other function.
- The notation of the picture reads a `Named` as a call with keyword arguments, and writes that call
  back as the same node (`draw/notation.py`).

The grammar of an expression has no `=`, so an expression of a file has no argument by name. That
grammar reads the form `**x`: it gives a pair whose name is None, and the typing refuses the call. A
file writes arguments by name only where a value is a distribution: the value of an input or of a
`let`, or the value that an option gives an input. `model/uncertain.py` reads such a distribution
from its written text ([What is not here yet](#what-is-not-here-yet)).

The step fails in two ways:

- `Resolver.fail` adds a diagnostic with the code `structure`, at the place of the part. The resolver
  collects these diagnostics and raises `Problems`, and the front end raises `ModelError` with them.
- A model file with no scenario line has the code `version`.

```text
{'code': 'structure', 'path': 'clinic/review', 'message': 'an event that fires once has no window: once, or each W', 'severity': 'error', 'line': 26, 'column': 5}
```

A name that names nothing does not stop the resolver, and neither does an expression that the grammar
cannot read. Each is a `Problem` in the tree, and the lowering reports it (step 3). So these
diagnostics come in the order of the lowering.

### 3. From the resolved model to the flat structures

- **Modules.** `model/lower/` is the lowering ([The lowering](#the-lowering)).
  `model/analysis/structure.py` has the checks of a structure ([The analysis](#the-analysis)).
  `model/structure.py` has the typed parts.
- **Input.** The `Scenario`, the table of the runs and the library.
- **Output.** One structure for each set of start-state options that a run uses. The key of a
  structure is the sorted tuple of those options, and `()` for the runs that have none.

The function `built` of `model/model.py` calls the builder in this order:

1. `builder.build()` makes the structure that every set shares.
2. `builder.start_sets()` gives the sets of start-state options, in the order of the runs.
3. `builder.derive(base, starts)` gives the structure of one set. It has the start values of the set.
   It does not have the parts that cannot act from those values.

The builder also keeps the whole structure of each set (`builder.whole`), which has every part. It
keeps the parts that each structure leaves out, with the reason for each (`builder.left_out`).

The builder writes each structure as a mapping, and each expression in it as its node. The build
reads each mapping into typed records at once, in one place (`typed_of` of `model/model.py`), and it
keeps no mapping. A record holds the node that the builder wrote: no text is written and read again. The model, the hybrid core and each program read typed records.
`Model.structures[starts]`, `Model.whole[starts]` and `Model.structure_of(run)` each give a
`Structure` ([python-api.md](python-api.md#the-structure)). `Structure.of` reads it from the mapping,
one time. It loses nothing: a key of the mapping that no field takes raises `StructureError`.

The lowering guarantees these things:

- Each part has its name in the structure ([python-api.md](python-api.md#names)) and its `path`.
- Each expression reads only names of the structure, in the form that the engine evaluates.
- The parts are in the compiled order. The entities go by name, each with its values in the order of
  the file. The flows go by name.

Then `finish` of `model/model.py` makes the typed parts of each structure and of each whole
structure (`Structure.of`), once, and gives them to `structure_facts`, the checks of a structure.
After it, these things hold:

- Each expression has the unit that its place needs.
- The formulas have an order in which each comes after the formulas that it reads
  (`computed_order`).
- Each `when` has a class: `discrete`, `timer`, `crossing` or `face`
  ([engine.md](engine.md#triggers)).
- The flows that take from one stock are in one share. A stock needs no share when the form of each
  rate shows that the rate is zero for an empty stock.

`finish` also checks the library, the records that the lines cite, the timescales and the start.

The step fails in three ways:

- The lowering raises `AnalysisError(path, message)`. The model makes it a diagnostic with the code
  `build`, at that path. A `Problem` of the resolver fails in this way.
- The lowering raises `RewriteError` for a form that has no meaning. Its diagnostic has the code
  `reference`, or `expression` for a text that is no expression.
- `structure_facts` gives every diagnostic of a structure: it does not stop at the first. Its codes
  include `expression`, `unit`, `bounds`, `cycle`, `allocation`, `coupling`, `unsupported_condition`,
  `lag`, `additive` and `link_basis`. Each diagnostic names its structure in `context`.

```text
{'code': 'build', 'path': 'clinic/report/when:', 'message': 'closed is not an event or a named state', 'severity': 'error', 'line': 24, 'column': 5}
{'code': 'reference', 'path': 'clinic/report/when:', 'message': 'since() must be one side of a comparison, e.g. since(e) >= d', 'severity': 'error', 'line': 24, 'column': 5}
{'code': 'unsupported_condition', 'path': 'clinic/review/each:', 'message': 'each W and while K read only values that change at moments', 'severity': 'error', 'context': 'structure []', 'line': 26, 'column': 5}
```

### 4. From a structure to a resolved run

- **Modules.** `model/model.py` has `Model.resolve`. `model/compile.py` has `resolve_structure` and
  `check_parameters`. `model/analysis/values.py` has the checks of a resolved run, and
  `model/uncertain.py` the central value of a distribution.
- **Input.** The name of a run, and `values` for some inputs. Each other input takes the value of the
  run.
- **Output.** A `Resolved`: a `Structure` with the fields of one run
  ([engine.md](engine.md) calls it the resolved structure).

| Field of a `Resolved` | What it holds |
| --- | --- |
| `values` | The value of each input, in execution units. |
| `parameter_values` | The value of each input, in the unit of the input. |
| `time`, `initiation` | The horizon, the timescales and the resolution; and the start, or None. |
| `run`, `options`, `starts`, `model_hash` | The run, its options, its start-state options and the hash of the model. |
| `proven_zero_stock_faces`, `proven_monotone_crossings`, `proven_cumulative_outcomes` | What the proofs of this step proved. |
| `distributions` | The distributions of the run, when its values hold some. The run takes their central values. |

`Model.resolve` works in four steps:

1. It takes the values of the run as its options write them, and then the values of the caller. A
   distribution takes its central value.
2. `Model.numbers` gives the numbers of the engine: a bool is 0 or 1, and a named value is its code.
   `check_parameters` checks each number against its input.
3. `resolve_structure` normalizes each value to execution units. It applies the blocking checks of
   the inputs, and then the checks of the values (`value_facts`, [The analysis](#the-analysis)). It
   gives what the resolution has of its own, and the number of each bound of a quantity that is
   written as an expression. It writes nothing into the structure.
4. `Resolved.over` makes the typed record: the parts of the structure themselves, with what the
   resolution has of its own.

**A resolution copies no part.** The parts of a structure cannot change. Thus each resolved run of
a structure shares them: the `flows` of the run are the `flows` of the structure, the same object.
Only a quantity with a bound that is written as an expression is made again, with the number of
that bound. Every check of a resolution reads those typed parts: the checks of the values of the
inputs too (`check_parameters` reads each input as a `Parameter`). The reports and the key of the
run store read them as well. No structure and no resolved run keeps a mapping of the builder: a
reader reads its parts, and `plain()` writes its plain data for a report, a key or a test. A reader that wants
another run makes one from that plain data (`Resolved.of`) or from the parts (`changed`).
`Resolved.adding` gives a run the keys that come after its resolution (its name and its options,
its distributions, the luck of a sample); the copy shares the parts of the run.

The step guarantees these things:

- Each value is in the range of its input, and a fixed value did not change.
- The blocking checks of the inputs hold.
- Each bound of a quantity is a number, and each start value is within its bounds.
- Each expression has a value in every state that the bounds allow. The proof is by intervals: it
  does not sample.
- Each crossing is in a proved class ([engine.md](engine.md#triggers)).
- No check on the state can fail and hold again between two solver points
  ([engine.md](engine.md#checks)).

The build resolves each run that it admits, one time, and keeps the result. So `Model.resolve(run)`
with no other values gives a copy of that result, and it proves nothing again. The build also checks
each whole structure that leaves a part out (`whole_errors` of `model/model.py`). It applies the
checks of a resolved run, with the values of one of the runs of that structure.

The step raises `ModelError`. A diagnostic of a value has a code such as `input`, `locked`, `bounds`
or `binary_control`. A blocking check has the code `check:` with its name. The codes of the checks
of a resolved run (`value_facts`) include `initial_bound`, `dynamic_domain`, `rule_domain`, `output_domain`,
`check_domain`, `unsupported_condition`, `cumulative_proof` and `invariant_proof`. Each of its
diagnostics names its run in `context`.

```text
{'code': 'initial_bound', 'path': 'clinic/waiting', 'message': 'Initial value violates its bounds', 'severity': 'error', 'context': 'runs/base', 'run': 'base', 'line': 8, 'column': 5}
```

### 5. From a resolved run to the engine

`simulate(rs, library, settings)` of `engine/runtime.py` takes a `Resolved` and gives the trajectory
of the run. [engine.md](engine.md) is its contract. A typed part holds each expression as its node:
`rs.flows[name].rate` is a node of `core/expr.py`, and `str` of it is its text. The plan of the
engine reads the typed parts: those of the resolved run (`timeline.Plan.flat`), or, for a model
with a table, those of the structure with each list as one node (`timeline.Plan.of`, which takes
them from `Hybrid.listed`). One plan serves each run of one structure: the engine keeps the last
plans by a digest of the typed parts, and it keeps the digest of each part by the part itself,
because the runs of one structure share their parts. The checks of a structure have not read a
structure with each list as one node, so the hybrid core gives the trigger of each rule its place
and its class itself, with the classifier of the compiler (`hybrid.classified`). The classifier
reads the typed parts. A trigger that the classifier refuses has no class, and the plan names it.
The engine evaluates with programs that `core/evaluation.py` writes from the nodes.

A run that stops gives its diagnostics in the trajectory, and the engine rejects the study that holds
it ([engine.md](engine.md#when-a-run-stops)).

## Typed expressions

`core/expr.py` has the nodes of an expression. The resolver and the lowering make them, and the
analysis and the engine read them.

### The nodes

| Node | What it is | The function that makes it |
| --- | --- | --- |
| `Const` | A constant: a number, a yes/no or a text. | `const(value)` |
| `Ref` | A reference to a named value. | `ref(name)` |
| `Unary` | An operation on one value: `neg`, `pos` or `not`. | `unary(op, operand)` |
| `Binary` | An operation on two values: `add`, `sub`, `mul`, `div` or `pow`. | `binary(op, left, right)` |
| `Compare` | A chain of comparisons: `eq`, `ne`, `lt`, `le`, `gt`, `ge`. | `compare(ops, operands)` |
| `BoolOp` | `and` or `or` of two values or more. | `boolean(op, values)` |
| `IfElse` | A choice: `body if test else orelse`. | `if_else(test, body, orelse)` |
| `Call` | A call of a function of `expr.FUNCTIONS`. | `call(function, args)` |
| `Foreign` | A part that is outside the language. | `foreign(tree)` |

`expr.FUNCTIONS` has fourteen functions: `min`, `max`, `clip`, `abs`, `sqrt`, `exp`, `expm1`, `ln`,
`log1p`, `erf`, `q` and the three over the members of a list, `sum`, `any` and `all`
(`expr.LISTED`). `q(number, unit)` is a number with its unit. `sum(a, b, c)` is `a + b + c`, added
from the left; `any` and `all` are the `or` and the `and` of their members; one member is that
member. An author writes them over a list (`sum(zones.x)`), and the lowering gives the members.

A caller makes a node with its function, never with its class. A node cannot change: a write to a
field raises `AttributeError`. `node.children` gives the nodes that it is made of, in their order.
`made(kind, *fields)` makes a node of a kind that another module defines. The five leaves of the
resolver are such kinds, and so is its call with arguments by name (`Named`).

### Three things that the compiler keeps apart

1. **The identity of a computation** is the node. Two nodes with the same kind, the same operation
   and the same parts are one object. So `a is b` says that two expressions compute the same thing.
   A node is also a key of a dict by itself. A node holds no unit and no place in a file.
2. **What holds of a computation in a context** is no field of a node: its unit, its interval,
   whether it moves in a segment. The analysis that finds a fact keeps it, by the node and the
   context. For example, the classifier of the engine keeps what it proves to be zero by the node and
   by the facts of the branch (`engine/continuous/kernels.py`).
3. **The places where a computation is written** are apart from the node, because one node can be
   written in many places. Today a place is the `where` of an `Expression` of the resolved model, and
   the `path` of a part of a structure. The line map of the model gives the line of a place.

### One node for one computation

- Each node that is alive is in one table, by its key: its kind, its operation and its parts. A
  function that makes a node looks in the table first, under a lock. So two threads that ask for one
  key get one object.
- A constant has the type of its value in its key. So `1`, `1.0` and `True` are three constants, and
  `0.0` and `-0.0` are two.
- `written(value)` gives the node of a constant as a text writes it. A number below zero is the
  negation of the number above it: `-1` is `-(1)`. So the text of a node reads back to the same node.
- A node pickles to itself in one process, and a copy of a node is the node.

**What a node lives by.** A node is alive while something holds it: a part of a model, a larger node,
or a memory with a limit. The table holds a node weakly, so it does not keep the node alive. Two
memories hold nodes or their functions, each with a limit of 65,536 entries:

- `expr.read` keeps the nodes of the last texts that it read;
- `evaluation.function` keeps the functions of the last nodes.

So a long study, which reads new numbers for each sample, does not fill the memory with nodes.

```python
from napkin.core import expr

a = expr.read('rate * staff')
b = expr.binary('mul', expr.ref('rate'), expr.ref('staff'))
print(a is b, repr(a))
print(expr.const(1) is expr.const(1.0), expr.read('-1') is expr.written(-1))
node = expr.read("min(a.x, q(2, 'h')) if b.on == 1 else -a.x ** 2")
print(expr.text(node))
print(sorted(expr.names(node)))
```

```
True <Binary rate * staff>
False True
min(a.x, q(2, 'h')) if b.on == 1 else -a.x ** 2
['a.x', 'b.on']
```

### Read and write a node

| Function | What it gives |
| --- | --- |
| `read(source)` | The node of an expression text. It reads a number or a yes/no as its text, and a node is itself. It applies the limits of size. It keeps the nodes of the last texts, so it reads a text in use one time. |
| `parse(written, functions)` | The node of a text, with no limit of size and no memory. `functions` names the functions whose calls are calls. |
| `of_tree(tree, functions)` | The node of one part of Python's tree of an expression. |
| `text(node)` | The expression as text. For a node with no part outside the language, it is the text that `ast.unparse` writes for Python's tree. That text reads back to the same node. |
| `names(node)` | The names that the expression reads: each reference in it. The name of a function is no name that it reads. |
| `outside(node)` | Whether the expression has a part that is outside the language. |
| `walk(node)` | Each node of the expression: the node itself, then the nodes of each part, in order. |
| `breadth_first(node)` | Each node, level by level: the order in which `ast.walk` gives the parts of Python's tree. The engine finds the switching surfaces of a run in this order. |

`text`, `names` and `outside` keep their answer on the node. `read` raises `SyntaxError` for a text
that Python cannot read, and `TypeError` for a source that is no text and no number.

### A part outside the language

A text can hold an operator or a form that the language does not have, such as `a % 2` or
`floor(b)`. That part is a `Foreign` node. It keeps Python's tree of the part, and its identity is the
dump of that tree. A call is a `Call` only for a name of `functions`. So `parse('since(e) >= 2')`
gives a `Foreign` part for `since(e)`: `since` is no function of the engine.

A text with such a part does not fail when it is read. It fails when a consumer asks for its value or
its unit. The value of `a % 2 + floor(b)` is the error `Unsupported operator`, and its unit the error
`Unsupported arithmetic operator`. A model cannot hold such a part: the checks of a structure refuse
it with the code `expression`.

### The limits of size

`read` refuses a text of more than 10,000 characters (`LONGEST`), a text whose Python tree has more
than 1,000 parts (`LARGEST`), and a text with more than 150 operations one inside the other
(`DEEPEST`). Each is an `ExpressionError`. `parse` applies the limit of depth only: it is for a
reader of the form of an expression whose size another check judges.

`limited(node)` applies the three limits to a node, on the text of the node (`text`) and Python's
tree of that text. The count of the parts has the tree of the whole text with them, so a node can
have one part fewer than a text that `read` takes. A text that Python cannot read is an
`ExpressionError` too. `parts(node)` gives the number of parts of Python's tree of the text of a node,
and each node keeps it. `compile_expression` of `napkin/expressions.py` calls `limited` for each
expression of a structure.

The limits count the text of the node that a structure holds. There, a sum over a list is a chain
with one term for each member ([The lowering](#the-lowering)), so each member counts, and the chain
is as deep as the number of its members.

The limit of depth is there because the readers of an expression go down its tree with calls: at
most four for each level, where Python has 1,000 calls one inside the other. `height(node)` gives the
depth of a node, with a list and not with calls. The resolver gives an expression of a file that is
deeper than the limit a problem at its place, so the diagnostic of the author has the line. A sum
over the members of a list that is too deep is refused by the builder, with the code `expression`,
at the line of the part that holds it. A model with a table has no such limit for its lists: the
hybrid core holds a list as one node
([What is known for every row of a table](#what-is-known-for-every-row-of-a-table)).

The limit also holds for what the checks and the engine make of an expression. The engine writes
each formula in the place of its name (`timeline.plan`), so the checks of a structure refuse an
expression whose tree, with its formulas written in, is deeper than the limit, at the place of
each part that holds such an expression (`analysis.structure._written_out_errors`): a chain of
formulas that read one another can be too deep, although each formula is within the limit by
itself. The proofs of the checks of a run put an expression under the guard of its rule, or
multiply it by a coefficient, and refuse what they make when it is too deep, with the code of the
proof. So an expression within a few levels of the limit can be refused by such a proof.

## The contract of an operation

`core/ops.py` has one `Operation` for each operation that a node can have. There are 31. They are
the two signs, `not`, `and`, `or`, the six comparisons, the choice (`if`), the five operators of
arithmetic and the fourteen functions. A contract states what no consumer may decide for itself.

| Field | What it states |
| --- | --- |
| `name` | The name of the operation. |
| `arity` | The number of its arguments. None means one or more. |
| `units` | Its rule for units: one of the eleven names of `UNIT_RULES`. |
| `domain` | Where it has a value, as a sentence. |
| `kinks` | Where it is not smooth, as a sentence. |
| `partials` | Its partial derivative by each argument, where it is smooth. It is a function: it takes the nodes of the arguments and gives one node for each argument. It gives None for an argument that has no derivative of its own, and the field is None for a condition. |
| `monotone` | How its value moves with each argument while the others stay. `+`: it never falls when the argument rises. `-`: it never rises. `none`: it can do both. `sign`: it is one of the two while the argument stays on one side of zero, and the other arguments decide which one. |

For example, the partials of `div` by `x` and by `y` are the nodes of `1 / y` and `-(x / (y * y))`. An
operation with no fixed number of arguments has one entry in `monotone` for all of them.

The code reads two of these fields today. `core/evaluation.py` reads `arity` for the calls, and
`core/units.py` reads `units`. `domain` and `kinks` are sentences. The contracts state `partials` and
`monotone`, and `tests/core/test_ops.py` tests them against the values of each operation. No consumer
reads them yet.

`operation_of(node)` gives the name of the operation of a node. It gives None for a constant, a
reference and a part outside the language. For a chain of comparisons it gives the first one, and
`node.ops` has them all.

**The rules for units.** Each rule of `UNIT_RULES` has a name and a sentence:

| Rule | Operations | What it says |
| --- | --- | --- |
| `number` | `neg`, `pos`, `abs` | The argument is a number in any unit, and the result has that unit. |
| `condition` | `not`, `and`, `or`, `any`, `all` | Each argument is a yes/no, and so is the result. |
| `compared` | `eq`, `ne`, `lt`, `le`, `gt`, `ge` | The arguments have one unit, and the result is a yes/no. Only numbers have an order. |
| `choice` | `if` | The test is a yes/no. The two branches have one unit, which the result has. |
| `same` | `add`, `sub`, `min`, `max`, `clip`, `sum` | The arguments are numbers of one unit, and the result has that unit. A plain zero has every unit. |
| `product`, `quotient` | `mul`, `div` | The arguments are numbers. The result has the product, or the quotient, of their units. |
| `power` | `pow` | The exponent is a plain number. A base with a unit needs an exponent that is a written number. |
| `root` | `sqrt` | The result has the unit of the argument to the power one half. |
| `plain` | `exp`, `expm1`, `ln`, `log1p`, `erf` | The argument is a plain number, and so is the result. |
| `literal` | `q` | The first argument is a plain number, and the second the written name of a unit. The result has that unit. |

**The check of a consumer's table.** A consumer keeps what it does with each operation in a table,
from the name of the operation to its handler. `handlers(consumer, table, unsupported=())` checks such
a table and gives it back. It raises `LookupError`, with the names, in three cases:

- the table has no handler for an operation that the consumer does not name in `unsupported`;
- the table, or `unsupported`, names an operation that the language does not have;
- an operation has a handler and is also in `unsupported`.

Each consumer with a table calls `handlers` when Python reads its module. So a new operation with no
handler in some consumer is an error at import, and not a wrong value in a run. The message names the
consumer and the operation: `the value of an expression: no handler for erf`. No consumer names an
operation in `unsupported` today.

## The consumers

| Consumer | Module | Entry | What it gives | Its table |
| --- | --- | --- | --- | --- |
| The value and the programs | `core/evaluation.py` | `function`, `value`, `program` | Python code that computes the value of a node. | `TABLE` |
| The values for many instances | `core/arrays.py` | `values` | The value of a node for each instance of a family in one pass, with numpy: for each instance the value that the first consumer gives, with a choice and an `and` read for each instance by itself. The engine reads it for the instances of a space (`Run.value` of `engine/timeline/run.py`). | `TABLE` |
| The units | `core/units.py` | `unit_of` | The unit of a node, and the names that it reads. | `RULES`, `TABLE` |
| The intervals | `core/intervals.py` | `prover` | The closed interval of a node, with the proof that it has a value. | `TABLE` |
| The zero faces | `core/faces.py` | `constant_on_faces` | The stocks that a node compares with zero. | None |

### The value and the programs

`function(node)` gives `f(E, R)`: the value of the node in the environment `E`, with the registry of
units `R`. `value(node, environment, registry)` calls it. `program(assignments, outputs, …)` gives one
function for many expressions. It assigns each named node of `assignments` in order, and then gives
the tuple of the values of `outputs`.

Both are Python code that the module writes from the nodes, with one meaning:

- The code checks each part that gives a value: a number must be finite and real. A comparison, `and`
  and `or` give a yes/no, which the code does not check.
- A choice computes only the branch that its test takes. `and` and `or` stop at the term that
  decides.
- A name with no value fails when the code reaches it, and not before.
- A call with a wrong number of arguments fails when the code reaches it. So does a part outside the
  language.

A program can know some values before it runs (`constants`). `program` computes a part that reads
only known values one time, when it makes the program, and it writes the value into the code. A part
whose computation fails stays code, so it fails only when a run reaches it. The engine makes its
programs in this way ([engine.md](engine.md#the-store-and-the-environment)).

Python reads no code with more than 200 brackets one inside the other, and the code of one checked
operation has up to six. So the code of a node with more than 24 operations one inside the other
(`SPLIT`) is written in parts. Each part is a line of its own, `_pN = lambda: …`, and the code above
it calls `_pN()` where it would compute the part. A part is cut where the code under it, down to the
cuts below, has 24 operations one inside the other, so no code is deeper than that, whatever the
form of the tree. The part is computed where it was, when it was, and only when the code reaches
it: the values, their order and each failure are those of the code in one piece. A node that is not
that deep has the code that it had.

A failure is an `ExpressionError` (`core/errors.py`), or an error of Python's arithmetic.
`checked_value` makes each of them an `ExpressionError` that names the expression.

`TABLE` has one handler for each of the 31 operations. A handler gives the code of its operation and,
when the arguments are known, its value. `RUNTIME` has the names that the written code reads.

### The units

A `Unit` has its dimensions, its scale in execution units and its kind. The kind is a number, a
yes/no, a text or the plain zero, which has every unit of a number. A `UnitRegistry` holds the units
that a model declares, and it composes the other units from them ([language.md](language.md), §2.1).

`unit_of(node, symbol_units, registry)` gives the unit of an expression and the names that it reads.
`symbol_units` gives the unit of each name. An expression that breaks a rule is an `ExpressionError`:
the first one that a reader meets from left to right.

The contract decides the rule. `RULES` has one function for each rule of `ops.UNIT_RULES`, and the
handler of an operation is the function of the rule that its contract names. A rule with no function
is a `LookupError` when Python reads the module.

```python
from napkin.core import expr, units

registry = units.UnitSystem({'days': {'dimensions': {'time': 1}, 'scale': 24}})
people = units.Unit((('people', 1),))
symbols = {'stock': people, 'wait': registry.parse_unit('days'), 'on': units.BOOLEAN}
unit, names = units.unit_of(expr.read('stock / wait if on else 0'), symbols, registry)
print(unit.dimensions, sorted(names))
```

```
(('people', 1), ('time', -1)) ['on', 'stock', 'wait']
```

### The intervals

`prover(ranges, registry, aliases)` gives a function of one node. The function gives the closed
interval of the node over `ranges`, which gives the interval of each name in execution units. It
raises `ExpressionError` when it cannot show that a part has a value:

- a divisor that can be zero;
- a logarithm of a number that can be zero or less;
- a root of a number that can be below zero;
- an exponential that can leave the range of a float.

The proof is conservative: what it cannot show, it refuses. It does not sample. These rules decide
what it can show:

- `aliases` gives the node of the formula of a name. Such a name has the interval of its formula.
- A name with no range and no formula can be any number.
- A condition narrows the branch that it guards. In `x / y if y > 0 else 0`, the divisor is above
  zero.
- The prover keeps the interval of a formula for the facts of the branch that reads it. So it proves a
  formula that many formulas read one time for each such set of facts.
- `prove.over(ranges)` gives the prover of the same formulas over other ranges. The two keep their
  answers together. An answer has a key that stands for everything that it depends on: the formula
  or the expression, and the range of each name that it reads through the formulas. So what one
  prover found of a formula is not found again by the other where each of those names has one range
  for both, also when a range changes and changes back. What a prover gives is what a new prover
  over its ranges gives. The answers that are kept have a limit (`KEPT`); when it is reached, all of
  them go and are proved again when they are asked for.
- `prover(ranges, registry, aliases, weights)`: `weights.get(name, 1)` says how many values a member
  of a list that reads `name` stands for. A `sum` counts such a member that many times. A least, a
  greatest, `any` and `all` need no count. The hybrid core uses it for the rows of a table (below).

```python
from napkin.core import expr, intervals

prove = intervals.prover({'x': (0.0, 4.0), 'y': (-1.0, 1.0)}, None, {'f': expr.read('x + 1')})
print(prove(expr.read('f * 2')), prove(expr.read('x / y if y > 0 else 0')))
try:
    prove(expr.read('x / y'))
except ValueError as error:
    print(error)
```

```
(2.0, 10.0) (0.0, inf)
Cannot prove nonzero denominator in 'x / y'; declare bounds or guard the branch
```

### The zero faces

A stock is on its zero face while it is at zero and stays there. An expression is constant on such
faces when it reads the stocks only in comparisons with zero. On the face, each such comparison has
one value.

`constant_on_faces(node, static_names, zero_stocks, aliases, parameters, registry)` gives the stocks
of `zero_stocks` that the node compares with zero. It gives None when the node reads anything else
that moves. That is a stock outside such a comparison, the time, or a name that is not fixed. The
proof of a condition on stocks reads it ([engine.md](engine.md#triggers)).

This consumer has no table. It knows a reference, a constant and a comparison, and it reads the parts
of each other node. So an operation needs no handler here.

### The entries of `napkin/expressions.py`

A structure holds each expression as its node, and its plain data writes the text of the node
(`Structure.plain`). The entries of `napkin/expressions.py` take an expression as its node, or as a
number or a yes/no. A number is the constant that it is. A text is a `TypeError`: a caller that has a
text, such as a test, a tool or plain data, reads it first with `expr.read`.

| Entry | What it does |
| --- | --- |
| `evaluate(source, environment, units)` | The value of an expression. Each failure is an `ExpressionError` that names the expression. |
| `compile_program(assignments, outputs, …)` | A program (`evaluation.program`). |
| `names_in(source)` | The names that an expression reads. A number reads none. |
| `compile_expression(source, symbol_units, registry, expected)` | The check of the size (`expr.limited`) and of the units. It gives an `Expression` that holds the node, with its `unit` and its `dependencies`. |
| `domain_prover(ranges, units, aliases)` | The function of `intervals.prover`, which takes a node. `aliases` gives the node of the formula of each name, or its number. |
| `validate_domains(source, ranges, units, aliases)` | The interval of one expression (`domain_prover`). |
| `stock_face_dependencies(source, …)` | The proof on the zero faces (`faces.constant_on_faces`). |

Other readers read the form of a node by its kind, with no table. They are the checks and the proofs
of `model/analysis/`, the classifier of a segment (`engine/continuous/kernels.py`) and the switching
surfaces (`engine/continuous/integrate.py`).

## The lowering

`model/lower/` makes the flat structures from the resolved model. It has three modules.
`expressions.py` gives each expression the names and the form of the structure. `builder.py` writes
the parts. `starts.py` finds the parts that a set of start-state options leaves out.

### The typing

`Typing(analysis, ctx, reads, path).visit(node)` reads a resolved expression and gives a typed node
with the names of the structure. `analysis` is the builder, which says what each name is. `ctx` is
the entity whose expression it is. `reads` collects the names of other entities that the expression
reads: they become the links of the entity. `path` is the place for an error.

| What the typing reads | What it gives |
| --- | --- |
| A value of an entity (`Ref`) | A reference to its name in the structure, such as `clinic.waiting`. Copy k of a set is `set_k`. |
| The `copy` of a copy | Its number. |
| A bool input or a bool state | The engine keeps it as the number 0 or 1. As a condition it reads `x == 1`, and `not x` reads `x == 0`. `1 if x else 0` is the name itself. |
| A test of a named input: `plan is "fast"` | A test of the code of the value. When `fast` is the second value of the input `desk.plan`, the test reads `desk.plan == 1`. A value that the input does not have is an error. |
| A test of a named state with a text | The same test. The typing checks that the text is a value of the state. |
| A bool formula: `let busy: bool = …` | Its expression, in the place of the name. A formula that reads itself is an error. |
| An output | A reference, in the expression of an output only: an output never feeds back into the model. |
| `since(e)`, `count(e)`, `elapsed(s)` | A call on the event, or on the named state, by its name in the structure: `since(clinic.close)`. |
| `sum`, `count`, `any`, `all`, `min` or `max` of a list | The members, one by one (`Typing.reduction`, `Typing.call`). |
| `delayed(x, D)`, or a distribution | A name of the event that reads it (`Typing.fired`). Outside an event it is an error. |
| Any other call | A call with typed arguments, for a function of `FUNCTIONS`. Any other name is the error `unknown function`. |
| A `Problem` | An `AnalysisError` with its message. |

`desugared(node, path)` then gives the form that the engine evaluates: `count`, `since` and `elapsed`
become reads of names that the structure keeps. A name that holds `__` is a name of the structure
itself. So `desugared` refuses such a name in an expression, unless it is the name of a value that
an event reads.

`Builder.flat(source, path, unit)` does the last step for each expression of a part. It calls
`desugared` and gives the node that the structure holds (`flat_node`). With a `unit`, a bare number
becomes a quantity of that unit (`typed`). A node that is deeper than the limit of depth is refused
here, at the place of its part ([The limits of size](#the-limits-of-size)): the builder makes such
a node from a list of many members.

### The forms that are no operation of the engine

Each form of the language that is no operation of the engine has one function in
`model/lower/expressions.py`. The table is the one at the top of that module.

| The file writes | The function | What the structure holds |
| --- | --- | --- |
| `count(e)` | `count_form` | A read of `e__count`. |
| `since(e) OP x` | `since_form` | `e__count > 0 and t - e__time OP x` |
| `elapsed(s)` | `elapsed_form` | `t - s__entered` |
| `sum`, `count`, `any`, `all`, `min`, `max` of a list | `Typing.reduction`, `Typing.call` | The members, one by one. |
| `delayed(x, D)` in an event | `Firing.delayed` | A name of the event, with `x` and `D` among its `extras`. |
| A distribution in an event | `Firing.draw` | A name of the event, with the family and its arguments among its `extras`. |
| A bare number in a typed field | `typed` | A quantity of the field's unit. |

- **The clocks.** `since()` is one side of one comparison. The resolver writes `since(s)` of a named
  state `s` as `elapsed(s)`, so its form has no test of a count.
- **The lists.** In a flat structure, a `sum` is a chain of `add`, from the left, in the order of the
  members. A `count` adds `1 if m else 0` for each member. `any` is an `or` and `all` an `and`. `min`
  and `max` are one call, with each member as an argument. With no members, a sum and a count are 0,
  `any` is False and `all` is True. The model of the representatives of `model/hybrid.py` writes a
  `sum`, an `any` and an `all` as one node each, `sum(a, b, c)`, whatever the number of the members:
  the value is the value of the chain, bit for bit.
- **The values that an event reads.** The names are `<rule>__delayed<k>` and `<rule>__draw<k>`. `k`
  counts the values of the event in the order in which the event writes them. The `stage` of a value
  is `trigger` for the delay of the event, else `fire`.

A model with three copies of a ward (`wards: Ward * 3`) shows the lists and the values of an event.
In its template, `held` is a number `var` and `full` a bool `var`:

| The file writes | The structure holds |
| --- | --- |
| `sum(wards.held)` | `wards_1.held + wards_2.held + wards_3.held` |
| `count(wards.full) >= 2` | `(1 if wards_1.full == 1 else 0) + (1 if wards_2.full == 1 else 0) + (1 if wards_3.full == 1 else 0) >= 2` |
| `max(wards.held, 0 people)` | `max(wards_1.held, wards_2.held, wards_3.held, q(0, 'people'))` |
| `reported = delayed(total, 2 h) * uniform(0.9, 1.1)` in the event `desk.tally` | `desk.tally__delayed0 * desk.tally__draw1` |

Other steps write some forms in another way before the typing reads them, or after it:

- The grammar writes `12 h` as `q(12, 'h')`, and `is` as `==` (`model/language/expressions.py`).
- The resolver writes the line `x += v` as the value `x + v` (`Resolver.line`).
- The builder writes the rate of a flow `at R while C` as `R if C else 0` (`Builder.flow_part`).
- A flow whose one pair fills a tally from outside the model is the rate of the tally
  (`Builder.rate_part`).

### The parts of a structure

`Builder.build` writes each section of a structure with one method:

| Method | What it writes |
| --- | --- |
| `parameter` | An input or a fixed value (`parameters`). |
| `entity_part` | An entity (`entities`), with its named states (`modes`) and its formulas (`computed`). It calls the next four methods. |
| `quantity_part` | A stock, a tally or a number state (`quantities`). |
| `status_part` | The status of an entity (`labels`). |
| `flow_part`, `rate_part` | A flow (`flows`), the group of the pairs of a flow (`coupling`), and the rate of a tally (`rates`). |
| `event_part` | An event as a rule (`rules`): its condition, its delay, its window and its rank. `branch_part` writes each outcome. `steps`, `assign` and `transfer` write the lines of an outcome. |
| `rationing_part` | The share of a stock (`allocation`). |
| `check_part` | The sum checks (`partitions`), and the other checks, which `derive` places. |
| `outcome_part`, `lag_part` | An output (`outcomes`) and its lag. |
| `time_part`, `initiation_part` | The time of the model, and the start. |

`Builder.derive` then makes the structure of one set of start-state options. It places each check in
`input_checks` or `state_checks`. `finish_events` writes the events with the rules that make them
happen (`events`), and `link_part` the links of each entity (`links`).

### The parts that a set of start-state options leaves out

A run takes some options that set start states. From those start values, some parts of the model can
never act. `model/lower/starts.py` finds them, and `Builder.derive` leaves them out.

- `Acting(s)` finds what the runs can reach from the start values, as a fixed point over the rules.
  It finds the values that each named state can take and the events that can happen. It also finds
  the rules that can fire and the outcomes that can happen. Each condition on a stock, a time or
  anything else counts as possible. So it misses nothing that can happen.
- `idle_parts(s, check_owner, checks, option_states)` gives the parts that cannot act, as
  `{section: {name: why}}`. `WHY` has the sentence of each reason.
- `remove(s, dead)` takes those parts out of the structure. It also takes out each line of an outcome
  that names a rule that is left out.
- `settled(source, starts, zeros)` gives an expression with the named states at their start values,
  and with the stocks that are left out at zero. `derive` uses it to place each check, and to write
  an output that reads such a stock.

The structure leaves out four kinds of part:

- a rule that cannot fire;
- a stock or a tally that starts at zero, when no part that acts changes it or reads it;
- a named state that no part that acts changes or reads;
- an entity none of whose parts can act, when no part that acts reads it.

Each part that stays keeps each part that it names, so each name of a structure resolves. The whole
structure (`builder.whole[starts]`) keeps every part, and the model checks it too.
[python-api.md](python-api.md#the-parts-that-cannot-act) gives the rules in full.

## The analysis

`model/analysis/` has one module for each time at which a fact becomes known.

| Module | When the fact is known | Entry | The facts |
| --- | --- | --- | --- |
| `structure.py` | For a structure, whatever the values of its inputs are. | `structure_facts(s, library, units)` | `computed_order`, `triggers` |
| `values.py` | For a resolved run: the typed parts of a structure with the values of its inputs (`structure.Resolved`). | `value_facts(rs, library)` | `bounds`, `proven_zero_stock_faces`, `proven_monotone_crossings`, `proven_cumulative_outcomes` |

### What is known for a structure

`structure_facts` gives the diagnostics of one structure and two facts:

- `computed_order`: the formulas, in an order in which each comes after the formulas that it reads. It
  is empty when the formulas form a circle, and the diagnostic has the code `cycle`.
- `triggers`: the classified trigger of each rule whose condition has a class. `classify` reads a
  `when` as an `and` of conditions. It gives the `gate`, the `kind`, and the `times` of a timer, the
  `var`, `op` and `value` of a crossing, or the `face` ([engine.md](engine.md#triggers)).

The checks read the unit of each expression at its place. They also read the bounds, the groups of
flows, the rules, the checks, the outputs and the records of the links. The module also answers
three questions for the other checks:

- `expanded`: the names that an expression reads through the formulas;
- `evolving_parts`: the quantities that move between moments;
- `discrete_names`: the names that change only at moments.

### What is known for a resolved run

`value_facts` gives the diagnostics of one resolved run and these facts:

- `bounds`: the number of each bound that the file writes as an expression, as
  `{quantity: {'min': number, 'max': number}}`;
- `proven_zero_stock_faces`: the stocks of each closed network in which a rule watches a stock reach
  zero;
- `proven_monotone_crossings`: the rules that watch a quantity that only rises or only falls;
- `proven_cumulative_outcomes`: the outputs that never fall. This fact is there when no check
  failed.

The checks go in this order:

1. the bounds, each as a number;
2. the timescales;
3. the start values, each within its bounds;
4. the delays of the lags;
5. the interval of each expression, with one prover for the run;
6. the class of each crossing;
7. the claims of the outputs and of the checks on the state.

`input_check_failures` gives the blocking checks of the inputs that fail.

A model resolves one structure with many sets of values: each run, each choice of options that no
run makes, each sample of a study. `value_facts(rs, library, proofs=...)` takes what the caller keeps
for the structure (`Proofs`): the prover of the last set of values. The checks take it over the
ranges of the new values (`prove.over`), so a formula that reads no value that changed is not proved
again. The diagnostics and the facts are those of checks that keep nothing. `Model.resolve_in` keeps
a `Proofs` for each of the last few structures that it resolved; it is empty in a copy of the model
that goes to another process. With the `Proofs` it keeps the typed parts of the structure, which
every check of a run reads and every resolved run shares. So a resolution copies no part
([From a structure to a resolved run](#4-from-a-structure-to-a-resolved-run)).

### What is known for every row of a table

The model of the representatives of the hybrid core has one instance for each class of the rows of a
table (`model/hybrid.py`), so `value_facts` proves it for one row of each class. `hybrid.compile`
makes the value checks once more for each declared run, on the structure in which each list is one
node, with `rows` (`hybrid.row_facts`, `value_facts(rs, library, rows)`). The typed parts of that
structure are made once (`Hybrid.typed`). The checks of a structure have not read it, so the
hybrid core gives each trigger its class with the classifier of those checks
(`hybrid.classified`): the proofs of a crossing and of a zero face read the class, and prove
nothing for a trigger that has none. `rows` has:

- `ranges`: for each input that a column gives, the least and the greatest of its values over the
  rows of its class;
- `starts`: the same for each start that a column gives;
- `weights`: the number of the rows of the class of each representative.

The pass first checks the value of each row against the range of its input, as the compiler checks
the value of each instance of a flat model.

An input whose values differ from row to row is taken out of the fixed values of the run. Each proof
then reads it as a range: the interval prover has the range, and a `sum` over a list counts a member
one time for each row. The checks of the start (the timescales, each start within its bounds, the
delays of a lag) are made with intervals. The claims of the outputs read such an input as a value
that does not move in a run. So a proof of this pass holds for every row, and its cost does not grow
with the rows. `Hybrid.facts` keeps the three proved lists of each declared run, and the engine reads
them in the place of those of the representatives (`Hybrid.proved`).

The pass is conservative in two ways that the flat compile of the same file is not. A failure names
the class and says that the proof is over the range of its rows:

- a proof that needs what two columns of one row have to do with each other fails. An example is
  `sqrt(high - low)` where `high` is above `low` in each row, and the range of `high` goes below the
  range of `low`;
- a bound of a quantity that reads a value of a column is refused (`bounds`): the rows of a class
  have one bound.

There is a third such case, before this pass. The model of the representatives is checked and proved
as every model is, with one row of each class, so a list over a table has one member for each class
there. A proof that holds only with every row of the list fails in that model. An example is
`sqrt(sum(Cell.k) - 2.5)` over three rows that each have `k = 1`: with one member, the argument is
below zero. That refusal has the code of the proof and does not name the class. The flat compile of
the same file holds such a model.

A run from the hybrid core that is given other values makes the checks for those values before it
starts ([engine.md](engine.md#tables-and-tiers)).

### The functions of facts write nothing

`structure_facts` and `value_facts` read their input and leave it as it is. `value_facts` reads the
typed parts of a run, which cannot change. The value checks need each bound as a number, so they
read a run whose quantities have the numbers: a copy of those parts only.

No function of facts writes into what it reads. `structure_facts` reads the typed parts of a
structure and gives its diagnostics and its facts: the order of the formulas, and the classified
trigger of each rule (a `Trigger`). `Structure.with_facts` gives a new structure with those facts;
`finish` keeps it as the structure of the model (`checked` of `analysis/structure.py` does the two
steps). No function writes a fact into a mapping. For a resolved run, `resolve_structure` gives
the numbers of the bounds and the three proved lists to the caller, which makes the run with them
(`Resolved.over`). So the typed records hold the facts: `Rule.trigger.kind`,
`Structure.computed_order` and `Resolved.proven_zero_stock_faces`.

## Three features from the file to the structure

This model has the three features: a condition with `since(e)`, a share with an order, and an event
with a window. This section follows each from the file to the structure, and then the three into
the engine. The model uses only the units of the prelude. Save it as `clinic/model.scn`.

```text
scenario "A clinic"
    summary "People wait at a clinic. Two wards admit them."
    horizon 48 h
    scope "The people who wait at one clinic."

clinic:
    "The clinic."
    var waiting: people = 60 people size 60 people  @counts
        "People who wait"
    var ward_a: people = 0 people size 60 people  @counts
        "People in ward A"
    output ward_a
    var ward_b: people = 0 people size 60 people  @counts
        "People in ward B"
    output ward_b
    var door: "open" | "closed" = "open"
        "Door"
    flow admit_a: waiting -> ward_a at 4 people/h  @counts
    flow admit_b: waiting -> ward_b at 2 people/h  @counts
    share waiting limit 5 people/h order admit_a, admit_b  @counts
    event close once when t >= 6 h:  @counts
        "The clinic closes its door."
        door = "closed"
    event report once when since(close) >= 12 h:  @counts
        "The clinic reports the day."
    event review each door when t >= 1 h:  @counts
        "The staff review the wards."

record counts: identity "The model counts each person once."
```

The examples of this section run in order, in one Python session, from the folder that holds
`clinic/`. The first example does each step of the chain by its own function:

```python
import napkin
from napkin.model.ir import thaw
from napkin.model.language import front
from napkin.model.language.resolve import resolve
from napkin.model.library import load_library

path = 'clinic/model.scn'
file, files = front.load(path)                                    # step 1
library = thaw(load_library(path, document=front.projection(file)))
scenario, resolver = resolve(file, library, files)                # step 2
model = napkin.load_scenario(path)                                # steps 1 to 4
(structure,) = model.structures.values()
print(list(model.structures), type(structure).__name__)

syntax = {member.name: member for member in file.things[0].members}
resolved = scenario.entities[0]
events = {event.name: event for event in resolved.events}
```

```
[()] Structure
```

### A condition with `since(e)`

The file writes `event report once when since(close) >= 12 h:`.

1. **The syntax node** is an `Event` of `model/language/nodes.py`. Its `when` is an `Expr`: the place
   of the condition and its tokens.
2. **The resolver** reads `close` as an event of the entity `clinic`. `Resolver.resolve_tree` puts an
   `EventRef` in the place of the name. The call keeps its name, `since`.
3. **The lowering** has two functions for it. `Typing.call` gives the event its name in the
   structure. `since_form` then gives the form that the engine evaluates.
4. **The structure** holds that form as the `when` of the rule `clinic.report`. The analysis
   classifies it as a timer: the count is the gate, and the time of the event is the anchor of the
   clock.

```python
from napkin.core import expr
from napkin.model.lower import Builder
from napkin.model.lower.expressions import Context, Reads, Typing, desugared
from napkin.model.runs import Runs

when = syntax['report'].when
print(when.place, [token.value for token in when.tokens])

when = events['report'].when
call = when.node.operands[0]
print(when.written, '|', call.function, type(call.args[0]).__name__, call.args[0].key)

builder = Builder(scenario, Runs.from_scenario(scenario, library).table, library)
typed = Typing(builder, Context('clinic'), Reads(builder, 'clinic'), when.where).visit(when.node)
print(expr.text(typed))
print(expr.text(desugared(typed, 'clinic/report/when:')))

trigger = structure.rules['clinic.report'].trigger
print(trigger.when)
print(trigger.kind, trigger.gate, trigger.times)
```

```
('clinic', 'report', 'when:') ['since', '(', 'close', ')', '>=', '12', 'h']
since(close) >= 12 h | since EventRef clinic.close
since(clinic.close) >= q(12, 'h')
clinic.close__count > 0 and t - clinic.close__time >= q(12, 'h')
clinic.close__count > 0 and t - clinic.close__time >= q(12, 'h')
timer (clinic.close__count > 0) ("clinic.close__time + (q(12, 'h'))",)
```

The structure keeps the event `clinic.close` in `events`, with the rule that makes it happen. The
engine keeps `clinic.close__count` and `clinic.close__time` in its store
([engine.md](engine.md#the-store-and-the-environment)). The door closes at 6 h, so the report fires at
18 h.

### A share with an order

The file writes `share waiting limit 5 people/h order admit_a, admit_b`.

1. **The syntax node** is an `Allocate`. It has the name `share_waiting`, the name of the stock, the
   limit as an `Expr`, and the flows of the order in `serve`. `serve` is None for a share with no
   order.
2. **The resolver** (`Resolver.allocation`) gives an `Allocation` of `model/semantic.py`. Its stock is
   a `Ref`, its limit an `Expression`, and each flow of the order has its entity.
3. **The lowering** (`Builder.rationing_part`) makes one group of every flow that takes from the
   stock. The group has the policy `priority` when the share has an order, else `proportional`. Each
   flow of the group gets the name of the group in its `allocation`.
4. **The structure** holds the group as an `Allocation` in the section `allocation`, under the name
   `clinic.share_waiting`. The limit of the file is its `capacity`.

```python
share = syntax['share_waiting']
limit = [token.value for token in share.limit.expr.tokens]
print(share.stock, limit, [name for name, place in share.serve])

share = resolved.allocations[0]
print(share.stock.entity, share.stock.member, [(owner, name) for _, owner, name, _ in share.serve])

group = structure.allocation['clinic.share_waiting']
print(group.policy, group.order, group.capacity)
print({name: flow.allocation for name, flow in structure.flows.items()})
print(structure.flows_from('clinic.waiting'))
```

```
waiting ['5', 'people/h'] ['admit_a', 'admit_b']
clinic waiting [('clinic', 'admit_a'), ('clinic', 'admit_b')]
priority ('clinic.admit_a', 'clinic.admit_b') q(5, 'people/h')
{'clinic.admit_a': 'clinic.share_waiting', 'clinic.admit_b': 'clinic.share_waiting'}
('clinic.admit_a', 'clinic.admit_b')
```

The lowering refuses two kinds of order, with the code `build`. One names a flow that does not take
from the stock. The other does not name each such flow one time. The analysis checks that the limit
has the unit of the stock for each hour. In a run, ward A asks for 4 people in an hour and gets them.
Ward B asks for 2 and gets the 1 that the limit leaves.

### An event with a window

The file writes `event review each door when t >= 1 h:`.

1. **The syntax node** is an `Event`. Its `each` is a list with one `Expr` for each value of the
   window, at the place `('clinic', 'review', 'each:')`.
2. **The resolver** (`Resolver.event`) reads each value as an expression of the entity. It refuses an
   event that has `each` and `once`, with the code `structure`.
3. **The lowering** (`Builder.event_part`) writes the window as a part of the rule: the texts of its
   values in `each`, and their place in `each_path`. An event with a window and no `when` gets the
   condition `True`.
4. **The structure** holds the rule `clinic.review` with `each`. The analysis checks that each value
   of the window changes only at moments.

```python
print([(item.place, [token.value for token in item.tokens]) for item in syntax['review'].each])
print([(item.written, item.node.entity, item.node.member) for item in events['review'].each])

rule = structure.rules['clinic.review']
print(rule.each, rule.each_path, rule.once, rule.named)
print([(role, source) for role, source in rule.sources()])

study = napkin.evaluate_study(model)
report = napkin.sample_result(study, reporting_times=[6])['runs']['base']
print([(entry['t'], entry['rule']) for entry in report['trace']])
print(report['reporting_points']['6.0']['values'])
```

```
[(('clinic', 'review', 'each:'), ['door'])]
[('door', 'clinic', 'door')]
('clinic.door',) clinic/review/each: False False
[('when', "t >= q(1, 'h')"), ('each', 'clinic.door')]
[(1.0, 'clinic.review'), (6.0, 'clinic.close'), (6.0, 'clinic.review'), (18.0, 'clinic.report')]
{'clinic.ward_a.output': 24.0, 'clinic.ward_b.output': 6.0}
```

The run keeps the values of the window when the rule triggers
(`engine/timeline/run.py`). The rule triggers at 1 h. It triggers again at 6 h, because the door then
has another value: that is a new window.

### The three features in the engine

The engine makes a plan of the resolved run and runs it
([engine.md](engine.md#tables-and-tiers)). The plan holds each expression as its node.

1. **The condition with `since(e)`** is a rule of the kind `timer`. Its gate is the count of the
   event `close`, and its one time is the time of that event and 12 h. The timeline reads a rule
   only when its answer can have changed ([engine.md](engine.md#one-moment)). So the run does not
   read this rule until the step of `close` writes its count and its time at 6 h. Then the rule is
   due at 18 h, and the run reads it there.
2. **The share with an order** is a group of the plan with the policy `priority`, its order and
   its limit. While the stock holds people, ward A gets 4 people in an hour and ward B the 1 that
   the limit leaves. The stock is empty at 12 h. From there it rests on its bound, and its flows
   deliver what comes in, which is nothing. At 48 h the wards hold 48 and 12 people.
3. **The event with a window** is a rule that holds the node of each value of its window (`each`).
   The run keeps the values of the window at each trigger, and it reads the rule again when a step
   writes one of them: the step of `close` at 6 h.

The things of a model with no table are one space of the plan. By default that space is in the
general tier, where the allocation in full gives the rates of the flows.

```python
from napkin.engine import timeline

plan = timeline.Plan.flat(model.resolve('base'), thaw(model.library))
rules = {rule.name: rule for rule in plan.rules}
report = rules['clinic.report']
print(report.kind, '|', report.gate, '|', [str(time) for time in report.times])
group = plan.groups['clinic.share_waiting']
print(group.policy, group.order, group.capacity)
print([str(node) for node in rules['clinic.review'].each])

result = timeline.run(plan)
print([(time, rule) for time, rule, _ in result.trace])
print(result.outputs)
```

```
timer | clinic.close__count > 0 | ["clinic.close__time + q(12, 'h')"]
priority ('clinic.admit_a', 'clinic.admit_b') q(5, 'people/h')
['clinic.door']
[(1.0, 'clinic.review'), (6.0, 'clinic.close'), (6.0, 'clinic.review'), (18.0, 'clinic.report')]
{'clinic.ward_a.output': 48.0, 'clinic.ward_b.output': 12.0}
```

## What is not here yet

This page describes the compiler after Stage A of the release work. The release ledger moved these
parts to later stages:

| Part | Its stage | What the code does today |
| --- | --- | --- |
| The family core. It has one family for each member of a template over each class of instances with one shape. It has the signature of an instance, a template that is lowered one time for each signature, and a checking mode. | Stage X and the thin slice of Stage B1 | The resolver writes out each instance, and each structure is flat. |
| Parts that hold typed expressions, each with its places. | Stage X and Stage B1, with the family core | A typed part holds the node of each expression (`structure.Source`): the node that the builder wrote into its mapping. The checks of a structure, of the values of a run and of its inputs, the plan of the engine, the reports, the key of the run store and the model's own readers (its inputs, the values of a run, its evidence index) read the typed parts. The hybrid core and the units that the identity reaches read them too: no reader outside the lowering reads that mapping. The places of an expression are not in a part. |
| A sum over a list as one node, and a limit of size that counts what the author wrote. | Stage X and Stage B1, with the family core | A sum is a chain, and the limit counts each member. |
| The choice of the parts for each set of start-state options as a product. | Stage X and Stage B1 | `Builder.derive` copies the shared structure for each set. |
| The facts of a segment, each kept by the values that it reads: a third module of `model/analysis/`. | Stage B | The engine computes them for each segment. |
| The products of a structure that the engine reads. They are the switching surfaces, the shapes of a repayment, the pattern of the Jacobian, and what each part reads and writes. | Stage B | The engine finds the first three from the expressions of a run. The queries of a `Structure` give what a rule reads and writes. |
| The two exercises of [extending.md](extending.md). | Stage X | |
| The reader of a distribution on the typed nodes of the resolver. | Stage X | `model/uncertain.py` reads the written text of a distribution with Python's parser, because a distribution of an edit document is a text, and because the units of the library say where a unit ends inside a word (`2 h/x`). It makes the typed node of each argument. It finds the unit and the value of an argument that reads no name from that node. It keeps an argument that reads other values as the author wrote it, with a space where a unit ends inside a word; the resolver reads that text once, as it reads an expression of the file. No node is written back to text. |

Instances from a table are here ([language.md](language.md), §2.3): the resolver writes each row out
as an instance, and `model/hybrid.py` gives the classes of the rows, the model of one representative
for each class and the family of each class, with a checking mode. The engine reads the flat
structure of a run, and it reads the families of the hybrid core
([engine.md](engine.md#tables-and-tiers)). `napkin run` gives it the hybrid core of a model with a
table, and `timeline.reports.study_of` does so for a caller in Python
([cli.md](cli.md#a-model-with-a-table)).

Each entry of the engine, the reports and the tools takes typed parts (`Structure`, `Resolved`): a
caller that has a mapping makes the parts of it first (`Structure.of`, `Resolved.of`). Some code
stays only until each reader inside them reads typed parts and typed nodes, with the family core.
That code is the builder's mappings, which the build reads into typed parts at once (`typed_of` of
`model/model.py`). The mappings hold nodes and numbers. The writer of the checking mode of the hybrid
core writes plain data, in which each expression is its text; it reads its structure into typed parts
before the helpers of the builder read it (`Structure.of`, and `Structure.plain` with nodes).
