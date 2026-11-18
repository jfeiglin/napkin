# Brief S0-F: the front end, first slice

Read `briefs/COMMON-B.md` first. State file: `scratch/rewrite/b1/s0-front/STATE.md`.

## Why

Stage S0 runs the first model from source to report with the new language. The old front end is
replaced in place. You write the new front end: it parses the whole notation of the spec, formats
it, and resolves, checks and lowers the subset of this slice to a program (`napkin/program/`).
Later slices extend the lowering. Another agent re-aims the engine at programs at the same time.

## You own

`napkin/model/language/` (rewrite in place), `napkin/model/semantic.py` (rewrite as the declared
model), a new `napkin/model/lowering.py`, `napkin/model/compile.py` (rewrite), `tests/language/`
(new), and `examples/piano_tuners/`. You may change `napkin/model/library.py`, `load.py` and
`evidence.py` if you need to, keeping `tests/test_locator.py` and `tests/test_strict_yaml.py`
green. Do not change `napkin/model/ir.py`, `structure.py`, `analysis/`, `uncertain.py`, `hybrid.py`,
`lower/`, `model.py`, `resolved.py` or `runs.py` (the engine still imports some of them; the main
session deletes them when the slice switches over), nor `napkin/program/`, `napkin/engine/` or
`napkin/core/`. If the contract in `napkin/program/` lacks something that you need, work around it
and list the change in your last message.

## Read

- `scratch/rewrite/g0-decisions.md`, and `scratch/rewrite/spec.md` in full (it is the notation).
- `scratch/rewrite/a1/FINDINGS.md`, `scratch/rewrite/a1/types.md` and `scratch/rewrite/a1/parser.py`:
  a prototype parser of the notation before G0. Its rules for units, for `in`, for `if` and for a
  missing bound were changed at G0: follow the spec.
- The module docstrings of `napkin/program/` and `napkin/program/build.py`, and
  `tests/program/examples.py`.
- What to reuse from the old front end: the lines, indentation and texts of `napkin/model/language/lex.py`,
  the parsing of records and notes in `parse.py`, and `modules.py`, `tables.py`, `library.py`.

## What to build

1. **Lexer and parser** for every construct of `spec.md`: one tree for one text, ambiguity refused.
   Units by D12: a compound unit with `*` and `/`, `48 h/2` and `48 h / 2` both 24 h, no `^`, no
   hyphen products. One-sided ranges (`in [0,]`). `if`/`else` in a stage. `switch` with guarded
   cases. `categorical(A: p, B: q)`, `.draw()`, `actor.choose(d)`. No `none`, no `output`, no
   `report:` block, `scale` for the old `size`. A diagnostic has a code and the place in the file.
2. **The formatter**: `format(parse(text))` gives a text that parses to the same tree and is stable
   when formatted again.
3. **The declared model** (`semantic.py`): the parsed model with names resolved and types and units
   checked, holding the texts, the records and the scenario line for the report and, later, draw.
   Each declared part has a stable path, which the program uses as its `origin`.
4. **Lowering** (`lowering.py`), through `napkin/program/build.py`, for the subset of this slice: the
   scenario line; entities declared once; inputs (with ranges, and a default that draws from a
   distribution), stored values, formulas, `readonly`; units of the library and of the model; ranges
   with either side open; stores; directed flows with `request` and `capacity`, each a value or a
   formula, between stores and to or from `SOURCE` and `SINK`; texts; `@record` and records;
   values at the top level. Any other construct parses and formats, and lowering refuses it with a
   diagnostic that names the construct and says that a later slice brings it.
5. **The entry point** in `compile.py`: a model file gives its declared model, its program and the
   configuration of its default run.
6. **The example**: `examples/piano_tuners/model.scn` in the new language. Start from
   `scratch/rewrite/a5/translated/examples/piano_tuners/model.scn` and apply G0 (`in [0,]`,
   `tuner * year`, no report block, no `none`).
7. **Tests** (`tests/language/`): lexing and parsing; refusals with their codes; the D12 cases (also a
   value whose name is a unit, which needs brackets); formatting round trips over a corpus of every
   code block of `spec.md`, copied into `tests/language/corpus/` (tests never read `scratch/`); and
   source to program: for each example of `tests/program/examples.py` that this slice can lower
   (`tank_delivery`, the unit examples, and others in the subset), a source text whose program has
   the same canonical bytes as the example's. Also the piano tuners file lowers and passes `finish()`.

## Exit

`tests/language` passes, `tests/program` and `tests/core` still pass, and `piano_tuners` lowers.
Your last message lists what lowers, what is refused for a later slice, and each change that you
need in `napkin/program/`.
