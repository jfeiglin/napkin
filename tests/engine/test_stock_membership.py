"""Stock ledgers follow their declaration roles through setup, occurrence entry and checkpoint replay."""

from dataclasses import replace
from fractions import Fraction

import pytest

from napkin.commands.run import Offered
from napkin.engine.timeline import Plan, Run, read
from napkin.model.compile import compile_text
from napkin.program import artifact
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from napkin.program.record import Unavailable
from tests.engine.resume_parity import assert_resume_parity

UNITS = {'L': {'volume': 1}, 'h': {'time': 1}}


def test_a_dormant_move_declares_its_endpoints_but_assignments_and_settings_do_not():
    model = compile_text(
        """scenario "Inventory adjustment"
    horizon 2 h
Tank:
    volume: L = 1 L
    ordinary: L = 10000000000000000 L
    configured: L = 3 L
        inflow.capacity = 1 L/h
north: Tank
south: Tank
yard:
    ready = true
    ticks = 0
    receipt: L = 0 L
    transfer = event():
        after 1 h:
            move 1 L from north.volume to this.receipt
    adjust = event():
        after 1 h:
            if this.ready:
                north.volume = 4 L
                this.ticks += 1
                north.ordinary += 1 L
                north.ordinary = north.ordinary - 10000000000000000 L
yard.adjust.start()
""",
        UNITS,
    )
    machine = Run(Plan.of(model.program, model.configuration), (Breakpoint('yard.adjust.step[0]'),))
    paused = machine.run()
    assert isinstance(paused, Checkpoint)
    final = machine.resume()
    assert read(final, model.program, ['north.ordinary'], [1])[0].values == (0,)
    for record in (paused.record, final):
        assert record.failure is None
        assert read(record, model.program, ['north.volume.external'], [0])[0].values == (0,)
        offered = Offered(record, model.program)
        assert 'north.volume.external' in offered.held
        for path in (
            'south.volume.external',
            'north.ordinary.external',
            'north.configured.external',
            'yard.ready.external',
            'yard.ticks.external',
        ):
            with pytest.raises(KeyError):
                read(record, model.program, [path], [0])
            assert path not in offered.held and offered.refused(path) is not None


def test_occurrence_stock_ledgers_follow_the_concrete_start_in_a_reloaded_program():
    model = compile_text(
        """scenario "Temporary stock"
    horizon 4 h
yard:
    receipt: L = 0 L
    pour = event():
        batch: L = 1 L
        reserve: L = 0 L
        ordinary = 7
        flow pipe: SOURCE -> batch
            request = 0 L/h
        after 1 h:
            move batch from batch to this.receipt
    spare = event():
        job = this.pour.occurrences.at(t)
        after 1 h:
            move 1 L from job.reserve to this.receipt
    launch = event():
        after 1 h:
            this.pour.start()
        after 2 h:
            this.pour.start()
yard.launch.start()
""",
        UNITS,
    )
    record = Run(Plan.of(model.program, model.configuration)).run()
    assert record.failure is None, record.failure
    program = artifact.loads(model.artifact().data()).program
    offered = Offered(record, program)
    for index, birth in enumerate((1, 3)):
        owner = f'yard.pour#{index}'
        path = f'{owner}.batch.external'
        before, opening, finish = read(record, program, [path], [birth - 0.5, birth, birth + 1])[0].values
        assert isinstance(before, Unavailable) and 'has not started' in before.reason
        assert opening == finish == 0
        assert path in offered.held and offered.refused(path) is None
        assert read(record, program, [f'{owner}.reserve.external'], [birth])[0].values == (0,)
        assert offered.refused(f'{owner}.ordinary.external') is not None
    assert read(record, program, ['yard.receipt'], [4])[0].values == (2,)


def test_potential_pipes_follow_parameter_links_and_unitless_move_endpoints_have_ledgers():
    model = compile_text(
        """scenario "Potential inventory"
    horizon 1 h
Tank:
    water: L = 0 L
north: Tank
south: Tank
Port:
    recipient: Tank
gate: Port
    recipient = north
yard:
    credits = 4
    spent = 0
    delivery = event(port: Port):
        flow pipe: SOURCE -> port.recipient.water
            request = 0 L/h
        after 1 h:
            move 1 from this.credits to this.spent
""",
        UNITS,
    )
    record = Run(Plan.of(model.program, model.configuration)).run()
    assert record.failure is None and not record.entries('start')
    paths = ['north.water.external', 'yard.credits.external', 'yard.spent.external']
    assert [row.values for row in read(record, model.program, paths, [0, 1])] == [(0, 0)] * 3
    with pytest.raises(KeyError, match=r'south\.water is no store'):
        read(record, model.program, ['south.water.external'], [0])


def test_editing_an_assignment_only_occurrence_slot_preserves_ordinary_finish():
    model = compile_text(
        """scenario "Occurrence edit"
    horizon 2 h
yard:
    visit = event():
        remembered: L = 3 L
        after 1 h:
            remembered += 1 L
yard.visit.start()
""",
        UNITS,
    )
    live = Run(Plan.of(model.program, model.configuration), (Breakpoint('yard.visit.step[0]'),))
    assert isinstance(live.run(), Checkpoint)
    edited = live.edit('yard.visit#0.remembered', 5)
    replay = Run.restored(Plan.of(model.program, model.configuration), loads(dumps(edited)))
    for machine in (live, replay):
        record = machine.resume()
        assert record.failure is None and len(record.entries('finish')) == 1
        assert read(record, model.program, ['yard.visit#0.remembered'], [2])[0].values == (6,)
        with pytest.raises(KeyError, match='is no store'):
            read(record, model.program, ['yard.visit#0.remembered.external'], [2])


def test_loading_a_checkpoint_from_before_the_first_move_recovers_the_literal_opening():
    model = compile_text(
        """scenario "Legacy inventory"
    horizon 1 h
yard:
    tank: L = 10000000.0000000003 L
    receipt: L = 0 L
    adjust = event():
        after 1 h:
            move 10000000 L from this.tank to this.receipt
yard.adjust.start()
""",
        UNITS,
    )
    live = Run(Plan.of(model.program, model.configuration), (Breakpoint('yard.adjust.step[0]'),))
    paused = live.run()
    assert isinstance(paused, Checkpoint)
    saved = dict(paused.saved)
    state = dict(saved['run'])
    state.pop('stock_ranges')
    state['stocks'] = ()  # earlier checkpoints left these unposted until the first move
    saved['run'] = tuple(state.items())
    legacy = loads(dumps(replace(paused, saved=tuple(saved.items()))))
    restored = Run.restored(Plan.of(model.program, model.configuration), legacy)
    assert_resume_parity(model.program, model.configuration, live.resume(), restored.resume())
    assert restored.stock_balance('yard.tank', 1) == Fraction(3, 10**10)
