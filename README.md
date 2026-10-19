# ShowEOS

ShowRunner plugin for ETC Eos lighting control: a console state screen and touch
buttons with your own Eos actions. It runs on ShowRunner's OSC connection layer.

## Install

```sh
uv sync
```

Entry point: `showeos = "showeos.plugin:ShowEosPlugin"` (group `showrunner`).

## Configure

In the show's `show.toml`, turn off ShowRunner's built-in OSC plugin (ShowEOS owns `/osc`)
and add the Eos console as a connection:

```toml
[plugins]
disabled = ["ShowOscPlugin"]

[plugins.showosc]
eos_user = 99  # optional: commands run as Eos user 99; omit for the Eos default user
[[plugins.showosc.connections]]
name = "eos"
ports = [{ name = "tcp", direction = "out", address = "192.168.1.141", port = 3032, protocol = "tcp" }]
```

`eos_user` is sent as `/eos/user` on every (re)connect, so key presses and commands on that
socket run as that user. Unset, Eos uses its default user. The `/osc` page shows the value but
does not edit it. A show with a saved OSC row in its database ignores `show.toml`, so set
`eos_user` in that saved row too.

On the Eos console, enable OSC in Setup. Eos TCP port 3032 is bidirectional: the same socket
sends commands and receives feedback (length-prefixed frames, verified on Offline Eos 3.3.9.25).
Details: `docs/eos-osc.md`.

## Screens

- `/eos`: console state. Active, pending and previous cue, command line (red on error), user,
  lock state, latency, a GO button and a monitor log.
- `/eos/buttons`: touch pages of buttons. **Run** presses them. **Design** adds, edits, moves,
  and deletes buttons and pages. Layouts are saved per show.
- `/osc`: connection settings and raw OSC test, same as ShowOSC.

Button actions: `cue` (fire `list/cue`, e.g. `1/13.1`), `key` (press an Eos key, e.g. `go_0`),
`cmd` (command line text ending in Enter, e.g. `Clear Enter`), `osc` (raw address and args).

## Development

```sh
uv run pytest
```

Tests: `tests/test_eos.py` (address building, reply parsing, TCP framing against a fake Eos) and
`tests/test_buttons.py` (button validation, OSC mapping, JSON round-trip).

## Limits

- Cue push from Lights cues is not implemented. `showeos/cues.py` maps Lights cues to Eos cue
  numbers (decimal numbers only), but Eos Record and Label syntax is not verified safe (see
  `docs/eos-osc.md`).
- Back and Stop/Back keys are not verified; the console has only GO.
