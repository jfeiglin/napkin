"""The live view's server (`ui/server.py`): what it answers, against the view's own frames of the same run.

One server with one worker serves one place of the session's places, and a page of a temporary folder."""

import http.client
import json
import threading

import pytest

from napkin import evaluate_study
from scenarios.water_controls_wipe.tests import family
from scenarios.water_controls_wipe.ui import server, view
from tests.helpers import catalogue_model

PAGE = b'<!doctype html><title>page</title>'


@pytest.fixture(scope='module')
def served(tmp_path_factory):
    dist = tmp_path_factory.mktemp('dist')
    (dist / 'index.html').write_bytes(PAGE)
    (dist.parent / 'secret.txt').write_text('outside the page')
    name = family.places()[0]
    engine = server.Engine([name], jobs=1)
    found = server.server(engine, 0, dist=dist)
    thread = threading.Thread(target=found.serve_forever, daemon=True)
    thread.start()
    yield name, found.server_address[1]
    found.shutdown()
    found.server_close()
    engine.close()


def get(port, path, host='localhost'):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=600)
    connection.request('GET', path, headers={'Host': f'{host}:{port}'})
    response = connection.getresponse()
    body = response.read()
    connection.close()
    return response.status, body


def test_the_places_are_those_it_serves(served):
    name, port = served
    status, body = get(port, '/api/places')
    assert status == 200
    assert [p['id'] for p in json.loads(body)['places']] == [name]


def test_a_frame_from_the_server_is_the_views_frame_of_the_same_run(served):
    name, port = served
    key = name.split(':', 1)[1]
    status, body = get(port, f'/api/places/{key}')
    assert status == 200
    place = json.loads(body)
    model = catalogue_model(name)
    assert place == json.loads(json.dumps(view.describe(model, name)))
    run = place['featured']
    status, body = get(port, f'/api/places/{key}/runs/{run}')
    assert status == 200
    study = evaluate_study(model, None, runs=[run])
    assert json.loads(body) == json.loads(json.dumps(view.frame(model, study, run)))


def test_it_refuses_what_it_does_not_serve(served):
    name, port = served
    key = name.split(':', 1)[1]
    assert get(port, '/api/places/no_such_place')[0] == 404
    assert get(port, f'/api/places/{key}/runs/no_such_run')[0] == 404
    assert get(port, '/api/nothing')[0] == 404
    assert get(port, '/../secret.txt')[0] == 404
    assert get(port, '/%2e%2e/secret.txt')[0] == 404
    assert get(port, '/api/places', host='example.com')[0] == 403
    assert get(port, '/') == (200, PAGE)
