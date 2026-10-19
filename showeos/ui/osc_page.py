"""``/osc`` page for ShowEOS: ShowOSC's page, bound to the Eos manager, with TCP defaults."""

from showrunner.plugins.osc import OSC_COMMANDS, OscPage


class EosOscPage(OscPage):
    title = 'OSC (ETC Eos)'
    commands = OSC_COMMANDS + ['eos.key', 'eos.cue', 'eos.cmd']
    port_defaults = {'address': '127.0.0.1', 'port': 3032, 'protocol': 'tcp'}

    def test_out(self, m) -> None:
        conn = m.connection or self.manager.default_output()
        if not conn:
            raise KeyError('no output connection configured')
        self.manager.send(conn, m.message, m.args, m.port or None)

    def extra_cards(self, ui) -> None:
        # shortcut: the raw test sender card is gone; mapping Test buttons cover raw sends
        # shortcut: eos_user is read-only here; ConnectionPage's draft would overwrite edits, so set it in show.toml
        user = self.manager.settings.eos_user
        with ui.card():
            ui.label('Eos user').classes('text-h6')
            ui.label(
                f'{user}: commands run as this user (set in show.toml, [plugins.showosc] eos_user)'
                if user
                else 'not set: commands run as the Eos default user'
            )
