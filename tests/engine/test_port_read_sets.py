"""A keyed, filtered row supplies one live occurrence's flow until that occurrence retires."""

from dataclasses import replace
from random import Random

import pytest

from napkin.engine.report import report
from napkin.engine.timeline import Plan, Run
from napkin.engine.timeline.record import Reader, key_of
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, Checkpoint
from napkin.program.proofs import reads

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
ROOT = 'plant.live'


def model_of(seed):
    rng = Random(seed)
    ids = ('first', 'middle', 'last')
    offers = dict(zip(ids, rng.sample(range(1, 12), 3), strict=True))
    numbers = dict(zip(ids, sorted(rng.sample(range(1, 12), 3)), strict=True))
    # The lookup time can change. A third, filtered-out row's payload is a negative control.
    active = {'first': True, 'middle': True, 'last': False}
    lines = [
        'scenario "Read sets"',
        '    horizon 2 h',
        'Row:',
        '    input rank = 0',
        '    input eligible = true',
        '    offer: L/h = 1 L/h',
    ]
    tags = {}
    for name in ids:
        lines.append(f'{name}: Row')
        for field, value in [
            ('rank', numbers[name]),
            ('eligible', str(active[name]).lower()),
            ('offer', f'{offers[name]} L/h'),
        ]:
            tag = f'{name}_{field}'
            lines.append(f'    {field} = {value} @{tag}')
            tags[f'{name}.{field}'] = tag
    tags['plant.pick'] = 'selector'
    lines.extend(
        [
            'plant:',
            f'    pick = {numbers["first"]} @selector',
            '    pool: L = 100 L',
            '    job = event():',
            '        flow pipe: this.pool -> SINK',
            '            request = formula(Row.instances.where(eligible).by(rank).at(this.pick).offer)',
            '        after 1.5 h',
            '    change = event():',
            '        after 1 h:',
            f'            this.pick = {numbers["middle"]}',
            '    live = formula(sum(this.pool.outflow.flows.request))',
            'plant.job.start()',
            'plant.change.start()',
        ]
    )
    lines.extend(f'record {tag}: source "Measured {tag}."' for tag in tags.values())
    return compile_text('\n'.join(lines) + '\n', UNITS), offers, tags


class ObservedReader(Reader):
    """Observe successful physical reads below the reader's dependency/evidence bookkeeping."""

    def __init__(self, record, program):
        super().__init__(record, program)
        self.consulted = set()

    def _known(self, name, t):
        number = super()._known(name, t)
        self.consulted.add(name)
        return number


@pytest.mark.parametrize('seed', range(8))
def test_observed_fields_are_planned_retained_and_credited(seed):
    compiled, offers, tags = model_of(seed)
    program = compiled.program
    cfg = replace(
        compiled.configuration,
        request=replace(compiled.configuration.request, everything=False, keys=(key_of(program, ROOT),)),
    )
    machine = Run(Plan.of(program, cfg), (Breakpoint('plant.change.step[0]'),))
    stopped = machine.run()
    assert isinstance(stopped, Checkpoint), stopped
    pipe = 'plant.job#0.pipe'
    (planned,) = [connected.reads for connected, _ in machine.ways.sets.values() if pipe in connected.flows]
    record = machine.resume()
    assert record.failure is None, record.failure
    reading = reads(program, cfg, key_of(program, ROOT))
    times = [(1.25, 'middle'), (1.75, None), (0.5, 'first')]
    for at, selected in times if seed % 2 else reversed(times):
        reader = ObservedReader(record, program)
        number = reader.at(ROOT, at)
        assert number == (offers[selected] if selected else 0), (seed, at, number)
        leaves = reader.consulted & tags.keys()
        assert leaves <= planned, (seed, at, 'planner', leaves - planned)
        assert all(machine.recorder.wanted(n) for n in leaves), (seed, at, 'recorder', leaves)
        # The proof admits both rows; the evidence at an instant distinguishes the selected one.
        proof_names = {f'{part.owner}.{part.origin.rsplit(".", 1)[-1]}' for part in reading.edges}
        assert leaves <= proof_names, (seed, at, 'proof', leaves - proof_names)
        used = set()
        (row,) = report(record, program, cfg, [ROOT], [at], model=compiled.declared).values
        for entry in row.trail:
            if entry.exercised:
                used.update(entry.records)
        assert used == {tags[name] for name in leaves}, (seed, at, leaves, used)
        expected = (
            {
                'first.eligible',
                'middle.eligible',
                'last.eligible',
                'first.rank',
                'middle.rank',
                'plant.pick',
                f'{selected}.offer',
            }
            if selected
            else set()
        )
        assert leaves == expected, (seed, at, 'actual reads', leaves, expected)
