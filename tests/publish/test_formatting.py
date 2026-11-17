"""The text of an input in the Python summaries."""

from napkin.model.structure import Parameter
from tools.publish.texts import _text_options, input_text


def test_a_loss_reads_with_its_sign_before_the_currency():
    assert input_text(-500, 'USD2025_m') == '-$500m'
    assert input_text(500, 'USD2025_m') == '$500m'


def test_only_a_bool_input_reads_as_a_switch_whatever_its_evidence():
    # A share defined by identity is a number: 0 and 1 read as shares, not as No and Yes.
    identity = {'kind': 'identity', 'explanation': 'By definition.'}
    share = {
        'entity': 'thing',
        'label': 'Share',
        'path': 'thing/share',
        'unit': 'fraction',
        'value': 1,
        'adjust': {'mode': 'range', 'min': 0, 'max': 1},
        'basis': identity,
    }
    assert _text_options(Parameter.of(share))['switch'] is False
    assert input_text(1, 'fraction', **_text_options(Parameter.of(share))) == '100%'
    control = {**share, 'metadata': {'control': 'binary'}}
    assert input_text(1, 'fraction', **_text_options(Parameter.of(control))) == 'Yes'
