"""Case 10: two bottlenecks. Fair sharing gives (2, 2, 3) with 11 W unmet; minimize(sum(unmet)) first gives (4, 0, 5), 9 W."""
from ref import Model, N, SINK, SOURCE, calc, flow, fmax, fsum, minimize, solver, this
from ref.run import Run


def build(objective):
    m = Model()
    m.template('Consumer', fields=[calc('unmet', fmax(0, this.use.request - this.use.actual_rate))],
               flows=[flow('use', SOURCE, SINK, capacity=6, request=6)])
    for name in 'abc':
        m.instance(name, 'Consumer')
    m.entity('provider', solvers=[solver(
        'share', inputs={'consumers': N.Consumer.instances, 'a': N.a.use, 'b': N.b.use, 'c': N.c.use},
        solve_for=[N.consumers.use.actual_rate],
        constraints=[N.a.actual_rate + N.b.actual_rate <= 4, N.b.actual_rate + N.c.actual_rate <= 5],
        objective=[minimize(fsum(N.consumers.unmet))] if objective else [])])
    return m


def result(objective):
    r = Run(build(objective), horizon=0).run()
    return tuple(r.read(x.use.actual_rate) for x in (N.a, N.b, N.c)), r.read(fsum(N.Consumer.instances.unmet))


def test_fair_sharing():
    assert result(False) == ((2, 2, 3), 11)


def test_total_shortfall_first():
    assert result(True) == ((4, 0, 5), 9)
