"""Case 13: a provider limit across two connections. 6 and 2; requests 2 and 6 give 2 and 6; East full gives 0 and 6."""
from ref import Model, N, SOURCE, flow, fmax, minimize, solver, this, value
from ref.run import Run


def build(east_request=6, west_request=6, east_energy=0):
    m = Model()
    m.entity('east_site', fields=[value('energy', east_energy, 0, 10)],
             flows=[flow('charge', SOURCE, this.energy, capacity=6, request=east_request)])
    m.entity('west_site', fields=[value('energy', 0, 0, 10)],
             flows=[flow('charge', SOURCE, this.energy, capacity=6, request=west_request)])
    m.entity('provider', fields=[value('contract_limit', 8)], solvers=[solver(
        'charging', inputs={'east': N.east_site.charge, 'west': N.west_site.charge, 'limit': this.contract_limit},
        solve_for=[N.east.actual_rate, N.west.actual_rate],
        constraints=[N.east.actual_rate + N.west.actual_rate <= N.limit],
        objective=[minimize(fmax(0, N.east.request - N.east.actual_rate)),
                   minimize(fmax(0, N.west.request - N.west.actual_rate)),
                   minimize(N.east.actual_rate + N.west.actual_rate)])])
    return m


def rates(**kw):
    r = Run(build(**kw), horizon=0).run()
    return r.read(N.east_site.charge.actual_rate), r.read(N.west_site.charge.actual_rate)


def test_east_first():
    assert rates() == (6, 2)


def test_two_and_six():
    assert rates(east_request=2) == (2, 6)


def test_east_full():
    assert rates(east_energy=10) == (0, 6)


def test_east_fills_during_run():
    r = Run(build(), horizon=3).run()
    assert r.read(N.east_site.energy, 2) == 10  # 6 W from 0 Wh: full at 5/3 h
    assert (r.read(N.east_site.charge.actual_rate, 2), r.read(N.west_site.charge.actual_rate, 2)) == (0, 6)
