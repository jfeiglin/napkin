# Census of the present models (base commit)

23 `.scn` files under `examples/` and `scenarios/` of `/home/user/napkin-base`, read with the
present lexer and parser. `census_names.py` makes this file again.

## Declared names

| Kind | Distinct names |
| --- | ---: |
| changed member | 63 |
| event | 88 |
| field | 858 |
| flow | 124 |
| link | 10 |
| outcome | 6 |
| output | 107 |
| record | 507 |
| run | 36 |
| share | 30 |
| template | 15 |
| thing | 153 |

## Reserved words that a present model declares

None.

## Contextual words that a present model declares

These stay valid names: the next token decides (`status ok` against `status: ...`).

| Word | Declared as | Files |
| --- | --- | --- |
| `status` | field | scenarios/heat_wave_blackout/model.scn, scenarios/iv_fluid_shortage/model.scn, scenarios/water_controls_wipe/water.scn |

## Type words that a present model declares

A value can keep the name; a unit or a template cannot.

| Word | Declared as | Files |
| --- | --- | --- |
| `number` | field | scenarios/water_controls_wipe/water.scn |

## Function names that a present model declares

These stay valid names: a call has `(` after the name.

| Word | Declared as | Files |
| --- | --- | --- |
| `priority` | field | scenarios/cyber_learning_loop/model.scn |
| `proportional` | field | scenarios/cyber_learning_loop/model.scn |

## Built-in member names that a present model declares

A name is refused only on an owner whose type has the built-in member (R-A1-09).

| Word | Declared as | Files |
| --- | --- | --- |
| `active` | field | scenarios/cyber_learning_loop/model.scn |
| `capacity` | changed member, field | scenarios/cyber_learning_loop/model.scn, scenarios/water_controls_wipe/variants/jamestown/model.scn, scenarios/water_controls_wipe/variants/minot/model.scn and 2 more |
| `done` | field | examples/piano_tuners/model.scn |
| `draw` | flow | scenarios/water_controls_wipe/water.scn |
| `inflow` | field | examples/reservoir/model.scn |
| `request` | field | scenarios/water_controls_wipe/water.scn |
| `start` | event | scenarios/cyber_learning_loop/model.scn, scenarios/heat_wave_blackout/model.scn, scenarios/iv_fluid_shortage/model.scn and 1 more |

## Python keywords, not reserved by the proposal, that a present model declares

None.

## Units

- Reserved or type words that are declared units: none.
- Names of values that are also declared units: `accesses`, `customers`, `facilities`, `hours`, `parts`, `people`, `strikes`.
- Names with a capital first letter, by kind: none.
- Templates with a small first letter: none.

| Where | Distinct | Uses | With `/` | With `-` | With `^` | With `{name}` | Outside the proposed grammar |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| After a number | 69 | 1289 | 404 | 62 | 0 | 0 | 0 |
| In a type | 55 | 931 | 222 | 63 | 0 | 0 | 0 |
| Declared in a registry | 111 | | 56 | 19 | 0 | 0 | 0 |

Unit words outside the proposed grammar: none.

## Notation counts

| Form | Count |
| --- | ---: |
| ** (power of a value) | 32 |
| comment lines (a whole line) | 149 |
| comparisons with < > <= >= | 159 |
| is (equality) | 249 |
| logical lines that a bracket wraps | 307 |
| texts | 3289 |
| texts over several lines | 945 |
| texts with a brace | 26 |
| &#124; (named values) | 68 |

## Expressions

Each expression of a model, read with the present reader (`expressions.tree`).

| Form | Count |
| --- | ---: |
| a ** b | 32 |
| a if C else b | 99 |
| a text in an expression (a named value) | 417 |
| expressions | 2956 |
| chains of comparisons that point one way | 0 |
| chains of comparisons that point two ways, or hold == | 0 |

Calls by function: `q` 1289, `max` 110, `sum` 52, `exp` 46, `since` 31, `min` 30, `ln` 28, `clip` 27, `sqrt` 23, `erf` 14, `count` 9, `abs` 4, `elapsed` 4, `expm1` 3, `pert` 1, `normal` 1.

Functions that the present models call and the proposal does not have: none.

## Examples

- **: `scenarios/cyber_learning_loop/model.scn:658`; `scenarios/cyber_learning_loop/model.scn:735`; `scenarios/cyber_learning_loop/model.scn:738`; `scenarios/cyber_learning_loop/model.scn:738`; `scenarios/cyber_learning_loop/model.scn:742`; `scenarios/cyber_learning_loop/model.scn:742`
