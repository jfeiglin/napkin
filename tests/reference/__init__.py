"""The oracle: a small, slow and exact interpreter of the rules of the rewrite, and its tests.

The new engine is checked against it. It shares no code with napkin's evaluation: a model is plain
data (`model.py`), and `run.py` with its helpers (`evaluate.py`, `network.py`, `order.py`,
`exact.py`, `poly.py`) runs it in fractions. Where it cannot run a model exactly it raises
`errors.NotCovered` with the reason, and never guesses."""
