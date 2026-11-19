"""The analysis of a run's dynamics: its field, equilibria, branches, basins and sensitivity
(docs/python-api.md, "Dynamics").

The analysis reads the engine's own field of a program's run under a configuration (the instances of
the ways of its connected sets that move), so the equations that it analyses are the equations that
the engine runs. It gives data, never a figure, and changes no program or record.
"""

from .basins import Threshold, input_threshold, state_threshold, threshold
from .continuation import Bifurcation, Branch, Family, Inadmissible, Point, continue_equilibrium, fold_curve
from .equilibria import (
    NONHYPERBOLIC,
    SADDLE,
    STABLE,
    UNSTABLE,
    Equilibrium,
    Side,
    classify,
    equilibria,
    equilibrium_at,
    newton,
)
from .field import OutsideDomain, VectorField, configured, started, value_at, vector_field
from .sensitivity import Factor, MorrisResult, SobolResult, input_factors, morris, run_function, sobol

__all__ = [
    'NONHYPERBOLIC',
    'SADDLE',
    'STABLE',
    'UNSTABLE',
    'Bifurcation',
    'Branch',
    'Equilibrium',
    'Factor',
    'Family',
    'Inadmissible',
    'MorrisResult',
    'OutsideDomain',
    'Point',
    'Side',
    'SobolResult',
    'Threshold',
    'VectorField',
    'classify',
    'configured',
    'continue_equilibrium',
    'equilibria',
    'equilibrium_at',
    'fold_curve',
    'input_factors',
    'input_threshold',
    'morris',
    'newton',
    'run_function',
    'sobol',
    'started',
    'state_threshold',
    'threshold',
    'value_at',
    'vector_field',
]
