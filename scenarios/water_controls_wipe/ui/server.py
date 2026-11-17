"""The package's live view: a local HTTP server that runs the engine on each place and run that the page asks
for, and serves the page (ui/README.md).

The engine runs in worker processes, because a compiled model keeps caches that one thread at a time may use.
Each place always goes to the same worker, which compiles it once; each worker uses the run store of the
checkout, so a run that the store holds comes back at once. The server keeps the frames that it made last
in memory and makes each one once, however many requests ask for it."""

import json
import mimetypes
import multiprocessing
import threading
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor
from functools import cache
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from napkin import evaluate_study, load_scenario, store
from scenarios.water_controls_wipe.ui import view
from tools import catalogue

DIST = Path(__file__).resolve().parent / 'web' / 'dist'
HOSTS = ('localhost', '127.0.0.1')
FRAMES = 96  # the frames that the server keeps in memory


# --- In each worker ------------------------------------------------------------------------------


def _start(directory):
    store.activate(directory)


@cache
def _model(name):
    return load_scenario(catalogue.scenario_path(view.ROOT, name))


def describe(name):
    """The description of a place (`view.describe`)."""
    return view.describe(_model(name), name)


def frame(name, run):
    """The frame of one run of a place (`view.frame`), or the errors that stop the run."""
    model = _model(name)
    study = evaluate_study(model, None, runs=[run])
    if not study.admissible:
        return {'errors': [d for d in study.diagnostics if d.get('severity') == 'error']}
    return view.frame(model, study, run)


# --- In the server -------------------------------------------------------------------------------


class Engine:
    """The worker processes and what they made: each place's description and the frames of its runs."""

    def __init__(self, names, jobs=4, use_store=True):
        self.names = tuple(names)
        context = multiprocessing.get_context('spawn')
        directory = store.default_directory() if use_store else None
        count = max(1, min(jobs, len(self.names)))
        self.workers = [
            ProcessPoolExecutor(1, mp_context=context, initializer=_start, initargs=(directory,))
            for _ in range(count)
        ]
        self.lock = threading.Lock()
        self.descriptions = {name: self._worker(name).submit(describe, name) for name in self.names}
        self.frames = OrderedDict()

    def _worker(self, name):
        return self.workers[self.names.index(name) % len(self.workers)]

    def description(self, name):
        return self.descriptions[name].result()

    def frame(self, name, run):
        """The frame of a run, made once: a request for a frame that a worker makes waits for it."""
        key = (name, run)
        with self.lock:
            found = self.frames.get(key)
            if found is None or (found.done() and found.exception() is not None):
                found = self.frames[key] = self._worker(name).submit(frame, name, run)
            self.frames.move_to_end(key)
            while len(self.frames) > FRAMES:
                oldest = next(iter(self.frames))
                if not self.frames[oldest].done():
                    break
                del self.frames[oldest]
        return found

    def warm(self, name):
        """Ask for each run of a place, the featured run first, so that a change of run is quick."""
        place = self.description(name)
        runs = [r['id'] for r in place['runs']]
        for run in [place['featured'], *(r for r in runs if r != place['featured'])]:
            self.frame(name, run)

    def close(self):
        for worker in self.workers:
            worker.shutdown(wait=False, cancel_futures=True)


def summary(place):
    """What the map and the menu of places show of a place."""
    return {
        'id': place['id'],
        'key': place['key'],
        'name': place['name'],
        'title': place['title'],
        'systems': len(place['systems']),
        'people': place['people'],
        'hospitals': sum(len(s['hospitals']) for s in place['systems']),
    }


class Handler(BaseHTTPRequestHandler):
    """GET only: the API under /api/, and the built page's files."""

    server_version = 'water-view'
    engine: Engine
    dist: Path
    hosts: tuple

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        host = (self.headers.get('Host') or '').rsplit(':', 1)[0].strip('[]')
        if host not in self.hosts:
            return self.send_json(
                HTTPStatus.FORBIDDEN, {'error': 'This server answers only on this computer.'}
            )
        path = unquote(urlsplit(self.path).path)
        if path == '/api' or path.startswith('/api/'):
            return self.api([part for part in path.split('/')[2:] if part])
        return self.file(path)

    def api(self, parts):
        engine = self.engine
        keys = {name.split(':', 1)[1]: name for name in engine.names}
        if parts == ['places']:
            places = [summary(engine.description(name)) for name in engine.names]
            return self.send_json(
                HTTPStatus.OK, {'package': engine.description(engine.names[0])['package'], 'places': places}
            )
        if len(parts) >= 2 and parts[0] == 'places' and parts[1] not in keys:
            return self.send_json(HTTPStatus.NOT_FOUND, {'error': 'No such place.', 'places': sorted(keys)})
        if len(parts) == 2 and parts[0] == 'places':
            name = keys[parts[1]]
            place = engine.description(name)
            threading.Thread(target=engine.warm, args=(name,), daemon=True).start()
            return self.send_json(HTTPStatus.OK, place)
        if len(parts) == 4 and parts[0] == 'places' and parts[2] == 'runs':
            name, run = keys[parts[1]], parts[3]
            runs = [r['id'] for r in engine.description(name)['runs']]
            if run not in runs:
                return self.send_json(HTTPStatus.NOT_FOUND, {'error': 'No such run.', 'runs': runs})
            found = engine.frame(name, run).result()
            if 'errors' in found:
                return self.send_json(HTTPStatus.UNPROCESSABLE_ENTITY, found)
            return self.send_json(HTTPStatus.OK, found)
        return self.send_json(HTTPStatus.NOT_FOUND, {'error': 'No such address.'})

    def file(self, path):
        root = self.dist.resolve()
        target = (root / path.lstrip('/')).resolve()
        if target.is_dir():
            target = target / 'index.html'
        if not target.is_relative_to(root) or not target.is_file():
            return self.send_json(HTTPStatus.NOT_FOUND, {'error': 'No such file.'})
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header('Content-Type', mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(len(body)))
        self.send_header(
            'Cache-Control', 'no-cache' if target.suffix == '.html' else 'max-age=31536000, immutable'
        )
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, payload):
        body = json.dumps(payload, separators=(',', ':'), allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)


def server(engine, port=8765, dist=DIST, hosts=HOSTS):
    """A server of `engine` and of the page in `dist` on 127.0.0.1 (port 0: a free port), which answers
    requests whose `Host` names one of `hosts`."""
    handler = type('Bound', (Handler,), {'engine': engine, 'dist': Path(dist), 'hosts': tuple(hosts)})
    found = ThreadingHTTPServer(('127.0.0.1', port), handler)
    found.daemon_threads = True
    return found
