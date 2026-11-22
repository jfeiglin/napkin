"""Render the committed summaries from the canonical models and their completed studies.

Each builder is a pure function ``artifacts(ctx) -> {path: str}``. Every path is a committed
summary in the source checkout that ``--check`` compares byte for byte, alongside any file left in a
builder's committed locations that it no longer produces. The context builds each model and
evaluates each study once, so builders share completed results instead of reading each other's
output.
"""

from __future__ import annotations

import contextlib
import multiprocessing
import re
from concurrent.futures import ProcessPoolExecutor
from decimal import Decimal
from functools import cache, cached_property, partial
from importlib import import_module
from pathlib import Path

from napkin import store
from napkin.model import load_scenario
from napkin.model.library import load_library

from .. import catalogue
from ..catalogue import ROOT

# These builders describe the complete catalogue or library, not a selection of scenarios.
AGGREGATE = ('manifest',)
HISTORICAL = ('assumptions', 'briefs', 'html', 'methods', 'runs')
# A committed location in the results folder of each owner of the catalogue: `{results}/brief.md` is
# `scenarios/water_wipe/results/brief.md` for the scenario water_wipe (`catalogue.result`).
RESULTS = '{results}'


def _selection(scenario_ids):
    """A stable, deduplicated selection, or None for the full catalogue."""
    identifiers = sorted(set(scenario_ids or ()))
    if any(not re.fullmatch(catalogue.OWNER, sid, re.ASCII) for sid in identifiers):
        raise ValueError(
            'Scenario IDs must have the form of a package, a lowercase letter, then lowercase letters, '
            'digits and _, and a variant after a colon'
        )
    return tuple(identifiers) or None


@cache
def _model(root, scenario_id):
    root = Path(root)
    return load_scenario(catalogue.scenario_path(root, scenario_id))


def _default_study(root, scenario_id):
    """The compiled model revision and its completed default run records from one worker."""
    model = _model(root, scenario_id)
    return model.model_hash, catalogue.completed_study(model)


class Context:
    """Lazily compiled models and completed studies shared by all builders.

    ``studies`` supplies ``{scenario: (compiled model, completed records by run)}``; otherwise each is evaluated
    once, in ``jobs`` worker processes. ``scenario_ids`` restricts compilation and evaluation to
    known catalogue IDs; validation precedes reading the library or compiling a model.
    ``committed_spreads`` takes each brief's spread section from the committed brief instead of
    sampling it (`tools.check` without `--spreads`, D-39).
    """

    def __init__(
        self, root=ROOT, *, jobs=1, progress=None, studies=None, scenario_ids=None, committed_spreads=False
    ):
        self.root = Path(root)
        self.jobs = jobs
        self.committed_spreads = committed_spreads
        self.progress = progress or (lambda message: None)
        self.scenario_ids = _selection(scenario_ids)
        if self.scenario_ids is not None:
            known = catalogue.entries(self.root)
            packages = {name.partition(':')[0] for name in known}
            unknown = sorted(set(self.scenario_ids).difference(known, packages))
            if unknown:
                raise ValueError('Unknown scenario IDs: ' + ', '.join(unknown))
            self.scenario_ids = tuple(
                name
                for name in known
                if name in self.scenario_ids or name.partition(':')[0] in self.scenario_ids
            )
        if studies is not None:
            supplied = {
                sid: study
                for sid, study in studies.items()
                if self.scenario_ids is None or sid in self.scenario_ids
            }
            self.__dict__['studies'] = {sid: records for sid, (_, records) in supplied.items()}
            self.__dict__['models'] = {sid: model for sid, (model, _) in supplied.items()}

    @cached_property
    def libraries(self):
        return {sid: load_library(self.paths[sid]) for sid in self.models}

    @cached_property
    def paths(self):
        """The selected source files, in catalogue order; all files when no selection was given."""
        return {
            sid: path
            for sid, path in catalogue.entries(self.root).items()
            if self.scenario_ids is None or sid in self.scenario_ids
        }

    @cached_property
    def models(self):
        return {sid: load_scenario(path) for sid, path in self.paths.items()}

    @cached_property
    def studies(self):
        """Every scenario's accepted default study."""
        self.progress(f'evaluating {len(self.models)} default studies')
        if self.jobs == 1 or len(self.models) <= 1:
            return {
                sid: catalogue.completed_study(model, jobs=self.jobs) for sid, model in self.models.items()
            }
        studies = {}
        with ProcessPoolExecutor(
            min(self.jobs, len(self.models)),
            mp_context=multiprocessing.get_context('spawn'),
            **store.pool_options(),
        ) as pool:
            futures = {sid: pool.submit(_default_study, str(self.root), sid) for sid in self.models}
            for sid, future in futures.items():
                model_hash, records = future.result()
                if model_hash != self.models[sid].model_hash:
                    raise ValueError(f'{sid}: a worker built another model revision')
                studies[sid] = records
        return studies


def builders():
    """The ordered registry: each builder with the committed locations it owns.

    A location is a glob pattern under the checkout whose ``*`` and ``[...]`` stay within one
    directory, or a file in the results folder of each owner of the catalogue (``{results}/name``,
    `_locations`). Every committed summary a builder writes lies in one of its locations, and a file
    there that a fresh render does not produce is an orphan: ``drift`` reports it and ``prune``
    deletes it. Locations name only what a builder can write (the results folders of the catalogue's
    folders, `catalogue.folders`), so a hand-written file beside them is never taken for an orphan.
    """
    from ..evidence import manifest

    return {
        'readings': (partial(_artifacts, 'readings'), (f'{RESULTS}/readings.md',)),
        'dossier': (partial(_artifacts, 'dossier'), (f'{RESULTS}/source-dossier.json',)),
        'manifest': (lambda ctx: manifest.artifacts(ctx.root), (manifest.PATH,)),
    }


def _artifacts(name, ctx):
    """Load a renderer when a selection asks it to generate an artifact."""
    return import_module(f'.{name}', __name__).artifacts(ctx)


def sample_spreads(ctx):
    """Run each declared spread of the selection at its authored settings through the public sampler."""
    from napkin.engine import edits_for
    from napkin.model.load import load_json
    from napkin.spread import spread

    from .brief import brief_of, shown, spread_document, value_note

    total = 0
    for sid, model in ctx.models.items():
        brief = brief_of(model)
        for spec in brief.spreads:
            path = spread_document(model, spec)
            body = load_json(path, exact_numbers=True)
            if not isinstance(body, dict):
                raise ValueError(f'{path}: an edit document is a JSON object')
            edits = edits_for(model, body)
            paths = [
                name
                for name in spec.outputs or shown(brief, model)
                if value_note(model, 'not_estimated', name, 'reason') is None
            ]
            for run in spec.runs:
                ctx.progress(f'sampling {sid} {spec.id} {run}: {spec.samples} samples, seed {spec.seed}')
                result = spread(
                    model, paths, run=run, edits=edits, samples=spec.samples, seed=spec.seed, jobs=ctx.jobs
                )
                if result.refused:
                    raise ValueError(f'{sid} {spec.id} {run}: {result.refused}')
                total += len(result.samples)
    ctx.progress(f'verified {total} samples from current declared spreads')


def _located(path, locations):
    """Whether a checkout path lies in one of these locations, matched as ``Path.glob`` would."""

    def expression(location):
        # Literal text alternates with the wildcards the split captures.
        parts = re.split(r'(\*|\[[^\]/]+\])', location)
        return ''.join(
            re.escape(part) if index % 2 == 0 else '[^/]*' if part == '*' else part.replace('[!', '[^', 1)
            for index, part in enumerate(parts)
        )

    return any(re.fullmatch(expression(location), path) for location in locations)


def selected(only=None, scenario_ids=None):
    """The builders to run: ``only`` names them; otherwise every builder. A selection of scenarios
    runs no aggregate builder."""
    for name in only or ():
        if name in HISTORICAL:
            raise ValueError(
                f'{name} is a historical publication format at revision 8488047. '
                'Current formats are readings, dossier and manifest.'
            )
        if name not in builders():
            raise ValueError(f'Unknown publication format {name!r}')
    selection = _selection(scenario_ids)
    if selection is not None:
        requested = [name for name in AGGREGATE if only and name in only]
        if requested:
            raise ValueError('--scenario cannot select aggregate builders: ' + ', '.join(requested))
    return [
        name
        for name in builders()
        if (not only or name in only) and (selection is None or name not in AGGREGATE)
    ]


def _locations(locations, root=ROOT, scenario_ids=None):
    """The committed locations of a builder in the checkout at `root`. A location ``{results}/name`` is
    the file `name` in the results folder of each folder of the catalogue (`catalogue.folders`, with or
    without a model: a removed case's results are orphans), or of each selected owner. A selection keeps
    a location in the folder of an owner only when it selects the owner, and omits catalogue-wide files."""
    selection = _selection(scenario_ids)
    folders = None
    scoped = []
    for location in locations:
        if location.startswith(RESULTS):
            if selection is None and folders is None:
                folders = catalogue.folders(root)
            owners = folders if selection is None else selection
            scoped.extend(catalogue.result(name) + location[len(RESULTS) :] for name in owners)
        elif selection is None or catalogue.owner_of(location, root) in selection:
            scoped.append(location)
    return tuple(scoped)


def build(ctx, only=None):
    """Return {path: content} from the selected builders, in registry order."""
    outputs = {}
    scenario_ids = getattr(ctx, 'scenario_ids', None)
    names = selected(only, scenario_ids)
    if scenario_ids is not None:
        ctx.progress('skipping aggregate builders: ' + ', '.join(AGGREGATE))
    for name, (builder, locations) in builders().items():
        if name not in names:
            continue
        scoped = _locations(locations, getattr(ctx, 'root', ROOT), scenario_ids)
        if not scoped:
            ctx.progress(f'skipping {name}: no output for the selected scenarios')
            continue
        ctx.progress(f'building {name}')
        for path, content in builder(ctx).items():
            if path in outputs:
                raise ValueError(f'Two builders produce {path}')
            if not _located(path, scoped):
                raise ValueError(f'{name} writes {path} outside its committed locations')
            outputs[path] = content
    return outputs


def cell(value):
    """Authored text as one markdown table cell: a pipe or a line break cannot split the row."""
    return ' '.join(str(value).splitlines()).replace('|', '\\|')


def limits(limitations, page):
    """The part of a page that lists the limits of a scenario's results that its reviewers state
    (`review.limitations`, each `{id, statement}`).

    The calculation never reads them; they qualify what it shows. Each limit shows once on a page:
    one that the rest of ``page`` already states word for word, such as in the summary or the
    decisive defender choice, is not listed again. Without a limit left to list there is no part.
    """
    shown = ' '.join(page.split())
    statements = dict.fromkeys(' '.join(item['statement'].split()) for item in limitations)
    listed = [statement for statement in statements if statement not in shown]
    if not listed:
        return []
    return [
        '## Limits of the results',
        '',
        'The reviewers of this scenario state these limits.',
        '',
        *(f'- {statement}' for statement in listed),
        '',
    ]


def stable(value):
    """A calculated value as a Decimal at nine significant figures, before its display rounding.

    Its last digits differ between computers, because the BLAS and SIMD kernels differ, and a committed
    summary must be the same on every computer: a value on a rounding tie (4125 at three figures, or
    78 hours as 3.25 days) then rounds the same way everywhere.
    """
    return Decimal(f'{value:.9g}')


def orphans(outputs, root=ROOT, names=None, *, scenario_ids=None):
    """Files in the committed locations of the builders that rendered ``outputs`` (``names``, else
    the default selection) that the fresh render did not produce: a removed case's brief or a methods
    record no longer written."""
    root = Path(root)
    names = selected(scenario_ids=scenario_ids) if names is None else names
    found = {
        path.relative_to(root).as_posix()
        for name, (_, locations) in builders().items()
        if name in names
        for pattern in _locations(locations, root, scenario_ids)
        for path in root.glob(pattern)
        if path.is_file()
    }
    return sorted(found - outputs.keys())


def drift(outputs, root=ROOT, names=None, *, scenario_ids=None):
    """Committed summaries whose checkout bytes differ from a fresh render, then the orphans.

    Text compares as its exact UTF-8 bytes, so changed line endings or encodings are drift too.
    """
    stale = []
    for path, content in outputs.items():
        target = Path(root) / path
        expected = content if isinstance(content, bytes) else content.encode('utf-8')
        if not target.is_file() or target.read_bytes() != expected:
            stale.append(path)
    return stale + orphans(outputs, root, names, scenario_ids=scenario_ids)


def prune(outputs, root=ROOT, names=None, *, scenario_ids=None):
    """Delete the orphans in the rendering builders' committed locations; return their paths."""
    removed = orphans(outputs, root, names, scenario_ids=scenario_ids)
    for path in removed:
        target = Path(root) / path
        target.unlink()
        with contextlib.suppress(OSError):  # a location left empty goes too
            target.parent.rmdir()
    return removed


def write(files, destination):
    """Write each file's exact content: text as UTF-8 with its own line endings on every platform."""
    destination = Path(destination)
    for path, content in files.items():
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding='utf-8', newline='')
