"""Address building, reply parsing, and the TCP framing against a fake Eos."""

import socket
import struct
import threading

from pythonosc.osc_message import OscMessage
from pythonosc.osc_message_builder import build_msg

from showeos import eos
from showeos.osc import EosClient


def test_key_press_sends_press_edge_only():
    assert eos.key_press('go_0') == [('/eos/key/go_0', 1.0)]


def test_fire_cue_keeps_decimal_cue_number():
    assert eos.fire_cue(1, '13.1') == ('/eos/cue/1/13.1/fire', None)


def test_command_and_subscribe():
    assert eos.command('Clear Enter') == ('/eos/cmd', 'Clear Enter')
    assert eos.subscribe() == ('/eos/subscribe', 1)


def test_parse_cue_text_active_with_percent():
    assert eos.parse_cue_text('1/13 cold summer 25.0 100%') == {'number': '1/13', 'name': 'cold summer'}


def test_parse_cue_text_pending_without_percent():
    assert eos.parse_cue_text('1/90 dreary drizzle 35.0') == {'number': '1/90', 'name': 'dreary drizzle'}


def test_parse_cue_text_keeps_numeric_word_in_name():
    assert eos.parse_cue_text('1/1 Act 2 5.0 100%') == {'number': '1/1', 'name': 'Act 2'}


def test_state_update_from_replies():
    st = eos.EosState()
    st.update('/eos/out/show/name', ['LittleWomen'])
    st.update('/eos/out/user', [1])
    st.update('/eos/out/active/cue/text', ['1/13 cold summer 25.0 100%'])
    st.update('/eos/out/cmd', ['LIVE: Cue 1 : Clear - Error: Syntax Error', 1])
    st.update('/eos/out/event/locked', [0])
    assert (st.show, st.user, st.active) == ('LittleWomen', 1, {'number': '1/13', 'name': 'cold summer'})
    assert st.cmd_error is True and st.locked is False


def test_state_ignores_unknown_and_empty_replies():
    st = eos.EosState()
    st.update('/eos/out/active/cue/text', [])
    st.update('/eos/out/unknown', [1])
    assert st.active == {'number': '', 'name': ''}


def _fake_eos(replies: list[bytes], received: list[bytes]):
    """One-connection TCP server that speaks Eos framing: 4-byte big-endian length + OSC."""
    srv = socket.socket()
    srv.bind(('127.0.0.1', 0))
    srv.listen(1)

    def run():
        conn, _ = srv.accept()
        buf = bytearray()
        while len(received) < 1:
            data = conn.recv(4096)
            if not data:
                break
            buf += data
            while len(buf) >= 4 and len(buf) >= 4 + struct.unpack('!I', buf[:4])[0]:
                (n,) = struct.unpack('!I', buf[:4])
                received.append(bytes(buf[4 : 4 + n]))
                del buf[: 4 + n]
        for r in replies:
            conn.sendall(struct.pack('!I', len(r)) + r)
        conn.close()
        srv.close()

    threading.Thread(target=run, daemon=True).start()
    return srv.getsockname()[1]


def test_client_sends_length_prefixed_and_reads_replies():
    received: list[bytes] = []
    reply = build_msg('/eos/out/ping', ['stamp']).dgram
    port = _fake_eos([reply], received)
    got = []
    client = EosClient('127.0.0.1', port, on_message=lambda a, args: got.append((a, args)),
                       on_lost=lambda c: got.append('lost'))
    client.send(*eos.subscribe())
    for _ in range(100):  # wait for the reply and the peer-closed notice
        if len(got) >= 2:
            break
        threading.Event().wait(0.05)
    client.close()
    assert OscMessage(received[0]).address == '/eos/subscribe'
    assert OscMessage(received[0]).params == [1]
    assert got[0] == ('/eos/out/ping', ['stamp'])
    assert got[1:] == ['lost']  # the fake server closed after replying


def test_set_user_only_when_configured():
    assert eos.handshake(None, 1.0)[0][0] == '/eos/subscribe'  # unset: Eos default user
    assert ('/eos/user', 99) in eos.handshake(99, 1.0)
    assert [m for m, _ in eos.handshake(99, 1.0)][:2] == ['/eos/user', '/eos/subscribe']


def test_user_setting_must_be_positive():
    import pytest
    from pydantic import ValidationError

    from showeos.osc import EosOscSettings

    assert EosOscSettings(eos_user=99).eos_user == 99
    assert EosOscSettings().eos_user is None
    with pytest.raises(ValidationError):
        EosOscSettings(eos_user=0)
