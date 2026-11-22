"""Integrate a short triangular excess above a rising stock and check its saved history."""

from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
from itertools import pairwise
from math import fsum, isclose
from random import Random
from traceback import format_exc

from napkin.engine import read, run
from napkin.engine.report import Lag, report
from napkin.engine.timeline.record import key_of
from napkin.model.compile import compile_text

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


def bend_model(seed):
    rng = Random(seed)
    rate, opening, width = (
        (1, 510, 20)
        if seed == 0
        else (rng.randint(1, 8), rng.randint(10, 900), rng.choice((2, 5, 10, 20, 50, 80)))
    )
    left = Decimal(opening) / 1000
    right = Decimal(opening + width) / 1000
    rising = f'2 * this.x - {rate * left} L'
    cap = f'{rate * right} L'
    inner = ''
    if seed and seed % 3 == 1:
        inner = f'    capped = formula(min({rising}, {cap}))\n'
        arm = 'this.capped'
    else:
        arm = f'min({rising}, {cap})'
    source = f"""scenario "A narrow bend"
    horizon 1 h
yard:
    x: L = 0 L
    flow fill: SOURCE -> this.x
        request = {rate} L/h
{inner}    credit = formula(max(this.x, {arm}))
    plain = formula(this.x)
"""
    return source, rate, float(left), float(right)


def _compare(errors, label, actual, expected, rate):
    if not isinstance(actual, (float, int)) or not isclose(
        actual, expected, rel_tol=1e-9, abs_tol=1e-9 * rate
    ):
        errors[label] = (expected, actual)


def check_lag_bends(seed):
    source, rate, a, b = bend_model(seed)
    center = (a + b) / 2
    # On either side of the narrow triangle the straight stock is its own lower envelope.
    # Its area above that stock is base * height / 2 = rate * (b-a)^2 / 4.
    exact = {'yard.credit': rate * (0.5 + (b - a) ** 2 / 4), 'yard.plain': rate * 0.5}
    interior = (a, (a + center) / 2, center, (center + b) / 2, b)
    # Split the independent trapezoid calculation at all three mathematical bends so
    # even a triangle entirely between two grid readings contributes its full area.
    grid = sorted({*(i / 50 for i in range(51)), *interior})
    model = compile_text(source, UNITS)
    differences = {}
    for selective in (False, True):
        errors = {}
        try:
            cfg = model.configuration
            if selective:
                cfg = replace(
                    cfg,
                    request=replace(
                        cfg.request,
                        everything=False,
                        keys=tuple(key_of(model.program, path) for path in exact),
                    ),
                )
            record = run(model.program, cfg)
            if record.failure is not None:
                errors['run'] = repr(record.failure)
            plain = report(record, model.program, cfg, list(exact), interior)
            delayed = report(record, model.program, cfg, list(exact), [1], {p: Lag(0, 1) for p in exact})
            for values, shown, lagged in zip(
                read(record, model.program, list(exact), grid), plain.values, delayed.values, strict=True
            ):
                path = values.path
                history = record.history(key_of(model.program, path))
                for t, direct in zip(interior, shown.values, strict=True):
                    expected = rate * (max(t, min(2 * t - a, b)) if path == 'yard.credit' else t)
                    _compare(errors, f'{path}/report@{t:g}', direct, expected, rate)
                    _compare(errors, f'{path}/history@{t:g}', history.at(t), expected, rate)
                area = fsum(
                    (end - start) * (low + high) / 2
                    for (start, end), (low, high) in zip(pairwise(grid), pairwise(values.values), strict=True)
                )
                _compare(errors, path + '/integral of reads', area, exact[path], rate)
                _compare(errors, path + '/lag vs analytic', lagged.values[0], exact[path], rate)
                _compare(errors, path + '/lag vs integral of reads', lagged.values[0], area, rate)
                if lagged.lag is None:
                    errors[path + '/lag refused'] = lagged.note
        except Exception:
            errors['exception'] = format_exc()
        if errors:
            differences['selective' if selective else 'full'] = errors
    assert not differences, {
        'seed': seed,
        'source': source,
        'sha256': sha256(source.encode()).hexdigest(),
        'observations': differences,
    }
