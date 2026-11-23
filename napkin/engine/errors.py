"""The error of a run: the engine stops a run that it cannot carry on (docs/engine/README.md)."""

from __future__ import annotations


class SimulationError(RuntimeError):
    def __init__(self, message, diagnostics=None):
        super().__init__(message)
        items = [{'message': message, **item} for item in diagnostics or []]
        if not any(item.get('severity') == 'error' for item in items):
            items.append({'severity': 'error', 'message': message})
        self.diagnostics = items
