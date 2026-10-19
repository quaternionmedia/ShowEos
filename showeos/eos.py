"""ETC Eos OSC addresses and reply parsing. Pure functions, no I/O.

Addresses were verified on Offline Eos 3.3.9.25; see docs/eos-osc.md.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

# "1/13 cold summer 25.0 100%": cue number, name, optional time, optional percent.
_CUE_TEXT = re.compile(r'^(?P<number>\S+)\s+(?P<name>.+?)(?:\s+[\d.]+)?(?:\s+\d+%)?$')


def key_press(name: str) -> list[tuple[str, float]]:
    """Press a key, e.g. 'live', 'go_0'. Press edge only: a release also fires GO (verified)."""
    return [(f'/eos/key/{name}', 1.0)]


def fire_cue(cue_list: int, cue: str) -> tuple[str, None]:
    """Fire a cue, e.g. list 1, cue '13.1' -> /eos/cue/1/13.1/fire."""
    return f'/eos/cue/{cue_list}/{cue}/fire', None


def command(text: str) -> tuple[str, str]:
    """Send command-line text. Include 'Enter' to run it."""
    return '/eos/cmd', text


def ping(stamp: float) -> tuple[str, str]:
    """Ping; Eos echoes the stamp back in /eos/out/ping for latency."""
    return '/eos/ping', repr(stamp)


def get_version() -> tuple[str, None]:
    """Reply: /eos/out/get/version [version, ...]."""
    return '/eos/get/version', None


def subscribe() -> tuple[str, int]:
    """Ask Eos to send feedback (cue fires, command line, active cue) on this socket."""
    return '/eos/subscribe', 1


def set_user(user: int) -> tuple[str, int]:
    """Make this socket's commands run as Eos user N (e.g. 99). Unset = Eos default user."""
    return '/eos/user', user


def handshake(user: int | None, stamp: float) -> list[tuple[str, Any]]:
    """Messages sent on every (re)connect, in order. The user comes first so it covers the rest."""
    msgs: list[tuple[str, Any]] = []
    if user is not None:
        msgs.append(set_user(user))
    msgs += [subscribe(), get_version(), ping(stamp)]
    return msgs


def parse_cue_text(text: str) -> dict[str, str]:
    """Split an Eos cue text reply into its number and name."""
    text = text.strip()
    m = _CUE_TEXT.match(text)
    if m:
        return {'number': m['number'], 'name': m['name']}
    number, _, name = text.partition(' ')
    return {'number': number, 'name': name.strip()}


@dataclass
class EosState:
    """Console state, filled from Eos replies (see ``update``)."""

    version: str = ''
    show: str = ''
    user: int | None = None
    cmd: str = ''  # last command-line text Eos echoed
    cmd_error: bool = False
    active: dict[str, str] = field(default_factory=dict)  # {'number', 'name'}
    pending: dict[str, str] = field(default_factory=dict)
    previous: dict[str, str] = field(default_factory=dict)
    channels: str = ''
    locked: bool = False
    latency_ms: float | None = None

    def update(self, address: str, args: list[Any]) -> None:
        first = args[0] if args else None
        if address == '/eos/out/get/version':
            self.version = str(first or '')
        elif address == '/eos/out/show/name':
            self.show = str(first or '')
        elif address == '/eos/out/user':
            self.user = first
        elif address == '/eos/out/cmd':
            self.cmd = str(first or '')
            self.cmd_error = len(args) > 1 and bool(args[1])
        elif address == '/eos/out/active/cue/text':
            self.active = parse_cue_text(str(first or ''))
        elif address == '/eos/out/pending/cue/text':
            self.pending = parse_cue_text(str(first or ''))
        elif address == '/eos/out/previous/cue/text':
            self.previous = parse_cue_text(str(first or ''))
        elif address == '/eos/out/active/chan':
            self.channels = str(first or '')
        elif address == '/eos/out/event/locked':
            self.locked = bool(first)
        elif address == '/eos/out/ping':
            try:
                self.latency_ms = (time.monotonic() - float(first)) * 1000
            except (TypeError, ValueError):
                pass
