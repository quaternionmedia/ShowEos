"""Button model: validation per action, the OSC each button sends, and JSON round-trip."""

import pytest
from pydantic import ValidationError

from showeos import buttons as model
from showeos.buttons import EosButton, EosLayout, EosPage


def test_cue_button_fires_list_and_cue():
    b = EosButton(label='Go 13', action='cue', target='1/13.1')
    assert model.messages(b) == [('/eos/cue/1/13.1/fire', None)]


def test_key_button_presses_then_nothing_on_release():
    b = EosButton(label='GO', action='key', target='go_0')
    assert model.messages(b) == [('/eos/key/go_0', 1.0)]


def test_raw_osc_button_passes_args_through():
    b = EosButton(label='Ch 1 full', action='osc', target='/eos/chan/1', args=[100])
    assert model.messages(b) == [('/eos/chan/1', [100])]


@pytest.mark.parametrize(
    'action, target',
    [('cue', '13'), ('cue', 'a/b'), ('key', 'Go Key'), ('cmd', '   '), ('osc', 'eos/cmd')],
)
def test_invalid_target_rejected(action, target):
    with pytest.raises(ValidationError):
        EosButton(label='x', action=action, target=target)


def test_label_length_limited():
    with pytest.raises(ValidationError):
        EosButton(label='x' * 41, target='1/1')


def test_layout_round_trips_through_json():
    layout = EosLayout(pages=[
        EosPage(name='Main', buttons=[
            EosButton(label='Go 13', color='positive', action='cue', target='1/13'),
            EosButton(label='Clear', action='cmd', target='Clear Enter'),
            EosButton(label='Ch 1', action='osc', target='/eos/chan/1', args=[50, 'x']),
        ]),
        EosPage(name='Specials'),
    ])
    again = EosLayout.model_validate_json(layout.model_dump_json())
    assert again == layout
    assert again.pages[1].buttons == []


def test_default_layout_has_one_page():
    assert [p.name for p in EosLayout().pages] == ['Main']
