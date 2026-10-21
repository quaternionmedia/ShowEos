# ETC Eos OSC: verified on Offline Eos 3.3.9.25 (192.168.1.141)

Verified by probe against the live Offline Eos; show "LittleWomen", list 1 has 45 cues.

## Transport
- **TCP 3032, length-prefixed framing (OSC 1.0 style).** Each message is a 4-byte big-endian length followed by the OSC datagram. This is `pythonosc` `MODE_1_0`, NOT the default `MODE_1_1` (SLIP). The SLIP assumption in the first plan was wrong.
- TCP is bidirectional on one socket. Replies arrive on the same socket.
- **UDP:** `/eos/ping` sent to 192.168.1.141:8000 returns replies to local UDP 8001.

## Verified addresses
| Send | Reply / effect |
|---|---|
| `/eos/ping` `"<str>"` | `/eos/out/ping` `["<str>"]` plus a state burst (`/eos/out/active/cue/text`, `/eos/out/show/name`, `/eos/out/user`, `/eos/out/cmd`, ...) |
| `/eos/subscribe` `1` | accepted, no separate reply seen |
| `/eos/get/version` | `/eos/out/get/version` `["3.3.9.25", "3.3.9.2", 0]` |
| `/eos/get/cue/1/count` | `/eos/out/get/cue/1/count` `[45]` |
| `/eos/get/cue/1/1` | `/eos/out/get/cue/1/1/0/list/0/31` (cue detail, name is arg 2 "preshow thoughts") |
| `/eos/key/live` `1.0` then `0.0` | `/eos/out/event/state` `[1]`, `/eos/out/cmd` "LIVE: Cue 13" |
| `/eos/cue/1/1/fire` `1.0` | fires; `/eos/out/event/cue/1/1/fire` `["preshow thoughts"]`; `/eos/out/active/cue/text` |
| `/eos/cue/1/13/fire` (no args) | fires |
| `/eos/cmd` `"Clear"` (unterminated) | `/eos/out/cmd` `["... - Error: Syntax Error", 1]` |
| `/eos/cmd` `"Clear Enter"` | `/eos/out/cmd` `[..., 0]` |

## Reply addresses seen
- `/eos/out/active/cue/text` `"1/13 cold summer 25.0 100%"` (number, name, time, percent)
- `/eos/out/pending/cue/text`, `/eos/out/previous/cue/text`
- `/eos/out/active/cue/1/13` `[1.0]` (per-cue active flag)
- `/eos/out/cmd` `[text, error_flag]`, `/eos/out/user/<n>/cmd`
- `/eos/out/user` `[1]`, `/eos/out/show/name` `["LittleWomen"]`
- `/eos/out/active/chan` `[""]`, `/eos/out/event/state`, `/eos/out/event/locked`
- `/eos/out/softkey/<n>`, `/eos/out/wheel`, `/eos/out/switch`

## Not yet verified
- Go and Back keys (`/eos/key/go_0`, `/eos/key/back`): verify before wiring buttons.
- Record and label command syntax for cue push.

## Keys (step 7 checks)
- `/eos/key/go_0` 1.0 then 0.0: VERIFIED. Fires the pending cue: `/eos/out/event/cue/1/90/fire`, active becomes 1/90, pending 1/90.1.
- `/eos/key/back`: sent, no visible state change on Offline Eos. Not used on the console screen until checked on a real show.
- `/eos/key/stop_back`: REJECTED. Eos echoes `Cue 1 / Stop Back - Error: Syntax Error`, so the key name is not valid.

## Verified later (Offline Eos 3.3.9.25)

- `/eos/key/go_0`: fires on press (1.0). A release (0.0) fires GO again, so only the press is sent.
- `/eos/key/back`: no visible change in two probes. Not verified; not used by the console.
- Command line label: `Label <text> Enter` after the console selects a cue. Quotes are stored
  literally (`"x"` becomes `"x"` with quotes). The console keeps the selected cue (e.g. `Cue 91`)
  on the command line, so a label can land on the selected cue, not the one you typed.
- `/eos/cue/1/91/label` (OSC): no effect on the cue name.
- `Record` and `Delete` were not run. Probe side effects on the offline show were restored.
  Cue 1/91 is named `but darker`.
- Command line stays in error state until cancelled; `/eos/key/cancel` then `Clear Enter` helped.
  Plain `Clear` without Enter is a syntax error.

## Eos user (verified 99, Offline Eos 3.3.9.25)

- `/eos/user` with int 99 is echoed as `/eos/out/user [99]`. After that, `/eos/cmd` replies come
  on `/eos/out/user/99/cmd`, so the socket's commands run as user 99.
- Subscribing and state replies come from the connection's user, and user 99 has its own
  active cue (`LIVE: Cue 0.1`).
- Setting: `[plugins.showosc] eos_user = 99` in `show.toml` (test server). Unset = no `/eos/user`
  message, Eos default user 1.
- Probe side effect: user 99's command line on Offline Eos is stuck with `Record Cue 91 Clear -
  Error: Syntax Error`. Clear (`/eos/cmd` '', `Clear Enter`, `/eos/key/clear`) did not reset it.
  User 1's line was cleared. Restart the Eos session or clear it at the console.

## Record and label (not verified safe)

- `Record Cue 1/97 Enter` (user 99) returned `Record Cue 91 1/97 - Error: Syntax Error`. Eos
  inserts `Cue 91` (the last recorded or selected cue) before typed text.
- Cue numbers 1/96, 1/97, 1/98, 1/500 already exist on Offline Eos. Recording over a used number
  overwrites it, so a push must check `/eos/get/cue/1/<n>` first and refuse existing numbers.
- Cue 1/91 ("but darker") was checked intact after every probe.

## Label an existing cue (blocked, not safe yet)

- Goal: an existing numbered cue (e.g. 1/97 'receding rain') gets the ShowRunner label.
- The command line always starts with the active cue, shown as `Cue 91` in the echo. A typed
  `Cue 1/97` after it fails: `Cue 91 1/97 - Error: Syntax Error`, also via `/eos/newcmd`.
- `Label <name> Enter` renames the active cue (91), never the typed one. Tested: 1/91 renamed to
  `probe` and restored to `but darker`. 1/97 was not changed.
- Eos/OSC ways to select cue 1/97 without the prefix are not found yet. Re-check on a clean desk.

## Record a new cue (verified on users 1 and 99, Offline Eos 3.3.9.25)

- `/eos/newcmd` `Record Cue 904 Label probe Enter` creates cue 1/904 named 'probe' (verified). Echo
  `LIVE: Cue 904 : Record Cue 904 Label probe #`. The same without `Label ...` makes an empty name.
- Record over an existing number overwrites it. The push therefore sends only numbers that a
  `/eos/get/cue/1/<n>` reply did not report within 2 s (`showeos/cues.py` `cue_status`).
- Before each record the push sends `Clear Enter` on the same socket.
- Delete: `Delete Cue 904 Enter` answers `Please Confirm` (flag 1); a second `Enter` deletes it.
  Used to clean up probe cues 901, 902, 903, 904. Count back to 45.
- Probe side effect: user 1's active cue moved from 91 to 700 ('stormy thoughts'). Not restored.
- User 99's command line on this desk kept `Record Cue 91 ...` residue. `Clear Enter` did not clear
  it, and no `/eos/out/user/99/cmd` reply came back for `Clear Enter`. Recording as user 99 failed
  with the `Cue 91` prefix, so the push cannot yet be trusted on the 99 socket.
- The user's old template had `p{cue.page}`. ShowRunner's Cue has no page field, so the label is
  `name` only.

## Rename an existing cue (update: doc-sourced, not yet run)

- ETC OSC Dictionary (Eos Online Help, OSC Set): `/eos/set/cue/<list>/<number>/label` with a string
  argument. The earlier `/eos/cue/1/91/label` probe had no effect and is a different address.
- `showeos/eos.py` `set_cue_label(cue, label)` sends it. The push renames only numbers that already
  exist and whose name differs. It never records over them.
- VERIFIED on Offline Eos (user 99): `/eos/set/cue/1/905/label` 'push a' -> 'push a2' renamed the
  cue; the get reply confirmed the name. Cue 1/91 was renamed by mistake to 'should not change' and
  restored to 'but darker' with the same address (verified by get reply).
- Absent cue: `/eos/get/cue/1/<n>` gets a reply `/eos/out/get/cue/1/<n> []` with NO args. Existing:
  `/eos/out/get/cue/1/<n>/0/list/0/31 [-1, uid, name, ...]`; name is args[2]. The fx, links and
  actions sub-replies also have args and no name.

- Push end to end (user 99): check -> 905 'push a' renamed, 906 'push b' untouched, 907 'push c'
  recorded (`Record Cue 907 Label push c #`). Throwaway cues deleted; count back to 45.
