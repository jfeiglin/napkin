"""Audit-only pytest reporter. Load on the controller with -p audit_report_ledger."""

import base64
import json
import os
import sqlite3
from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption('--audit-report-ledger', metavar='NEW.sqlite',
                     help='Write every received test phase to a new local SQLite journal.')


def pytest_configure(config):
    path = config.getoption('--audit-report-ledger')
    if not path or hasattr(config, 'workerinput'):
        return
    path = Path(path).absolute()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError as exc:
        raise pytest.UsageError(f'Cannot create audit report ledger {path}: {exc}') from exc
    os.close(fd)
    connection = sqlite3.connect(path, isolation_level=None)
    config.add_cleanup(connection.close)
    connection.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        CREATE TABLE reports (
            seq INTEGER PRIMARY KEY, nodeid TEXT NOT NULL, phase TEXT NOT NULL,
            outcome TEXT NOT NULL, worker TEXT, duration REAL,
            user_properties TEXT NOT NULL, longrepr TEXT, sections TEXT NOT NULL,
            wasxfail TEXT
        );
        CREATE INDEX reports_by_node ON reports(nodeid, seq);
        CREATE TABLE session (name TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE VIEW node_outcomes AS
        SELECT nodeid, COUNT(*) AS received_reports,
            MAX(phase = 'teardown') AS teardown_received,
            CASE
                WHEN MAX(outcome = 'failed') THEN 'failed'
                WHEN MAX(outcome = 'skipped' AND wasxfail IS NOT NULL) THEN 'xfailed'
                WHEN MAX(outcome = 'skipped') THEN 'skipped'
                WHEN MAX(phase = 'call' AND wasxfail IS NOT NULL) THEN 'xpassed'
                WHEN MAX(phase = 'call' AND outcome = 'passed') THEN 'passed'
                ELSE 'pending'
            END AS observed_outcome
        FROM reports GROUP BY nodeid;
    """)
    connection.executemany('INSERT INTO session VALUES (?, ?)', [
        ('schema_version', '1'), ('pytest_version', pytest.__version__),
        ('invocation', json.dumps(list(config.invocation_params.args))),
    ])
    config.pluginmanager.register(Receiver(connection), 'audit-ledger-controller')


def json_value(value):
    if isinstance(value, bytes):
        return {'base64_bytes': base64.b64encode(value).decode('ascii')}
    return {'python_type': type(value).__qualname__, 'repr': repr(value)}


class Receiver:
    def __init__(self, connection):
        self.connection = connection

    def store(self, report, phase):
        # One INSERT is one transaction. No session finalizer or stdout flush is needed.
        self.connection.execute(
            'INSERT INTO reports(nodeid, phase, outcome, worker, duration, '
            'user_properties, longrepr, sections, wasxfail) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (report.nodeid, phase, report.outcome, getattr(report, 'worker_id', None),
             getattr(report, 'duration', None),
             json.dumps(getattr(report, 'user_properties', ()), default=json_value),
             report.longreprtext if report.longrepr is not None else None,
             json.dumps(list(report.sections), default=json_value), getattr(report, 'wasxfail', None))
        )

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_logreport(self, report):
        self.store(report, report.when)

    @pytest.hookimpl(tryfirst=True)
    def pytest_collectreport(self, report):
        if not report.passed:
            self.store(report, 'collect')

    def pytest_sessionfinish(self, session, exitstatus):
        self.connection.execute('INSERT INTO session VALUES (?, ?)', ('exitstatus', str(int(exitstatus))))
