"""A scenario built for the engine (docs/python-api.md).

`build_model(path)` reads a model file (`model.scn`, `language/front.py`), builds one flat structure for
each set of profiles that set start states (`lower/`), checks and proves each one with the
compiler's functions (`model/analysis/`, `model/compile.py`), and validates the authored resolution
of every run. The front end reads the file into its semantic model (`model/semantic.py`), and the
rest of the build (`finish`) reads only that model and what the front end gives it (`Source`). The
model shows its profile menu, its runs and its inputs; `resolve(run, values)` gives the engine what
it runs for one run and a dict of input values.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType

from ..expressions import ExpressionError, UnitSystem, compile_expression
from .analysis import structure as structure_analysis
from .analysis import values as value_analysis
from .compile import check_parameters, implementation_hash, resolve_structure
from .evidence import (
    basis_content,
    basis_digest,
    basis_errors,
    datum_errors,
    dependencies_of,
    digest,
    library_checks,
)
from .identity import library_content, model_identity, reached
from .ir import LANGUAGE_VERSION, ModelError, diagnostic, freeze, thaw
from .lower import Builder, RewriteError
from .runs import Runs, RunTable
from .semantic import (
    MAIN,
    AnalysisError,
    Scenario,
    flat_entity,
    flat_key,
    path_text,
    split_key,
)
from .structure import Resolved, Structure, node
from .uncertain import DistributionProblem, is_distribution, point_values

TIME_UNIT = structure_analysis.TIME_UNIT
# How many structures a model keeps the proofs of, from one set of values to the next (`resolve_in`).
KEPT_PROOFS = 8


@dataclass(frozen=True)
class Model:
    """A scenario, built for the engine.

    `structures` gives one structure for each set of start-state options, keyed by the sorted tuple
    of those options (`()` when a run has none), as typed parts (`structure.Structure`). `left_out`
    says, for each structure, the parts that cannot act in it and that the builder leaves out, with
    the reason. `whole` gives, for each structure, every part before the builder leaves any out: the
    engine never runs it, and the evidence trail reads it, so that the evidence of a part left out
    shows as possible but not used. Each structure has the facts that its checks found
    (`Structure.with_facts`), and each one of `structures` has the parts that it leaves out
    (`Structure.left`). The model keeps no mapping of the builder: the build reads each one into
    typed parts at once (`typed_of`).
    """

    origin: str
    lines: Mapping
    library: Mapping
    library_hash: str
    model_hash: str
    implementation_hash: str
    menu: Mapping
    runs: Mapping
    start_options: tuple
    inputs: Mapping
    entities: Mapping
    outputs: Mapping
    events: Mapping
    # {start-state options: the structure} of each set of start-state options that a run of the model
    # starts from (`structure.Structure`).
    structures: Mapping
    left_out: Mapping
    # {start-state options: the whole structure}: every part, also those that no run with those
    # options can make act.
    whole: Mapping
    time: Mapping
    initiation: Mapping | None
    index: Mapping
    run_table: RunTable
    evidence: Mapping
    # The semantic model of the scenario (`model/semantic.py`), which the pages and the reports read.
    scenario: Scenario
    # None means full admission; a tuple admits only these named runs numerically.
    # Structures, evidence and units remain checked across the authored model.
    admission_runs: tuple[str, ...] | None = None
    # The arguments of each distribution that read other values, compiled with the structure's names:
    # {input: {its text: {argument: expression}}} (`model/uncertain.py`).
    arguments: Mapping = field(default_factory=dict)
    # The file of each line that is not in `origin`, for a model of several files (`language/modules.py`):
    # {place: file}.
    files: Mapping = field(default_factory=dict)
    # The validated authored resolution of each run, filled when the model is built; callers get copies.
    defaults: dict = field(default_factory=dict, compare=False, repr=False)
    # What each run and each choice of options that the build checked resolves with (`choice_key`):
    # each held every check, so a study resolves none of them again (`engine.study.resolve_edits`).
    proven: set = field(default_factory=set, compare=False, repr=False)
    # One plain copy of the library, which the checks of every resolution read and never change.
    plain: dict = field(default_factory=dict, compare=False, repr=False)

    def structure_of(self, run):
        """The structure that a run uses: the one of its start-state options."""
        return self.structures[self.runs[run]['starts']]

    def run_values(self, run):
        """{input: value} of a run as its options write it: each input's own value, then the value of
        each of the run's options that sets it (options of two groups never set one input). A
        distribution takes its central value (`point_values`)."""
        return self.point_values(self.written_values(run))

    def written_values(self, run):
        """{input: value} of a run as `run_values`, with each distribution as its record."""
        if run not in self.runs:
            raise ModelError([diagnostic('run', 'runs', f'Unknown run {run!r}')])
        values = Runs.from_table(self.run_table).values_of(self.runs[run]['options']).values
        return {input_name(name): thaw(value) for name, value in values.items()}

    def point_values(self, values, pick=None):
        """{input: value} with each distribution replaced: by its central value, the median of a
        number and the most likely bool or named value, or by `pick(input, record, arguments)`. A
        distribution that reads other values reads theirs (`model/uncertain.py`). Raises ModelError
        for a distribution whose arguments or support are not valid with those values."""
        values = {input_name(name): value for name, value in values.items()}
        definitions = next(iter(self.structures.values())).parameters
        if 'units' not in self.plain:
            self.plain['units'] = UnitSystem(thaw(self.library['units']))
        try:
            return point_values(values, self.arguments, definitions, self.plain['units'], pick)
        except DistributionProblem as exc:
            where = f'values/{exc.name}' if exc.name else 'values'
            raise ModelError([diagnostic('distribution', where, str(exc))]) from None

    def resolve(self, run, values=None):
        """The resolved structure that the engine runs for one run.

        `values` maps inputs (`entity.field`; a copy's `set.k.field` or `set_k.field`) to values: a
        number in the input's unit, or True or False for a bool input. An input it does not name
        takes the run's value (`run_values`). The values are checked against the inputs' ranges, a
        fixed value cannot change, and the blocking checks of the inputs and the proofs of the run's
        structure must hold."""
        return self._resolved(run, values)

    def _resolved(self, run, values=None):
        """`resolve(run, values)`, with every check of it."""
        if self.admission_runs is not None and run not in self.admission_runs:
            raise ModelError(
                [
                    diagnostic(
                        'admission_scope',
                        f'runs/{run}',
                        f"Run {run!r} is outside this model's admission scope",
                    )
                ]
            )
        effective = self.written_values(run)
        for name, value in (values or {}).items():
            effective[input_name(name)] = value
        numbers, errors = self.numbers(self.point_values(effective))
        if errors:
            raise ModelError(errors)
        default = self.defaults.get(run)
        if default is not None and default.parameter_values == numbers:
            rs = default  # a resolved run cannot change: the run of the build is the answer
        else:
            rs = self._resolve(run, numbers, checked=True)
        # The distributions of the run, whose central values the run takes.
        uncertain = {name: value for name, value in effective.items() if is_distribution(value)}
        if uncertain:
            rs = rs.adding(distributions=uncertain)
        return rs

    def numbers(self, values):
        """The engine's numbers of a dict of input values, and the diagnostics of the values that are
        not allowed."""
        errors, numbers = [], {}
        for name, given in values.items():
            info = self.inputs.get(name)
            where = f'values/{name}'
            if info is None:
                errors.append(diagnostic('input', where, 'Unknown input'))
                continue
            number = given
            if is_distribution(given):
                errors.append(
                    diagnostic('distribution', where, 'Give a point value: the central value or a draw')
                )
                continue
            if info['type'] == 'bool':
                if given is True or given is False:
                    number = 1 if given else 0
                elif isinstance(given, bool) or given not in (0, 1):
                    errors.append(diagnostic('binary_control', where, 'A bool input is true or false'))
                    continue
            if info['type'] == 'names':
                if isinstance(given, str) and given in info['values']:
                    number = info['values'].index(given)
                else:
                    errors.append(
                        diagnostic('choice', where, f'A named input takes one of {list(info["values"])}')
                    )
                    continue
            # A fixed value is its own value; one whose own value is a distribution takes its draws.
            if info['fixed'] and info['distribution'] is None and number != numbers_of(info)['value']:
                errors.append(diagnostic('locked', where, 'A fixed value cannot change'))
            numbers[name] = number
        definitions = next(iter(self.structures.values())).parameters
        check_parameters(definitions, numbers, 'values', errors)
        missing = sorted(definitions.keys() - values.keys())
        errors += [
            diagnostic('input', f'values/{name}', 'The run has no value for this input') for name in missing
        ]
        return numbers, errors

    def resolve_in(self, structure, numbers, context, checked=True):
        """One structure resolved with the engine's numbers of every input (`numbers`), as a
        `Resolved`: the blocking checks of the inputs first when `checked`, then the bounds, domains
        and proofs. `structure` is a `Structure`. The resolved run shares the parts of the structure
        (`Resolved.over`): a resolution copies no part."""
        source = {'time': thaw(self.time), 'initiation': thaw(self.initiation)}
        if 'library' not in self.plain:
            self.plain['library'] = thaw(self.library)
        # What the checks of this structure keep from one set of values to the next: the prover and
        # the typed parts, which every check reads and every resolved run shares. Neither changes.
        # The structure is held with them, so that no other object can have its place in the
        # memory. The memory holds the last few structures that the model resolved.
        kept = self.plain.setdefault('proofs', {})
        entry = kept.pop(id(structure), None)
        if entry is None or entry[0] is not structure:
            entry = (structure, value_analysis.Proofs())
        kept[id(structure)] = entry
        while len(kept) > KEPT_PROOFS:
            del kept[next(iter(kept))]
        proofs = entry[1]
        if proofs.typed is None:
            proofs.typed = structure
        own, bounds = resolve_structure(
            proofs.typed,
            source,
            self.plain['library'],
            numbers,
            context,
            checked=checked,
            proofs=proofs,
        )
        return Resolved.over(proofs.typed, own, bounds)

    def _resolve(self, run, numbers, checked):
        info = self.runs[run]
        rs = self.resolve_in(self.structures[info['starts']], numbers, f'runs/{run}', checked)
        return rs.adding(
            run=run,
            options=info['options'],
            starts=info['starts'],
            model_hash=self.model_hash,
        )

    def combination(self, run, options):
        """The model whose one run is `run` with `options` in place of its options of their groups
        (`Runs.combination`), checked when it is asked for as a run of a model is checked when the
        model is built: its values, the blocking checks of its inputs and the proofs of its structure.

        The derived model keeps this model's identity, structures and evidence, and its run keeps its
        name: an edit document of this model applies to it as to a run, with the edits of every run,
        of each option of the combination and of the run. The combination runs in the structure of its
        start-state options, which a run of this model must start from: else it is a diagnostic. A
        diagnostic of the combination gives its options (`options`, and `context`). Raises ModelError
        with every problem."""
        if isinstance(options, str) or not all(isinstance(option, str) for option in options):
            raise ModelError([diagnostic('combination', 'options', 'Give a collection of option names')])
        table = Runs.from_table(self.run_table)
        combined, problems = table.combination(run, tuple(options))
        if problems:
            raise ModelError(problems)
        states = set(self.start_options)
        starts = tuple(sorted(p for p in combined if p in states))
        where = {'options': list(combined), 'context': 'options ' + ' · '.join(combined)}
        if starts not in self.structures:
            message = f'No run of the model starts from the start states of these options: {list(starts)}'
            raise ModelError([{**diagnostic('combination', f'runs/{run}', message), **where}])
        info = self.runs[run]
        derived = replace(
            self,
            runs=freeze(
                {
                    run: {
                        'options': combined,
                        'name': info['name'] if combined == tuple(info['options']) else ' · '.join(combined),
                        'comparison_of': None,
                        'starts': starts,
                    }
                }
            ),
            run_table=RunTable(freeze({**thaw(self.run_table.data), 'runs': {run: combined}}), table.units),
            admission_runs=None,
            defaults={},
            proven=set(self.proven),
            plain=dict(self.plain),
        )
        numbers, problems = derived.numbers(derived.run_values(run))
        try:
            if problems:
                raise ModelError(problems)
            derived.defaults[run] = derived._resolve(run, numbers, checked=True)
        except ModelError as exc:
            raise ModelError([{**item, **where} for item in exc.diagnostics]) from None
        derived.proven.add(choice_key(starts, derived.run_values(run)))
        return derived


def input_name(name):
    """An input's name in the structure: `entity.field`, with a copy `set.k` written `set_k`."""
    return flat_key(name)


def numbers_of(info):
    value = info['value']
    if info['type'] == 'names':
        return {'value': list(info['values']).index(value)}
    return {'value': (1 if value else 0) if info['type'] == 'bool' else value}


def build_model(path, library=None, *, admission_runs=None):
    """Read, build, check and prove one model file (`model.scn`, `language/front.py`). Without `library`,
    the model reads the library of its scenario folder."""
    from .language import front

    return front.build(Path(path), library, admission_runs=admission_runs)


def located(errors, lines, origin, files=None, columns=None):
    """Diagnostics with the line and the column of the part each one is about: the line of its place,
    or of the nearest place that holds it, in the line map of the file, the column where that line
    starts (`columns`, {place: column}), and the file of that line (`files`, {place: file}, for a
    model of several files; else `origin`). A diagnostic that names its line keeps it and its own
    column; one that names its file keeps it."""
    out = []
    for item in errors:
        key = tuple(int(p) if p.isdigit() else p for p in str(item.get('path', '')).split('/') if p)
        while key and key not in lines:
            key = key[:-1]
        if item.get('line'):
            line, column = item['line'], item.get('column')
        else:
            line = lines.get(key) if key else None
            column = (columns or {}).get(key) if line else None
        file = item.get('file') or ((files or {}).get(key) if key else None) or origin
        out.append(
            {
                **item,
                **({'line': line} if line else {}),
                **({'column': column} if column else {}),
                'file': file,
            }
        )
    return out


@dataclass(frozen=True)
class Source:
    """What a front end gives the shared build of a model (`finish`): its line map, {place: line},
    and its name; what the evidence walkers read (`evidence.basis_errors`,
    `identity.reached`), every record and citation of the file with its place; and what the model hash
    covers."""

    lines: Mapping
    origin: str
    evidence: object
    identity: object
    files: Mapping | None = None  # {place: file} of the lines of the other files of the model
    columns: Mapping | None = None  # {place: the column where its line starts}


def typed_of(mapping, starts, left_out=None):
    """The typed parts (`structure.Structure`) of a structure that the builder derives for the
    start-state options `starts`, with the parts that it leaves out (`left_out`), when it leaves any
    out. It is the one place that reads a mapping of the builder: each step after it reads the typed
    parts."""
    return Structure.of(mapping, f'structure {list(starts)}: ', left_out)


def built(declare, lines, origin, library, files=None, *, admission_runs=None, columns=None, listed=False):
    """(builder, {start-state options: structure}) of the scenario whose semantic model and run table
    `declare()` gives. Each structure is its typed parts (`typed_of`), with the parts that it leaves
    out, and is not yet checked. A problem that the analysis finds is a diagnostic at its line."""
    try:
        scenario, run_table = declare()
        if admission_runs is not None:
            unknown = set(admission_runs) - {run.name for run in scenario.runs}
            if unknown:
                raise ModelError(
                    located(
                        [diagnostic('run', 'runs', f'Unknown admission runs {sorted(unknown)}')],
                        lines,
                        origin,
                        files,
                        columns,
                    )
                )
        builder = Builder(scenario, run_table, library, listed)
        # A distribution that its input cannot take is the run table's problem, with its own code: the
        # build reads no such value.
        written = builder.distribution_problems()
        if written:
            raise ModelError(located(written, lines, origin, files, columns))
        base = builder.base = builder.build()
        structures = {}
        for starts in builder.start_sets():
            mapping = builder.derive(base, starts)
            structures[starts] = typed_of(mapping, starts, builder.left_out[starts])
    except AnalysisError as exc:
        raise ModelError(
            located([diagnostic('build', path_text(exc.path), str(exc))], lines, origin, files, columns)
        ) from None
    except RewriteError as exc:
        raise ModelError(located([exc.diagnostic], lines, origin, files, columns)) from None
    except ExpressionError as exc:
        # An expression of a flat structure that is over the limit of size: a list of many members,
        # which a flat structure writes member by member.
        message = (
            f'{exc}: a flat structure writes a list member by member, so a sum over hundreds of '
            'instances is too long for it. The hybrid core takes such a list as one node when a '
            'table makes the instances (napkin.model.hybrid.compile)'
        )
        raise ModelError(
            located([diagnostic('expression', '', message)], lines, origin, files, columns)
        ) from None
    return builder, structures


def finish(source, declare, library, *, errors=(), admission_runs=None):
    """The model of a scenario that a front end reads: `source` (`Source`), and `declare()`, which
    gives its semantic model and its run table. `errors` are the front end's diagnostics of the file
    that come with those of the library. Every check of a model is here, so a model that is built is
    valid: its library and bases, the structure of each set of start states and every part of it, the
    first move, every run, and every option that no run names with the other options of each run. Each
    run and each choice resolves with the blocking checks of its inputs, so the default study of a
    fully admitted model is admissible. Any other combination of options is checked when a caller asks
    for it (`Model.combination`).
    An explicit ``admission_runs`` retains global structure/evidence/unit checks but
    limits numerical resolutions and whole-part proofs to those named runs."""
    lines, origin, files, columns = source.lines, source.origin, source.files, source.columns
    errors = [*library_checks(library)[0], *errors]
    if errors:
        raise ModelError(located(errors, lines, origin, files, columns))
    if admission_runs is not None:
        if isinstance(admission_runs, str):
            raise ModelError(
                [diagnostic('admission_scope', 'runs', 'Give a nonempty collection of run names')]
            )
        admission_runs = tuple(admission_runs)
        if not admission_runs or any(not isinstance(run, str) for run in admission_runs):
            raise ModelError(
                [diagnostic('admission_scope', 'runs', 'Give a nonempty collection of run names')]
            )
        admission_runs = tuple(dict.fromkeys(admission_runs))
    builder, structures = built(
        declare,
        lines,
        origin,
        library,
        files,
        admission_runs=admission_runs,
        columns=columns,
    )
    scenario = builder.scenario
    # The whole structure of each set of start-state options, as typed parts.
    whole = {starts: typed_of(mapping, starts) for starts, mapping in builder.whole.items()}
    # The library of the model: every unit, and the records that the model reaches; and what its hashes
    # cover: those records and the units that it uses, as the file writes them and as the whole
    # structures and the values' types read them.
    types = [
        {'type': v.type} for entity in scenario.entities for v in entity.values if isinstance(v.type, str)
    ]
    library, content = reached(source.evidence, library, types=types, structures=whole.values())
    library_hash = digest(library_content(content))
    units = UnitSystem(library['units'])
    time = builder.time
    # The references of every basis of the file, once; each default and option value that cites a
    # datum, once, against its own basis and with the unit that the structure gives its input.
    errors += basis_errors(source.evidence, library)
    errors += datum_errors({'values': builder.datum_values}, library)

    # Each structure with what its checks found (`Structure.with_facts`): the rest of the build reads
    # these, and the model keeps them.
    typed, whole_typed = {}, {}
    for starts, structure in structures.items():
        context = f'structure {list(starts)}'
        found, typed[starts] = structure_analysis.checked(structure, library, units)
        errors += [{**item, 'context': context} for item in found]
    # The whole structures too, so that a part that every run leaves out is still checked. An error
    # that a structure already gave is not given again.
    reported = {(item.get('code'), item.get('path'), item.get('message')) for item in errors}
    for starts, structure in whole.items():
        found, whole_typed[starts] = structure_analysis.checked(structure, library, units)
        for item in found:
            key = (item.get('code'), item.get('path'), item.get('message'))
            if key not in reported:
                reported.add(key)
                errors.append({**item, 'context': f'every part of structure {list(starts)}'})
    first = next(iter(typed.values()))
    errors += timescale_errors(time, scenario.timescales, first, units)
    errors += start_errors(builder, typed)
    # The problems of the runs' table that the build does not find itself: the values of the options
    # that no run names (a run's values are checked when it resolves), and each unit that the table
    # cannot read: the unit of an input's type (`types.written_unit`), and a number that its unit does not
    # read (`types.number_in`). A model that builds then has a table that every study reads without a
    # problem.
    table = Runs.from_table(builder.run_table)
    unnamed = set(table.unnamed())
    settings = {
        f'{setting["path"]}/value'
        for item in table.inputs.values()
        for option, setting in item.options.items()
        if option in unnamed
    }
    # Scoped numerical admission still requires a well-formed table: the selected study
    # validates that same source table and every edit as a transaction. Only effective
    # numerical resolutions are deferred, never malformed or out-of-range assignments.
    errors += [
        item
        for item in table.problems
        if admission_runs is not None or item['path'] in settings or item['code'] in ('unit', 'distribution')
    ]
    if errors:
        raise ModelError(located(errors, lines, origin, files, columns))
    menu = {group.name: {p.name: thaw(p.text) for p in group.profiles} for group in scenario.groups}
    model = Model(
        origin=origin,
        lines=freeze(lines),
        library=freeze(library),
        library_hash=library_hash,
        model_hash=model_identity(source.identity, content, LANGUAGE_VERSION),
        implementation_hash=implementation_hash(),
        menu=freeze(menu),
        runs=freeze(runs_of(builder)),
        start_options=tuple(builder.start_states()),
        inputs=freeze(inputs_of(builder, first)),
        entities=freeze(
            {
                **{builder.hosts[e]: e for e in builder.entity_class},
                **({MAIN: MAIN} if MAIN in first.entities else {}),
            }
        ),
        outputs=freeze({key: oid for key, oid in builder.outcome_of.items()}),
        events=freeze(events_of(builder)),
        structures=MappingProxyType(typed),
        left_out=freeze({starts: builder.left_out[starts] for starts in structures}),
        whole=MappingProxyType({starts: whole_typed[starts] for starts in structures}),
        time=freeze(time),
        initiation=freeze(builder.initiation),
        index=freeze(evidence_index(scenario, whole_typed, lines, origin, files)),
        files=freeze(dict(files or {})),
        run_table=builder.run_table,
        evidence=freeze(evidence_of(scenario, library)),
        scenario=scenario,
        admission_runs=admission_runs,
        arguments=freeze(builder.arguments),
    )
    for run in model.runs if admission_runs is None else admission_runs:
        numbers, problems = model.numbers(model.run_values(run))
        try:
            if problems:
                raise ModelError(problems)
            # The blocking checks of the inputs hold for the values of every run, as they hold for every
            # choice of options that no run makes (`choice_errors`): one rule, so a model that builds has
            # an admissible default study.
            model.defaults[run] = model._resolve(run, numbers, checked=True)
            model.proven.add(choice_key(model.runs[run]['starts'], model.run_values(run)))
        except ModelError as exc:
            errors += [{**item, 'run': run} for item in exc.diagnostics]
    if errors:
        raise ModelError(located(errors, lines, origin, files, columns))
    errors = whole_errors(model)
    errors += choices_errors(model, builder, table, library, numerical=admission_runs is None)
    if errors:
        raise ModelError(located(errors, lines, origin, files, columns))
    return model


def evidence_of(scenario, library):
    """Resolved language-defined basis slots and references; the notes are not interpreted."""
    sites = {}
    definitions = {record.name: thaw(record.content) for record in scenario.records}
    records = {basis_digest(record): basis_content(record) for record in definitions.values()}
    for site in scenario.sites:
        resolved = sites[site.where] = thaw(site.value)
        for record in resolved if isinstance(resolved, list) else [resolved]:
            if isinstance(record, dict) and 'kind' in record:
                records.setdefault(basis_digest(record), basis_content(record))
    reached = dependencies_of(((c.kind, c.id, c.where) for c in scenario.citations), library)
    return {
        'sites': sites,
        'claims': reached['claims'],
        'assumptions': reached['assumptions'],
        'records': records,
        'aliases': {name: basis_digest(record) for name, record in definitions.items()},
    }


def whole_errors(model):
    """The bounds, domains and proofs of every part, also of a part that every run leaves out: the
    checks of a resolved run (`analysis.values.value_facts`) on each whole structure, with the values of the
    first run that starts from its start states. A structure that leaves nothing out was checked when
    its runs resolved."""
    errors, first = [], {}
    for run, info in model.runs.items():
        if run not in model.defaults:
            continue
        first.setdefault(info['starts'], run)
    library = thaw(model.library)
    for starts, run in first.items():
        if not any(model.left_out[starts].values()):
            continue
        # The whole structure with what the run of the build has of its own, but for what its
        # checks proved: the checks of the whole structure find their own facts.
        own = {
            key: value
            for key, value in model.defaults[run].own().items()
            if key in Resolved.ALWAYS and key not in value_analysis.PROVED
        }
        rs = Resolved.over(model.whole[starts], own)
        context = f'every part of structure {list(starts)}'
        errors += [{**item, 'context': context} for item in value_analysis.value_facts(rs, library)[0]]
    return errors


def choices_errors(model, builder, table, library, *, numerical=True):
    """The choices of options that no run makes, each resolved and checked: every option that no run
    names with the other options of each run (`Runs.unnamed_choices`). A choice whose start states no
    run has runs in the structure that the builder derives for them, checked as the runs' structures
    are. Scoped admission retains those structural checks but omits the numerical resolutions
    (``numerical=False``)."""
    units = UnitSystem(library['units'])
    derived = {}

    def structure_for(starts):
        if starts not in derived:
            try:
                structure = typed_of(builder.derive(builder.base, starts), starts)
            except AnalysisError as exc:
                raise ModelError([diagnostic('build', path_text(exc.path), str(exc))]) from None
            except RewriteError as exc:
                raise ModelError([exc.diagnostic]) from None
            # The typed parts with the facts: the resolution of a choice reads them as they are.
            problems, typed = structure_analysis.checked(structure, library, units)
            if problems:
                raise ModelError(problems)
            derived[starts] = typed
        return derived[starts]

    # The keys go into the model: a model that is built proved each one (`Model.proven`).
    checked = model.proven
    choices = table.unnamed_choices()
    if not numerical:
        errors = []
        states = set(model.start_options)
        starts_to_check = {tuple(sorted(p for p in options if p in states)) for options in choices}
        for starts in sorted(starts_to_check - model.structures.keys()):
            try:
                structure_for(starts)
            except ModelError as exc:
                errors += [{**item, 'context': f'structure {list(starts)}'} for item in exc.diagnostics]
        return errors
    values = {options: table.values_of(options).values for options in choices}
    return choice_errors(model, values, checked, structure_for)


def choice_key(starts, values):
    """What one resolution checks: a structure (its start-state options) and the input values."""
    return tuple(starts), json.dumps({input_name(k): thaw(v) for k, v in values.items()}, sort_keys=True)


def choice_errors(model, choices, checked, structure_for=None):
    """The diagnostics of choices of options that no run makes, `{options: input values}`. Each one is
    resolved through the structure of a run with the same start-state options, with its blocking
    input checks and the proofs of that structure, and each of its diagnostics gives the options
    (`options`, and `context`). A choice with the start states and values of a run or of an earlier
    choice is resolved once (`checked` holds their keys). A choice whose start states no run has takes
    `structure_for(starts)`, when it is given, and is otherwise a diagnostic."""
    by_starts = {}
    for run, info in model.runs.items():
        by_starts.setdefault(info['starts'], run)
    states = set(model.start_options)
    errors = []
    for options, values in choices.items():
        starts = tuple(sorted(p for p in options if p in states))
        context = 'options ' + ' · '.join(options)
        where = {'options': list(options), 'context': context}
        key = choice_key(starts, values)
        if key in checked:
            continue
        try:
            if starts in by_starts:
                model._resolved(by_starts[starts], values)  # the checks; nobody reads the result
            elif structure_for is not None:
                numbers, problems = model.numbers(model.point_values(values))
                if problems:
                    raise ModelError(problems)
                model.resolve_in(structure_for(starts), numbers, context)
            else:
                message = 'No run starts from the start states of these profiles'
                menu = path_text(model.scenario.menu_where)
                errors.append({**diagnostic('options', menu, message), **where})
                continue
        except ModelError as exc:
            errors += [{**item, **where} for item in exc.diagnostics]
        else:
            checked.add(key)
    return errors


def runs_of(builder):
    """{run: its options, its name, the run it is the comparison of, and its start-state options}. The
    name that the pages show is the run's text, or its options joined by " · ", or, for a run without
    options, the run's own name."""
    out = {}
    for run in builder.scenario.runs:
        options = tuple(run.profiles)
        out[run.name] = {
            'options': options,
            'name': thaw(run.text) if run.text is not None else ' · '.join(options) or run.name,
            'comparison_of': thaw(run.comparison),
            'starts': builder.run_starts(options),
        }
    return out


def inputs_of(builder, structure):
    """{entity.field: what the input is, its own value and range, and the options that set it}. The
    value of a distribution is its central value, and `distribution` holds its record (None for a
    point value). `structure` is the typed structure (`structure.Structure`) whose inputs these are."""
    group_of = builder.run_table.data['group_of']
    by_name = {pid: key for key, pid in builder.parameter_of.items()}
    parameters = structure.parameters
    defaults = {pid: thaw(builder.run_table.data['inputs'][key]['value']) for pid, key in by_name.items()}

    def central(name, value):
        """The central value of `value`, a distribution or a point value of input `name`, with the
        defaults of the inputs that it reads."""
        if not is_distribution(value):
            return value
        try:
            return point_values({**defaults, name: value}, builder.arguments, parameters, builder.units)[name]
        except DistributionProblem:
            return None  # the resolution of each run that takes the value reports its problem

    out = {}
    for name, parameter in parameters.items():
        e, f = split_key(by_name[name])
        item = builder.run_table.data['inputs'][by_name[name]]
        is_bool = item['is_bool']
        names = item['names']
        options = {}
        for option, setting in item['options'].items():
            options[option] = {
                'value': central(name, thaw(setting['value'])),
                'distribution': thaw(setting['value']) if is_distribution(setting['value']) else None,
                'basis': builder.resolved(thaw(setting['basis'])),
                'group': group_of.get(option),
            }
        adjust = parameter.adjust
        kind = 'bool' if is_bool else 'names' if names else 'number'
        out[name] = {
            'entity': flat_entity(e),
            'field': f,
            'doc': parameter.label,
            'type': kind,
            **({'values': list(names)} if names else {}),
            'unit': parameter.unit,
            'value': central(name, thaw(item['value'])),
            'distribution': thaw(item['value']) if is_distribution(item['value']) else None,
            'fixed': item['fixed'],
            'range': [adjust.minimum, adjust.maximum]
            if adjust.mode == 'range' and kind == 'number'
            else None,
            'basis': builder.resolved(thaw(item['basis'])),
            'options': options,
            'groups': sorted({p['group'] for p in options.values() if p['group']}),
        }
    return out


def events_of(builder):
    """{event in the language: the event of the structure}: each event, and each of its outcomes,
    `entity.event.outcome`, in the order of the entities and their events."""
    out = {}
    for entity in builder.scenario.entities:
        for event in entity.events:
            key = f'{entity.name}.{event.name}'
            rid = builder.rule_id(key)
            out[key] = rid
            for outcome in event.outcomes or ():
                out[f'{key}.{outcome.name}'] = f'{rid}.{outcome.name}'
            if not event.outcomes:
                out[f'{key}.done'] = f'{rid}.done'
    return out


def timescale_errors(time, written, structure, units):
    """The shortest physical times are times computed from inputs alone. `written` are the timescales
    of the semantic model, whose places name them. `structure` is a typed structure
    (`structure.Structure`), whose inputs the timescales read."""
    symbols = {}
    for pid, parameter in structure.parameters.items():
        try:
            symbols[pid] = units.dimension(parameter.unit)
        except ExpressionError:
            continue
    errors = []
    # The time of a model is plain data: it writes each timescale as its text.
    for expr, part in zip(time.get('timescales', []), written or ()):
        try:
            compile_expression(node(expr), symbols, units, TIME_UNIT)
        except (ExpressionError, SyntaxError) as exc:
            errors.append(diagnostic('timescale', path_text(part.where), exc))
    return errors


def start_errors(builder, structures):
    """The start is a part of every structure (`{start-state options: structure.Structure}`): the
    rule of the event `start`."""
    initiation = builder.initiation
    if not initiation:
        return []
    errors = []
    for starts, structure in structures.items():
        if initiation['rule'] not in structure.rules:
            errors.append(
                diagnostic(
                    'initiation',
                    path_text(builder.scenario.start.where),
                    f'The start is not a part of the structure {list(starts)}',
                )
            )
    return errors


def evidence_index(scenario, structures, lines, origin, files=None):
    """Every use of a basis in the scenario's file, with the part it supports and its line; and who
    calls and reads whom in the structures (the whole structures: also the parts that a run leaves
    out; `structures` holds them as typed structures, `structure.Structure`). The notes and the named
    records are not uses. Each site has its named records written out (the record, with its `name`)."""
    uses = []

    def record(item, part):
        if not isinstance(item, Mapping) or 'status' in item:
            return  # a range note gives the reasons for a range; it is not a basis
        key = tuple(part)
        while key and key not in lines:
            key = key[:-1]
        uses.append(
            {
                'part': '/'.join(map(str, part)),
                'name': item.get('name'),
                'kind': item.get('kind'),
                'claims': sorted({link['claim'] for link in item.get('links', []) if 'claim' in link}),
                'assumption': item.get('assumption'),
                **({'convention': item['convention']} if item.get('convention') else {}),
                **({'line': lines[key]} if key in lines else {}),
                **({'file': files[key]} if files and key in files and files[key] != origin else {}),
            }
        )

    for site in scenario.sites:
        # The notes are the authors' and the reviewers' texts, and their records are no uses of a part.
        if site.where[0] != 'notes:':
            value = thaw(site.value)
            for item in value if isinstance(value, list) else [value]:
                record(item, site.part)
    callers, readers = {}, {}
    for structure in structures.values():
        for rid, rule in structure.rules.items():
            for outcome in rule.outcomes:
                for event in outcome.do.fire:
                    callers.setdefault(event, set()).add(f'{rid}.{outcome.name}')
        for eid, links in structure.links.items():
            for name, link in links.items():
                readers.setdefault(link.target, set()).add(f'{eid}.{name}')
    return {
        'file': origin,
        'uses': uses,
        'callers': {k: sorted(v) for k, v in sorted(callers.items())},
        'readers': {k: sorted(v) for k, v in sorted(readers.items())},
    }
