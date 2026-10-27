# Changelog

## v2.1.0 (2026-10-27)

New feature:

- **12 Fill 2:** a second fill. Hold PAGE, then also FUNC: Fill 2 instead of Fill 1 (also with the fill latched by
  TRACK + PAGE). New trig conditions **FIL2** (plays only in Fill 2) and **!FIL2** (plays except in Fill 2), right
  after FILL / !FILL in the list. During Fill 2, FILL trigs are silent and !FILL trigs play. Patterns from the stock OS
  load unchanged.

**No Elektron code in the repository.** Patches 00–11 write exactly the same bytes as in v2.0.0.

- Where a hook moves original firmware instructions into a patch's own code (and where the delay effects reuse the
  firmware's delay-time calculation), the patch files no longer contain those bytes. They hold a placeholder plus a
  SHA-256 (`from_original`), and `tools/build.py` copies the bytes from your own firmware file.
- The generators in `src/` no longer contain original bytes either: hook checks are a length plus a SHA-256, and
  moved instructions are read from your image.
- The groove MIDI clips are no longer in the repository; `grooves/grooves.json` holds the groove tables.

Docs: the README and the project page list the patches newest first.

## v2.0.0 (2026-10-26)

**Modular.** Every feature can now be installed on its own. Things several features share (gesture handling,
popups, SETTINGS as a modifier, slow effect selection, pattern storage) moved into a small **core** (patch 00).
Patches that belong together are grouped: the reverb effects in one patch, the delays in another.

New features:

- **10 Control mode:** CONTROL ALL relative (stock) or absolute; hold TRACK + tap SETTINGS to switch. Also for
  TRACK + LEVEL (volume), FUNC + TRACK + LEVEL (pan) and the humanize of the groove patch.
- **11 Trig select:** a selection mode for trigs (SETTINGS + PAGE). Tap trigs to select them, FUNC + PAGE for all;
  knobs, note / velocity / length, nudge and copy / paste / clear locks then act on all selected trigs. With control
  mode Absolute, all selected trigs take the value of the first one.

Changed:

- **Effect choices, delay speed, strum and groove are now stored in the pattern**, like humanize already was. Every
  pattern can have its own reverb-slot effect, delay, strum and groove. They are no longer device settings.
- The load meter is now always off after power-on (in v1.0.0 it could come up on, because that RAM is not cleared at
  start-up).

The sound of every effect, the strum, the grooves and humanize is bit-identical to v1.0.0 (checked by the tests).

### Patch numbers

| v2.0.0 | Contains (v1.0.0) |
|---|---|
| 00 core | new; the shared parts of 05 and 09 |
| 01 mute-solo, 02 live-mute, 03 hold-mute, 04 delay-notes | 01–04, unchanged |
| 05 reverb-fx | 05 Chorus, 06 Phaser, 08 RAZR |
| 06 delay-fx | 07 Digital delay, 09 VIBDEL / CHODEL |
| 07 strum | 10 |
| 08 load-meter | 11 |
| 09 groove | 12 |
| 10 control-mode | new |
| 11 trig-select | new |

### Upgrading from v1.0.0

- Build from the official OS file as before; v2.0.0 replaces v1.0.0 completely.
- Projects keep working. Patterns saved with v1.0.0 (or the stock OS) load with the stock reverb and delay, Swing and
  no strum, because v1.0.0 kept these choices in the device settings and not in the pattern. Humanize is kept. Choose
  the effects again where you want them and save the project.
- The device settings bytes v1.0.0 used (`0x404e9b5b`, `0x404e9b5c`, `0x404e9b5e`, `0x404e9b64`) are no longer read.
  `0x404e9b5d` now holds the control mode; a value left over from v1.0.0 counts as relative (stock).

## v1.0.0 (2026-10-25)

First release, for the official Model:Cycles OS 1.13.

- 01 Solo in latching mute mode (needs drumkilla's latching mute)
- 02 Mute also applies to live notes (pads, MIDI IN)
- 03 Hold a pad to mute its track while the sequencer runs
- 04 Delay Time as note values, exact triplets
- 05 Chorus I / II on the reverb slot
- 06 Phaser on the reverb slot
- 07 Digital delay on the delay slot
- 08 RAZR: dark lo-fi reverb into a phaser
- 09 VIBDEL / CHODEL modulated delays, firmware-style value popups, SETTINGS as a modifier, slower effect selection
- 10 STRUM for the CHORD machine
- 11 Audio load meter
- 12 Seven groove templates (Boom Bap, Disco, Reggae, Bongo, Caixixi, Highlife, Kuduro), humanize timing and velocity
  per track and pattern, CONTROL ALL for humanize, MACHINE menu on release

Tested on a Model:Samples running the Cycles OS. Not yet tested on a real Model:Cycles.

Earlier versions of some of these features were made for the Model:Samples on *Modded Cycles OS 2.0* (up to v21,
in a separate repository). Compared with those, v1.0.0 added patches 08–11, rewrote the grooves (12), and kept the
effect state in cached RAM to lower the audio load.
