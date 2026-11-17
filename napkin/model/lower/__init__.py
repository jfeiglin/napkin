"""The lowering: from the semantic model of a scenario to the flat structures that the engine runs.

- `builder`: the parts of a structure, one structure for each set of start-state options;
- `expressions`: an expression of the semantic model as a typed node with the structure's names, and
  its engine's form (`count`, `since`, `elapsed`, a sum over a list, a draw, a value of the past);
- `starts`: the parts that a set of start-state options leaves out.
"""

from .builder import Builder
from .expressions import RewriteError
from .starts import Acting

__all__ = ['Acting', 'Builder', 'RewriteError']
