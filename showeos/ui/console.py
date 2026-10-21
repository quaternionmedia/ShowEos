"""``/eos``: touch-friendly console state screen. Reads ``EosOscManager.state``."""

import time

from nicegui import ui

from showrunner.ui import _current_show_id, header
from showeos import cues as cue_map
from showeos import eos


def register(manager) -> None:
    @ui.page('/eos')
    def page() -> None:
        build(manager)


def _act(fn) -> None:
    try:
        fn()
    except Exception as e:  # no connection, or every port failed
        ui.notify(str(e), type='negative', multi_line=True)


def _check(manager, plan, st) -> None:
    st['checked'] = time.monotonic()
    st['pushed'].clear()  # the Eos readback decides now, not what this session pushed earlier
    for c in plan:
        if c.skip is None:
            # Eos sends nothing for a deleted cue, so forget the old name; the reply re-adds it
            manager.state.cues.pop(c.number, None)
            manager.send_eos(*eos.get_cue(1, c.number))


def _push(manager, plan, st) -> None:
    for c in plan:
        if c.skip:
            continue
        status = cue_map.cue_status(c.number, manager.state.cues, st['pushed'], st['checked'], time.monotonic())
        if status == 'exists':  # existing number: rename it, never record over it
            if c.label and manager.state.cues.get(c.number) != c.label:
                manager.send_eos(*eos.set_cue_label(c.number, c.label))
        elif status == 'free':
            manager.send_eos(*eos.command('Clear Enter'))  # a leftover command-line text would be prefixed
            manager.send_eos(*eos.record_cue(c.number, c.label))
            st['pushed'].add(c.number)


def build(manager) -> None:
    ui.dark_mode(True)
    header()
    show_id = _current_show_id()
    if show_id != manager.show_id:
        manager.activate(show_id)
    plan = cue_map.plan(cue_map.lights_cues(show_id)) if show_id else []
    st = {'checked': None, 'pushed': set()}

    with ui.column().classes('w-full max-w-6xl mx-auto p-4 gap-4'):
        with ui.row().classes('w-full items-center gap-4'):
            title = ui.label().classes('text-h5')
            ui.space()
            status = ui.label().classes('text-h6')

        with ui.row().classes('w-full gap-4 no-wrap items-stretch'):
            with ui.card().classes('grow'):
                ui.label('Active cue').classes('text-grey text-h6')
                active_no = ui.label().classes('text-h2 font-bold')
                active_name = ui.label().classes('text-h4')
                ui.separator()
                pending = ui.label().classes('text-h6')
                previous = ui.label().classes('text-h6 text-grey')
            with ui.card().classes('grow'):
                ui.label('Command line').classes('text-grey text-h6')
                cmd = ui.label().classes('text-h5 font-mono break-all')
                ui.separator()
                info = ui.label().classes('text-body1')
                channels = ui.label().classes('text-body1 font-mono')

        with ui.row().classes('w-full gap-4'):
            ui.button('GO', icon='play_arrow',
                      on_click=lambda: _act(lambda: manager.press('go_0'))
                      ).props('color=positive size=xl').classes('grow min-h-24 text-h4')

        with ui.card().classes('w-full'):
            ui.label('Push Lights cues as new Eos cues').classes('text-h6')
            ui.label('Existing Eos cue numbers are never overwritten. Check on Eos first, then push.'
                     ).classes('text-grey')
            if not plan:
                ui.label('No Lights cues for this show.').classes('text-grey')
            with ui.row().classes('gap-2'):
                ui.button('Check on Eos', icon='fact_check',
                          on_click=lambda: _act(lambda: _check(manager, plan, st)))
                ui.button('Push new cues', icon='upload',
                          on_click=lambda: _act(lambda: _push(manager, plan, st))).props('color=primary')
            cue_status = {}
            for c in plan:
                with ui.row().classes('items-center gap-4'):
                    ui.label(c.number).classes('font-mono w-20')
                    ui.label(c.label).classes('w-64')
                    cue_status[c.number] = ui.label().classes('text-grey')

        with ui.card().classes('w-full'):
            ui.label('Monitor').classes('text-h6')
            log = ui.log(max_lines=100).classes('w-full h-48 font-mono text-xs')

    last = {'seq': 0}

    def tick() -> None:
        s = manager.state
        n, total = manager.port_counts()
        err = next((e for e in manager.errors.values()), None)
        status.set_text('● connected' if total and n == total else f'○ {err or "not connected"}')
        status.classes(replace='text-h6 text-green' if total and n == total else 'text-h6 text-red')
        title.set_text(f'Eos {s.version or "?"} · {s.show or "no show"}')
        active_no.set_text(s.active.get('number', '–'))
        active_name.set_text(s.active.get('name', ''))
        pending.set_text(f'Pending  {s.pending.get("number", "–")}  {s.pending.get("name", "")}')
        previous.set_text(f'Previous {s.previous.get("number", "–")}  {s.previous.get("name", "")}')
        cmd.set_text(s.cmd or '—')
        cmd.classes(replace='text-h5 font-mono break-all text-red' if s.cmd_error
                    else 'text-h5 font-mono break-all')
        latency = f'{s.latency_ms:.0f} ms' if s.latency_ms is not None else '—'
        info.set_text(f'User {s.user if s.user is not None else "–"} · '
                      f'{"LOCKED" if s.locked else "unlocked"} · latency {latency}')
        channels.set_text(f'Channels: {s.channels or "–"}')
        for c in plan:
            cue_status[c.number].set_text(c.skip or cue_map.cue_status(
                c.number, s.cues, st['pushed'], st['checked'], time.monotonic()))
        for e in manager.monitor.copy():  # deque.copy is atomic vs. the protocol thread
            if e['seq'] > last['seq']:
                last['seq'] = e['seq']
                log.push(manager.describe(e))

    ui.timer(0.25, tick)
