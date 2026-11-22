"""An occurrence read belongs to the recorded invocation that captured its target."""

import json
import subprocess
import sys
from random import Random

from napkin.engine import read, run
from napkin.model.compile import compile_text
from napkin.program.artifact import loads
from napkin.program.checkpoint import decode, encode
from napkin.program.config import Configuration, InputValue, Quantity, Request
from napkin.program.record import Key, Unavailable

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
OWNER = 'yard.capture#0'
KEYS = tuple(Key(OWNER, (name,)) for name in ('observed', 'origin', 'started'))


def _case(seed):
    if seed:
        rng = Random(seed)
        first, second = rng.sample(range(1, 300), 2)
        early = rng.randint(1, 6) / 8
        gap = early + rng.randint(1, 7) / 8
        late = gap + rng.randint(1, 6) / 8
        horizon = late + rng.randint(1, 6) / 8
    else:
        first, second, early, gap, late, horizon = 2, 9, 0.25, 1, 1.25, 3
    source = f"""scenario "Read the occurrence captured by this run"
    horizon {horizon} h
yard:
    input delay: h = {early} h
    measure = event(amount: L):
        after {horizon + 1} h
    capture = event():
        job = this.measure.occurrences.at(t)
        observed = formula(job.amount)
        origin = formula(job.started)
        after {horizon + 1} h
    load = event():
        after {gap} h:
            this.measure.start({second} L)
    launch = event():
        after this.delay:
            this.capture.start()
yard.measure.start({first} L)
"""
    starts = ('yard.load.start()', 'yard.launch.start()')
    source += '\n'.join(starts[::-1] if seed % 2 else starts) + '\n'
    times = [0, (early + gap) / 2, (late + horizon) / 2, horizon]
    # A captures the first measurement before the next one starts; B captures the second.
    expected = {'A': (first, 0, early), 'B': (second, gap, late)}
    return source, times, expected


def _reads(record, program, times):
    rows = {}
    for key in KEYS:
        try:
            (row,) = read(record, program, [key], times)
        except Exception as error:
            rows[key.steps[0]] = f'{type(error).__name__}: {error}'
            continue
        found = []
        for value in row.values:
            if isinstance(value, Unavailable):
                # An absent dependency in a selective record has a different cause.
                found.append(None if value.reason.startswith(f'{OWNER} has not started') else value.reason)
            else:
                found.append(value)
        rows[key.steps[0]] = found
    return rows


def _expect(errors, label, record, program, times, expected):
    for direction, query in (('forward', times), ('backward', times[::-1])):
        rows = _reads(record, program, query)
        for key, value in zip(KEYS, expected, strict=True):
            hand = [value if at >= expected[2] else None for at in query]
            field = key.steps[0]
            if rows[field] != hand:
                errors[f'{label}/{direction}/{field}'] = {'expected': hand, 'observed': rows[field]}


def _fresh_read(payload):
    """One reopened artifact, two decoded records, and no preceding simulation in this reader."""
    program = loads(payload['program'].encode()).program
    records = {label: decode(saved) for label, saved in payload['records'].items()}
    errors = {}
    for i, occurrence in enumerate(payload['order']):
        _expect(
            errors,
            f'fresh/{i}-{occurrence}',
            records[occurrence],
            program,
            payload['times'],
            payload['expected'][occurrence],
        )
    return errors


_CHILD = """import json, sys
from tests.engine.record_identity_cases import _fresh_read
print(json.dumps(_fresh_read(json.load(sys.stdin))))
"""


def check_record_identity(seed):
    source, times, expected = _case(seed)
    errors = {}
    for everything in (True, False):
        mode = 'full' if everything else 'selective'
        for order in ('AB', 'BA'):
            # Both runs of this pair share precisely the same program object.
            model = compile_text(source, UNITS)
            records = {}
            for label in order:
                key = f'{mode}/{order}/after-{label}'
                request = Request(times[-1], everything=everything, keys=() if everything else KEYS)
                inputs = (InputValue('yard', 'delay', Quantity(expected[label][2], 'h')),)
                try:
                    record = run(model.program, Configuration(request, inputs))
                    if record.failure:
                        raise ValueError(record.failure)
                    records[label] = record
                except Exception as error:
                    errors[key + '/run'] = f'{type(error).__name__}: {error}'
                    continue
                # The newest record, then each prior record, then the newest one again.
                sequence = (label, order[0], label) if len(records) == 2 else (label,)
                for i, which in enumerate(sequence):
                    _expect(
                        errors,
                        f'{key}/read-{which}-{i}',
                        records[which],
                        model.program,
                        times,
                        expected[which],
                    )
            if len(records) == 2:
                payload = {
                    'program': model.artifact().data().decode(),
                    'records': {label: encode(record) for label, record in records.items()},
                    'order': order + order[0],
                    'times': times,
                    'expected': expected,
                }
                try:
                    if seed == 0:
                        done = subprocess.run(
                            [sys.executable, '-B', '-c', _CHILD],
                            input=json.dumps(payload),
                            text=True,
                            capture_output=True,
                            timeout=30,
                            check=True,
                        )
                        reopened = json.loads(done.stdout)
                    else:
                        reopened = _fresh_read(payload)
                except subprocess.CalledProcessError as error:
                    reopened = {'reader': error.stderr}
                except Exception as error:
                    reopened = {'reader': f'{type(error).__name__}: {error}'}
                errors.update({f'{mode}/{order}/{key}': value for key, value in reopened.items()})
    assert not errors, (
        seed,
        'record-identity',
        {'source': source, 'times': times, 'runs': expected, 'reads': errors},
    )
