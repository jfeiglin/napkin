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
from functools import cache, cached_property
from pathlib import Path

from napkin import store
from napkin.engine import evaluate_study
from napkin.engine.study import StudyResult
from napkin.model import load_scenario

from .. import catalogue
from ..catalogue import ROOT

# These builders describe the complete catalogue or library, not a selection of scenarios.
AGGREGATE = ('manifest',)
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
    """One scenario's default study, evaluated in a worker: its runs and diagnostics."""
    model = _model(root, scenario_id)
    study = evaluate_study(model)
    return (
        model.model_hash,
        model.implementation_hash,
        study.admissible,
        study.diagnostics,
        study.effective_edits,
        study.runs,
    )


class Context:
    """Lazily compiled models and completed studies shared by all builders.

    ``studies`` supplies completed default studies (with their models); otherwise each is evaluated
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
            unknown = sorted(set(self.scenario_ids).difference(known))
            if unknown:
                raise ValueError('Unknown scenario IDs: ' + ', '.join(unknown))
        if studies is not None:
            supplied = {
                sid: study
                for sid, study in studies.items()
                if self.scenario_ids is None or sid in self.scenario_ids
            }
            self.__dict__['studies'] = supplied
            self.__dict__['models'] = {sid: study.model for sid, study in supplied.items()}

    @cached_property
    def libraries(self):
        return {sid: model.library for sid, model in self.models.items()}

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
        if self.jobs > 1:
            # Each worker studies one scenario at a time. With fewer scenarios than jobs, the processes
            # that this one may use (itself and its helpers) and no worker takes go to the workers as
            # helpers that simulate the runs of their study.
            workers = max(1, min(self.jobs, len(self.models)))
            helpers = max(0, (store.helpers() + 1) // workers - 1)
            with ProcessPoolExecutor(
                workers,
                mp_context=multiprocessing.get_context('spawn'),
                **store.pool_options(helpers=helpers),
            ) as pool:
                futures = {sid: pool.submit(_default_study, str(self.root), sid) for sid in self.models}
                completed = {sid: future.result() for sid, future in futures.items()}
            studies = {}
            for sid, (
                model_hash,
                implementation_hash,
                admissible,
                diagnostics,
                edits,
                runs,
            ) in completed.items():
                model = self.models[sid]
                if (model_hash, implementation_hash) != (model.model_hash, model.implementation_hash):
                    raise ValueError(f'{sid}: a worker built another model revision')
                studies[sid] = StudyResult(
                    model_hash,
                    admissible,
                    diagnostics,
                    edits,
                    runs,
                    model=model,
                    implementation_hash=implementation_hash,
                )
        else:
            studies = {sid: evaluate_study(model) for sid, model in self.models.items()}
        for sid, study in studies.items():
            if not study.admissible:
                raise ValueError(f'{sid}: default study rejected: {study.diagnostics}')
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
    from . import assumptions, briefs, dossier, methods, runs

    return {
        'briefs': (briefs.artifacts, (f'{RESULTS}/brief.md', briefs.INDEX)),
        'methods': (methods.artifacts, (f'{RESULTS}/methods.md',)),
        'dossier': (dossier.artifacts, (f'{RESULTS}/source-verification.json',)),
        'manifest': (lambda ctx: manifest.artifacts(ctx.root), (manifest.PATH,)),
        'assumptions': (assumptions.artifacts, (f'{RESULTS}/assumption-review.json',)),
        'runs': (runs.artifacts, (f'{RESULTS}/runs.json', f'{RESULTS}/runs.csv')),
    }


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
        ctx.progress(f'skipping the catalogue index: {catalogue.INDEX}')
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
