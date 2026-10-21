"""Lights cues from ShowRunner, mapped to the Eos cues they would become. Pure mapping plus one read.

Only the plan lives here; nothing is written to Eos. Eos list 1 is assumed (shortcut: one Eos list).
"""

from __future__ import annotations

import re
from typing import NamedTuple

from showrunner.connection import get_db
from showrunner.models import Cue, CueList
from sqlmodel import select

_NUMERIC = re.compile(r'^\d+(\.\d+)?$')  # Eos cue numbers used here: 13 or 13.1 only


class LightCue(NamedTuple):
    number: str | None
    name: str | None
    layer: str | None
    sequence: int


class EosCue(NamedTuple):
    number: str  # Eos cue number in list 1, e.g. '13.1'
    label: str
    skip: str | None  # why it is not pushed; None when it is pushable


def plan(cues: list[LightCue]) -> list[EosCue]:
    """Lights cues in sequence order. Non-numeric or duplicate numbers are skipped, not renumbered."""
    out: list[EosCue] = []
    seen: set[str] = set()
    for c in sorted(cues, key=lambda c: c.sequence):
        if c.layer != 'Lights':
            continue
        number = (c.number or '').strip()
        label = (c.name or '').strip()
        skip = None
        if not _NUMERIC.match(number):
            skip = 'number is not a decimal Eos cue number'
        elif number in seen:
            skip = 'duplicate number in this show'
        elif '"' in label:
            skip = 'label has a quote, which the Eos command line would store literally'
        seen.add(number)
        out.append(EosCue(number, label, skip))
    return out


def cue_status(number: str, known: dict[str, str], pushed: set[str], checked_at: float | None, now: float,
               wait: float = 2.0) -> str:
    """'exists' | 'pushed' | 'unchecked' | 'checking' | 'free'. Only 'free' may be recorded."""
    if number in known:
        return 'exists'
    if number in pushed:
        return 'pushed'
    if checked_at is None:
        return 'unchecked'
    # shortcut: 'free' = no get reply within 2 s; upgrade to a real reply wait if Eos runs slow
    return 'free' if now - checked_at >= wait else 'checking'


def lights_cues(show_id: int) -> list[LightCue]:
    """All cues of the show's cue lists (the reader; the mapping is in ``plan``)."""
    with get_db().session() as s:
        rows = s.exec(
            select(Cue).join(CueList, Cue.cue_list_id == CueList.id).where(CueList.show_id == show_id)
        ).all()
        return [LightCue(r.number, r.name, r.layer, r.sequence) for r in rows]
