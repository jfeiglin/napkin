# Evidence and scientific reproduction

Each scenario owns its sources, claims, assumptions and research note in `scenarios/<ID>/evidence/`.
Claims carry source locators, substantive verification fields, supporting excerpts, source-byte
digests and extraction digests. Assumptions carry the chosen model conditions, supporting evidence
and review status. Each scenario has its source dossier (`results/source-verification.json`) and its
assumption inventory (`results/assumption-review.json`) in its own `results/` folder. The
[source acquisition manifest](source-manifest.json) reports the sources of the current catalogue.

The shared vocabulary (`scenarios/library/vocabulary.json`) holds the units that the prelude does not hold,
such as physical and currency units, and the conventions of the project: records that a model's
`convention` record names by its ID, such as `HAZUS-SEVERITY`, which the casualty outputs cite. It
lists no categories: an output's category is a tag.

## Reproduce evidence checks

Use Python 3.14 and Ghostscript 10.07.1 for the recorded extraction identifiers. Install Ghostscript
and put `gs` on PATH, or set `EVIDENCE_GHOSTSCRIPT` to its executable path.

```sh
python -m tools.evidence.manifest --check
python -m tools.evidence.manifest --restore-project
python -m tools.evidence.manifest --acquire SOURCE_ID
python -m tools.evidence.manifest --acquire-all
python -m tools.evidence.manifest --import SOURCE_ID=/path/to/raw-document
python -m tools.evidence.integrate --check --complete --report complete-evidence-check.json
```

`manifest` and `integrate --check` accept `--root PATH`. `manifest --scenario ID` selects source
acquisition; its publication still covers the full catalogue. `integrate --check --scenario ID`
selects verification and accepts repeated scenario selections. They do not take a monolithic library
path. Bulk acquisition restores every source and reuses hash-matching cached bytes. Its report
identifies publications that need an archived-byte import. Import admits bytes only when the recorded
digest and byte count match.

The raw-byte cache is shared by content hash. `EVIDENCE_CACHE` chooses its directory. Otherwise,
the tools find the main checkout through Git's common directory, falling back to the repository
root. A linked worktree therefore uses the same acquired bytes as the main checkout.

The complete check (`integrate --check --complete`) requires retrieval records and cached raw bytes
for every source and claim. It re-extracts the original bytes, checks extraction identifiers and text
digests, and matches every excerpt. Its report records coverage, acquisition checks, missing bytes
and each claim's result.

## Evidence status and dependencies

`verified` records a substantive primary-source review of the named claim fields. `partial` records
the checked subset and access method. `unverified` records the work still required. A claim's content
digest binds substantive content to its verification record. `unreviewed` assumptions retain that
status until their own record changes; a numerical result does not establish a scientific review.

A scenario depends on every `claim` and `assumption` reference in its model, and on the plain
claim-ID lists in its review. That set includes the supports of cited assumptions,
recursive `related` claims and the sources of all reached claims. Hashing, validation, integration
and publication use the same dependency closure.

Numerical bases distinguish reported values, source transfers, identities, project conventions and
assumptions. A transfer states the source population, endpoint and exposure. A mechanism's support
and a coefficient's numerical choice are separate claims. Each scenario's research note explains
its application, bounds and measurements still needed. The [consequence guide](consequences/README.md)
summarizes the common accounting rules.

## Relations in the library

The library links its own records: a claim to the claims related to it (`related`), and an
assumption to the claims that inform it (`supports`). Each link has a relation, and a note can say how
the claim bears on the record. A scenario's records do not repeat these links. A record lists its
claims, and its explanation says how they support the part.

| Relation | The claim |
| --- | --- |
| `mechanism_support` | shows that the mechanism works as the record says |
| `mechanism_precedent` | reports an earlier event in which the mechanism occurred |
| `specifies_component` | describes a part that the record uses: a device, a step or a time |
| `reports_value` | reports a figure that the record uses |
| `calibrates` | gives the reference from which the record sets its value |
| `defines_conditions` | sets the conditions in which the record applies |
| `accounting_rule` | gives a rule for counting a quantity or a cost |
| `consistent_with` | agrees with the record, but does not establish it |
| `bounds` | gives a limit of the value; it does not support the value |
| `context_limitations` | limits the setting in which the record applies |
| `contradicts` | argues against the record |
| `adopts` | gives a definition or a convention that the project adopts |

The briefs mark a claim that bounds an assumption or limits its setting as "Limit", and a claim that
argues against it as "Contradicts". No page counts these claims as support.

## Author and adopt records

`integrate` is the only writer of claims and sources. Each pack identifies one `scenario`, and a batch
writes one scenario folder. Source and assumption packs use `scenario`, not an owner registry.

A variant of a package (`SCnn:east`) reads the records of its own folder and of its package's folder
(`SCnn`), and a record in either folder can support its lines. A pack names the folder that it
writes: `"scenario": "SCnn:east"` for the records of that variant only, in the folder
`scenarios/SCnn/variants/east/`, or `"scenario": "SCnn"` for records of the package's folder, which
the package and all its variants read. The pack schema is `tools/evidence/evidence-pack.schema.json`.
A batch writes that one folder and cannot change a record of another folder that the models read.
Each record of a package's folder must be used by its model or by one of its variants, at least; the
dry run reports a record that none of them reaches. `--prune` removes such records, with the sources that only they reach, through
the same writer; an assumption pack with nothing to upsert or retire names the folder to prune.
The command accepts optional `--root PATH` and `--scenario ID` selectors; it has no `--library` option.
Use its dry run to inspect a pack, then its write mode to apply the validated records. A model may
cite a record before a pack adds it: integrate checks every citation of the scenarios that read the
folder against the library that the packs make, and refuses, in a dry run too, while one is missing.

A pack records the retrievals of its source. `fetch URL` stores the raw bytes of a document in the
cache and prints their retrieval record. `fetch --extract PATH` extracts the text of cached bytes.
`integrate --coverage` prints what each entity and each outcome rests on, and the claims that no
scenario reaches. Each mode of a command refuses the options of its other modes.

```sh
python -m tools.evidence.fetch URL --out retrieval.json
python -m tools.evidence.fetch --extract .evidence-cache/sha256/ab/SHA256.pdf
python -m tools.evidence.integrate --help
python -m tools.evidence.integrate --coverage
python -m tools.evidence.adopt --from SOURCE_SCENARIO --to TARGET_SCENARIO --id RECORD_ID
python -m tools.evidence.adopt --from SOURCE_SCENARIO --to TARGET_SCENARIO --id RECORD_ID --write
python -m tools.publish --write --only dossier --only manifest --only assumptions
```

`adopt` previews a record and its dependencies by default; `--write` copies them through the same
validated writer as `integrate`. It refuses a conflicting destination record. Copies are independent:
a later change in one folder does not update another, and no cross-folder equality check is required.
There is no synchronization command. The source acquisition manifest identifies a source by both
scenario and ID.

Review the concrete causal chain: access, action, service disruption, exposed people, protection,
clinical or economic conversion, recovery and final accounting. Record the reviewer's identity,
context, methods and conclusion in the owning model or assumption. Each scenario's generated
inventory reports those authored records without links to retired central review files.

## Evidence beside declarations

Single-use basis records may sit beside the values or rules they support. Shared definitions within
one model live in a class (`ClassName.record_name`) or at the root (an unqualified name). Both use the
same record schema. Resolution has no inheritance, local fallback or definition aliases. Each
support obligation still cites its own record.

The compiler keeps content identities, aliases and use locations separate. Content digests omit
resolver-added names and locations; moving a record does not change its scientific content. The
index retains source locations, including inline records. Migration comparisons apply explicit
rename and location maps to indexes, reports and traces.
