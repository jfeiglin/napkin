"""The continuous part of a run: what moves between moments, and how each segment is integrated.

- `system`: the fixed description of a run (quantities, bounds, flows, the step cap) and the
  state that changes as it proceeds;
- `fields`: the allocated vector field and its Jacobian pattern;
- `bounds`: state checks, balanced roundoff, active bounds and stock faces;
- `kernels`: the segment classifier and the exact affine and compartment solutions;
- `integrate`: roots and the numerical segment;
- `segment`: the step between two moments, which chooses among them.
"""
