## S7 declared scales and solver ranks

On macOS, 304 of the 600 seed IDs failed at `97a7b3e`. All 600 completed. The declared-unknown family had 121 failing and 179 passing IDs. The mixed-flow family had 183 failing and 117 passing IDs. The scenarios independently check uniquely determined coordinates, objective values at each rank, flow rates, hard feasibility and unbounded diagnostics. Free nonflow ties are checked against their constraints and objective. [Every result and failing model](baseline.jsonl.gz).

With the bounds [0, 1e9] L on both unknowns, the engine maximized x + y at (1e9, 0) after declaring a 1 L scale on y. Both coordinates should reach 1e9. When the upper bound on y was removed, the engine still returned a finite answer. [Bounded model](scale-bounded.explicit.scn), [unbounded model](scale-unbounded.explicit.scn).

Seven direct solver cases failed and nine controls passed. One feasible vertex received an infeasible diagnosis. A hard equality triggered a numerical residual, and two equally sized claims were served at fractions 1 and 0 instead of one half each. The two final-distance controls retained their expected metric-dependent ties. [Direct pytest output](physical-ranks-complete-red.log.gz), [exact reference observations](physical-ranks-reference.log.gz).

A physical interval [0, 1e-12] found an additional copy of the problem in bound pinning. After maximizing its only coordinate, a second objective minimizing that coordinate returned zero with reference scale 1. The result should still be 1e-12. A matching-width reference scale passed on the pinned original. [Failure and control](narrow-interval-red.log.gz).

Four direct fair-sharing cases failed on the original solver. They use unequal requests at two magnitudes, a blocked aggregate alongside an eligible claim, and a later tier constrained by an earlier one. [Full discrepancies](unequal-claims-red.log.gz).
