"""A stage can redefine a formula before any of its readers execute."""

from random import Random

from napkin.engine.timeline import Plan, Run, read
from napkin.model.compile import compile_text
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.reference.from_program import run_of, values_at


def scalar_stage_model(seed):
    """The source and independent expected readings for one deterministic family member."""
    rng = Random(seed)
    if seed == 0:
        old, new, threshold = 0, 2, 1
        old_floor, new_floor = 'narrow', 'wide'
        target = new
    else:
        lo = rng.randrange(12)
        threshold = lo + rng.randint(1, 4)
        hi = threshold + rng.randint(1, 4)
        old, new = (hi, lo) if rng.getrandbits(1) else (lo, hi)
        old_floor, new_floor = ('wide', 'narrow') if rng.getrandbits(1) else ('narrow', 'wide')
        target = old if rng.getrandbits(1) else new

    source = f"""box:
    a = formula({old})
    half = formula({old}.5)
    nested = formula(this.a > {threshold})
    narrow: number = 0.000001 scale 1
    wide: number = 0.000001 scale 10000
    probe = formula(this.{old_floor})
    direct: number = -1
    greater: bool = false
    equal: bool = false
    member: bool = false
    choice: number = -1
    guarded: number = -1
    selected: number = -1
    indirect: bool = false
    difference: number = -1
    within_floor: bool = false
    stock: L = 32 L
    moved: L = 0 L
    captured: L = 0 L
    remember = event(amount: L):
        after 0 h:
            this.captured = amount
    change = event():
        after 1 h:
            this.a = formula({new})
            this.half = formula({new}.5)
            this.probe = formula(this.{new_floor})
            this.direct = this.a
            this.greater = this.a > {threshold}
            this.equal = this.a == {target}
            this.member = (this.a in [{target}, {target}])
            this.choice = 7 if this.a > {threshold} else 3
            if this.a > {threshold}:
                this.guarded = 7
            else:
                this.guarded = 3
            switch categorical(PICK: 2, PASS: 1).draw():
                PICK when this.a > {threshold}:
                    this.selected = 7
                PASS:
                    this.selected = 3
            this.indirect = this.nested
            this.difference = this.half - {threshold}
            this.within_floor = this.probe == 0
            move (7 L if this.a > {threshold} else 3 L) from this.stock to this.moved
            this.remember.start(7 L if this.a > {threshold} else 3 L)
box.change.start()
"""
    qualifies = new > threshold
    chosen = 7 if qualifies else 3
    return source, {
        'direct': new,
        'greater': qualifies,
        'equal': new == target,
        'member': new == target,
        'choice': chosen,
        'guarded': chosen,
        'selected': chosen,
        'indirect': qualifies,
        'difference': new + 0.5 - threshold,
        'within_floor': new_floor == 'wide',
        'stock': 32 - chosen,
        'moved': chosen,
        'captured': chosen,
    }


def scalar_stage_observations(seed):
    """Read each result after commit; retain reference discrepancies separately."""
    source, expected = scalar_stage_model(seed)
    program = compile_text(source, {'h': {'time': 1}, 'L': {'volume': 1}}).program
    config = Configuration(Request(2))
    keys = [Key('box', (name,)) for name in expected]
    oracle, failed = run_of(program, config)
    assert failed is None, (seed, 'reference', failed)
    oracle_rows = values_at(oracle, program, keys, [2])
    differences = {
        key.steps[0]: (oracle_rows[key][0], expected[key.steps[0]])
        for key in keys
        if oracle_rows[key][0] != expected[key.steps[0]]
    }
    assert not differences, (seed, 'reference', differences)
    record = Run(Plan.of(program, config)).run()
    assert record.failure is None, (seed, 'engine', record.failure)
    rows = read(record, program, keys, [2])
    return expected, {name: row.values[0] for name, row in zip(expected, rows, strict=True)}


def check_scalar_stage(seed):
    expected, actual = scalar_stage_observations(seed)
    differences = {name: (actual[name], value) for name, value in expected.items() if actual[name] != value}
    assert not differences, (seed, 'stage reads', differences)
