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
