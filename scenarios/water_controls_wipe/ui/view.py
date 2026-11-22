"""Read-only civilian service readings for a place, its water utilities and a named response."""

from pathlib import Path

from napkin import read
from tools import catalogue
from tools.publish.brief import brief_of

FOLDER = Path(__file__).resolve().parents[1]
PACKAGE = FOLDER.name
ROOT = FOLDER.parents[1]

AREA = (
    'restored_share',
    'people_interrupted_now',
    'people_under_advisory',
    'person_days_lost',
    'unserved_volume',
    'hospital_hours_constrained',
    'economic_loss',
    'support.accepted',
    'support.filtered',
    'relief.throughput',
    'support.reserved',
    'emergency_water_deficit',
    'support.waiting',
    'support.completed',
    'support.delivered',
)
UTILITY = ('service', 'delivered')
INTERVAL = 6  # the overview samples; a request for a particular hour reads the Record at that exact time


def places(root=ROOT):
    return tuple(catalogue.readers(root).get(PACKAGE, ()))


def utilities(model):
    return [m for m in model.declared.members if m.template == 'Utility']


def describe(model, name):
    """Menu, scope and model revision. Reading the menu does not simulate the place."""
    scenario = model.declared.scenario
    brief = brief_of(model)
    # Compare responses under the same initial outage. Other scenario options can also change which
    # systems were initially affected; such runs are different study populations.
    runs = [
        {'id': run.name, 'name': run.text or ' · '.join(run.options) or run.name}
        for run in model.declared.runs
        if all(
            model.declared.option(opt).group in (brief.choice_group, 'Regional support workload')
            for opt in run.options
        )
    ]
    run_names = [r['id'] for r in runs]
    featured = next((name for name in brief.featured or () if name in run_names), run_names[0])
    return {
        'id': name,
        'key': name.split(':', 1)[-1],
        'name': scenario.title.rsplit(': ', 1)[-1],
        'title': scenario.title,
        'package': PACKAGE,
        'what': scenario.summary,
        'horizon': model.configuration.request.horizon,
        'model_hash': model.model_hash,
        'runs': runs,
        'featured': featured,
        'systems': [
            {'id': m.path, 'name': m.title or m.path.replace('_', ' ').title()} for m in utilities(model)
        ],
    }


def frame(model, record, run, hour=None):
    """Read the public series in authored units. An optional hour returns precisely one observation."""
    horizon = record.manifest.horizon
    if record.stop is not None or record.end != horizon:
        return {'errors': [{'message': record.stopped() or f'Run stopped at {record.end:g} h.'}]}
    hours = [hour] if hour is not None else [*range(0, int(horizon), INTERVAL)]
    if hour is None and (not hours or hours[-1] != horizon):
        hours.append(horizon)
    systems = utilities(model)
    paths = [*AREA, *(f'{member.path}.{metric}' for member in systems for metric in UTILITY)]
    series = read(record, model.program, paths, hours)
    return {
        'run': run,
        'horizon': horizon,
        'hours': hours,
        'model_hash': model.model_hash,
        'readings': {row.path: {'unit': row.unit, 'values': list(row.values)} for row in series},
    }
