"""The solver examples of the spec (`scratch/rewrite/spec.md` at af5428b), formed by hand as problems, by the
rules that the engine will apply: a flow's request is its target and its claim, a capacity is an
upper bound, a stock held at a bound gives a row on its net rate (at an empty stock the outflow can
use only the inflow), and an unmet request max(0, request - rate) is a positive part."""

import numpy as np

from napkin.engine.solve import FLOW, OTHER, Problem

INF = np.inf


def bottlenecks(objective):
    """Three consumers each request 6 W, with a + b <= 4 W and b + c <= 5 W; with `objective`,
    minimize(sum(consumers.unmet)) comes first."""
    p = Problem()
    flows = {name: p.unknown(name, 0.0, 6.0, FLOW, 6.0) for name in 'abc'}
    p.at_most('first limit', {flows['a']: 1.0, flows['b']: 1.0}, 4.0)
    p.at_most('second limit', {flows['b']: 1.0, flows['c']: 1.0}, 5.0)
    for column in flows.values():
        p.claim({column: 1.0}, 6.0)
    if objective:
        unmet = [p.positive_part(('unmet', name), {column: -1.0}, 6.0) for name, column in flows.items()]
        p.minimize(dict.fromkeys(unmet, 1.0))
    return p


def staffing(available):
    """The clinic's staff hours: care + outreach == available, outreach at least 30%, maximize care."""
    p = Problem()
    care = p.unknown('care', 0.0, available, OTHER)
    outreach = p.unknown('outreach', 0.30 * available, available, OTHER)
    p.equal('all hours', {care: 1.0, outreach: 1.0}, available)
    p.maximize({care: 1.0})
    return p


def pump(clinic=6.0, town=6.0, tank_empty=True):
    """The pump and battery: an empty battery (charge 1 W at most), the pump's 0.5 Wh per litre and
    4 L/h, an empty tank (or one with water in it), and the provider's four ranked objectives."""
    p = Problem()
    charge = p.unknown('charge', 0.0, 1.0, FLOW)  # W
    motor = p.unknown('motor', 0.0, INF, FLOW)  # W
    fill = p.unknown('fill', 0.0, 4.0, FLOW)  # L/h
    to_clinic = p.unknown('clinic', 0.0, INF, FLOW, clinic)  # L/h
    to_town = p.unknown('town', 0.0, INF, FLOW, town)
    p.at_least('battery empty', {charge: 1.0, motor: -1.0}, 0.0)
    if tank_empty:
        p.at_least('tank empty', {fill: 1.0, to_clinic: -1.0, to_town: -1.0}, 0.0)
    p.equal('power per litre', {motor: 1.0, fill: -0.5}, 0.0)
    p.claim({to_clinic: 1.0}, clinic)
    p.claim({to_town: 1.0}, town)
    p.minimize({p.positive_part('clinic unmet', {to_clinic: -1.0}, clinic): 1.0})
    p.minimize({p.positive_part('town unmet', {to_town: -1.0}, town): 1.0})
    p.minimize({fill: 1.0})
    p.minimize({charge: 1.0})
    return p


def provider(east=6.0, west=6.0, east_full=False, limit=8.0):
    """Two chargers under a contract limit of 8 W; East's battery full with no discharge makes its
    inflow at most its outflow, zero."""
    p = Problem()
    to_east = p.unknown('east', 0.0, 6.0, FLOW, east)
    to_west = p.unknown('west', 0.0, 6.0, FLOW, west)
    p.at_most('contract', {to_east: 1.0, to_west: 1.0}, limit)
    if east_full:
        p.at_most('east full', {to_east: 1.0}, 0.0)
    p.claim({to_east: 1.0}, east)
    p.claim({to_west: 1.0}, west)
    p.minimize({p.positive_part('east unmet', {to_east: -1.0}, east): 1.0})
    p.minimize({p.positive_part('west unmet', {to_west: -1.0}, west): 1.0})
    p.minimize({to_east: 1.0, to_west: 1.0})
    return p


PLACES = ('junction', 'clinic', 'garden')
ROUTES = (('junction_clinic', 'junction', 'clinic'), ('garden_junction', 'garden', 'junction'))


def network(needs=(0, 6, 6), supply=(8, 0, 0), garden_up=True, clinic_first=False, unit=1.0, order=None):
    """The worked network of the spec: three places with stocks fixed at 0 Wh, two reversible
    routes whose rate is strength * (origin level - destination level), levels in [-30, 30] with
    reference zero, `use` with the need as request and capacity, and minimize(sum(places.unmet)).
    `unit` is the size in W of the unit in which the rates are written (1000 for kW); `order`
    permutes the places and the routes, as a reordered table would."""
    places = PLACES if order is None else tuple(PLACES[i] for i in order)
    routes = ROUTES if order is None else ROUTES[::-1]
    need = dict(zip(PLACES, (value / unit for value in needs)))
    limit = dict(zip(PLACES, (value / unit for value in supply)))
    scale = 1.0 / unit  # the flows share one physical scale: one W
    p = Problem()
    level, supply_of, use = {}, {}, {}
    for place in places:
        level[place] = p.unknown(('level', place), -30.0, 30.0, OTHER)
        supply_of[place] = p.unknown(('supply', place), 0.0, limit[place], FLOW, 0.0, scale)
        use[place] = p.unknown(('use', place), 0.0, need[place], FLOW, need[place], scale)
    carried = {}
    for route, origin, destination in routes:
        carried[route] = p.unknown(('carried', route), -INF, INF, FLOW, 0.0, scale)
        pull = (1.0 if garden_up or route != 'garden_junction' else 0.0) / unit
        p.equal(
            ('rate follows levels', route),
            {carried[route]: 1.0, level[origin]: -pull, level[destination]: pull},
            0.0,
        )
    for place in places:
        terms = {supply_of[place]: 1.0, use[place]: -1.0}
        for route, origin, destination in routes:
            if origin == place:
                terms[carried[route]] = -1.0
            if destination == place:
                terms[carried[route]] = 1.0
        p.equal(('balance', place), terms, 0.0)
    unmet = {place: p.positive_part(('unmet', place), {use[place]: -1.0}, need[place]) for place in places}
    for place in places:
        p.claim({use[place]: 1.0}, need[place])
    if clinic_first:
        p.minimize({unmet['clinic']: 1.0})
    p.minimize(dict.fromkeys(unmet.values(), 1.0))
    return p


def bridge(capped):
    """Prototype A3's five-route bridge (R-A3-07): places J (supply 10), X (need 0.1), Y (need 0),
    B (need 10); routes J-X, J-Y, X-B, Y-B and the bridge X-Y, of strengths 2, 1, 1, 2 and 1, the
    bridge with capacity 0.1; minimize(sum(unmet)). With `capped`, each use is capped at its need."""
    names = ('J', 'X', 'Y', 'B')
    need = {'J': 0.0, 'X': 0.1, 'Y': 0.0, 'B': 10.0}
    routes = (('J', 'X', 2.0, 100.0), ('J', 'Y', 1.0, 100.0), ('X', 'B', 1.0, 100.0), ('Y', 'B', 2.0, 100.0))
    routes += (('X', 'Y', 1.0, 0.1),)
    p = Problem()
    level = {name: p.unknown(('level', name), -30.0, 30.0, OTHER) for name in names}
    use = {
        name: p.unknown(('use', name), 0.0, need[name] if capped else INF, FLOW, need[name]) for name in names
    }
    source = p.unknown('source', 0.0, 10.0, FLOW)
    carried = {}
    for origin, destination, strength, capacity in routes:
        key = (origin, destination)
        carried[key] = p.unknown(('carried', key), -capacity, capacity, FLOW)
        p.equal(
            ('law', key), {carried[key]: 1.0, level[origin]: -strength, level[destination]: strength}, 0.0
        )
    for name in names:
        terms = {use[name]: -1.0}
        if name == 'J':
            terms[source] = 1.0
        for (origin, destination), column in carried.items():
            if origin == name:
                terms[column] = -1.0
            if destination == name:
                terms[column] = 1.0
        p.equal(('balance', name), terms, 0.0)
        p.claim({use[name]: 1.0}, need[name])
    unmet = [p.positive_part(('unmet', name), {use[name]: -1.0}, need[name]) for name in names]
    p.minimize(dict.fromkeys(unmet, 1.0))
    return p, need


def junctions():
    """Two junctions fixed at 0 L: 1 L/h feeds the first, which sends to A and onward to the second,
    which sends to B and C; each of the four outgoing pipes requests 1 L/h; one solver, no objective."""
    p = Problem()
    feed = p.unknown('feed', 0.0, 1.0, FLOW)
    pipes = {name: p.unknown(name, 0.0, INF, FLOW, 1.0) for name in ('to_a', 'onward', 'to_b', 'to_c')}
    p.equal('first', {feed: 1.0, pipes['to_a']: -1.0, pipes['onward']: -1.0}, 0.0)
    p.equal('second', {pipes['onward']: 1.0, pipes['to_b']: -1.0, pipes['to_c']: -1.0}, 0.0)
    for column in pipes.values():
        p.claim({column: 1.0}, 1.0)
    return p


def one_pipe(cap=None):
    """One pipe whose source, pipe and sink request 10, 8 and 6 L/h: three claims on one rate."""
    p = Problem()
    pipe = p.unknown('pipe', 0.0, INF if cap is None else cap, FLOW, 8.0)
    for request in (10.0, 8.0, 6.0):
        p.claim({pipe: 1.0}, request)
    return p


def legs(labor, work, labor_limit=INF):
    """A flow with two legs as one served fraction: the legs request `labor` and `work` at full
    service, and the labor leg is limited to `labor_limit`."""
    p = Problem()
    asks = labor > 0 or work > 0
    fraction = p.unknown('served fraction', 0.0, 1.0, FLOW, 1.0 if asks else 0.0)
    p.at_most('labor limit', {fraction: labor}, labor_limit)
    if asks:
        p.claim({fraction: 1.0}, 1.0)
    return p


def band(target, kind=OTHER):
    """4 <= x + y <= 6 in the distance step."""
    p = Problem()
    x = p.unknown('x', kind=kind, target=target)
    y = p.unknown('y', kind=kind, target=target)
    p.row('band', {x: 1.0, y: 1.0}, 4.0, 6.0)
    return p


def sum_one(kind=OTHER):
    """x + y == 1 in the distance step, targets zero."""
    p = Problem()
    x = p.unknown('x', kind=kind)
    y = p.unknown('y', kind=kind)
    p.equal('one', {x: 1.0, y: 1.0}, 1.0)
    return p


def shared_limit(occurrences):
    """Occurrences that each own one pipe of request 2 L/h, under a shared limit of 3 L/h."""
    p = Problem()
    pipes = [p.unknown(('pipe', name), 0.0, INF, FLOW, 2.0) for name in occurrences]
    p.at_most('shared limit', dict.fromkeys(pipes, 1.0), 3.0)
    for column in pipes:
        p.claim({column: 1.0}, 2.0)
    return p


def reservoir(tiers):
    """A reservoir limited to 10 L/h with requests of 8 and 12 L/h, in the given priority tiers."""
    p = Problem()
    first = p.unknown('first', 0.0, INF, FLOW, 8.0)
    second = p.unknown('second', 0.0, INF, FLOW, 12.0)
    p.at_most('outflow', {first: 1.0, second: 1.0}, 10.0)
    p.claim({first: 1.0}, 8.0, tiers[0])
    p.claim({second: 1.0}, 12.0, tiers[1])
    return p
