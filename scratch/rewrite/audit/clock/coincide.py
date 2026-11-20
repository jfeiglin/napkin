from napkin.engine import read, run
from napkin.model.compile import compile_text
from tests.program.examples import UNITS

def text(stage, body):
    return f'''scenario "Clock"
    horizon 4 h

plant:
    water: L = 0 L in [0,]
    seen: L/h = 0 L/h
    flow fill: SOURCE -> this.water
        request = formula({body})
    look = event():
        after {stage}:
            this.seen = 7 L/h

plant.look.start()
'''
for stage, body in (('2 h', '1 L/h if this.water < 2 L else 3 L/h'), ('2 h', '3 L/h if this.water >= 2 L else 1 L/h'),
                    ('2 h', '1 L/h if t < 2 h else 3 L/h'), ('1 h', '1 L/h if this.water < 1 L else 3 L/h'),
                    ('2 h', '1 L/h if this.water < 2 L else 0.5 L/h')):
    compiled = compile_text(text(stage, body), UNITS)
    record = run(compiled.program, compiled.configuration)
    if record.failure is not None:
        print(stage, body, '-> fails at', record.failure.t, record.failure.detail('message')[:90])
    else:
        (w,) = read(record, compiled.program, ['plant.water'], [1, 2, 3, 4])
        print(stage, body, '-> water', [round(v, 9) for v in w.values])
