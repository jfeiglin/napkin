"""The run tables: for each scenario that declares sweeps, its catalogue runs plus the sweeps.

Each row records the model and implementation hashes, the complete effective inputs in authored units, every final
outcome with its estimation status, and the inputs that the edits change in the row's run, with
the assumptions behind them. The sweeps (`[[sweep]]` in the brief settings of each model,
`publish/brief.py`) are edits for one run each, by input names (`entity.value`), and record the
declared operational conditions. The canonical model supplies every evaluated quantity. A scenario
without sweeps has no run table.
"""

import csv
import io
import json
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from decimal import Decimal

from napkin import store
from napkin.engine import edits_for, evaluate_study, sample_result
from napkin.engine.study import EDIT_LEVELS
from napkin.model.ir import basis_records
from napkin.model.model import input_name
from napkin.model.runs import Runs
from napkin.model.uncertain import is_distribution

from .. import catalogue
from . import stable
from .brief import brief_file, brief_of, read_brief
from .formatting import NEGLIGIBLE, rounded

# Final values have six significant figures: the last digits of a calculated value differ between
# computers, and the committed table must be the same on every computer.
FIGURES = 6


def changed_inputs(model, run, edits):
    """{input: value} of the inputs that an edit body changes in one run, in the order that the body
    writes them. The run layer gives the origin of each value of the run (`Resolved.origins`): an
    edit of another run or of an option that the run does not name changes nothing in it. Each value
    is the one that the run takes, from the narrowest edit that reaches it. The body must have no
    problems, as in an admissible study."""
    edits = edits or {}
    table = Runs.from_table(model.run_table)
    resolved = table.values_of(table.runs[run], edits, run)
    written = list(edits.get('set') or {})
    for values in (edits.get('options') or {}).values():
        written += values
    for values in (edits.get('runs') or {}).values():
        written += values
    return {
        name: resolved.values[name]['text']
        if is_distribution(resolved.values[name])
        else resolved.values[name]
        for name in dict.fromkeys(written)
        if resolved.origins[name][0] in EDIT_LEVELS
    }


def row(study, run, rid, description, edits, *, report=None):
    if not study.admissible:
        raise ValueError(f'{rid}: {study.diagnostics}')
    report = sample_result(study) if report is None else report
    if not report['admissible']:
        raise ValueError(f'{rid}: {report["diagnostics"]}')
    final = report['runs'][run]['reporting_points']['final']
    resolved = study.runs[run]['resolved']
    return {
        'id': rid,
        'description': description,
        'run': run,
        'options': list(resolved.options),
        'edits': edits,
        'changed': {
            name: {
                'value': value,
                'assumption': next(
                    (
                        r['assumption']
                        for r in basis_records(resolved.parameters[input_name(name)].basis)
                        if r.get('assumption')
                    ),
                    None,
                ),
            }
            for name, value in changed_inputs(study.model, run, edits).items()
        },
        'inputs': dict(resolved.parameter_values),
        'outcomes': {
            k: {'value': final_value(final['values'][k]), 'status': final['statuses'][k]}
            for k in final['values']
        },
    }


def final_value(value):
    """A final value at FIGURES significant figures, the same on every computer; a residual reads 0."""
    if value is None:
        return None
    return 0.0 if abs(value) < NEGLIGIBLE else float(rounded(stable(value), FIGURES))


def plain(value):
    """A final value as plain decimal text for the CSV: 2013570, never 2.01357e+06."""
    return format(Decimal(repr(value)).normalize(), 'f')


def sweep_row(model, run, rid, description, edits):
    """One sweep's row. Each row reads one run, so only that run runs under the sweep."""
    study = evaluate_study(model, edits_for(model, edits), runs=[run])
    return row(study, run, rid, description, edits)


def _sweep_row(root, scenario_id, expected, *job):
    from . import _model

    model = _model(root, scenario_id)
    if (model.model_hash, model.implementation_hash) != expected:
        raise ValueError(f'{scenario_id}: a sweep worker built another model or implementation revision')
    return sweep_row(model, *job)


def declares_sweeps(path):
    """Whether the brief settings of the model file `path` (`brief.brief_file`: a variant's own, else its
    package's) declare sweeps, read without the model: the run tables build the model of a scenario only
    when it declares them."""
    brief = brief_file(path)
    return brief is not None and bool(read_brief(brief.read_text(encoding='utf-8'), str(brief)).sweeps)


def artifacts(ctx):
    outputs = {}
    for sid, path in ctx.paths.items():
        if declares_sweeps(path):
            outputs.update(table(ctx, sid, brief_of(ctx.models[sid]).sweeps))
    return outputs


def table(ctx, sid, declared):
    """The run table of one scenario: its catalogue runs, then its sweeps (`brief.Sweep`), in the order
    of its brief settings."""
    model = ctx.models[sid]
    base = ctx.studies[sid]
    base_report = sample_result(base)
    rows = [row(base, run, run, model.runs[run]['name'], None, report=base_report) for run in model.runs]
    jobs = [(sweep.run, sweep.id, sweep.description, sweep.edits) for sweep in declared]
    if ctx.jobs > 1:
        with ProcessPoolExecutor(
            ctx.jobs, mp_context=multiprocessing.get_context('spawn'), **store.pool_options()
        ) as pool:
            identities = [(model.model_hash, model.implementation_hash)] * len(jobs)
            rows.extend(
                pool.map(_sweep_row, [str(ctx.root)] * len(jobs), [sid] * len(jobs), identities, *zip(*jobs))
            )
    else:
        rows.extend(sweep_row(model, *job) for job in jobs)
    table = {
        'scenario': sid,
        'model_hash': model.model_hash,
        'implementation_hash': model.implementation_hash,
        'engine_version': base_report['engine_version'],
        'horizon_h': model.time['horizon'],
        'note': 'Completed fatalities, serious casualties, economic loss and operational values at the declared horizon, with each outcome’s scope and input basis. Each value has six significant figures. A numerical residual below 0.000001 reads 0.',
        'rows': rows,
    }
    keys = [k for k in rows[0]['outcomes']]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(['id', 'description', 'run', 'model_hash', 'implementation_hash', 'changed', *keys])
    for r in table['rows']:
        writer.writerow(
            [
                r['id'],
                r['description'],
                r['run'],
                table['model_hash'],
                table['implementation_hash'],
                '; '.join(f'{k}={v["value"]:g}' for k, v in r['changed'].items()),
            ]
            + ['' if r['outcomes'][k]['value'] is None else plain(r['outcomes'][k]['value']) for k in keys]
        )
    return {
        catalogue.result(sid, 'runs.json'): json.dumps(table, indent=2, ensure_ascii=False) + '\n',
        catalogue.result(sid, 'runs.csv'): buffer.getvalue(),
    }
