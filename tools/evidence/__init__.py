"""Evidence authoring tools. Five commands, each with its own main:

- fetch: retrieve a document's raw bytes into the evidence cache, and extract their text (--extract);
- integrate: apply evidence packs, the only writer of claims and sources; check the library against
  the cached source bytes (--check); print the evidence coverage report (--coverage);
- manifest: the source acquisition manifest, and the restoration of hash-matching source bytes;
- adopt: copy a record and its dependencies from one scenario or family folder to another;
- trail: what the values that a run reports rest on, from the declared model's records and the
  report's evidence trail, resolved in the library.

The helpers have no main: cache (where the content cache is) and normalize (quote normalization and
matching). The evidence collections that each folder owns come from the catalogue's locator
(`tools/catalogue.py`).

The engine never imports these tools; the publisher reads the source manifest (`manifest.artifacts`
and `manifest.PATH`). Only the code of fetch uses the network, and manifest acquires sources through
it.
"""
