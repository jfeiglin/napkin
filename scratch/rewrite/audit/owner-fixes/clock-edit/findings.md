# A stock crossing at a clock handoff

In seed 37 the stock reaches 6 L before the clock changes. Starting an occurrence rebuilds the method at 3 h. With its starting inventory perturbed downward by two ULPs, the outgoing stock trajectory crossed the threshold between adjacent representable times. Requiring a clock float at which the stock equalled the threshold lost that crossing. The event then captured 6 L/h, while the reference and the unperturbed run both gave 3 L/h.

The departure check in ee36192 also recognizes a change of sign between adjacent samples for a directly moving stock against a fixed threshold. The nine combinations of perturbation, direct run, live edit, and restored edit agree with the reference. All 1,200 S3 family cases, 22 direct and stock-contact tests and 573 neighboring switch tests passed. [Original observations](baseline.jsonl) · [Rechecked observations](verified.jsonl)

Three alternating pairs at ee36192 against 6202824 gave median time ratios of 1.002765 for Sparse tanks and 0.978931 for Component tanks. [All timings and schedules](speed.json)
