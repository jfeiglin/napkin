"""The runs of a scenario: each run's input values and start states, under an edit document.

A run is a choice of profiles, which the code and the edit documents call options
(docs/language.md, §2.9). Its values are the values' defaults, then the values that each option of
the run gives, then the edits of an edit document (napkin/schema/edits.schema.json), whose inputs are named
`entity.value`. The narrower edit wins: an edit of one run, then of one option, then of every run.
Every edit wins over the value that an option gives, and that value wins over the default. Two edits
of one input at one level that meet in one run are an error, because neither is narrower.

An edit document is one transaction over the declared runs. `resolve` checks it in every run; if one
check fails, it resolves nothing. An edit of an option that no run names changes no run: it applies
in a combination of options that a caller asks for (`Model.combination`), which is checked when it
is asked for. The checks here are those of single inputs: names, references, bool values, units
and ranges, and the edits that meet. The checks that read several inputs, and the checks of the
structure that runs the values, belong to that structure.

The file writes each number with its unit (`72 h`, `3 days`); the table holds it as a number in the
unit of the input's type (`duration`: hours), a bool as True or False, and a named value as its
name. An input's value can also be a distribution, which the table holds as a record
(`model/uncertain.py`) with its numbers in the unit of the input. An edit gives a number in that
unit, True or False for a bool, a name, or a distribution written as in the file, with its units.
A start value is a named state, a number or an expression, as the file writes it.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from functools import cached_property

from .. import distributions
from ..expressions import ExpressionError, UnitSystem
from .ir import ModelError, close_names, diagnostic, freeze, thaw
from .library import prelude_units
from .load import schema_errors
from .semantic import path_text
from .types import BOOL, OWN_TEXT, STARTS, UnitProblem, family_of, number_in, written_unit
from .uncertain import DistributionProblem, is_distribution, read_distribution, reads

# Where a value comes from, broadest first: the default, the value that an option of the model sets
# (`option`), then the edits of every run (`set`), of one option (`options`, the edit document's
# level) and of one run. A later level wins.
LEVELS = ('default', 'option', 'set', 'options', 'runs')


@dataclass(frozen=True)
class Input:
    """An input or a fixed value of one entity, `entity.field`."""

    name: str
    doc: str | None
    fixed: bool
    is_bool: bool
    names: tuple | None  # the named values of an input that takes one of them
    unit: str | None  # the library unit of a number; None for a bool or a named value
    value: object  # the default: a number in `unit`, True or False, a name, or a distribution
    range: tuple | None  # (min, max) of an input of a number
    basis: object
    range_basis: object
    options: dict  # {option: {'value', 'basis', 'path'}}: the options that set it
    path: str  # where the file writes it


@dataclass(frozen=True)
class Resolved:
    """The values of one run (`run` None for a combination of options that no run names), by
    `entity.field`, with where each value comes from: `('default',)`, `('option', P)`, `('set',)`,
    `('options', P)` or `('runs', R)`."""

    run: str | None
    options: tuple
    values: dict  # every input and fixed value
    starts: dict  # the start value of every named state, stock, tally and number state
    texts: dict  # every cosmetic and fixed text
    origins: dict  # the level of each value in `values`


def library_units(library=None):
    """The units of a library, or of the prelude without one."""
    if isinstance(library, UnitSystem):
        return library
    return UnitSystem(prelude_units() if library is None else library['units'])


@dataclass(frozen=True)
class RunTable:
    """The immutable result of input/option analysis; no lowering or proofs are performed."""

    data: Mapping
    units: UnitSystem


class Runs:
    """The menu, the runs and the inputs of one scenario, and the values of its runs under an edit
    document: of a scenario's semantic model (`from_scenario`), or of the table that a model keeps
    (`from_table`)."""

    @classmethod
    def from_scenario(cls, scenario, library=None):
        """The runs of a scenario's semantic model, as a front end declares it: its profiles, its runs,
        and its entities with their values and the settings of their profiles. `library` is the
        scenario's library or its units; without one, the units of the shared vocabulary."""
        runs = cls.__new__(cls)
        runs._read(scenario, library_units(library))
        return runs

    def _read(self, scenario, units):
        self.units = units
        self.menu = {group.name: [p.name for p in group.profiles] for group in scenario.groups}
        self.group_of = {p: g for g, options in self.menu.items() for p in options}
        self.runs = {run.name: run.profiles for run in scenario.runs}
        self.problems = []  # the problems of the document's own values
        self.unread = set()  # the paths of the values that their unit cannot read, with a problem
        self.inputs, self.starts, self.texts = {}, {}, {}
        self.option_values, self.option_starts, self.option_texts = {}, {}, {}
        for entity in scenario.entities:
            self._entity(entity)
        for key, item in self.inputs.items():
            for option, setting in item.options.items():
                self.option_values.setdefault(option, {})[key] = setting['value']

    @cached_property
    def table(self):
        """Freeze the analyzed values once, without retaining or compiling the source document."""
        keys = (
            'menu',
            'group_of',
            'runs',
            'starts',
            'texts',
            'option_values',
            'option_starts',
            'option_texts',
            'problems',
        )
        data = {key: getattr(self, key) for key in keys}
        data['inputs'] = {name: asdict(item) for name, item in self.inputs.items()}
        return RunTable(freeze(data), self.units)

    @classmethod
    def from_table(cls, table):
        """Read an existing compiled table; do not re-read source, units or option definitions."""
        result = cls.__new__(cls)
        for key, value in table.data.items():
            setattr(result, key, value)
        result.inputs = {name: Input(**item) for name, item in table.data['inputs'].items()}
        result.problems = [thaw(item) for item in table.data['problems']]
        result.units = table.units
        result.__dict__['table'] = table
        return result

    # ---- the document --------------------------------------------------------------------------

    def _entity(self, entity):
        """The values of one entity (a copy is an entity of its own): its texts, inputs and start
        values, with the values that profiles give them."""
        for value in entity.values:
            key = f'{entity.name}.{value.name}'
            if value.kind == 'text':
                self.texts[key] = thaw(value.value)
                for setting in value.settings:
                    self.option_texts.setdefault(setting.profile, {})[key] = thaw(setting.written)
            elif value.kind in ('input', 'fixed'):
                self.inputs[key] = item = self._input(key, value, entity)
                self._check_document(item, path_text(value.range_where))
            elif value.kind in STARTS:
                self.starts[key] = thaw(value.value)
                for setting in value.settings:
                    written = thaw(setting.written)
                    start = written.get('value') if isinstance(written, dict) else written
                    self.option_starts.setdefault(setting.profile, {})[key] = start

    def _input(self, key, value, entity):
        written_type = thaw(value.type)
        is_flag = written_type == BOOL
        names = tuple(written_type) if isinstance(written_type, list) else None
        unit = None if is_flag or names else self._unit(written_type, entity, path_text(value.type_where))
        kind = 'bool' if is_flag else 'names' if names else 'unit'
        bounds, range_basis = None, None
        if value.range is not None:
            range_basis = thaw(value.range.basis)
            if value.range.edges:
                bounds = tuple(
                    None if edge is None else self._number(thaw(edge[0]), unit, entity, path_text(edge[1]))
                    for edge in value.range.edges
                )
        options = {}
        for setting in value.settings:
            written = thaw(setting.written)
            item = written if isinstance(written, dict) else {'value': written}
            where = path_text(setting.where)
            options[setting.profile] = {
                'value': self._value(item.get('value'), kind, unit, names, entity, f'{where}/value'),
                'basis': copy.deepcopy(item.get('basis')),
                'path': where,
            }
        return Input(
            name=key,
            doc=thaw(value.text),
            fixed=value.kind == 'fixed',
            is_bool=is_flag,
            names=names,
            unit=unit,
            value=self._value(thaw(value.value), kind, unit, names, entity, path_text(value.value_where)),
            range=bounds if value.kind == 'input' and kind == 'unit' else None,
            basis=thaw(value.records),
            range_basis=range_basis,
            options=options,
            path=path_text(value.value_where),
        )

    def _value(self, written, kind, unit, names, entity, path):
        """A written value of an input: a number in the input's unit, a bool or a name as written, or
        the record of a distribution. A value that cannot be read stays as written, with a problem."""
        if family_of(written) is not None:
            return self._distribution(written, kind, unit, names, entity, path)
        if kind != 'unit':
            return written
        return self._number(written, unit, entity, path)

    def _distribution(self, written, kind, unit, names, entity, path):
        """The record of a written distribution, with its numbers in the unit of the input."""
        if kind == 'unit' and unit is None:
            return written  # the input's unit is unknown, which is its own problem
        filled = OWN_TEXT.sub(lambda m: entity.text_of(m.group(1)), written)
        try:
            return read_distribution(written, kind, unit, self.units, names, filled)
        except DistributionProblem as exc:
            self.problems.append(diagnostic('distribution', path, str(exc)))
            self.unread.add(path)
            return written

    def _number(self, written, unit, entity, path):
        """A written number of an input (`72 h`) as a number in the input's unit. A value that the unit
        cannot read stays as written, with a problem, so that its checks name it once."""
        if unit is None:
            return written

        def fill(text):
            return written_unit(text, entity.text_of)

        try:
            return number_in(written, unit, self.units, fill)
        except (UnitProblem, ValueError, ExpressionError) as exc:
            self.problems.append(diagnostic('unit', path, str(exc)))
            self.unread.add(path)
            return written

    def _unit(self, written, entity, path):
        """The library unit of a number (`types.written_unit`): its type, with the text field of its entity
        that braces name filled in. None, with a problem, when the library has no such unit."""

        try:
            if not isinstance(written, str):
                raise ValueError('no unit')
            unit = written_unit(written, entity.text_of)
            self.units.parse_unit(unit)
        except (ValueError, ExpressionError):
            self.problems.append(
                diagnostic('unit', path, f'The type {written!r} is not a unit of the library')
            )
            return None
        return unit

    def _check_document(self, item, range_path):
        """The default and the option values of one input: numbers in range, bool values, names,
        distributions, units. A value that its unit cannot read has its problem already, and an input
        of an unknown unit has the unit's problem."""
        if item.unit is None and not item.is_bool and item.names is None:
            return
        if any(path.startswith(f'{range_path}/') for path in self.unread):
            return
        if item.range is not None:
            low, high = item.range
            if not (_number(low) and _number(high)) or low > high:
                self.problems.append(
                    diagnostic('bounds', range_path, f'{item.name} needs a range [min, max] of numbers')
                )
                return
        elif not item.fixed and not item.is_bool and item.names is None:
            self.problems.append(
                diagnostic('bounds', range_path, f'{item.name} is an input: it needs a range')
            )
            return
        if item.path not in self.unread:
            self.problems += self.value_errors(item, item.value, item.path)
        for setting in item.options.values():
            if f'{setting["path"]}/value' not in self.unread:
                self.problems += self.value_errors(item, setting['value'], f'{setting["path"]}/value')

    # ---- values --------------------------------------------------------------------------------

    def value_errors(self, item, value, path):
        """The problems of one value of an input: its kind, its range and its unit, and for a
        distribution its arguments and its support."""
        if is_distribution(value):
            return self.distribution_errors(item, value, path)
        if item.names is not None:
            if isinstance(value, str) and value in item.names:
                return []
            return [diagnostic('value', path, f'{item.name} takes one of its values {list(item.names)}')]
        if item.is_bool:
            if isinstance(value, bool):
                return []
            return [diagnostic('bool', path, f'{item.name} is a bool: it takes true or false')]
        if not _number(value):
            return [diagnostic('value', path, f'{item.name} takes a finite number')]
        if item.range is not None and not item.range[0] <= value <= item.range[1]:
            low, high = item.range
            return [diagnostic('bounds', path, f'{item.name}: {value} is outside [{low}, {high}]')]
        if item.unit is None:
            return []  # the document's problem says that the unit is unknown
        try:
            self.units.normalize(value, item.unit)
        except ExpressionError as exc:
            return [diagnostic('unit', path, f'{item.name}: {exc}')]
        return []

    def distribution_errors(self, item, record, path):
        """The problems of a distribution whose arguments are numbers: their values, and a support
        inside the input's range. A distribution that reads other values is checked where they are
        known, in each run and each sample (`model.Model.point_values`)."""
        if reads(record):
            return []
        found = distributions.problems(record['family'], dict(record['args']))
        if found:
            return [diagnostic('distribution', path, f'{item.name}: {record["text"]}: {"; ".join(found)}')]
        if item.range is not None and distributions.FAMILIES[record['family']].kind == 'number':
            low, high = distributions.support(record['family'], record['args'])
            if low < item.range[0] or high > item.range[1]:
                return [
                    diagnostic(
                        'bounds',
                        path,
                        f'{item.name}: {record["text"]} takes values from {low} to {high}, outside its range '
                        f'[{item.range[0]}, {item.range[1]}]',
                    )
                ]
        return []

    def edit_value(self, item, value, path):
        """(value, problems) of one value of an edit: a written distribution becomes its record, and
        any other value is as the edit gives it."""
        if family_of(value) is None:
            return value, []
        kind = 'bool' if item.is_bool else 'names' if item.names else 'unit'
        try:
            record = read_distribution(value, kind, item.unit, self.units, item.names)
        except DistributionProblem as exc:
            return value, [diagnostic('distribution', path, f'{item.name}: {exc}')]
        if reads(record):
            message = f'{item.name}: a distribution in an edit has numbers only; one that reads other values belongs in the file'
            return value, [diagnostic('distribution', path, message)]
        return record, []

    def edit_errors(self, key, value, path):
        """The problems of one edit: the input that it names and the value that it gives."""
        item = self.inputs.get(key)
        if item is None:
            if key in self.starts:
                message = f'{key} is a state: profiles set its start value, edits do not'
            elif key in self.texts:
                message = f'{key} is a text, which edits do not change'
            else:
                message = f'{key} is not an input' + close_names(key, self.inputs)
            return [diagnostic('input', path, message)]
        if item.fixed:
            return [diagnostic('locked', path, f'{key} is a fixed value: it is locked')]
        value, problems = self.edit_value(item, value, path)
        return problems or self.value_errors(item, value, path)

    # ---- runs and choices of options ------------------------------------------------------------

    def unnamed(self):
        """The options of the menu that no run names."""
        named = {p for options in self.runs.values() for p in options}
        return [p for options in self.menu.values() for p in options if p not in named]

    def unnamed_choices(self):
        """Each option that no run names with the other options of each run (the run's option of its
        group replaced): the choices that the model checks when it is built, so that an option that no
        run takes is still valid. A choice that a run or an earlier item makes is not repeated."""
        seen = {frozenset(options) for options in self.runs.values()}
        out = []
        for option in self.unnamed():
            group = self.group_of[option]
            for options in self.runs.values():
                choice = (option, *(p for p in options if self.group_of.get(p) != group))
                if frozenset(choice) not in seen:
                    seen.add(frozenset(choice))
                    out.append(choice)
        return out

    def combination(self, run, options):
        """(options, problems) of one combination that a caller asks for: the options of `run`, in its
        order, with each of `options` in place of the run's option of the same group, then each option
        of a group that the run does not name. An option is one of the menu, and a combination takes
        one option of each group; else the options are None and the problems say why."""
        if run not in self.runs:
            return None, [
                diagnostic('run', f'runs/{run}', f'{run} is not a run' + close_names(run, self.runs))
            ]
        chosen, problems = {}, []
        for option in options:
            group = self.group_of.get(option)
            if group is None:
                message = f'{option} is not an option' + close_names(option, self.group_of)
                problems.append(diagnostic('reference', f'options/{option}', message))
            elif chosen.get(group, option) != option:
                message = f'{chosen[group]} and {option} are two options of the group {group}'
                problems.append(diagnostic('combination', f'options/{option}', message))
            else:
                chosen[group] = option
        if problems:
            return None, problems
        combined = [chosen.pop(self.group_of[p], p) for p in self.runs[run]]
        return (*combined, *chosen.values()), []

    def errors(self, edits=None, model_hash=None):
        """Every problem of the document's values and of one edit document, in every run: the names
        that the document gives are declared ones, each value fits its input, and no two edits of one
        level meet in a run. An edit of an option that no run names changes no run, and it is
        accepted: it applies in a combination that names the option (`Model.combination`)."""
        errors = list(self.problems)
        if not edits:
            return errors
        edits = thaw(edits)
        shape = schema_errors(edits, 'edits')
        if shape:
            return errors + [{**item, 'path': f'edits/{item["path"]}'.rstrip('/')} for item in shape]
        if model_hash is not None and edits['model_hash'] != model_hash:
            errors.append(diagnostic('model_hash', 'edits', 'The edits are for a different model revision'))
        for key, value in (edits.get('set') or {}).items():
            errors += self.edit_errors(key, value, f'edits/set/{key}')
        for option, values in (edits.get('options') or {}).items():
            if option not in self.group_of:
                message = f'{option} is not an option' + close_names(option, self.group_of)
                errors.append(diagnostic('reference', f'edits/options/{option}', message))
                continue
            for key, value in values.items():
                errors += self.edit_errors(key, value, f'edits/options/{option}/{key}')
        for run, values in (edits.get('runs') or {}).items():
            if run not in self.runs:
                message = f'{run} is not a run' + close_names(run, self.runs)
                errors.append(diagnostic('reference', f'edits/runs/{run}', message))
                continue
            for key, value in values.items():
                errors += self.edit_errors(key, value, f'edits/runs/{run}/{key}')
        return errors + self._meetings(edits)

    def _meetings(self, edits):
        """Two edits of one input by two options that meet in one run: neither is narrower."""
        errors, seen = [], set()
        by_option = edits.get('options') or {}
        for run, options in self.runs.items():
            where = f'run {run}'
            editors = {}
            for option in options:
                for key in by_option.get(option) or {}:
                    editors.setdefault(key, []).append(option)
            for name, owners in editors.items():
                if len(owners) < 2 or (name, frozenset(owners)) in seen:
                    continue
                seen.add((name, frozenset(owners)))
                errors.append(
                    diagnostic(
                        'meeting',
                        f'edits/options/{owners[1]}/{name}',
                        f'{name} has two edits of one level, options {owners[0]} and {owners[1]}, that meet in {where}',
                    )
                )
        return errors

    def values_of(self, options, edits=None, run=None):
        """The values of one choice of options: the defaults, then each option's values, then the edits
        from the broadest level to the narrowest. A choice that is no run (`run` None) takes only the
        edits of every run and of its options. The edits must have no problems (`errors`)."""
        edits = thaw(edits or {})
        values = {key: item.value for key, item in self.inputs.items()}
        origins = dict.fromkeys(values, ('default',))
        starts = thaw(self.starts)
        texts = dict(self.texts)

        def put(changes, origin):
            changes = {key: self.edit_value(self.inputs[key], value, '')[0] for key, value in changes.items()}
            values.update(changes)
            origins.update(dict.fromkeys(changes, origin))

        for option in options:
            put(self.option_values.get(option, {}), ('option', option))
            starts.update(thaw(self.option_starts.get(option, {})))
            texts.update(self.option_texts.get(option, {}))
        put(edits.get('set') or {}, ('set',))
        for option in options:
            put((edits.get('options') or {}).get(option) or {}, ('options', option))
        if run is not None:
            put((edits.get('runs') or {}).get(run) or {}, ('runs', run))
        return Resolved(run, tuple(options), values, starts, texts, origins)

    def resolve(self, edits=None, runs=None, model_hash=None):
        """{run: Resolved} of every run (or of `runs`), after checking the edits as one transaction.
        Raises ModelError with every problem, and resolves nothing, if one check fails."""
        errors = self.errors(edits, model_hash)
        errors += [
            diagnostic('reference', f'runs/{r}', f'{r} is not a run' + close_names(r, self.runs))
            for r in runs or ()
            if r not in self.runs
        ]
        if errors:
            raise ModelError(errors)
        return {
            run: self.values_of(options, edits, run)
            for run, options in self.runs.items()
            if runs is None or run in runs
        }


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
