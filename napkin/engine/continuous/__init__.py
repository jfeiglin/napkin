"""The continuous part of a run: what moves between moments, and how each segment is integrated.

- `system`: the numerical settings of a run, the context that the continuous engine reads of it
  (formulas, diagnostics), and the state that changes as it proceeds;
- `fields`: the allocated vector field and its Jacobian pattern;
- `bounds`: state checks, balanced roundoff, active bounds and stock faces;
- `kernels`: the segment classifier and the exact affine and compartment solutions;
- `integrate`: roots and the numerical segment;
- `segment`: the step between two moments, which chooses among them;
- `dense`: how a weighted sum of stores moves over a piece of a segment, from the form of its
  solution, which bounds the first contact of a condition on values that turn.
"""
