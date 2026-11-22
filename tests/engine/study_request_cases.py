"""Each fixed sample must have the same selected values and budget outcome when run alone."""

from dataclasses import replace

from napkin.engine.sampling import SamplingSettings, sampled
from napkin.engine.timeline import read, run
from napkin.engine.uncertainty import monte_carlo
from napkin.model.compile import compile_text
from napkin.program.config import Request
from napkin.program.record import Key


def study_case(seed, pieces, initial_selection, samples):
    target = ('red', 'blue')[seed % 2]
    other = 'blue' if target == 'red' else 'red'
    baseline = 7 + seed % 11
    change = 1 + seed % 5
    threshold = ('0.5', '0.55', '0.6')[seed % 3]
    source = f"""scenario "Two counters"
    horizon 2 h
yard:
    input roll = uniform(0, 1).draw()
    {target} = {baseline}
    {other} = 3
    update = event():
        after 1 h:
            this.{target} = {baseline + change} if this.roll > {threshold} else {baseline}
yard.update.start()
"""
    model = compile_text(source, {'h': {'time': 1}})
    key = Key('yard', (target,))
    selected = Request(2, everything=False, keys=(key,), pieces=pieces)
    request = {
        'selected': selected,
        'other': replace(selected, keys=(Key('yard', (other,)),)),
        'full': replace(selected, everything=True, keys=()),
    }[initial_selection]
    path = f'yard.{target}'
    times = (0, 2)
    settings = SamplingSettings(samples, seed)
    study = monte_carlo(model.program, replace(model.configuration, request=request), [path], times, settings)
    outcomes = {}
    central = study.central.values[0]
    outcomes['central'] = (
        (None, path, (baseline, baseline)),
        (study.central.stopped, central.path, central.values),
    )
    config = replace(model.configuration, request=selected)
    found = {sample.seed: sample for sample in study.samples}
    configurations = sampled(config, settings)
    outcomes['seed order'] = (
        tuple(c.seed for c in configurations),
        tuple(sample.seed for sample in study.samples),
    )
    for index, sample_config in enumerate(configurations):
        solo = run(model.program, sample_config)
        failure = solo.failure
        stop = None if failure is None else f'the run failed at {failure.t:g} h: {failure.detail("message")}'
        if failure is not None:
            assert (failure.t, failure.detail('budget')) == (1, pieces)
        values = read(solo, model.program, (path,), times)[0].values
        sample = found.get(sample_config.seed)
        outcomes[sample_config.seed] = (
            (stop, values),
            None if sample is None else (sample.stopped, sample.values[0]),
        )
        if stop is not None:
            expected_reason = f'sample {index} (seed {sample_config.seed}) stops: {stop}'
            outcomes[f'refusal.{sample_config.seed}'] = True, expected_reason in (study.refused or '')
    refused = [key for key, pair in outcomes.items() if isinstance(key, int) and pair[0][0] is not None]
    outcomes['refusal'] = bool(refused), study.refused is not None
    return source, outcomes


def check_study_request(seed):
    pieces = 1 if seed % 4 != 3 else 2
    selection = ('selected', 'other', 'full')[seed % 3]
    source, outcomes = study_case(seed, pieces, selection, samples=3)
    differences = {str(key): pair for key, pair in outcomes.items() if pair[0] != pair[1]}
    assert not differences, (seed, selection, pieces, source, differences)
