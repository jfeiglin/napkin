"""A closed continuous transfer must leave enough inventory to refund its donor."""

from textwrap import dedent

import pytest

import napkin


def refund(tmp_path, name, rate, restate_at=None, *, bulk=10000000, empty=False):
    folder = tmp_path / name
    folder.mkdir()
    (folder / 'units.json').write_text('{"L":{"dimensions":{"volume":1},"scale":1}}')
    src = dedent(f"""\
        scenario "Refund"
            horizon 1 h
        plant:
            donor: L = 1 L in [0,]
            pool: L = {bulk} L in [0,]
            bulk: L = 0 L in [0,]
            paid: L = 0 L in [0,]
            pace = formula({rate})
            flow delivery: this.donor -> this.pool
                request = formula(this.pace)
            pay = event():
                after 1 h:
                    this.delivery.request = 0 L/h
                    move {bulk} L from this.pool to this.bulk
                after 0 h:
                    move (1 L - this.donor) from this.pool to this.paid
    """)
    if restate_at is not None:
        src += f'    restate = event():\n        after {restate_at} h'
        src += '\n' if empty else f':\n            this.pace = formula({rate})\n'
    path = folder / 'model.scn'
    path.write_text(src + 'plant.pay.start()\n' + ('plant.restate.start()\n' if restate_at else ''))
    model = napkin.load_scenario(path)
    record = napkin.run(model.program, model.configuration)
    values = napkin.read(record, model.program, ['plant.donor', 'plant.pool', 'plant.paid'], [1])
    observed = tuple(reading.values[0] for reading in values)
    assert record.failure is None, (record.failure, observed)
    assert observed == pytest.approx((0.95, 0.0, 0.05), rel=0, abs=1e-10)


def test_refund_the_integrated_linear_rate(tmp_path):
    refund(tmp_path, 'flat', '0.05 L/h')
    # Integral over the first hour is 0.1 / 2 = 0.05 L.
    refund(tmp_path, 'ramp', '0.1 L/h * (t / (1 h))')


def test_reinstalling_the_same_rate_leaves_the_refund_feasible(tmp_path):
    refund(tmp_path, 'unsplit', '0.05 L/h')
    refund(tmp_path, 'midpoint', '0.05 L/h', 0.5)
    refund(tmp_path, 'quarter', '0.05 L/h', 0.25)


def test_empty_inspection_cannot_make_a_refund_possible(tmp_path):
    rate = '0.1 L/h * (t / (1 h))'
    refund(tmp_path, 'observed', rate, 0.5, bulk=1000000, empty=True)
    refund(tmp_path, 'unobserved', rate, bulk=1000000)
