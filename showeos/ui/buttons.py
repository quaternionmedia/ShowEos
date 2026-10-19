"""``/eos/buttons``: touch button pages. Run mode presses; design mode edits and saves per show."""

from __future__ import annotations

import json
from typing import Any, get_args

from nicegui import ui
from pydantic import ValidationError

from showrunner.ui import _current_show_id, header

from .. import buttons as model
from ..buttons import Color, EosButton, EosPage

ACTIONS = {'cue': 'Fire cue', 'key': 'Press key', 'cmd': 'Command line', 'osc': 'Raw OSC'}
HINTS = {
    'cue': "list/cue, e.g. 1/13 or 1/13.1",
    'key': 'Eos key name, e.g. go_0, live, back',
    'cmd': 'Command text, end with Enter, e.g. Clear Enter',
    'osc': 'OSC address, e.g. /eos/cmd or /eos/user/1',
}
TILE = 'grid gap-3 w-full'
TILE_STYLE = 'grid-template-columns: repeat(auto-fill, minmax(180px, 1fr))'


def register(manager) -> None:
    @ui.page('/eos/buttons')
    def page() -> None:
        build(manager)


def _act(fn) -> None:
    try:
        fn()
    except Exception as e:  # no connection, or every port failed
        ui.notify(str(e), type='negative', multi_line=True)


def run(manager, b: EosButton) -> None:
    for address, value in model.messages(b):
        manager.send_eos(address, value)


def build(manager) -> None:
    ui.dark_mode(True)
    header()
    show_id = _current_show_id()
    if show_id != manager.show_id:
        manager.activate(show_id)

    st: dict[str, Any] = {'layout': model.load(show_id), 'page': 0, 'design': False}

    def persist() -> None:
        if show_id is not None:
            model.save(show_id, st['layout'])

    def current() -> EosPage:
        return st['layout'].pages[st['page']]

    @ui.refreshable
    def tabs() -> None:
        with ui.row().classes('w-full items-center gap-2'):
            for i, pg in enumerate(st['layout'].pages):
                ui.button(pg.name, on_click=lambda i=i: select(i)).props(
                    'size=lg unelevated' if i == st['page'] else 'size=lg outline'
                ).classes('min-h-12')
            if st['design']:
                ui.button('New page', icon='add', on_click=add_page).props('size=lg flat')
                if len(st['layout'].pages) > 1:
                    ui.button('Delete page', icon='delete', on_click=confirm_delete_page
                              ).props('size=lg flat color=negative')

    @ui.refreshable
    def grid() -> None:
        with ui.element('div').classes(TILE).style(TILE_STYLE):
            for i, b in enumerate(current().buttons):
                ui.button(b.label, color=b.color,
                          on_click=lambda b=b, i=i: edit(b, i) if st['design'] else _act(
                              lambda: run(manager, b))
                          ).classes('min-h-24 text-h6 text-wrap')
            if st['design']:
                ui.button('Add button', icon='add', on_click=lambda: edit(None, None)
                          ).props('outline').classes('min-h-24 text-h6')

    def select(i: int) -> None:
        st['page'] = i
        tabs.refresh()
        grid.refresh()

    def add_page() -> None:
        st['layout'].pages.append(EosPage(name=f'Page {len(st["layout"].pages) + 1}'))
        st['page'] = len(st['layout'].pages) - 1
        persist()
        tabs.refresh()
        grid.refresh()

    def confirm_delete_page() -> None:
        pg = current()
        with ui.dialog() as dlg, ui.card().classes('gap-3'):
            ui.label(f'Delete page "{pg.name}" and its {len(pg.buttons)} buttons?').classes('text-h6')
            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('Cancel', on_click=dlg.close).props('flat')
                ui.button('Delete', color='negative', on_click=lambda: (delete_page(), dlg.close())
                          )
        dlg.open()

    def delete_page() -> None:
        st['layout'].pages.pop(st['page'])
        st['page'] = max(0, st['page'] - 1)
        persist()
        tabs.refresh()
        grid.refresh()

    def edit(b: EosButton | None, index: int | None) -> None:
        pg = current()
        draft: dict[str, Any] = b.model_dump() if b else {
            'label': '', 'color': 'primary', 'action': 'cue', 'target': '', 'args': None}

        def save() -> None:
            try:
                nb = EosButton.model_validate(draft)
            except ValidationError as e:
                ui.notify(e.errors()[0]['msg'].removeprefix('Value error, '),
                          type='negative', multi_line=True)
                return
            if index is None:
                pg.buttons.append(nb)
            else:
                pg.buttons[index] = nb
            finish()

        def finish() -> None:
            persist()
            grid.refresh()
            dlg.close()

        def move(delta: int) -> None:
            j = index + delta
            if 0 <= j < len(pg.buttons):
                pg.buttons[index], pg.buttons[j] = pg.buttons[j], pg.buttons[index]
                finish()

        def remove() -> None:
            pg.buttons.pop(index)
            finish()

        with ui.dialog() as dlg, ui.card().classes('w-[560px] max-w-full gap-3'):
            ui.label('Edit button' if b else 'New button').classes('text-h5')
            ui.input('Label', value=draft['label'],
                     on_change=lambda e: draft.update(label=e.value)).classes('w-full text-h6')
            with ui.row().classes('w-full items-center gap-3 no-wrap'):
                ui.select(list(get_args(Color)), label='Colour', value=draft['color'],
                          on_change=lambda e: draft.update(color=e.value)).classes('w-40')
                ui.select(ACTIONS, label='Action', value=draft['action'],
                          on_change=lambda e: (draft.update(action=e.value),
                                               hint.set_text(HINTS[e.value]),
                                               args_in.set_visibility(e.value == 'osc'))
                          ).classes('grow')
            ui.input('Target', value=draft['target'],
                     on_change=lambda e: draft.update(target=e.value)).classes('w-full')
            hint = ui.label(HINTS[draft['action']]).classes('text-sm text-grey')
            args_in = ui.input(
                'Args (JSON, optional)',
                value='' if draft['args'] is None else json.dumps(draft['args']),
                validation={'Invalid JSON': _valid_json},
                on_change=lambda e: _set_args(draft, e.value),
            ).classes('w-full')
            args_in.set_visibility(draft['action'] == 'osc')
            with ui.row().classes('w-full items-center gap-2'):
                if b is not None:
                    ui.button(icon='arrow_back', on_click=lambda: move(-1)).props('flat round')
                    ui.button(icon='arrow_forward', on_click=lambda: move(1)).props('flat round')
                    ui.button('Delete', icon='delete', color='negative', on_click=remove
                              ).props('flat')
                ui.space()
                ui.button('Test', icon='play_arrow',
                          on_click=lambda: _act(lambda: run(manager, EosButton.model_validate(draft)))
                          ).props('outline')
                ui.button('Save', icon='save', on_click=save).props('color=primary')
        dlg.open()

    with ui.column().classes('w-full max-w-7xl mx-auto p-4 gap-4'):
        with ui.row().classes('w-full items-center gap-4'):
            ui.label('Eos buttons').classes('text-h5')
            if show_id is None:
                ui.label('no show: changes not saved').classes('text-warning')
            ui.space()
            ui.toggle({'run': 'Run', 'design': 'Design'}, value='run',
                      on_change=lambda e: set_mode(e.value == 'design')).props(
                'unelevated size=lg')
        tabs()
        grid()

    def set_mode(design: bool) -> None:
        st['design'] = design
        tabs.refresh()
        grid.refresh()


def _valid_json(text: str) -> bool:
    try:
        json.loads(text) if text else None
        return True
    except ValueError:
        return False


def _set_args(draft: dict, text: str) -> None:
    if _valid_json(text):
        draft['args'] = json.loads(text) if text else None
