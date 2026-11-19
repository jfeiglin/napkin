"""The one driver of every walk of the dependency graph, with no recursion (re-audit 15).

A walk that follows formulas, links, reductions or keyed reads goes as deep as the chain that it
follows, so a walk by calls fails on a long chain with Python's recursion limit. Each such walk is a
computation instead: a generator that yields each computation that it needs and is sent its result,
and returns its own. `walked` keeps the computations that wait on an explicit stack. The timeline
walks the graph so (the start of a run, the present, the expansions of the plan, the conditions of a
run, the near-ties of a test), and so do the proofs of the continuous engine over the formulas of a
component (`kernels.py`), which is why the driver lives below both.
"""

from __future__ import annotations


def walked(computation):
    """The result of a computation over the dependency graph (see the module); an exception that a
    needed one raises is thrown into the one that waits for it, where a call would have raised it.
    An evaluation that the core compiles (`timeline/reads.lazily`) cannot yield: it raises
    `timeline.plan.Pending` for a value that its computation does not know yet, which yields that
    value's computation and evaluates it again (the reads that it made are kept, so none is made
    twice)."""
    stack, sent, thrown = [computation], None, None
    while True:
        top = stack[-1]
        try:
            asked = top.send(sent) if thrown is None else top.throw(thrown)
        except StopIteration as done:
            stack.pop()
            if not stack:
                return done.value
            sent, thrown = done.value, None
            continue
        except Exception as problem:
            stack.pop()
            if not stack:
                raise
            sent, thrown = None, problem
            continue
        stack.append(asked)
        sent, thrown = None, None
