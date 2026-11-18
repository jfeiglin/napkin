"""Case 6: a junction carries 8 W through a store held at 0 Wh."""
from ref import Model, N, SINK, SOURCE, flow, this, value
from ref.run import Run


def test_junction():
    m = Model()
    m.entity('junction', fields=[value('power', 0, 0, 0)],
             flows=[flow('supply', SOURCE, this.power, capacity=8), flow('use', this.power, SINK, request=8)])
    r = Run(m, horizon=1).run()
    assert r.read(N.junction.supply.actual_rate, 0) == 8
    assert r.read(N.junction.use.actual_rate, 0) == 8
    assert r.read(N.junction.power, 1) == 0
    c = r.conservation()
    assert c['from_source'] == 8 and c['to_sink'] == 8 and c['balanced']
