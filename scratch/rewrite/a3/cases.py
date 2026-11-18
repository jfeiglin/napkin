"""The expected answers of the brief, as assertions. Run: python cases.py  (prints one line a case)."""
import sys
import numpy as np

sys.path.insert(0, __file__.rsplit('/', 1)[0])
from solve.form import Problem, FLOW, OTHER, INTERNAL
from solve.select import Selector

INF = np.inf


class Model:
    """A small helper: named unknowns over one Problem."""

    def __init__(self):
        self.names, self.lo, self.hi, self.kind, self.target, self.scale = [], [], [], [], [], []
        self.rows, self.objectives, self.claims = [], [], []

    def var(self, name, lo=-INF, hi=INF, kind=FLOW, target=0.0, scale=1.0):
        self.names.append(name); self.lo.append(lo); self.hi.append(hi)
        self.kind.append(kind); self.target.append(target); self.scale.append(scale)
        return name

    def flow(self, name, lo=0.0, hi=INF, request=0.0, scale=1.0, tier=0):
        """A flow: target its request; a positive request makes a claim."""
        self.var(name, lo, hi, FLOW, request, scale)
        if request > 0:
            self.claims.append((name, request, tier))
        return name

    def short(self, flow, request):
        """The positive-part shortfall max(0, request - flow) as an internal unknown."""
        s = self.var(f'short_{flow}', 0.0, INF, INTERNAL)
        self.rows.append(({flow: 1.0, s: 1.0}, request, INF))
        return s

    def row(self, terms, lo=-INF, hi=INF):
        self.rows.append((terms, lo, hi))

    def minimize(self, terms):
        self.objectives.append(terms)

    def problem(self):
        at = {k: i for i, k in enumerate(self.names)}
        p = Problem(self.lo, self.hi, self.scale, self.target, self.kind)
        for terms, lo, hi in self.rows:
            p.row({at[k]: v for k, v in terms.items()}, lo, hi)
        for terms in self.objectives:
            p.minimize({at[k]: v for k, v in terms.items()})
        for name, q, tier in self.claims:
            p.claim(at[name], q, tier)
        return p

    def solve(self, **kw):
        answer = Selector(self.problem(), **kw).solve()
        return {k: answer.x[i] for i, k in enumerate(self.names)}


def close(got, want, tol=1e-6):
    for k, v in want.items():
        assert abs(got[k] - v) <= tol * max(1.0, abs(v)), f'{k}: {got[k]} against {v}'


def staffing(available):
    m = Model()
    care = m.var('care', 0.0, available, OTHER)
    outreach = m.var('outreach', 0.30 * available, available, OTHER)
    m.row({care: 1, outreach: 1}, available, available)
    m.minimize({care: -1.0})
    return m


def provider(east_request, west_request, limit=8.0):
    m = Model()
    e = m.flow('east', 0.0, 6.0, east_request)
    w = m.flow('west', 0.0, 6.0, west_request)
    m.row({e: 1, w: 1}, hi=limit)
    se, sw = m.short(e, east_request), m.short(w, west_request)
    m.minimize({se: 1}); m.minimize({sw: 1}); m.minimize({e: 1, w: 1})
    return m


def pump(clinic_request=6.0, town_request=6.0):
    """Empty tank and empty battery: at a stock on its lower bound, inflow >= outflow."""
    m = Model()
    charge = m.flow('charge', 0.0, 1.0)                  # W
    motor = m.flow('motor', 0.0, INF)                    # W
    fill = m.flow('fill', 0.0, 4.0)                      # L/h
    clinic = m.flow('clinic', 0.0, INF, clinic_request)  # L/h
    town = m.flow('town', 0.0, INF, town_request)
    m.row({charge: 1, motor: -1}, lo=0.0)                # battery empty
    m.row({fill: 1, clinic: -1, town: -1}, lo=0.0)       # tank empty
    m.row({motor: 1, fill: -0.5}, 0.0, 0.0)              # 0.5 Wh/L
    sc, st = m.short(clinic, clinic_request), m.short(town, town_request)
    m.minimize({sc: 1}); m.minimize({st: 1}); m.minimize({fill: 1}); m.minimize({charge: 1})
    return m


def bottlenecks(objective):
    m = Model()
    a, b, c = (m.flow(k, 0.0, 6.0, 6.0) for k in 'abc')
    m.row({a: 1, b: 1}, hi=4.0)
    m.row({b: 1, c: 1}, hi=5.0)
    if objective:
        s = [m.short(f, 6.0) for f in 'abc']
        m.minimize({k: 1.0 for k in s})
    return m


def worked(needs=(0.0, 6.0, 6.0), supply=(8.0, 0.0, 0.0), garden_up=True, clinic_first=False, unit=1.0):
    """The worked network: places junction, clinic, garden; routes junction->clinic, garden->junction.
    `unit` is the size of the written unit in W (1e3 for kW): every rate and strength is written in it."""
    m = Model()
    P = ['junction', 'clinic', 'garden']
    for p, q, cap in zip(P, needs, supply):
        m.var(f'level_{p}', -30.0, 30.0, OTHER)
        m.flow(f'supply_{p}', 0.0, cap / unit, scale=1.0 / unit)
        m.flow(f'use_{p}', 0.0, INF, q / unit, scale=1.0 / unit)
    routes = [('junction', 'clinic', 1.0), ('garden', 'junction', 1.0 if garden_up else 0.0)]
    for o, d, pull in routes:
        r = f'carried_{o}_{d}'
        m.flow(r, -INF, INF, scale=1.0 / unit)
        m.row({r: 1.0, f'level_{o}': -pull / unit, f'level_{d}': pull / unit}, 0.0, 0.0)
    for p in P:
        terms = {f'supply_{p}': 1.0, f'use_{p}': -1.0}
        for o, d, _ in routes:
            if o == p:
                terms[f'carried_{o}_{d}'] = -1.0
            if d == p:
                terms[f'carried_{o}_{d}'] = 1.0
        m.row(terms, 0.0, 0.0)
    shorts = {p: m.short(f'use_{p}', q / unit) for p, q in zip(P, needs)}
    if clinic_first:
        m.minimize({shorts['clinic']: 1.0})
    m.minimize({s: 1.0 for s in shorts.values()})
    return m


def membership():
    """Risk 3 on one kept instance: occurrences join and leave a 3 L/h limit, 2 L/h each."""
    from solve.form import Problem

    def moment(k):
        p = Problem(np.zeros(k), np.full(k, INF), target=np.full(k, 2.0))
        if k:
            p.row({j: 1.0 for j in range(k)}, -INF, 3.0)
            for j in range(k):
                p.claim(j, 2.0)
        else:
            p.row({}, -INF, 3.0)
        return p

    out = []
    sel = Selector(moment(1))
    out.append(sel.solve().x)                         # A
    sel.replace(moment(2), joined=1)
    out.append(sel.solve().x)                         # A and B
    sel.replace(moment(1), gone=[0])
    out.append(sel.solve().x)                         # B alone
    sel.replace(moment(0), gone=[0])
    out.append(sel.solve().x)                         # nobody
    fresh = [Selector(moment(k)).solve().x for k in (1, 2, 1, 0)]
    return out, fresh


def main():
    rows = []

    def ok(name, got):
        rows.append(name)
        print(f'ok  {name}: ' + ', '.join(f'{k}={v:.6g}' for k, v in got.items()))

    x = staffing(100.0).solve(); close(x, dict(care=70, outreach=30)); ok('staffing 100 h', x)
    x = staffing(80.0).solve(); close(x, dict(care=56, outreach=24)); ok('staffing 80 h', x)
    x = provider(6.0, 6.0).solve(); close(x, dict(east=6, west=2)); ok('provider 6 and 6', x)
    x = provider(2.0, 6.0).solve(); close(x, dict(east=2, west=6)); ok('provider 2 and 6', x)
    x = pump().solve(); close(x, dict(fill=2, clinic=2, town=0, motor=1, charge=1)); ok('pump', x)
    x = pump(0.0, 0.0).solve(); close(x, dict(fill=0, clinic=0, town=0, motor=0, charge=0)); ok('pump, no request', x)
    x = bottlenecks(False).solve(); close(x, dict(a=2, b=2, c=3)); ok('two bottlenecks, fair', x)
    x = bottlenecks(True).solve(); close(x, dict(a=4, b=0, c=5)); ok('two bottlenecks, objective first', x)
    for method in ('pin', 'row'):
        x = bottlenecks(True).solve(method=method); close(x, dict(a=4, b=0, c=5))
        x = provider(6.0, 6.0).solve(method=method); close(x, dict(east=6, west=2))
        x = pump().solve(method=method); close(x, dict(fill=2, clinic=2, town=0))
    rows.append('row method: the same three answers'); print('ok  row method gives the same answers')
    # the worked network
    x = worked().solve()
    close(x, dict(use_clinic=4, use_garden=4, supply_junction=8, carried_junction_clinic=4, carried_garden_junction=-4,
                  level_junction=8 / 3, level_clinic=-4 / 3, level_garden=-4 / 3)); ok('worked 0 h', x)
    x = worked(clinic_first=True).solve()
    close(x, dict(use_clinic=6, use_garden=2, carried_junction_clinic=6, carried_garden_junction=-2)); ok('worked clinic first', x)
    x = worked(needs=(0, 3, 3)).solve()
    close(x, dict(use_clinic=3, use_garden=3, supply_junction=6, carried_junction_clinic=3, carried_garden_junction=-3)); ok('worked 1 h', x)
    x = worked(garden_up=False).solve()
    close(x, dict(use_clinic=6, use_garden=0, supply_junction=6, carried_junction_clinic=6, carried_garden_junction=0,
                  level_junction=3, level_clinic=-3, level_garden=0)); ok('worked 2 h, garden route down', x)
    x = worked(needs=(0, 2, 6), supply=(4, 0, 0)).solve()
    close(x, dict(use_clinic=1, use_garden=3)); ok('worked, unequal claims', x)
    x = worked(unit=1e3).solve()
    close(x, dict(use_clinic=0.004, use_garden=0.004, level_junction=8 / 3), tol=1e-9); ok('worked in kW', x)
    out, fresh = membership()
    want = [[2.0], [1.5, 1.5], [2.0], []]
    for got, f, w in zip(out, fresh, want):
        assert np.allclose(got, w, atol=1e-7) and np.allclose(f, w, atol=1e-7), (got, f, w)
    rows.append('membership'); print('ok  membership on one kept instance: 2; 1.5 and 1.5; 2; nothing (= fresh each time)')
    print(f'{len(rows)} cases pass')


if __name__ == '__main__':
    main()
