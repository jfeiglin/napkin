## Observation for S8

The S4 capacity case `destination.4000000` (seed 0) commits a 0.0000000003 L withdrawal from 4,000,000 L at hour 1. A later move fails at hour 2. Its exact committed inventory is 3,999,999.9999999997 L. The nearest public float is 3,999,999.9999999995 L.

At the failed cutoff the S4 stock ledger now projects that balance. The historical compactor can still drop the hour-1 piece and report 4,000,000 L for a read at hour 1.5. Reuse the complete source in the S4 baseline ledger and read hours 0, 1, 1.5 and 2 for the S8 history corpus.
