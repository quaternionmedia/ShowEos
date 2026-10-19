"""ShowEOS: ETC Eos control on ShowRunner's OSC connection layer.

Takes over ``/osc`` from ShowOSC (disable ``ShowOscPlugin`` in show.toml) and adds Eos
commands: ``eos.key``, ``eos.cue``, ``eos.cmd``.
"""

from fastapi import APIRouter, HTTPException
from loguru import logger
from showrunner.connection import ConnectionPlugin, common_routes
from showrunner.plugins.osc import OscSend, _plain_args
import showrunner

from .osc import EosOscManager
from .ui import buttons as buttons_ui, console
from .ui.osc_page import EosOscPage

_eos = EosOscManager()
router = APIRouter(prefix='/osc', tags=['ShowEOS'])
common_routes(router, _eos, 'ShowEOS', lambda: True)


@router.post('/send')
async def post_send(body: OscSend):
    connection = body.connection or _eos.default_output()
    if not connection:
        raise HTTPException(400, 'no output connection configured')
    try:
        _eos.send(connection, body.message, body.args, body.port)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except Exception as e:  # every port it went to failed
        raise HTTPException(502, str(e))
    return {'sent': body.message, 'args': _plain_args(body.args)}


@router.post('/send/{mapping_name}')
async def post_mapping(mapping_name: str):
    try:
        _eos.send_mapping(mapping_name)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(502, str(e))
    return {'sent': 'mapping', 'name': mapping_name}


class ShowEosPlugin(ConnectionPlugin):
    """Commands: ``osc.send``, ``osc.mapping``, ``eos.key``, ``eos.cue``, ``eos.cmd``."""

    protocol = 'osc'
    label = 'ShowEOS'
    description = 'ETC Eos control over OSC/TCP: console state, touch buttons, cue push'
    version = '0.1.0'
    nav_label = 'OSC'
    icon = 'lightbulb'
    nav_order = 31
    manager = _eos
    router = router
    page_cls = EosOscPage

    @showrunner.hookimpl
    def showrunner_startup(self, app) -> None:
        if any(type(p).__name__ == 'ShowOscPlugin' for p in app.pm.get_plugins()):
            logger.error('ShowOscPlugin is also loaded: add it to [plugins] disabled in show.toml')
        super().showrunner_startup(app)
        console.register(self.manager)
        buttons_ui.register(self.manager)

    @showrunner.hookimpl
    def showrunner_command(self, command_name: str, data: dict | None) -> None:
        if not command_name.startswith('eos.'):
            return super().showrunner_command(command_name, data)
        try:
            self.handle_command(command_name, data or {})
        except Exception as e:
            logger.warning(f'{command_name} failed: {e}')

    def handle_command(self, command_name: str, d: dict) -> None:
        if command_name == 'osc.send':
            conn = d.get('connection') or _eos.default_output()
            if not conn:
                raise KeyError('no output connection configured')
            _eos.send(conn, d['message'], d.get('args'), d.get('port'))
        elif command_name == 'osc.mapping':
            _eos.send_mapping(d['mapping'])
        elif command_name == 'eos.key':
            _eos.press(d['key'])
        elif command_name == 'eos.cue':
            _eos.fire_cue(int(d['list']), str(d['cue']))
        elif command_name == 'eos.cmd':
            _eos.command(d['text'])

    @showrunner.hookimpl
    def showrunner_get_nav(self):
        return [
            super().showrunner_get_nav(),
            {'label': 'Eos', 'path': '/eos', 'icon': 'monitor', 'order': 32},
            {'label': 'Eos buttons', 'path': '/eos/buttons', 'icon': 'touch_app', 'order': 33},
        ]
