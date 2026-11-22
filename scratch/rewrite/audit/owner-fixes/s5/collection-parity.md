# Source and builder collection parity

At `bdf91d7bbd192d95a29e578583eb9855287cd1ca`, 300 seeds exercised each of the three collection families. Both authors accepted all 10,205 pairs. Their canonical program bytes matched on 9,905.

| Family | Compared pairs | Differences |
| --- | ---: | ---: |
| Collection kinds | 8,100 | 300 |
| Collection lexical scope | 1,505 | 0 |
| Historical filters | 600 | 0 |

Each collection-kind seed exposed the same difference in `member.first`. The source compiler resolves `Entry.instances.at(0).amount` as `first.amount`. The builder retains a `Lookup` of the entire collection. The selected row alone is the actual dependency. This distinction matters for a retained formula that would appear to depend on itself through the collection. The existing compiler regression `tests/language/test_collections.py::test_a_fixed_formula_reads_the_entry_that_its_key_selects` requires the named path.

`collection-parity-red.jsonl.gz` contains every seed, variant name, canonical SHA-256 digest for each author, duration, revision, generator digest and mismatch. The 600 historical-filter texts matched the frozen generator byte for byte. The reduced public tests in `tests/program/test_constant_member_keys.py` reproduce four missing static selections and two invalid natural keys the builder accepted. Six controls passed, including duplicate literals, an undershoot, omitted members, stored keys, filters and explicit rekeying. The focused pytest command was `.venv/bin/python -B -m pytest -q --no-focused tests/program/test_constant_member_keys.py`.
