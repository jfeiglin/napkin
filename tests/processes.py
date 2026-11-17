"""Work for the tests of processes: stand-ins for a simulation that a new process imports quickly."""

import os
import time


class Failure(Exception):
    """The failure of a stand-in simulation."""


def slow_run(rs, library, settings):
    """A simulation that takes `rs['seconds']` and gives its run and the process that ran it; a run
    with `fails` raises Failure instead."""
    time.sleep(rs['seconds'])
    if rs.get('fails'):
        raise Failure(f'{rs["run"]} fails')
    return {'run': rs['run'], 'process': os.getpid()}
