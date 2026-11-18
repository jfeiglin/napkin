"""P2: the solver examples of the syntax proposal as ranked linear programs, with the range of each
unknown over the answers that the ranked objectives leave. A range of no width means one answer."""
import numpy as np
from scipy.optimize import linprog

INF = np.inf


def ranked(names, bounds, eq, ub, objectives, tol=1e-9):
    """eq, ub: lists of ({name: coefficient}, right side). objectives: lists of {name: coefficient}, least first."""
    n = len(names); at = {k: i for i, k in enumerate(names)}

    def row(terms):
        r = np.zeros(n)
        for k, v in terms.items():
            r[at[k]] += v
        return r

    a_eq = [row(t) for t, _ in eq]; b_eq = [b for _, b in eq]
    a_ub = [row(t) for t, _ in ub]; b_ub = [b for _, b in ub]
    for terms in objectives:
        c = row(terms)
        res = linprog(c, A_ub=a_ub or None, b_ub=b_ub or None, A_eq=a_eq or None, b_eq=b_eq or None, bounds=bounds, method='highs')
        if res.status != 0:
            return res.message
        a_ub.append(c); b_ub.append(res.fun + tol)
    out = {}
    for k in names:
        span = []
        for sign in (1, -1):
            res = linprog(sign * row({k: 1}), A_ub=a_ub or None, b_ub=b_ub or None, A_eq=a_eq or None, b_eq=b_eq or None, bounds=bounds, method='highs')
            span.append(sign * res.fun if res.status == 0 else (-INF if sign > 0 else INF))
        out[k] = tuple(round(v, 6) + 0.0 for v in span)
    return out


def show(title, result, keep):
    print(title)
    if isinstance(result, str):
        print('   ', result); return
    for k in keep:
        lo, hi = result[k]
        print(f'    {k:8s} {lo:g}' if lo == hi else f'    {k:8s} {lo:g} to {hi:g}   <- not one answer')


# Staffing: care + outreach == available; outreach >= 30% of available; maximize care.
for available in (100.0, 80.0):
    r = ranked(['care', 'outreach'], [(0, available), (0.3 * available, available)],
               [({'care': 1, 'outreach': 1}, available)], [], [{'care': -1}])
    show(f'staffing, {available:g} h', r, ['care', 'outreach'])


def pump(tank_empty, battery_empty, clinic_request=6.0, town_request=6.0):
    names = ['charge', 'motor', 'fill', 'clinic', 'town', 'short_clinic', 'short_town']
    bounds = [(0, 1), (0, INF), (0, 4), (0, INF), (0, INF), (0, INF), (0, INF)]
    eq = [({'motor': 1, 'fill': -0.5}, 0.0)]
    ub = [({'clinic': -1, 'short_clinic': -1}, -clinic_request), ({'town': -1, 'short_town': -1}, -town_request)]
    if battery_empty:   # a store on its lower bound gives out no more than comes in
        ub.append(({'motor': 1, 'charge': -1}, 0.0))
    if tank_empty:
        ub.append(({'clinic': 1, 'town': 1, 'fill': -1}, 0.0))
    objectives = [{'short_clinic': 1}, {'short_town': 1}, {'fill': 1}, {'charge': 1}]
    return ranked(names, bounds, eq, ub, objectives)


keep = ['charge', 'motor', 'fill', 'clinic', 'town']
show('pump, as written (tank and battery empty)', pump(True, True), keep)
show('pump, both requests withdrawn', pump(True, True, 0.0, 0.0), keep)
show('pump, the same model with 10 L in the tank and 2 Wh in the battery', pump(False, False), keep)
show('pump, 10 L in the tank, battery empty', pump(False, True), keep)


def provider(east_request, west_request, east_full=False):
    names = ['east', 'west', 'short_east', 'short_west']
    bounds = [(0, 0 if east_full else 6), (0, 6), (0, INF), (0, INF)]
    ub = [({'east': 1, 'west': 1}, 8.0), ({'east': -1, 'short_east': -1}, -east_request), ({'west': -1, 'short_west': -1}, -west_request)]
    return ranked(names, bounds, [], ub, [{'short_east': 1}, {'short_west': 1}, {'east': 1, 'west': 1}])


show('provider, requests 6 and 6', provider(6, 6), ['east', 'west'])
show('provider, requests 2 and 6', provider(2, 6), ['east', 'west'])
show('provider, east full', provider(6, 6, True), ['east', 'west'])

# A grid of 3 places in the proposal's form: a store [0, 0] at each place, two directed flows for each
# route, forward - backward == b * (angle difference). Source at place 0 (up to 10), needs 3 and 4 at 1 and 2.
names = ['gen', 'load1', 'load2', 'short1', 'short2'] + [f'{d}{a}{b}' for a, b in ((0, 1), (1, 2), (0, 2)) for d in 'fb'] + ['angle0', 'angle1', 'angle2']
bounds = [(0, 10), (0, INF), (0, INF), (0, INF), (0, INF)] + [(0, INF)] * 6 + [(-INF, INF)] * 3
net = lambda a, b: {f'f{a}{b}': 1, f'b{a}{b}': -1}
eq = [
    ({'gen': 1, 'f01': -1, 'b01': 1, 'f02': -1, 'b02': 1}, 0.0),
    ({'f01': 1, 'b01': -1, 'f12': -1, 'b12': 1, 'load1': -1}, 0.0),
    ({'f12': 1, 'b12': -1, 'f02': 1, 'b02': -1, 'load2': -1}, 0.0),
] + [({**net(a, b), f'angle{a}': -1.0, f'angle{b}': 1.0}, 0.0) for a, b in ((0, 1), (1, 2), (0, 2))]
ub = [({'load1': -1, 'short1': -1}, -3.0), ({'load2': -1, 'short2': -1}, -4.0)]
r = ranked(names, bounds, eq, ub, [{'short1': 1, 'short2': 1}])
show('grid of 3 places, objective: least unmet request', r, ['gen', 'load1', 'load2', 'f01', 'b01', 'f12', 'f02', 'angle0', 'angle1'])
r = ranked(names, bounds, eq, ub, [{'short1': 1, 'short2': 1}, {k: 1 for k in names if k[0] in 'fb'}, {'load1': 1, 'load2': 1}])
show('grid of 3 places, then least total flow, then least delivery', r, ['gen', 'load1', 'load2', 'f01', 'b01', 'f12', 'f02', 'angle0', 'angle1'])
