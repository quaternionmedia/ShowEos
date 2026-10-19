# ShowEOS plan (draft 2)

## Context
- Repo `/home/harpo/ShowEOS` is a near-empty uv project: `pyproject.toml` (name `showeos`, requires-python >=3.14, dep `showrunner>=0.4.0`), stub `main.py`, no commits.
- Goal: a ShowRunner plugin "ShowEOS" for designing and manipulating ETC Eos lighting cues. It must:
  - integrate with ShowScripter cues (layer `Lights`),
  - talk to Eos through ShowRunner's OSC plugin, extended for Eos,
  - show a touch-friendly console-state screen,
  - let the user design custom touch buttons for Eos functions.
- Target: a tablet browser on the LAN, served by ShowRunner's NiceGUI web server. Big hit areas, no hover-only controls.
- Test target: Offline Eos at `192.168.1.141`. TCP 3032 is open (checked). Eos version 3.x.

## Decisions (from user)
1. Scope: (a) Eos control (fire, go/back, active cue and cue list display, command-line text) plus (b) one-way push of Showrunner `Lights` cues into Eos. No two-way editing in v1.
2. Transport: OSC over TCP to Eos port 3032. The user asked for the TCP path to be added.
3. Connection: reuse the existing `/osc` connection config (DB key `osc.settings`). Eos-specific connection options go on the same config page.
4. Console state screen: yes.
5. Custom buttons: yes, with design and run modes. Layouts are stored per show.
6. Test against the Offline Eos at 192.168.1.141.
7. Touch-first UI.

## Findings
### ShowRunner (installed in `.venv`, `showrunner` 0.4.0)
- Plugin discovery: `showrunner/utils.py::get_plugin_manager` loads setuptools entry points in group `showrunner` and instantiates classes. Disabled names come from `[plugins] disabled` in show.toml (matched case-insensitively against the class `__name__`).
- Hooks: `showrunner/hookspecs.py` (register, startup/shutdown(app), get_routes, command, event, nav, status, config_changed).
- Base classes: `showrunner/plugin.py::ShowRunnerPlugin` (`_app`, `emit`).
- ShowOSC: `showrunner/plugins/osc.py`
  - `OscClient(address, port, tcp)`: `connect/send/close`. TCP uses `pythonosc.tcp_client.SimpleTCPClient`.
  - `OscPort` rejects `direction='in'` with `protocol='tcp'` (`_no_tcp_in`). Input is UDP only, via `BlockingOSCUDPServer`.
  - `OscManager(ConnectionManager)`: `open/close/matches/payload/describe`, `send(connection, message, args, port)`, `send_mapping`. Module singleton `_osc`.
  - `ShowOscPlugin(ConnectionPlugin)`: `protocol='osc'`, `page_cls=OscPage` at `/osc`, handles `osc.send` and `osc.mapping`. Routes `/osc`, `/osc/send`, `/osc/send/{name}` come from the module router.
  - `pythonosc` is NOT installed in the venv (`HAS_OSC` is False), so ShowOSC is currently a no-op. It needs the `osc` extra (`showrunner[osc]`, python-osc>=1.10.2).
- Connection layer: `showrunner/connection.py` (`Port`, `Connection`, `Mapping`, `ConnectionSettings`, `ConnectionManager`, `ConnectionPlugin`, `common_routes`).
  - `ConnectionPlugin.showrunner_command` only handles commands whose name starts with `f'{protocol}.'`.
  - `ConnectionPlugin.showrunner_get_routes` returns a single router.
- ConnectionPage: `showrunner/connection_ui.py::ConnectionPage` with hooks `port_fields`, `mapping_fields`, `test_out`, `extra_cards`, and `register()`.
- UI: `showrunner/ui.py::header()`. NiceGUI pages use `ui.page(path)`. Nav entries come from `showrunner_get_nav`.
- DB: `showrunner/models.py`: `Show`, `Script`, `CueList(show_id, name)`, `Cue(cue_list_id, number, name, layer, notes, color, sequence, script_line…)`, `Config(show_id, key, value)`. Access via `showrunner.plugins.db.get_db().session()`.
- Scripter: `showrunner/plugins/scripter.py` has `LAYERS = ['Lights', 'Sound', 'Video', 'Audio', 'Stage']`, the `Cue` editing UI, and `_current_show_id` from `showrunner.ui`.
- ShowLighter (`showrunner/plugins/lighter.py`) is an empty stub. Leave it alone.

### ETC Eos OSC (ETC docs and community posts; verify on Offline Eos)
- TCP: Eos listens on 3032 and is bidirectional on one socket. Framing is SLIP (OSC 1.1), per CueSync's manual. python-osc's `MODE_1_1` = `SLIP_FRAMING` (default `mode` in `TCPClient`/`SimpleTCPClient`). `MODE_1_0` = 4-byte length prefix. So the default client framing matches Eos.
- Eos does not reply with feedback until the client asks. Community posts describe a handshake: send `/eos/ping`, subscribe with `/eos/subscribe` plus int arg 1, and keep pinging. Confirm.
- Addresses (ETC OSC docs):
  - `/eos/key/<name>` with float 1.0 down / 0.0 up (optional edge).
  - `/eos/cue/<list>/<cue>/fire` (float edge optional). `/eos/cue/<list>/<cue>/<part>/fire` also exists.
  - `/eos/chan/<n>/full` (float edge optional).
  - `/eos/cmd` with a string argument, e.g. `"Chan 1 At 75 Enter"`. Without `Enter` it is unterminated.
  - Get and reply: `/eos/get/cue/<list>/<index>` replies `/eos/out/get/cue/<list>/<index>/...`. The "OSC Get" page covers the sync flow.
  - Replies and feedback: `/eos/out/ping`, `/eos/out/active/cue/<list>/<cue>` (float 0.0–1.0), `/eos/out/active/chan` (string), `/eos/out/cmd` (string), `/eos/out/user/<n>/cmd` (string).
  - Unconfirmed: `/eos/user/<n>`, the exact `/eos/subscribe` form, and the cue-list fire form `/eos/cue/<list>/fire`. Check each on the Offline Eos before relying on it.

## Approach
1. **Package** `showeos/` in this repo. Entry point in `pyproject.toml`:
   `[project.entry-points.showrunner] showeos = "showeos.plugin:ShowEosPlugin"`.
2. **Extend ShowOSC instead of forking it** (`showeos/osc.py`):
   - `EosOscPort(OscPort)`: subclass without the `_no_tcp_in` validator, so TCP is allowed on `in` ports.
   - `EosOscSettings(ShowOscSettings)` with `connections: list[EosOscConnection]`. The JSON in DB `osc.settings` stays compatible.
   - `EosOscClient(OscClient)`: one socket for both directions. A reader thread parses SLIP replies and dispatches them. Uses python-osc's TCP dispatch client (confirm the class name: `TCPDispatchClient` is listed in `tcp_client.py`). Keepalive `/eos/ping` on a timer.
   - `EosOscManager(OscManager)`: overrides `open` so `in` TCP ports return the bidirectional client. Adds Eos helpers: `key(name, edge)`, `fire_cue(list, cue)`, `cmd(text)`, `ping()`, `subscribe()`.
3. **Replace the built-in ShowOSC page** instead of duplicating it. The plugin class `EosOscPlugin(ConnectionPlugin)` (or `ShowEosPlugin`) takes over `/osc`:
   - `EosOscPage(OscPage)` adds a TCP option on `in` ports in `port_fields`.
   - Routes `/osc`, `/osc/send`, `/osc/send/{name}` are re-added from our own router.
   - This requires `[plugins] disabled = ["ShowOscPlugin"]` in `show.toml`. **Needs user sign-off** (see questions).
4. **Screens** (`showeos/ui/`):
   - `/eos` console state screen. Shows connection status, ping latency, Eos version, active cue list and cue (name and number), active channels, last command line, active user, and a recent OSC monitor (reuses `manager.monitor`).
   - `/eos/buttons` touch button page. Pages of a grid, with run mode and a lock to design mode. Each button has label, colour, and one action: `fire_cue`, `key`, `cmd` (command-line text), or raw OSC with args.
5. **Storage**: button layouts go in the DB `Config` table under key `eos.buttons`, using the same pattern as `ConnectionManager.save_settings`. Validated with a pydantic model.
6. **Cue push** (`showeos/cues.py`): for the current show, read `Cue` rows with `layer == 'Lights'` from the show's `CueList`s. Map `number` to Eos cue number (sequential if not a number) and `name` to label. Push via `/eos/cmd` text (`Record Cue N Enter` and label command). Exact syntax to be verified on Offline Eos. One-way. Shows a preview list with a Push button.
7. **Scripter integration (v1)**: DB-level only, through `Cue` rows with layer `Lights`. No change to the ShowScripter UI in v1.

## Files to modify / create
- `pyproject.toml`: add `showrunner[osc]` (python-osc) and the `showrunner` entry point. Add `pytest` as a dev dependency.
- `main.py`: remove or leave the stub. Note that `main.py` is not used by the plugin.
- New: `showeos/__init__.py`, `showeos/plugin.py`, `showeos/osc.py`, `showeos/eos.py` (address builders and command helpers), `showeos/cues.py`, `showeos/buttons.py` (models and storage), `showeos/ui/console.py`, `showeos/ui/buttons.py`, `showeos/ui/osc_page.py`.
- New: `tests/` with address-builder, reply-parser, button-config round-trip, and cue-mapping tests.
- New: `README.md` section with the `show.toml` snippet (disable `ShowOscPlugin`, set Eos connection). Current README is empty.

## Reuse
- `showrunner.plugins.osc`: `OscClient`, `OscManager`, `OscPort`, `OscConnection`, `OscMapping`, `ShowOscSettings`, `OscPage`, `_plain`, `_plain_args`, `_loads`, `_valid_any`, `common_routes`.
- `showrunner.connection`: `ConnectionPlugin`, `ConnectionManager` (`apply`, `fan_out`, `record_out`, `on_message`, `monitor`, `get_status`, `port_counts`, `load_settings`, `save_settings`, `activate`).
- `showrunner.connection_ui`: `ConnectionPage` and `valid_json`.
- `showrunner.ui`: `header`, `_current_show_id`.
- `showrunner.plugins.db.get_db`, `showrunner.models`: `Config`, `CueList`, `Cue`, `Show`.
- `showrunner.plugins.scripter.LAYERS` for the layer name.

## Steps
- [x] Add `showrunner[osc]` to deps and run `uv sync` (the venv has no python-osc, so ShowOSC is inert today).
- [x] Verify Eos OSC on Offline Eos (192.168.1.141:3032): ping, subscribe, `/eos/cmd`, key, cue fire, `/eos/get/cue`. Record the exact replies.
- [x] Scaffold package and entry point. Confirm ShowRunner loads it.
- [x] `EosOscPort`, `EosOscSettings`, `EosOscClient` (SLIP reader thread), `EosOscManager`.
- [x] Replace the `/osc` page with the TCP option. Disable built-in `ShowOscPlugin` in show.toml.
- [x] `eos.py` helpers and tests.
- [x] Console state screen `/eos`.
- [x] Touch button designer and runner `/eos/buttons`, with DB storage.
- [ ] Cue push from `Lights` cues. Preview and push.
- [ ] Tests for new logic (address building, reply parsing, button model round-trip, cue mapping).
- [x] README snippet.

## Verification
- `uv run pytest` for unit tests.
- `uv run sr start`. Open `/osc`, add the Eos TCP connection to 192.168.1.141:3032, check the port opens and the monitor shows traffic.
- Against Offline Eos: `/eos/ping` gets `/eos/out/ping`. Fire a cue and see `/eos/out/active/cue/...`. Key press and `/eos/cmd` work.
- Push a Lights cue set and confirm it appears in the Eos cue list.
- Touch check at tablet size (e.g., 1280×800 landscape). Buttons usable without hover.

## Open questions
1. Disable the built-in `ShowOscPlugin` in show.toml and replace the `/osc` page with ours? It is the only clean way to add TCP-in without forking python-osc or ShowRunner. Confirm.
2. "Add the TCP server": I read this as a TCP connection *to* Eos on 3032, which is bidirectional, since Eos is the TCP server. If you meant ShowEOS should *host* a TCP listener for other apps, say so. That needs `ThreadingOSCTCPServer` and is a separate port.
3. Is the Offline Eos reachable from this machine? Port 3032 is open. Permission to send test traffic during implementation is assumed.
