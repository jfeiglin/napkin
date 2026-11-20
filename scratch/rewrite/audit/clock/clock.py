"""What a stage at a moment reads when the clock changes a rate there: engine vs oracle."""
import sys
from napkin.engine import read, run
from napkin.model.compile import compile_text
from tests.program.examples import UNITS
from tests.reference.from_program import run_of, value_at
from tests.reference.errors import RunFailed, NotCovered
from napkin.program.record import Key

HEAD = '''scenario "Clock"
    horizon 4 h

Reading:
    input hour: h = 0 h
    input factor = 1

r0: Reading
    hour = 0 h
    factor = 1
r1: Reading
    hour = 2 h
    factor = 3

'''
CASES = {
    'branch on t': '''plant:
    water: L = 0 L in [0,]
    seen: L/h = 0 L/h
    flow fill: SOURCE -> this.water
        request = formula(1 L/h if t < 2 h else 3 L/h)
    look = event():
        after 2 h:
            this.seen = this.fill.actual_rate

plant.look.start()
''',
    'keyed by time': '''plant:
    water: L = 0 L in [0,]
    seen: L/h = 0 L/h
    flow fill: SOURCE -> this.water
        request = formula(1 L/h * Reading.instances.by(hour).at(t).factor)
    look = event():
        after 2 h:
            this.seen = this.fill.actual_rate

plant.look.start()
''',
    'branch on a store': '''plant:
    water: L = 0 L in [0,]
    seen: L/h = 0 L/h
    flow fill: SOURCE -> this.water
        request = formula(1 L/h if this.water < 2 L else 3 L/h)
    look = event():
        after 2 h:
            this.seen = this.fill.actual_rate

plant.look.start()
''',
    'bound met': '''plant:
    water: L = 0 L in [0, 2 L]
    seen: L/h = 0 L/h
    flow fill: SOURCE -> this.water
        request = 1 L/h
    look = event():
        after 2 h:
            this.seen = this.fill.actual_rate

plant.look.start()
''',
}
for name, body in CASES.items():
    if len(sys.argv) > 1 and name not in sys.argv[1:]:
        continue
    compiled = compile_text(HEAD + body, UNITS)
    program, configuration = compiled.program, compiled.configuration
    record = run(program, configuration)
    if record.failure is not None:
        engine = f'fails at {record.failure.t}: {record.failure.detail("message")[:200]}'
    else:
        (found,) = read(record, program, ['plant.seen', ], [2, 3])
        engine = f'seen at 2, 3 h = {found.values}'
    try:
        oracle_run, problem = run_of(program, configuration)
        key = Key('plant', ('seen',))
        if problem is not None:
            oracle = f'fails: {str(problem)[:160]}'
        else:
            oracle = f'seen at 2, 3 h = {[float(value_at(oracle_run, program, key, t)) for t in (2, 3)]}'
    except NotCovered as problem:
        oracle = f'not covered: {str(problem)[:160]}'
    print(f'{name}:\n  engine: {engine}\n  oracle: {oracle}')
