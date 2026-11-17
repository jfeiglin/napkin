# Assumption inventory and authored reviews

Each scenario owns its assumption inventory, `results/assumption-review.json`, which lists the
scenario's assumptions, their origins, human-confirmation records and reachability. No inventory
covers the catalogue as a whole.

Scientific review records belong to the model or assumption they assess. The inventory reports
those records; it does not create a review status or link to retired catalogue-wide reviews.
Regenerate a scenario's inventory with `python -B -m tools.publish --write --scenario ID --only assumptions`.
