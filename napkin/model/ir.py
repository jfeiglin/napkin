"""Diagnostics, frozen data and the names of the flat structure that the engine runs.

A scenario builds into one flat structure for each set of options that set start states
(docs/python-api.md). The name of each part of an entity is qualified (`entity.member`); an output
of the main keeps its own name. An event is `entity.event`, and each of its outcomes
`entity.event.outcome`. Expressions are rewritten to these names, so the engine evaluates them in
one flat environment. Derived symbols the engine maintains end in a reserved suffix: `<event>__count`,
`<event>__time` (the last occurrence, valid when the count is positive) and `<mode>__entered` (when
the current value was entered).
"""

from __future__ import annotations

import copyreg
import difflib
import re
from collections.abc import Mapping
from types import MappingProxyType

# The version of the language, which the model hash covers (docs/language/README.md): the identity of a model
# changes with the language, never with the version of the package. It imports nothing of the package's
# root, so the run store's key does not read the root's exports (docs/engine/README.md, "The run store").
LANGUAGE_VERSION = '0.0.1'
EVENT_TIME_TOLERANCE_H = 1e-8
RESERVED = '__'
COUNT, TIME, ENTERED = '__count', '__time', '__entered'
# The names of the values that an event reads when it fires (`lower/expressions.Firing`): `entity.event__draw0`.
FIRING_VALUE = re.compile(r'__(?:draw|delayed)[0-9]+$')


def lag_delays(lag):
    """The delay expressions of an output's reporting lag, in order (`delays_of_lag`). `lag` is the
    mapping of the lag, or nothing for an output with no lag."""
    if not lag:
        return []
    shares = [(c['weight'], c['delay']) for c in lag.get('components', ())]
    return delays_of_lag(lag['type'], lag.get('delay'), lag.get('min'), lag.get('max'), shares)


def delays_of_lag(kind, delay, low, high, shares):
    """The delay expressions of a reporting lag from its parts, in order: the delay of a fixed lag
    (`kind` `fixed`), the two bounds of a uniform lag (`low`, `high`), or the delay of each share
    of a mixture (`shares`: (weight, delay) of each). A caller gives what the lag has: the keys of
    its mapping, or the fields of its typed part."""
    if kind == 'fixed':
        return [delay]
    if kind == 'uniform':
        return [low, high]
    return [later for _, later in shares]


def extra_sources(rule):
    """The expressions of the values that a rule reads when it fires (`extras`): each draw's arguments,
    and each delayed value with its delay."""
    for item in rule.get('extras', ()):
        yield from item.get('args', {}).values()
        for key in ('expr', 'delay'):
            if key in item:
                yield item[key]


def rule_events(rule):
    """Every event that a flat rule can add: its own, when it triggers, and each outcome's."""
    return [*rule['emits'], *(event for outcome in rule['outcomes'] for event in outcome['emits'])]


def rule_steps(rule):
    """The flat step of each outcome of a rule, in order."""
    return [outcome['do'] for outcome in rule['outcomes']]


def basis_records(basis):
    """The records of a resolved basis: one record, or each record of a list of two or more."""
    if basis is None:
        return []
    return list(basis) if isinstance(basis, (list, tuple)) else [basis]


def diagnostic(code, path, message, severity='error', **extra):
    return {'code': code, 'path': path, 'message': str(message), 'severity': severity, **extra}


def close_names(name, names):
    """What a diagnostic about `name`, which names nothing, adds: the names of `names` closest to it
    (`difflib.get_close_matches`), at most three, as `; did you mean a or b?`, or '' when no name is
    close."""
    found = difflib.get_close_matches(str(name), sorted({str(other) for other in names} - {str(name)}), n=3)
    if not found:
        return ''
    listed = found[0] if len(found) == 1 else f'{", ".join(found[:-1])} or {found[-1]}'
    return f'; did you mean {listed}?'


class ModelError(ValueError):
    """A model that cannot be compiled or run, with structured diagnostics (code, path, message)."""

    def __init__(self, diagnostics):
        if isinstance(diagnostics, str):
            diagnostics = [diagnostic('model', '', diagnostics)]
        self.diagnostics = list(diagnostics)
        super().__init__('; '.join(f'{d.get("path", "")}: {d["message"]}' for d in self.diagnostics))


def _frozen_mapping(items):
    return MappingProxyType(items)


# A completed study carries frozen model data; it pickles as plain items and is frozen again on
# loading, so studies can be evaluated in one process and read in another.
copyreg.pickle(MappingProxyType, lambda mapping: (_frozen_mapping, (dict(mapping),)))


# The module of the typed parts of a compiled model (`structure.py`), which imports nothing from here.
TYPED = 'napkin.model.structure'


def freeze(value):
    if isinstance(value, Mapping):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    return value


# The types that a model and a report hold, tested by their exact type before the general rule.
_MAPPINGS = (dict, MappingProxyType)
_SEQUENCES = (list, tuple)
_PLAIN = (str, int, float, bool, type(None))


def thaw(value):
    """Plain data that the caller can change: each mapping a dict, each tuple a list. A typed part of
    a compiled model is an error (see `structure.thawed`)."""
    kind = type(value)
    if kind in _MAPPINGS:
        return {key: thaw(item) for key, item in value.items()}
    if kind in _SEQUENCES:
        return [thaw(item) for item in value]
    if kind in _PLAIN:
        return value
    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw(item) for item in value]
    if kind.__module__ == TYPED:
        # A typed part is no plain data. To give it back as it is would let a caller go on with a
        # record where it asked for a copy that it can change.
        raise TypeError(f'thaw takes plain data, not a {kind.__name__}: use its plain()')
    return value


# The distributions of numbers that an event can draw when it fires, with their parameters in order.
DRAWN = {
    'uniform': ('min', 'max'),
    'triangular': ('min', 'mode', 'max'),
    'pert': ('min', 'mode', 'max'),
    'loguniform': ('min', 'max'),
    'normal': ('mean', 'sd', 'min', 'max'),
    'lognormal': ('median', 'gsd', 'min', 'max'),
    'beta': ('a', 'b'),
}
