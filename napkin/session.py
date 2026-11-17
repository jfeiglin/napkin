"""One played run, one decision at a time (docs/engine.md, "Play"): `Session`.

A session plays one run of a model. The decisions of the actors that `control` names wait for a pick;
the model takes every other decision. There are two ways to give the picks, and both give the same run,
bit for bit:

- live: a `resolver` answers each decision while the run is simulated, in one simulation;
- step by step: `advance()` stops at the first decision without a pick, `pick()` answers it, and the
  next `advance()` simulates the run again from t = 0 with the longer log. The engine keeps no paused
  run.

Each answer goes into the log (`picks`) before the engine takes it. `result()` reports the finished
run as `evaluate_study(…, play=…)` does, and `save()` and `Session.load()` keep the log with the
context that it replays in.

A session runs the checks of `evaluate_study`, in its order, with the engine's own functions, then the
engine's simulation and its check of a simulated run (`study.run_checks`), so that it refuses what a
study refuses, with the same diagnostics. The one check of the session's own is that of an answer: an
outcome that can happen now.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import fields
from pathlib import Path

from . import SCHEMA_VERSION
from .engine import study
from .engine.report import sample_result
from .engine.runtime import NumericalSettings, simulate
from .model.analysis.values import input_check_failures
from .model.ir import ModelError, thaw
from .model.load import load_json
from .paths import names_of

# The kind of a play log, and the fields of its context: a log continues only a session of the same
# context, so that it replays exactly.
KIND = 'play'
CONTEXT = ('model_hash', 'implementation_hash', 'run', 'options', 'control', 'edits', 'numerical_settings')


class OtherContext(ValueError):
    """A play log of another context than the session that would continue it: `fields` names each field
    of `CONTEXT` that differs, in that order."""

    def __init__(self, path, fields):
        self.fields = tuple(fields)
        listed = (
            self.fields[0]
            if len(self.fields) == 1
            else f'{", ".join(self.fields[:-1])} and {self.fields[-1]}'
        )
        super().__init__(
            f'{path} is the log of another play: it differs in {listed}, so it cannot continue this one'
        )


def _errors(diagnostics):
    return [item for item in diagnostics if item.get('severity', 'error') == 'error']


def _failures(exc, **context):
    """The diagnostics of a failure, as a study gives them. `study._errors` is private: a session uses
    it so that its refusals are the study's own."""
    return study._errors(exc, **context)


def _plain(value):
    """A JSON copy of `value`, or `value` itself when it has none."""
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError, RecursionError, OverflowError):
        return value


def _sorted(options):
    """The options, sorted and each once. A text or a collection with an item that is not a text is
    kept as it is, so that `Model.combination` refuses it."""
    if isinstance(options, str):
        return options
    options = tuple(options)
    if not all(isinstance(option, str) for option in options):
        return options
    return tuple(sorted(set(options)))


def _settings(settings):
    """The fields of numerical settings, as the run store's key reads them (`store.key`)."""
    return {item.name: getattr(settings, item.name) for item in fields(settings)}


def _context(model, run, control, options, edits, settings):
    """The context of a play log (`CONTEXT`), as plain data."""
    return {
        'model_hash': model.model_hash,
        'implementation_hash': model.implementation_hash,
        'run': run,
        'options': list(options),
        'control': _plain(control),
        'edits': _plain(edits) if edits else None,
        'numerical_settings': _settings(settings),
    }


def _document(edits):
    """The edit document that a study reads: the first steps of `evaluate_study`, before it resolves
    any run (`study.edit_document`: the shape, the input tree, the JSON copy). Raises ModelError with
    the diagnostic that the study gives."""
    document, problem = study.edit_document(edits)
    if problem:
        raise ModelError([problem])
    return document


def _shown(decision):
    """A decision as a session shows it: what the engine asks (docs/engine.md, "Play"), without the
    engine's count of the picks (`pick_index`, which is the decision's `pick`), as a copy."""
    return thaw({key: value for key, value in decision.items() if key != 'pick_index'})


def _available(decision):
    return [item['name'] for item in decision['outcomes'] if item['available']]


def _entry(decision, outcome, reason):
    """The log's entry of a pick: the decision's event and the outcome that the engine reads, and when,
    by whom and why."""
    return {
        'event': decision['event'],
        'outcome': outcome,
        't': decision['t'],
        'by': decision['by'],
        'reason': reason,
    }


def _check_answer(decision, outcome):
    """Raise ValueError unless `outcome` is an outcome of the decision that can happen now."""
    available = _available(decision)
    if outcome not in available:
        raise ValueError(
            f'{outcome!r} is not an outcome of {decision["event"]} that can happen now: '
            f'pick one of {", ".join(available)}'
        )


class Session:
    """One played run of a model (docs/engine.md, "Play").

    - `base`: the model as given;
    - `model`: the model of the run, `package.combined(base, run, options, edits)` when there are
      options, else `base`;
    - `run`: the name of the run;
    - `options`: the options in place of the run's own of their groups, sorted, each once;
    - `control`: who picks the decisions of each actor or choice: `{THING: 'reader' | 'agent' |
      'chance'}`, as `evaluate_study(play=…)` reads it;
    - `edits`: the edit document as given, or None;
    - `settings`: the numerical settings (`NumericalSettings.parse`);
    - `resolver`: `resolver(decision) -> (outcome, reason) | None`, which answers a decision while the
      run is simulated, or None to stop the run there; or None, for no live answers;
    - `picks`: the log, `[{event, outcome, t, by, reason}]`;
    - `decision`: the decision that waits for a pick, or None;
    - `trajectory`: the simulated run of the last `advance()`, which stops at `decision`;
    - `warnings`: the diagnostics of the last `advance()` that are not errors.

    A problem of the options, or of the edits with options, raises the engine's ModelError here.
    """

    def __init__(
        self, model, run, *, control, options=(), edits=None, picks=(), settings=None, resolver=None
    ):
        from .package import combined

        self.base = model
        self.run = run
        self.control = dict(control) if isinstance(control, dict) else control
        self.options = _sorted(options)
        self.edits = edits
        self.settings = NumericalSettings.parse(settings)
        self.resolver = resolver
        self.picks = [dict(item) if isinstance(item, dict) else item for item in picks]
        self.decision = None
        self.trajectory = None
        self.warnings = []
        # The edit document of the model of the run: with options, what reaches the run (`combined`).
        if self.options:
            document = None if edits is None else _document(edits)
            self.model, self._edits = combined(model, run, self.options, document)
        else:
            self.model, self._edits = model, edits

    def _play(self):
        return {'run': self.run, 'control': self.control, 'picks': self.picks}

    def _answer(self, raised):
        """The engine's resolver (`simulate(decision_resolver=…)`): it asks `resolver`, checks the answer,
        and logs the pick before it gives the engine the pick. Each exception of `resolver` goes into
        `raised`, so that it propagates as it is."""

        def answer(decision, env, trace):
            shown = _shown(decision)
            try:
                given = self.resolver(shown)
            except BaseException as exc:
                raised.append(exc)
                raise
            if given is None:
                return None
            try:
                outcome, reason = given
            except (TypeError, ValueError):
                raise ValueError(f'A resolver gives (outcome, reason) or None, not {given!r}') from None
            _check_answer(shown, outcome)
            self.picks.append(_entry(shown, outcome, reason))
            return {'event': shown['event'], 'outcome': outcome}

        return answer

    def advance(self):
        """Simulate the run from t = 0 with the log, to the first decision that neither the log nor the
        resolver answers, or to the end of the run. Gives that decision (also `decision`), or None when
        the run is finished.

        The checks are those of `evaluate_study(model, edits, settings, runs=[run], play=…)`, in its
        order; each failure raises the engine's ModelError with the study's diagnostics. An exception of
        the resolver propagates, and the log keeps every pick before it."""
        self.decision = self.trajectory = None
        self.warnings = []
        model, run = self.model, self.run
        edits = _document(self._edits)
        try:
            resolved = study.resolve_edits(model, edits, [run])
        except study.STUDY_FAILURES as exc:
            raise ModelError(_failures(exc)) from None
        problems = study.play_problems(model, resolved, self._play())
        if problems:
            raise ModelError(problems)
        # The engine reads which outcome each pick takes; the log keeps who picked, when and why.
        picks = [{'event': item['event'], 'outcome': item['outcome']} for item in self.picks]
        rs = resolved[run]
        library = thaw(model.library)
        diagnostics = list(study.evidence_warnings(model))
        try:
            checks = [{**item, 'run': run} for item in input_check_failures(rs, library['units'])]
        except study.STUDY_FAILURES as exc:
            raise ModelError(diagnostics + _failures(exc, run=run)) from None
        diagnostics += checks
        if _errors(checks):
            raise ModelError(diagnostics)
        raised = []
        resolver = self._answer(raised) if self.resolver is not None else None
        try:
            trajectory = simulate(
                rs,
                library,
                self.settings,
                play={'control': dict(self.control), 'picks': picks},
                pause_at_decision=True,
                decision_resolver=resolver,
            )
            diagnostics += study.run_checks(rs, trajectory, library, run)
        except study.STUDY_FAILURES as exc:
            if any(exc is item for item in raised):
                raise
            raise ModelError(diagnostics + _failures(exc, run=run)) from None
        if _errors(diagnostics):
            raise ModelError(diagnostics)
        self.trajectory, self.warnings = trajectory, diagnostics
        self.decision = _shown(trajectory.decision) if trajectory.paused else None
        return self.decision

    def pick(self, outcome, reason=None):
        """Answer the decision that waits (`decision`) with `outcome`, for `reason` (or None): the log
        takes the pick, and the next `advance()` goes on from it. Raises ValueError when no decision
        waits, or when `outcome` cannot happen now."""
        if self.decision is None:
            raise ValueError('No decision waits for a pick: call advance() first')
        _check_answer(self.decision, outcome)
        self.picks.append(_entry(self.decision, outcome, reason))
        self.decision = None

    def result(self, times=None):
        """The report of the finished run: `sample_result(evaluate_study(model, edits, settings,
        runs=[run], play=…), reporting_times=times)`. A study that the engine rejects gives its rejected
        report. Raises ValueError when the log leaves a decision without a pick."""
        found = study.evaluate_study(
            self.model,
            self._edits,
            _settings(self.settings),
            runs=[self.run],
            play=self._play(),
        )
        if found.decision is not None:
            decision = found.decision
            raise ValueError(
                f'The log has no pick for {decision["event"]} at t = {decision["t"]:g} h: the run is not '
                'finished'
            )
        return sample_result(found, reporting_times=times)

    def log(self):
        """The play log: `{schema_version, kind, model_hash, implementation_hash, scenario, variant, run,
        options, control, edits, numerical_settings, picks}`, as plain data. `scenario` and `variant`
        name the model by its folders (`paths.names_of`), as a report does."""
        scenario, variant = names_of(self.base.origin)
        context = _context(self.base, self.run, self.control, self.options, self.edits, self.settings)
        return {
            'schema_version': SCHEMA_VERSION,
            'kind': KIND,
            'model_hash': context['model_hash'],
            'implementation_hash': context['implementation_hash'],
            'scenario': scenario,
            'variant': variant,
            **{key: context[key] for key in CONTEXT[2:]},
            'picks': _plain(self.picks),
        }

    def save(self, path):
        """Write the play log (`log`) to `path` as JSON. The file is replaced whole or not at all: the
        log goes to a new file in the same folder first."""
        path = Path(path)
        text = json.dumps(self.log(), indent=2, allow_nan=False) + '\n'
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f'.{path.name}.', suffix='.tmp')
        try:
            with os.fdopen(handle, 'w', encoding='utf-8') as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    @classmethod
    def load(cls, path, model, run, *, control, options=(), edits=None, settings=None, resolver=None):
        """The session of `Session(model, run, …)` that continues the play log at `path` (`save`). The
        log must be of the same context: the hashes of the model and of the engine, the run, the
        options, the control, the edits and the numerical settings. Raises ValueError for a file that
        is not a play log, OtherContext (a ValueError that names each field that differs) for a log of
        another context, and OSError for a file that cannot be read."""
        record = load_json(path)
        if not isinstance(record, Mapping) or (record.get('schema_version'), record.get('kind')) != (
            SCHEMA_VERSION,
            KIND,
        ):
            raise ValueError(f'{path} is not a play log of schema {SCHEMA_VERSION}')
        picks = record.get('picks')
        if not isinstance(picks, list) or not all(isinstance(item, dict) for item in picks):
            raise ValueError(f'{path}: the picks of a play log are a list of objects')
        parsed = NumericalSettings.parse(settings)
        expected = _context(model, run, control, _sorted(options), edits, parsed)
        differ = [key for key in CONTEXT if key not in record or record[key] != expected[key]]
        if differ:
            raise OtherContext(path, differ)
        return cls(
            model,
            run,
            control=control,
            options=options,
            edits=edits,
            picks=picks,
            settings=parsed,
            resolver=resolver,
        )


__all__ = ['OtherContext', 'Session']
