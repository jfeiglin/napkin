"""Conventions shared by the independent oracles; no production engine or trace imports.

Inputs use authored units: hours, people, USD billions/year and USD/person-day.
Explicit conversion factors independently check the engine's dimensional math.
"""

import mpmath as mp

DPS = 60


def num(x):
    """Exact decimal reading of an authored literal, not its binary float."""
    return mp.mpf(str(x))
