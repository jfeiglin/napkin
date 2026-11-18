"""A reference interpreter for the execution rules of the napkin rewrite: small, slow and exact.

`ref.model` describes a model in plain records. `ref.run.Run` runs a description."""

from .errors import Diagnostic, Infeasible, NotCovered, Paused, RunFailed  # noqa: F401
from .model import *  # noqa: F401,F403
