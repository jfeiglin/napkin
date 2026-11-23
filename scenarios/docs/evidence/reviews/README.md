# Review status of assumptions

Each assumption in the `evidence/assumptions.json` file of a package has a `review` object. The
`status` of the review shows whether a person reviewed the assumption.

| Status | Meaning |
| --- | --- |
| `unreviewed` | No person reviewed the assumption. Each new assumption has this status. |
| `replaced` | A newer assumption replaces this assumption. `replaced_by` names the newer assumption. |

The tools apply these rules:

- An evidence pack cannot set a review. `python -m tools.evidence.integrate` refuses a pack
  assumption with a status other than `unreviewed`.
- A `retire` item of a pack has a `mode`. The mode `delete` removes the assumption. Each other mode
  sets the status to `replaced` and records `replaced_by` if the item gives it.
- The source trail (`tools/evidence/trail.py`) shows each assumption that a value reaches, with its
  review status.

The files `results/assumption-review.json` are historical publications of the earlier publisher.
The current publisher keeps them, but it does not write them. For the evidence of a package, read
`results/source-dossier.json` ([the evidence tools](../README.md)).
