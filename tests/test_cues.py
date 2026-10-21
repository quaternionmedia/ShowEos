"""Cue mapping: which Lights cues become Eos cues, in what order, and what is skipped."""

from showeos.cues import LightCue, plan


def test_only_lights_cues_in_sequence_order():
    got = plan([
        LightCue('2', 'second', 'Lights', 2),
        LightCue('9', 'sound', 'Sound', 0),
        LightCue('1', 'first', 'Lights', 1),
    ])
    assert [(c.number, c.label) for c in got] == [('1', 'first'), ('2', 'second')]
    assert all(c.skip is None for c in got)


def test_decimal_numbers_kept_as_is():
    (c,) = plan([LightCue('13.1', 'cold summer', 'Lights', 0)])
    assert c.number == '13.1' and c.skip is None


def test_non_numeric_number_is_skipped_not_renumbered():
    (c,) = plan([LightCue('q42', 'blackout', 'Lights', 0)])
    assert c.number == 'q42' and c.skip is not None


def test_duplicate_number_skips_later_cue():
    got = plan([LightCue('5', 'a', 'Lights', 0), LightCue('5', 'b', 'Lights', 1)])
    assert got[0].skip is None and got[1].skip == 'duplicate number in this show'


def test_quote_in_label_is_skipped():
    (c,) = plan([LightCue('7', 'the "good" one', 'Lights', 0)])
    assert c.skip is not None and 'quote' in c.skip


def test_missing_name_pushes_empty_label():
    (c,) = plan([LightCue('3', None, 'Lights', 0)])
    assert c.label == '' and c.skip is None


def test_cue_status_gates_the_push():
    from showeos.cues import cue_status

    # known on Eos: never pushed, whatever else is true
    assert cue_status('91', {'91': 'x'}, set(), 0.0, 10.0) == 'exists'
    # sent by us: not pushed again
    assert cue_status('902', {}, {'902'}, 0.0, 10.0) == 'pushed'
    # no check run yet: unknown, so not pushed
    assert cue_status('903', {}, set(), None, 10.0) == 'unchecked'
    # check sent, reply window still open
    assert cue_status('904', {}, set(), 10.0, 10.5) == 'checking'
    # check sent, no reply within the window
    assert cue_status('904', {}, set(), 10.0, 12.5) == 'free'


def test_check_forgets_deleted_cue_so_it_reads_free():
    from types import SimpleNamespace
    from showeos.cues import EosCue
    from showeos.ui.console import _check

    sent = []
    manager = SimpleNamespace(state=SimpleNamespace(cues={'5': 'old name', '6': 'kept'}),
                              send_eos=lambda addr, value=None: sent.append(addr))
    st = {'checked': None, 'pushed': {'5'}}
    _check(manager, [EosCue('5', 'x', None), EosCue('6', 'y', None), EosCue('7', 'z', 'skip')], st)
    assert '5' not in manager.state.cues and '6' not in manager.state.cues
    assert sent == ['/eos/get/cue/1/5', '/eos/get/cue/1/6']
    assert st['pushed'] == set()
