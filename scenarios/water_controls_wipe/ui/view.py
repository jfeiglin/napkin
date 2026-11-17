"""The frames of the package's live view: what the page shows of a place and of one of its runs.

A pure renderer. Every number comes from the compiled model of the place or from the engine's run of it,
and every word from the model, its evidence or the package's pages (`tools/publish/pages.py`). The parts of
a place (its water systems, the sales between them, their homes and their hospitals) are found from the
templates that make them and from the links between them, so this module keeps no roster of systems."""

import json
import re
from pathlib import Path

from napkin import sample_result
from napkin.core.units import UnitSystem
from napkin.model.ir import thaw
from tools import catalogue
from tools.publish.brief import brief_of, featured
from tools.publish.briefs import timeline
from tools.publish.pages import Pages

FOLDER = Path(__file__).resolve().parents[1]
PACKAGE = FOLDER.name
ROOT = FOLDER.parents[1]
RATE, VOLUME = 'Mgal/day', 'Mgal'  # the units that the page shows
COARSE = 720  # even times over the horizon that find where the story of a run ends
GRID = 360  # even times over the story, beside the times of its events
CARE_COMPARE = 'https://www.medicare.gov/care-compare/details/hospital/{ccn}'
# The outputs whose labels the page shows.
SHOWN = (
    'person_days_lost',
    'economic_loss',
    'hospital_hours_constrained',
    'unserved_volume',
    'people_interrupted_now',
    'people_under_advisory',
)


def places(root=ROOT):
    """The names of the package's places, `package:place`, in the order of the catalogue."""
    return tuple(catalogue.readers(root).get(PACKAGE, ()))


def made_by(model, template):
    """The entities of a model that a template makes, in the order of the file."""
    return [e.name for e in model.scenario.entities if e.template == template]


def owner(model, entity, member):
    """The one entity whose `member` the entity reads, over every structure of the model."""
    found = set()
    for structure in model.whole.values():
        found |= {
            name.rsplit('.', 1)[0]
            for name in structure.links.get(entity, {})
            if name.rsplit('.', 1)[1] == member
        }
    (name,) = found
    return name


def parts(model):
    """The parts of a place: its systems with the sellers before their buyers, its ties as
    {tie: (seller, buyer)}, and the homes and the hospitals of each system that has them."""
    systems = made_by(model, 'Utility')
    ties = {t: (owner(model, t, 'sales_share'), owner(model, t, 'need')) for t in made_by(model, 'Tie')}
    homes = {owner(model, h, 'service'): h for h in made_by(model, 'Households')}
    hospitals = {owner(model, h, 'service'): h for h in made_by(model, 'Hospitals')}
    order = []

    def place(system):
        if system in order:
            return
        for seller, buyer in ties.values():
            if buyer == system:
                place(seller)
        order.append(system)

    for system in systems:
        if any(seller == system for seller, _ in ties.values()):
            place(system)
    for system in systems:
        place(system)
    return order, ties, homes, hospitals


class Shown:
    """The values of a model in the units that the page shows, from the model's own units."""

    def __init__(self, model):
        self.units = UnitSystem(thaw(model.library['units']))

    def __call__(self, value, unit, digits=4):
        """A value in `unit`'s execution scale, in the unit `unit` names (`Mgal/day`, `Mgal`)."""
        return round(float(value) / self.units.scale(unit), digits)

    def own(self, parameter, unit, digits=4):
        """A parameter's value, which is in its own unit, in `unit`."""
        return self(parameter.value * self.units.scale(parameter.unit), unit, digits)


def evidence(name, root=ROOT):
    """The claims and sources of the package's folder and of the place's folder, by ID."""
    claims, sources = {}, {}
    for owner_name in (PACKAGE, name):
        folder = catalogue.locate(owner_name, root).evidence
        for file, into in (('claims.json', claims), ('sources.json', sources)):
            path = folder / file
            if path.exists():
                into.update((item['id'], item) for item in json.loads(path.read_text()))
    return claims, sources


def cited(parameter):
    """The claims that a parameter's record cites."""
    basis = parameter.basis or {}
    return [link['claim'] for link in basis.get('links', ()) if 'claim' in link]


def source_link(whole, claims, sources, system):
    """The document behind a system's daily use, and its title: the source of the first claim that its
    record cites."""
    for claim in cited(whole.parameters[f'{system}.demand']):
        if claim in claims:
            source = sources.get(claims[claim]['source'], {})
            return source.get('URL', ''), source.get('title', '')
    return '', ''


POINT = re.compile(r'point of (.+?) \(([0-9A-Z]{6})\)')


def hospital_name(text):
    """A CMS name, written as a name: 'MOSES H. CONE MEMORIAL HOSPITAL, THE' reads 'The Moses H. Cone
    Memorial Hospital'."""
    name = text.title().replace("'S ", "'s ")
    return f'The {name[:-5]}' if name.endswith(', The') else name


def hospital_list(whole, claims, entity):
    """The hospitals of one Hospitals entity: the claim that its count cites, and the join claims that
    report each hospital in the system's service area, with the CMS ID (CCN) and the name they give."""
    out = []
    for claim in cited(whole.parameters[f'{entity}.facilities']):
        for related in claims.get(claim, {}).get('related', ()):
            if related.get('relation') != 'reports_value' or related['claim'] not in claims:
                continue
            found = POINT.search(claims[related['claim']]['shows'])
            if found:
                ccn = found.group(2)
                out.append(
                    {'name': hospital_name(found.group(1)), 'ccn': ccn, 'href': CARE_COMPARE.format(ccn=ccn)}
                )
    return out


def status_words(whole, entity):
    """{value: text} of an entity's health, from its status lines."""
    label = whole.labels.get(f'{entity}.health')
    if label is None:
        return {}
    words = {}
    for case in label.cases:
        words.setdefault(case.value, case.text)
    if label.default is not None:
        words.setdefault(label.default.value, label.default.text)
    return words


def blurb(folder):
    """Why the place is in the package: the first sentence under "The place" in its README."""
    path = folder / 'README.md'
    found = re.search(r'## The place\n\n(.+?)(\n\n|$)', path.read_text(), re.S) if path.exists() else None
    if not found:
        return ''
    return re.split(r'(?<=\.)\s', ' '.join(found.group(1).split()), maxsplit=1)[0]


def describe(model, name, root=ROOT):
    """What the page shows of a place before a run: its systems with their sources, homes and hospitals,
    the sales between them, its runs and the words of its statuses and outputs. The values are the
    model's defaults; each frame gives those of its own run."""
    whole = next(iter(model.whole.values()))
    shown = Shown(model)
    claims, sources = evidence(name, root)
    order, ties, homes, hospitals = parts(model)
    pages = Pages(model)

    def value(name_, unit=None, digits=4):
        parameter = whole.parameters[name_]
        return shown.own(parameter, unit, digits) if unit else round(float(parameter.value), digits)

    systems = []
    for system in order:
        href, title = source_link(whole, claims, sources, system)
        home, hosp = homes.get(system), hospitals.get(system)
        buys = [t for t, (_, buyer) in ties.items() if buyer == system]
        systems.append(
            {
                'id': system,
                'name': whole.entities[system].label,
                'href': href,
                'tip': title,
                'people': round(value(f'{home}.population')) if home else 0,
                'buys': buys,
                'sells': [t for t, (seller, _) in ties.items() if seller == system],
                'hospitals': hospital_list(whole, claims, hosp) if hosp else [],
                'hospital_entity': hosp or '',
                'facilities': round(value(f'{hosp}.facilities')) if hosp else 0,
                **fixed_of(value, system, buys),
            }
        )
    hospital_states = next((status_words(whole, h) for h in hospitals.values()), {})
    runs = pages.runs()
    labels = pages.labels()['outcomes']
    title = model.scenario.title
    return {
        'id': name,
        'key': name.split(':', 1)[-1],
        'name': title.rsplit(': ', 1)[-1],
        'title': title,
        'package': title.rsplit(': ', 1)[0],
        'what': blurb(catalogue.locate(name, root).folder),
        'people': sum(s['people'] for s in systems),
        'systems': systems,
        'ties': [
            {'id': t, 'seller': a, 'buyer': b, 'capacity': value(f'{t}.capacity', RATE)}
            for t, (a, b) in ties.items()
        ],
        'runs': [{'id': run, 'name': info['name']} for run, info in runs.items()],
        'featured': featured(brief_of(model), model)[0],
        'hospital_states': hospital_states,
        'outputs': {k: labels.get(k, k) for k in SHOWN},
    }


def fixed_of(value, system, buys):
    """The fixed values of a system that its bars are drawn to: use, plant capacity, purchases from
    outside, sales to outside, usable storage, and the most it can buy. `value(name, unit)` reads one."""
    bought = value(f'{system}.bought', RATE)
    return {
        'use': value(f'{system}.demand', RATE),
        'cap': value(f'{system}.nameplate', RATE),
        'bought': bought,
        'sold': value(f'{system}.sold', RATE),
        'full': round(value(f'{system}.usable_share', None) * value(f'{system}.storage', VOLUME), 4),
        'icap': round(sum(value(f'{t}.capacity', RATE) for t in buys) + bought, 4),
    }


def compress(points, straight):
    """Points [[t, v], ...] without those that add nothing: for a stepped series, equal neighbours; for a
    series read straight between its points, the points on the line between their neighbours. Points at
    one time keep the last."""
    out = []
    for point in points:
        if out and abs(point[0] - out[-1][0]) < 1e-9:
            out[-1] = point
        else:
            out.append(point)
    if len(out) < 3:
        return out
    keep = [out[0]]
    for i in range(1, len(out) - 1):
        a, b, c = keep[-1], out[i], out[i + 1]
        if straight:
            w = (b[0] - a[0]) / (c[0] - a[0]) if c[0] > a[0] else 0
            if abs(a[1] + w * (c[1] - a[1]) - b[1]) <= 1e-6 * max(1.0, abs(b[1])):
                continue
        elif b[1] == a[1]:
            continue
        keep.append(b)
    keep.append(out[-1])
    return keep


def moments_of(pages, run, trace):
    """The moments of a run: each text of its story once, at its first time, with how often it happens
    and when it last does."""
    seen, moments = {}, []
    for t, text in timeline(pages, run, trace):
        if text in seen:
            seen[text]['times'] += 1
            seen[text]['last'] = round(t, 3)
            continue
        seen[text] = {'t': round(t, 3), 'text': text, 'times': 1, 'last': round(t, 3)}
        moments.append(seen[text])
    return moments


def frame(model, study, run):
    """What the page shows of one run of a place: when its story ends, its totals, its moments and, at the
    times of its grid, the state of each system, sale and hospital and the people without normal water
    and under an advisory. `study` is the engine's study of the run (`evaluate_study`)."""
    trajectory = study.runs[run]['trajectory']
    values = study.runs[run]['resolved'].values
    horizon = trajectory.horizon
    shown = Shown(model)
    order, ties, homes, hospitals = parts(model)
    pages = Pages(model)
    events = sorted({e['t'] for e in trajectory.trace if e['t'] <= horizon})

    def people(env):
        out = sum(env[f'{h}.without_service'] for h in homes.values())
        return out, sum(env[f'{h}.under_advisory'] for h in homes.values())

    # The story ends when service, the advisories and every system's controls have settled.
    coarse = sorted({*(i * horizon / COARSE for i in range(COARSE + 1)), *events})
    envs = [trajectory.env_at(t) for t in coarse]
    story = [(t, *people(env)) for t, env in zip(coarse, envs, strict=True)]

    def after(found):
        return None if found is None else next((t for t, *_ in story if t > found), horizon)

    back = after(max((t for t, out, _ in story if out > 0.5), default=None))
    advisory_end = after(max((t for t, _, adv in story if adv > 0.5), default=None))
    settled = max(
        (
            coarse[i]
            for system in order
            for i in range(1, len(coarse))
            if envs[i][f'{system}.controls'] != envs[i - 1][f'{system}.controls']
        ),
        default=0.0,
    )
    ends = [t for t in (back, advisory_end, settled) if t is not None]
    t_end = min(horizon, max(24.0, max(ends) * 1.12))
    times = sorted(
        {0.0, t_end, *(i * t_end / GRID for i in range(GRID + 1)), *(t for t in events if t <= t_end)}
    )

    flows = {s: {k: [] for k in ('prod', 'imp', 'stored', 'del', 'adv', 'ctl', 'mode')} for s in order}
    sales = {t: [] for t in ties}
    health = {s: [] for s in order if s in hospitals}
    out_series, adv_series = [], []

    def record(t, env):
        at = round(t, 4)
        out, adv = people(env)
        out_series.append([at, round(out)])
        adv_series.append([at, round(adv)])
        for s in order:
            row = flows[s]
            row['prod'].append([at, shown(env[f'{s}.production_rate'], RATE)])
            row['imp'].append([at, shown(env[f'{s}.purchases'] + env[f'{s}.bought_used'], RATE)])
            row['stored'].append([at, shown(env[f'{s}.finished'], VOLUME)])
            row['del'].append([at, shown(env[f'{s}.delivery_rate'], RATE)])
            row['adv'].append([at, 1 if env[f'{s}.use_status'] == 'boil_water' else 0])
            row['ctl'].append([at, env[f'{s}.controls']])
            row['mode'].append([at, env[f'{s}.mode']])
            if s in hospitals:
                health[s].append([at, env[f'{hospitals[s]}.health']])
        for t_ in ties:
            sales[t_].append([at, shown(env[f'{t_}.rate'], RATE)])

    for t in times:
        record(t, trajectory.env_at(t))

    before = trajectory.env_at(0.0, side='left')
    final = sample_result(study, [t_end])['runs'][run]['reporting_points']['final']['values']

    def fixed(name_, unit):
        return shown(values[name_], unit) if unit else float(values[name_])

    return {
        'run': run,
        'name': pages.runs()[run]['name'],
        'actor': pages.texts()[run].get('attacker.actor', ''),
        't_end': round(t_end, 4),
        'horizon': horizon,
        'peak': max(o for _, o in out_series),
        'back': None if back is None else round(back, 3),
        'advisory_end': None if advisory_end is None else round(advisory_end, 3),
        'person_days': final['person_days_lost'],
        'econ': final['economic_loss'],
        'hospital': final['hospital_hours_constrained'],
        'unserved': final['unserved_volume'],
        'out': compress(out_series, False),
        'adv': compress(adv_series, False),
        'moments': moments_of(pages, run, trajectory.trace),
        'fixed': {s: fixed_of(fixed, s, [t for t, (_, b) in ties.items() if b == s]) for s in order},
        'before': {
            'flows': {
                s: {
                    'prod': shown(before[f'{s}.production_rate'], RATE),
                    'imp': shown(before[f'{s}.purchases'] + before[f'{s}.bought_used'], RATE),
                    'stored': shown(before[f'{s}.finished'], VOLUME),
                    'del': shown(before[f'{s}.delivery_rate'], RATE),
                    'adv': 1 if before[f'{s}.use_status'] == 'boil_water' else 0,
                    'ctl': before[f'{s}.controls'],
                    'mode': before[f'{s}.mode'],
                }
                for s in order
            },
            'ties': {t: shown(before[f'{t}.rate'], RATE) for t in ties},
            'hospitals': {s: before[f'{h}.health'] for s, h in hospitals.items()},
        },
        'flows': {s: {k: compress(v, k == 'stored') for k, v in row.items()} for s, row in flows.items()},
        'ties': {t: compress(v, False) for t, v in sales.items()},
        'hospitals': {s: compress(v, False) for s, v in health.items()},
    }
