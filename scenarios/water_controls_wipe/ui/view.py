"""The frames of the package's live view: what the page shows of a place and of one of its runs.

Every number comes from the compiled model of the place or from the engine's record of a run, and every
word from the model or its evidence. The parts of a place (its water systems, the sales between them,
their homes and their hospitals) come from the templates that make them and the links between them, so
this module keeps no list of systems. The page (`web/src/`) draws the frames; it calculates nothing."""

import json
import re
from pathlib import Path

from napkin import read
from tools import catalogue
from tools.publish.brief import brief_of

FOLDER = Path(__file__).resolve().parents[1]
PACKAGE = FOLDER.name
ROOT = FOLDER.parents[1]
COARSE = 720  # even times over the horizon that find where the story of a run ends
GRID = 360  # even times over the story, beside the times of its events
CARE_COMPARE = 'https://www.medicare.gov/care-compare/details/hospital/{ccn}'
SHOWN = (
    'person_days_lost',
    'economic_loss',
    'hospital_hours_constrained',
    'unserved_volume',
    'people_interrupted_now',
    'people_under_advisory',
)
ACTOR = 'The attack'  # the marker where the attack starts; the model has no attacker of its own
POINT = re.compile(r'point of (.+?) \(([0-9A-Z]{6})\)')
PLACEHOLDER = re.compile(r'\{(\w+)\}')


def places(root=ROOT):
    """The names of the package's places, `package:place`, in the order of the catalogue."""
    return tuple(catalogue.readers(root).get(PACKAGE, ()))


# --- The parts of a place ------------------------------------------------------------------------


def members(model, template):
    """The members that a template makes, in the order of the file."""
    return [m for m in model.declared.members if m.template == template]


def link(member, name):
    """The member that a member's link names."""
    return next((given.init for given in member.links if given.name == name), None)


def given(model, member, name):
    """A member's own value of a field, else its template's: (value, unit, evidence)."""
    for found in member.values:
        if found.name == name:
            return _const(found.init), found.evidence
    template = next((e for e in model.declared.entities if e.path == member.template), None)
    for part in template.parts if template else ():
        if getattr(part, 'name', None) == name and getattr(part, 'init', None) is not None:
            return _const(part.init), getattr(part, 'evidence', ())
    return (None, None), ()


def _const(init):
    value = getattr(init, 'value', init)
    unit = getattr(getattr(init, 'type', None), 'unit', None)
    return value, unit


def per_day(value, unit):
    """A rate in million gallons a day, from Mgal/day or Mgal/h."""
    if value is None:
        return 0.0
    return round(float(value) * (24 if unit == 'Mgal/h' else 1), 4)


def parts(model):
    """The systems with each seller before its buyers, the ties {tie: (seller, buyer)}, and the homes and
    the hospitals of each system that has them."""
    systems = [m.path for m in members(model, 'Utility')]
    ties = {t.path: (link(t, 'seller'), link(t, 'buyer')) for t in members(model, 'Tie')}
    homes = {link(h, 'utility'): h for h in members(model, 'Households')}
    hospitals = {link(h, 'utility'): h for h in members(model, 'Hospitals')}
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


def evidence(name):
    """The claims and the sources of the package's folder and of the place's folder, by ID."""
    claims, sources = {}, {}
    for folder in (FOLDER / 'evidence', catalogue.locate(name, ROOT).evidence):
        for file, into in (('claims.json', claims), ('sources.json', sources)):
            path = folder / file
            if path.exists():
                items = json.loads(path.read_text())
                into.update((item['id'], item) for item in (items if isinstance(items, list) else []))
    return claims, sources


def claimed(model, cites):
    """The claim IDs that the records of `cites` give."""
    records = {r.name: r for r in model.declared.records}
    return [c.id for cite in cites for c in getattr(records.get(cite.name), 'claims', ())]


def source_link(model, member, claims, sources):
    """The document behind a system's daily use, and its title."""
    _, cites = given(model, member, 'demand')
    for claim in claimed(model, cites):
        if claim in claims:
            source = sources.get(claims[claim].get('source'), {})
            return source.get('URL', ''), source.get('title', '')
    return '', ''


def hospital_name(text):
    """A CMS name, written as a name: 'MOSES H. CONE MEMORIAL HOSPITAL, THE' reads 'The Moses H. Cone
    Memorial Hospital'."""
    name = text.title().replace("'S ", "'s ")
    return f'The {name[:-5]}' if name.endswith(', The') else name


def hospital_list(model, member, claims):
    """The hospitals of one Hospitals member: the join claims that place each hospital in the system's
    service area, with the CMS ID (CCN) and the name that they give."""
    _, cites = given(model, member, 'facilities')
    out = []
    for claim in claimed(model, cites):
        for related in claims.get(claim, {}).get('related', ()):
            if related.get('relation') != 'reports_value' or related.get('claim') not in claims:
                continue
            found = POINT.search(claims[related['claim']].get('shows', ''))
            if found:
                ccn = found.group(2)
                out.append(
                    {'name': hospital_name(found.group(1)), 'ccn': ccn, 'href': CARE_COMPARE.format(ccn=ccn)}
                )
    return out


def status_words(model):
    """{rating: text} and [rating of each case] of the hospitals' status lines."""
    template = next((e for e in model.declared.entities if e.path == 'Hospitals'), None)
    cases = template.status.cases if template and template.status else ()
    return {case.rating: case.text for case in cases}, [case.rating for case in cases]


def labels(model):
    """The words of the shown outputs, from the model's own lines."""
    texts = {getattr(v, 'path', None): getattr(v, 'text', None) for v in model.declared.root}
    return {key: texts.get(key) or key for key in SHOWN}


def fixed_of(value, system, buys):
    """The fixed values of a system that its bars are drawn to: normal use, plant capacity, purchases
    from outside, sales to outside, usable storage and the most it can buy. `value(name)` reads one as
    (value, unit)."""
    bought = per_day(*value(f'{system}.bought'))
    usable, _ = value(f'{system}.usable_share')
    storage, _ = value(f'{system}.storage')
    return {
        'use': per_day(*value(f'{system}.demand')),
        'cap': per_day(*value(f'{system}.nameplate')),
        'bought': bought,
        'sold': per_day(*value(f'{system}.sold')),
        'full': round(float(usable or 0) * float(storage or 0), 4),
        'icap': round(sum(per_day(*value(f'{t}.capacity')) for t in buys) + bought, 4),
    }


def describe(model, name):
    """What the page shows of a place before a run: its systems with their sources, homes and hospitals,
    the sales between them, its runs and the words of its statuses and outputs. The values are the
    model's own; each frame gives those of its own run. Reading the description runs nothing."""
    scenario = model.declared.scenario
    claims, sources = evidence(name)
    order, ties, homes, hospitals = parts(model)
    by_path = {m.path: m for m in model.declared.members}

    def value(path):
        owner, field = path.rsplit('.', 1)
        return given(model, by_path[owner], field)[0]

    systems = []
    for system in order:
        member = by_path[system]
        href, title = source_link(model, member, claims, sources)
        home, hosp = homes.get(system), hospitals.get(system)
        buys = [t for t, (_, buyer) in ties.items() if buyer == system]
        people, _ = given(model, home, 'population')[0] if home else (0, None)
        facilities, _ = given(model, hosp, 'facilities')[0] if hosp else (0, None)
        systems.append(
            {
                'id': system,
                'name': member.title
                or given(model, member, 'name')[0][0]
                or system.replace('_', ' ').title(),
                'href': href,
                'tip': title,
                'people': round(float(people or 0)),
                'buys': buys,
                'sells': [t for t, (seller, _) in ties.items() if seller == system],
                'hospitals': hospital_list(model, hosp, claims) if hosp else [],
                'hospital_entity': hosp.path if hosp else '',
                'facilities': round(float(facilities or 0)),
                **fixed_of(value, system, buys),
            }
        )
    brief = brief_of(model)
    runs = [
        {'id': run.name, 'name': run.text or ' · '.join(run.options) or run.name}
        for run in model.declared.runs
        if all(
            model.declared.option(opt).group in (brief.choice_group, 'Regional support workload')
            for opt in run.options
        )
    ]
    run_names = [r['id'] for r in runs]
    featured = next((name_ for name_ in brief.featured or () if name_ in run_names), run_names[0])
    words, _ = status_words(model)
    return {
        'id': name,
        'key': name.split(':', 1)[-1],
        'name': scenario.title.rsplit(': ', 1)[-1],
        'title': scenario.title,
        'package': scenario.title.rsplit(': ', 1)[0],
        'what': scenario.summary,
        'people': sum(s['people'] for s in systems),
        'horizon': model.configuration.request.horizon,
        'model_hash': model.model_hash,
        'systems': systems,
        'ties': [
            {'id': t, 'seller': a, 'buyer': b, 'capacity': per_day(*value(f'{t}.capacity'))}
            for t, (a, b) in ties.items()
        ],
        'runs': runs,
        'featured': featured,
        'hospital_states': words,
        'outputs': labels(model),
    }


# --- A run of a place ----------------------------------------------------------------------------


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


def event_texts(model):
    """{event path: text} of the events that have one, and {event path: {case: text}} of the cases of
    an event's switch that have one."""
    texts, cases = {}, {}

    def walk(node, event):
        for case in getattr(node, 'body', ()) or ():
            if type(case).__name__ == 'DeclaredCase' and getattr(case, 'text', None):
                cases.setdefault(event, {})[case.member] = case.text
            walk(case, event)
        for case in getattr(node, 'cases', ()) or ():
            if type(case).__name__ == 'DeclaredCase' and getattr(case, 'text', None):
                cases.setdefault(event, {})[case.member] = case.text
            walk(case, event)

    for entity in model.declared.entities:
        for part in entity.parts:
            if type(part).__name__ != 'DeclaredEvent':
                continue
            if part.text:
                texts[part.path] = part.text
            for step in part.steps:
                walk(step, part.path)
    return texts, cases


def filled(text, model, owner):
    """A text with its braces filled from the member that owns the event: `{name}` reads its name."""
    member = next((m for m in model.declared.members if m.path == owner), None)
    if member is None:
        return text

    def one(found):
        value, _ = given(model, member, found.group(1))[0]
        return str(value) if value is not None else found.group(0)

    return PLACEHOLDER.sub(one, text)


def moments_of(model, record, horizon, read_at):
    """The moments of a run: each text of its story once, at its first time, with how often it happens
    and when it last does. An event's text reads when its first stage commits. The outcome of the manual
    switch of a system is the mode that the system then has."""
    texts, cases = event_texts(model)
    seen, moments = {}, []
    for entry in record.trace:
        if entry.kind != 'commit' or entry.t > horizon or not entry.part.endswith('.step[0]'):
            continue
        event = entry.part.rsplit('.step[', 1)[0]
        owner = entry.owner.split('#', 1)[0].rsplit('.', 1)[0]
        text = texts.get(event)
        if text is None and event in cases:
            mode = read_at(f'{owner}.mode', entry.t)
            controls = read_at(f'{owner}.controls', entry.t)
            outcome = 'DONE' if mode == 'MANUAL' else 'STOPPED' if controls != 'WIPED' else 'SKIPPED'
            text = cases[event].get(outcome)
        if not text:
            continue
        text = filled(text, model, owner)
        if text in seen:
            seen[text]['times'] += 1
            seen[text]['last'] = round(entry.t, 3)
            continue
        seen[text] = {'t': round(entry.t, 3), 'text': text, 'times': 1, 'last': round(entry.t, 3)}
        moments.append(seen[text])
    return moments


def before(model, order, ties, hospitals, fixed, sales):
    """The state of each system before the attack, which the record does not hold. Its controls, its mode
    and its use status are the values that the model declares at the start; its stores are full, and it
    delivers its normal use. The sales are those at the end of the story, and each system makes what its
    use and its sales need beyond what it buys, within its plant capacity."""
    by_path = {m.path: m for m in model.declared.members}

    def start(system, name):
        (value, _), _ = given(model, by_path[system], name)
        return str(value).lower()

    flows = {}
    for s in order:
        bought = fixed[s]['bought'] + sum(sales[t] for t, (_, b) in ties.items() if b == s)
        sold = fixed[s]['sold'] + sum(sales[t] for t, (a, _) in ties.items() if a == s)
        flows[s] = {
            'prod': round(min(fixed[s]['cap'], max(0.0, fixed[s]['use'] + sold - bought)), 4),
            'imp': round(bought, 4),
            'stored': fixed[s]['full'],
            'del': fixed[s]['use'],
            'adv': 1 if start(s, 'use_status') == 'boil_water' else 0,
            'ctl': start(s, 'controls'),
            'mode': start(s, 'mode'),
        }
    return {'flows': flows, 'ties': sales, 'hospitals': {s: 'ok' for s in hospitals}}


def frame(model, record, run):
    """What the page shows of one run of a place: when its story ends, its totals, its moments and, at the
    times of its grid, the state of each system, sale and hospital and the people without normal water
    and under an advisory."""
    horizon = record.manifest.horizon
    if record.stop is not None or record.end != horizon:
        return {'errors': [{'message': record.stopped() or f'Run stopped at {record.end:g} h.'}]}
    order, ties, _, hospitals = parts(model)
    _, ratings = status_words(model)
    program = model.program
    events = sorted({e.t for e in record.trace if e.kind == 'commit' and e.t <= horizon})

    def readings(paths, times):
        return {row.path: (row.unit, list(row.values)) for row in read(record, program, paths, times)}

    # The story ends when service, the advisories and every system's controls have settled.
    coarse = sorted({*(i * horizon / COARSE for i in range(COARSE + 1)), *events})
    early = readings(
        ['people_interrupted_now', 'people_under_advisory', *(f'{s}.controls' for s in order)], coarse
    )
    out_c, adv_c = early['people_interrupted_now'][1], early['people_under_advisory'][1]

    def after(found):
        return None if found is None else next((t for t in coarse if t > found), horizon)

    back = after(max((t for t, v in zip(coarse, out_c) if v > 0.5), default=None))
    advisory_end = after(max((t for t, v in zip(coarse, adv_c) if v > 0.5), default=None))
    settled = max(
        (
            coarse[i]
            for s in order
            for i in range(1, len(coarse))
            if early[f'{s}.controls'][1][i] != early[f'{s}.controls'][1][i - 1]
        ),
        default=0.0,
    )
    ends = [t for t in (back, advisory_end, settled) if t is not None]
    t_end = min(horizon, max(24.0, max(ends) * 1.12))
    times = sorted(
        {0.0, t_end, *(i * t_end / GRID for i in range(GRID + 1)), *(t for t in events if t <= t_end)}
    )

    system_paths = {
        s: {
            'prod': [f'{s}.add_produced.actual_rate'],
            'imp': [f'{s}.add_bought_in.actual_rate', f'{s}.add_purchased.actual_rate'],
            'stored': [f'{s}.finished'],
            'del': [f'{s}.add_delivered.actual_rate'],
        }
        for s in order
    }
    states = [f'{s}.{k}' for s in order for k in ('use_status', 'controls', 'mode')]
    paths = [
        'people_interrupted_now',
        'people_under_advisory',
        *(p for row in system_paths.values() for group in row.values() for p in group),
        *states,
        *(f'{t}.rate' for t in ties),
        *(f'{h.path}.status' for h in hospitals.values()),
    ]
    found = readings(paths, times)

    def number(path, i):
        unit, values = found[path]
        return per_day(values[i], unit) if unit == 'Mgal/h' else round(float(values[i]), 4)

    def rating(value):
        index = re.fullmatch(r'case\[(\d+)\]', str(value))
        return ratings[int(index.group(1))] if index and int(index.group(1)) < len(ratings) else str(value)

    flows = {s: {k: [] for k in ('prod', 'imp', 'stored', 'del', 'adv', 'ctl', 'mode')} for s in order}
    sales = {t: [] for t in ties}
    health = {s: [] for s in order if s in hospitals}
    out_series, adv_series = [], []
    for i, t in enumerate(times):
        at = round(t, 4)
        out_series.append([at, round(found['people_interrupted_now'][1][i])])
        adv_series.append([at, round(found['people_under_advisory'][1][i])])
        for s in order:
            row = flows[s]
            for key, group in system_paths[s].items():
                row[key].append([at, round(sum(number(p, i) for p in group), 4)])
            row['adv'].append([at, 1 if found[f'{s}.use_status'][1][i] == 'BOIL_WATER' else 0])
            row['ctl'].append([at, str(found[f'{s}.controls'][1][i]).lower()])
            row['mode'].append([at, str(found[f'{s}.mode'][1][i]).lower()])
            if s in hospitals:
                health[s].append([at, rating(found[f'{hospitals[s].path}.status'][1][i])])
        for t_ in ties:
            sales[t_].append([at, number(f'{t_}.rate', i)])

    final = readings(list(SHOWN[:4]), [horizon])
    first = readings(
        [
            f'{s}.{k}'
            for s in order
            for k in ('bought', 'usable_share', 'storage', 'demand', 'nameplate', 'sold')
        ]
        + [f'{t}.capacity' for t in ties],
        [0.0],
    )

    def value(path):
        unit, values = first[path]
        return values[0], unit

    fixed = {s: fixed_of(value, s, [t for t, (_, b) in ties.items() if b == s]) for s in order}

    def last(series):
        return series[-1][1] if series else 0

    return {
        'run': run,
        'name': next((r.text or ' · '.join(r.options) for r in model.declared.runs if r.name == run), run),
        'actor': ACTOR,
        't_end': round(t_end, 4),
        'horizon': horizon,
        'model_hash': model.model_hash,
        'peak': max(o for _, o in out_series),
        'back': None if back is None else round(back, 3),
        'advisory_end': None if advisory_end is None else round(advisory_end, 3),
        'person_days': final['person_days_lost'][1][0],
        'econ': final['economic_loss'][1][0],
        'hospital': final['hospital_hours_constrained'][1][0],
        'unserved': final['unserved_volume'][1][0],
        'out': compress(out_series, False),
        'adv': compress(adv_series, False),
        'moments': moments_of(
            model, record, t_end, lambda path, t: read(record, program, [path], [t])[0].values[0]
        ),
        'fixed': fixed,
        'before': before(model, order, ties, hospitals, fixed, {t: last(sales[t]) for t in ties}),
        'flows': {s: {k: compress(v, k == 'stored') for k, v in row.items()} for s, row in flows.items()},
        'ties': {t: compress(v, False) for t, v in sales.items()},
        'hospitals': {s: compress(v, False) for s, v in health.items()},
    }
