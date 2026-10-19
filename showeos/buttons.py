"""Touch button layouts for Eos: the pydantic model, per-show DB storage, and the OSC each
button sends. Pure except ``load``/``save``.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from loguru import logger
from pydantic import BaseModel, Field, ValidationError, model_validator
from showrunner.connection import get_db
from showrunner.models import Config
from showrunner.plugins.osc import OscArgs
from sqlmodel import select

from . import eos

CONFIG_KEY = 'eos.buttons'
Color = Literal['primary', 'secondary', 'accent', 'positive', 'negative', 'warning', 'info', 'dark']
_CUE = re.compile(r'^\d+/\d+(\.\d+)?$')  # "list/cue", e.g. "1/13" or "1/13.1"
_KEY = re.compile(r'^[a-z0-9_]+$')  # Eos key names: "go_0", "live", "stop_back"


class EosButton(BaseModel):
    label: str = Field(..., min_length=1, max_length=40)
    color: Color = 'primary'
    action: Literal['cue', 'key', 'cmd', 'osc'] = 'cue'
    target: str = Field('', max_length=200)  # cue "list/cue"; key name; cmd text; osc address
    args: OscArgs = None  # osc only: one value or a list

    @model_validator(mode='after')
    def _target_fits_action(self):
        t = self.target
        if self.action == 'cue' and not _CUE.match(t):
            raise ValueError("cue target must be 'list/cue', e.g. '1/13.1'")
        if self.action == 'key' and not _KEY.match(t):
            raise ValueError("key target must be a key name, e.g. 'go_0'")
        if self.action == 'cmd' and not t.strip():
            raise ValueError('command target is empty')
        if self.action == 'osc' and not t.startswith('/'):
            raise ValueError("OSC target must start with '/'")
        return self


class EosPage(BaseModel):
    name: str = Field(..., min_length=1, max_length=24)
    buttons: list[EosButton] = Field(default_factory=list)


class EosLayout(BaseModel):
    pages: list[EosPage] = Field(default_factory=lambda: [EosPage(name='Main')], min_length=1)


def messages(button: EosButton) -> list[tuple[str, Any]]:
    """The (address, value) OSC messages this button sends, in order."""
    if button.action == 'cue':
        cue_list, cue = button.target.split('/', 1)
        return [eos.fire_cue(int(cue_list), cue)]
    if button.action == 'key':
        return eos.key_press(button.target)
    if button.action == 'cmd':
        return [eos.command(button.target)]
    return [(button.target, button.args)]


def load(show_id: int | None) -> EosLayout:
    """Layout saved for ``show_id``, else the default one-page layout."""
    if show_id is None:
        return EosLayout()
    try:
        with get_db().session() as s:
            row = s.exec(
                select(Config).where(Config.show_id == show_id, Config.key == CONFIG_KEY)
            ).first()
        if row and row.value:
            return EosLayout.model_validate_json(row.value)
    except (ValidationError, ValueError) as e:
        logger.warning(f'Eos buttons for show {show_id} unreadable, using default: {e}')
    return EosLayout()


def save(show_id: int, layout: EosLayout) -> None:
    with get_db().session() as s:
        row = s.exec(
            select(Config).where(Config.show_id == show_id, Config.key == CONFIG_KEY)
        ).first()
        if row is None:
            row = Config(show_id=show_id, key=CONFIG_KEY)
        row.value = layout.model_dump_json()
        s.add(row)
        s.commit()
