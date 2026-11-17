"""Resource-only cache controls preserve reuse within a test and release results after it."""

import gc
from contextlib import contextmanager
from functools import cache
from types import SimpleNamespace
from weakref import WeakSet, ref

import pytest

import conftest
from tests import result_cache as caches


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch):
    monkeypatch.setattr(caches, '_CACHES', WeakSet())


def test_registered_results_reuse_values_until_cleared():
    calls = []

    @caches.result_cache()
    def result(key):
        calls.append(key)
        return object()

    first = result('a')
    assert result('a') is first
    assert calls == ['a']
    assert result.cache_parameters() == {'maxsize': None, 'typed': False}
    assert caches.clear_result_caches() == 1
    assert result('a') is not first
    assert calls == ['a', 'a']


def test_registered_results_keep_the_requested_lru_limit():
    calls = []

    @caches.result_cache(maxsize=2)
    def result(key):
        calls.append(key)
        return object()

    first = result('a')
    result('b')
    assert result('a') is first
    result('c')
    assert result('a') is first
    result('b')
    assert calls == ['a', 'b', 'c', 'b']
    assert result.cache_parameters() == {'maxsize': 2, 'typed': False}
    assert caches.clear_result_caches() == 2


def test_empty_caches_do_not_request_garbage_collection(monkeypatch):
    collected = []
    monkeypatch.setattr(caches.gc, 'collect', lambda: collected.append(True))
    assert caches.clear_result_caches() == 0

    @caches.result_cache()
    def result():
        return object()

    assert caches.clear_result_caches() == 0
    assert collected == []
    result()
    assert caches.clear_result_caches() == 1
    assert collected == [True]
    assert caches.clear_result_caches() == 0
    assert collected == [True]


def test_clearing_results_releases_cycles_and_preserves_unregistered_caches():
    class Value:
        pass

    @caches.result_cache()
    def result():
        value = Value()
        value.cycle = value
        return value

    @cache
    def compiled_model():
        return Value()

    retained_result = ref(result())
    retained_model = ref(compiled_model())
    assert retained_result() is not None
    assert caches.clear_result_caches() == 1
    assert retained_result() is None
    assert retained_model() is compiled_model()
    assert compiled_model.cache_info().currsize == 1


def test_registry_does_not_extend_a_cache_function_lifetime():
    @caches.result_cache()
    def result():
        return object()

    result()
    registered = ref(result)
    del result
    gc.collect()
    assert registered() is None
    assert caches.clear_result_caches() == 0


@pytest.mark.parametrize('cache_scope', ['session', 'test'])
@pytest.mark.parametrize('failed', [False, True])
def test_protocol_releases_results_after_teardown_only_when_requested(monkeypatch, cache_scope, failed):
    @caches.result_cache()
    def result():
        return object()

    @cache
    def compiled_model():
        return object()

    first = result()
    model = compiled_model()
    events = []

    @contextmanager
    def use_store(directory):
        events.append('entered')
        try:
            yield
        finally:
            # The result remains reusable until the entire test protocol exits.
            assert result() is first
            events.append('left')

    monkeypatch.setattr(conftest.store, 'use', use_store)
    monkeypatch.setattr(conftest, 'uses_store', lambda path: False)
    item = SimpleNamespace(path=None, config=SimpleNamespace(getoption=lambda name: cache_scope))
    protocol = conftest.pytest_runtest_protocol(item, None)
    next(protocol)
    assert events == ['entered']
    assert result() is first
    if failed:
        error = RuntimeError('teardown failed')
        with pytest.raises(RuntimeError, match='teardown failed') as caught:
            protocol.throw(error)
        assert caught.value is error
    else:
        completed = object()
        with pytest.raises(StopIteration) as caught:
            protocol.send(completed)
        assert caught.value.value is completed
    assert events == ['entered', 'left']
    assert (result() is first) == (cache_scope == 'session')
    assert compiled_model() is model
