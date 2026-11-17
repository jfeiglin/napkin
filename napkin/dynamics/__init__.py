"""The analysis of a run's dynamics: its field, equilibria, branches, basins and sensitivity
(docs/python-api.md, "Dynamics").

The analysis reads the engine's own field of a compiled run, so the equations that it analyses are the
equations that the engine runs. It gives data, never a figure, and changes no model or result.
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
from .field import OutsideDomain, VectorField, vector_field
from .sensitivity import Factor, MorrisResult, SobolResult, factors_from_model, model_function, morris, sobol

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
    'continue_equilibrium',
    'equilibria',
    'equilibrium_at',
    'factors_from_model',
    'fold_curve',
    'input_threshold',
    'model_function',
    'morris',
    'newton',
    'sobol',
    'state_threshold',
    'threshold',
    'vector_field',
]
