"""Case 8: a common sink makes its request once: main and backup carry 4 and 2."""
from ref import Endpoint, Model, N, SOURCE, flow, priority, value
from ref.model import lit
from ref.run import Run


def test_common_sink():
    m = Model()
    m.entity('clinic', fields=[value('water', 0, 0, 100, inflow=Endpoint(request=lit(6), allocation=priority(N.pipes.main, N.pipes.backup)))])
    m.entity('pipes', flows=[flow('main', SOURCE, N.clinic.water, capacity=4), flow('backup', SOURCE, N.clinic.water)])
    r = Run(m, horizon=1).run()
    assert (r.read(N.pipes.main.actual_rate, 0), r.read(N.pipes.backup.actual_rate, 0)) == (4, 2)
    assert r.read(N.clinic.water.inflow.actual_rate, 0) == 6


def test_six_on_each_pipe_is_two_claims():
    """The contrast that the spec draws: a 6 L/h request on each pipe is two separate claims."""
    m = Model()
    m.entity('clinic', fields=[value('water', 0, 0, 100)])
    m.entity('pipes', flows=[flow('main', SOURCE, N.clinic.water, capacity=4, request=6), flow('backup', SOURCE, N.clinic.water, request=6)])
    r = Run(m, horizon=1).run()
    assert (r.read(N.pipes.main.actual_rate, 0), r.read(N.pipes.backup.actual_rate, 0)) == (4, 6)
