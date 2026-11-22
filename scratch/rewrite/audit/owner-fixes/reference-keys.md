# Reference collection keys

**POINT.** The owner specifies zero-based entity and flow creation numbers. An entity's number is local to its template. A flow or connection has its own number in the run. An occurrence collection uses start times. An explicit key shared by multiple members selects the later-created member.

At `6ce787aa780baf4e1fce1baade80bdccd9046ac9`, the reference assigned all entities one global sequence starting at 1 and also started the flow sequence at 1. The seven cases in `tests/reference/test_collection_keys.py` independently check the specified readings. Six failed and the equal-key control passed.

- Creating an unrelated template member before two members with readings 2 and 8 left both key 0 and key 1 uncovered in the reference. The engine returned 2 and 8 respectively. The checks exercise both `Member.instances` and a literal written in reverse order. A stored lookup key keeps the lookup from being folded at compile time.
- Two outgoing pipes with requests of 2 and 8 L/h should supply those rates at keys 0 and 1. The reference missed key 0 and returned 2 L/h at key 1.
- `Member.instances.by(rank).at(cursor)` selected the later-created member with reading 8 on equal explicit ranks.

The corrected reference assigns entity numbers per template and creates the first flow at 0. All seven cases pass. The other reference test files passed in two focused batches of 183 and 143 cases. The pattern search covered `itertools.count`, entity enumeration, direct `.number` reads, and collection construction in `tests/reference`. Instance, endpoint-flow, occurrence and literal collections now read their natural keys through `Run.key_of`. The occurrence scheduling serial and ordering-only uses of `.number` preserve their ordering.

## Production findings for S5

On the same commit the public builder accepts `box.stock.outflow.flows.at(key).actual_rate`. With the two pipes above, the engine returns an unavailable reading at key 0, 2 L/h at key 1 and 8 L/h at key 2. The text compiler rejects the same endpoint-flow lookup as a projection. At the audit base `b433a4d`, the one-based production assignments are in `napkin/engine/timeline/plan.py` at 1054, 1069 and 1092, with endpoint collection keys read at 2041. The production changes belong to S5.

## Separate reference finding

With the same two entities and equal ranks, `<second, first>.by(rank).at(cursor).weight` returns 8 in production and 2 in the original reference. At `d2a5b27`, the reference iterated the literal in authored order and replaced the winner on equal keys. Its tie reproduction failed with 13 passing controls.

**POINT.** The reference evaluator now compares the members' creation numbers on an equal explicit or natural key. It still prefers the greatest eligible key. The lookup retains the identity of the original member through projections and filters. This correction applies within a collection of one element type. The tests cover literals in both orders, distinct increasing and decreasing keys, equal-request flows and simultaneous occurrences. The focused post-fix run passed all 149 cases. A search of reference collection construction and lookup found one `.at` winner-selection loop in `Ev._call`.
