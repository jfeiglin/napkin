"""Compare independently authored programs and keep the evidence from every pair in a seed."""

from hashlib import sha256

from napkin.model.language.problems import LanguageError
from napkin.program.canonical import program_bytes
from napkin.program.check import ProgramError


def check_pairs(seed, pairs):
    failures = {}
    for variant, text, builder, accepted in pairs:
        observed = {}
        payloads = {}
        for label, make in (('text', text), ('builder', builder)):
            try:
                payloads[label] = program_bytes(make())
            except (LanguageError, ProgramError) as exc:
                observed[label] = ('refused', str(exc))
            except Exception as exc:
                observed[label] = ('error', f'{type(exc).__name__}: {exc}')
            else:
                observed[label] = ('accepted', sha256(payloads[label]).hexdigest())
        expected = 'accepted' if accepted else 'refused'
        if any(status != expected for status, _ in observed.values()) or (
            accepted and payloads.get('text') != payloads.get('builder')
        ):
            failures[variant] = {'expected': expected, **observed}
    if failures:
        raise AssertionError((seed, failures))


def authored_number(token):
    """Pass the builder a numeric literal with the precision and kind of the authored token."""
    import math
    from fractions import Fraction

    token = str(token)
    if token.lstrip('+-').isdigit():
        return int(token)
    exact = Fraction(token)
    machine = float(token)
    return machine if math.isfinite(machine) and Fraction(str(machine)) == exact else exact
