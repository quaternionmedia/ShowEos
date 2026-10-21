"""Eos extensions to ShowRunner's OSC connection layer.

Eos TCP (3032) is one bidirectional socket with 4-byte length-prefixed frames, not SLIP
(verified on Offline Eos; see docs/eos-osc.md). A TCP ``out`` port therefore both sends
and receives: the reader thread feeds replies into ``on_message`` like a UDP input.
"""

from __future__ import annotations

import socket
import struct
import threading
import time
from typing import Any, Callable, Literal

from loguru import logger
from pydantic import Field
from pythonosc.osc_message import OscMessage
from pythonosc.osc_message_builder import build_msg
from showrunner.connection import Connection
from showrunner.plugins.osc import (
    OscConnection,
    OscManager,
    OscPort,
    ShowOscSettings,
    _plain,
)

from . import eos

KEEPALIVE_SECONDS = 5.0  # Eos may drop an idle socket; a ping also refreshes latency


class EosOscPort(OscPort):
    """Eos defaults: TCP to the console's OSC port 3032."""

    port: int = Field(3032, ge=1, le=65535)
    protocol: Literal['udp', 'tcp'] = 'tcp'


class EosOscConnection(OscConnection):
    ports: list[EosOscPort] = Field(..., min_length=1)


class EosOscSettings(ShowOscSettings):
    auto_reconnect: bool = True  # a TCP socket can die silently; reopen it
    eos_user: int | None = Field(default=None, ge=1)  # None: Eos default user, e.g. 99 for tests
    connections: list[EosOscConnection] = Field(default_factory=list)


class EosClient:
    """One TCP socket to Eos. Sends from any thread; a reader thread delivers replies.

    ``on_message(address, args)`` runs on the reader thread. ``on_lost(self)`` runs once if
    the peer closes or errors while the client is still open.
    """

    def __init__(
        self,
        address: str,
        port: int,
        on_message: Callable[[str, list], None],
        on_lost: Callable[['EosClient'], None],
    ) -> None:
        self.on_message = on_message
        self.on_lost = on_lost
        self._send_lock = threading.Lock()
        self._stop = threading.Event()
        self._last_send = time.monotonic()
        self.sock = socket.create_connection((address, port), timeout=2.0)
        self.sock.settimeout(1.0)  # reader wakes this often to check _stop and keepalive
        self._thread = threading.Thread(target=self._read, daemon=True, name='eos-reader')
        self._thread.start()

    def send(self, message: str, value: Any = None) -> None:
        dgram = build_msg(message, '' if value is None else value).dgram
        with self._send_lock:
            self.sock.sendall(struct.pack('!I', len(dgram)) + dgram)
            self._last_send = time.monotonic()

    def _read(self) -> None:
        buf = bytearray()
        while not self._stop.is_set():
            try:
                data = self.sock.recv(65536)
            except socket.timeout:
                if time.monotonic() - self._last_send > KEEPALIVE_SECONDS:
                    self._keepalive()
                continue
            except OSError:
                break
            if not data:
                break
            buf += data
            while len(buf) >= 4:
                (size,) = struct.unpack('!I', buf[:4])
                if len(buf) < 4 + size:
                    break
                dgram = bytes(buf[4 : 4 + size])
                del buf[: 4 + size]
                try:
                    msg = OscMessage(dgram)
                except Exception:  # not OSC: skip the frame, keep the socket
                    continue
                try:
                    self.on_message(msg.address, [_plain(a) for a in msg.params])
                except Exception as e:  # a bad handler must not kill the socket's reader
                    logger.warning(f'Eos reply {msg.address} not handled: {e}')
        if not self._stop.is_set():
            self.on_lost(self)

    def _keepalive(self) -> None:
        try:
            self.send(*eos.ping(time.monotonic()))
        except OSError:
            pass  # the next recv sees the dead socket and reports it lost

    def close(self) -> None:
        self._stop.set()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()


class EosOscManager(OscManager):
    protocol = 'osc'  # keeps the osc.* commands, events and /osc routes
    settings_cls = EosOscSettings
    settings_key = 'osc.settings'  # same DB row as ShowOSC, so settings carry over
    toml_section = 'showosc'

    def __init__(self) -> None:
        super().__init__()
        self.state = eos.EosState()

    def open(self, conn: Connection, port: EosOscPort) -> Any:
        if port.direction != 'out' or port.protocol != 'tcp':
            return super().open(conn, port)
        key = (conn.name, port.name)
        client = EosClient(
            port.address,
            port.port,
            on_message=lambda addr, args: self.on_message(
                key[0], key[1], {'message': addr, 'args': args, 'host': port.address}
            ),
            on_lost=lambda c: self._lost(key, c),
        )
        try:
            for message, value in eos.handshake(self.settings.eos_user, time.monotonic()):
                client.send(message, value)  # ping stamp gives a first latency sample now
        except OSError:
            client.close()
            raise
        return client

    def _lost(self, key: tuple[str, str], client: EosClient) -> None:
        """Drop a dead socket so refresh() reopens it. Ignored if already replaced."""
        with self._lock:
            if self.handles.get(key) is not client:
                return
            del self.handles[key]
            self.errors[key] = 'connection lost'
        self.log('WARNING', key, 'connection lost')
        self._emit('disconnected', {'connection': key[0], 'port': key[1]})

    def close(self, key: tuple[str, str], handle: Any) -> None:
        if isinstance(handle, EosClient):
            handle.close()
        else:
            super().close(key, handle)

    def on_message(self, connection: str, port: str, msg: dict) -> None:
        self.state.update(msg['message'], msg['args'])
        super().on_message(connection, port, msg)

    # -- Eos helpers --------------------------------------------------------

    def send_eos(self, message: str, value: Any = None) -> None:
        conn = self.default_output()
        if not conn:  # the loaded settings have no enabled Output port; saved row wins over show.toml
            names = ', '.join(c.name for c in self.settings.connections) or 'none'
            raise KeyError(f'no enabled Eos output port (connections: {names}); save an Output port on /osc')
        self.send(conn, message, value)

    def press(self, name: str) -> None:
        for message, value in eos.key_press(name):
            self.send_eos(message, value)

    def fire_cue(self, cue_list: int, cue: str) -> None:
        self.send_eos(*eos.fire_cue(cue_list, cue))

    def command(self, text: str) -> None:
        self.send_eos(*eos.command(text))
