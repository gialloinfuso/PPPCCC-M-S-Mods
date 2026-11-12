# Changelog

## v2.3.0 (2026-11-12)

The final release. After 2.3 there will be no new features, only bug fixes as far as my time allows.

### New patch numbers

Live mute is now part of 01, so every later patch moved down by one; there are five new patches at the end.

| v2.3.0 | v2.2.0 |
|---|---|
| 00 core | 00 core |
| 01 mute-solo (latching mute + solo + live mute) | 01 mute-solo + 02 live-mute |
| 02 hold-mute … 14 direct-jump | 03 … 15 |
| 15 sampler (Grit), 16 strings (Vlvt), 17 mono (Monom), 18 param-undo, 19 pad-mode | new |

### New

- **15 Grit:** a 7th machine, a sampler in the style of the Model:Samples with six models (CLEAN, SP, LM, MIRAGE, TX16W, MPC60). Samples from
  the +Drive, chosen in the browser; start, length, loop, reverse; waveform while turning; sample locks lock only the
  sample; samples can be uploaded with Elektron Transfer (Device Config > Transfer: SMP).
- **16 Vlvt:** an 8th machine, a Solina-style string ensemble (chords like CHORD, 8' / 4' mix, tone, ensemble).
- **17 Monom:** a 9th machine, a warm, imperfect monophonic synth (8 waves, sub, drive, glide, noise).
- **18 Parameter undo:** the "old → new" popup (BACK = undo) stays three times as long.
- **19 Pad mode:** pad tracks are not played by the sequencer; the trig keys and MIDI notes 36–51 play their steps.
  TRACK + RETRIG (+ trig 1–6).

### Updated

- **00 Core:** amp attack on FUNC + DECAY for every machine; TRACK + T1–T6 selects the track (T1–T6 alone no longer do);
  FUNC + knob moves in fine steps; a 64 KB payload area appended to the MAIN OS; the parameter descriptor table
  extended to 96 entries. The core now also includes the multi-line browser, the scrolling names, volume and
  pan as numbers, and RETRIG for the save menu in the browser (RT=MENU).
- **01 Mute:** latching mute, solo and live mute are one patch.
- **04 Reverb FX:** three new reverbs, Hall, Room and Plate.
- **05 Delay FX:** modulation speed on **FUNC** + DELAY SEND (was SETTINGS + DELAY SEND).
- **06 Strum:** per track and saved with the sound, on CHORD and Vlvt tracks: FUNC + SHAPE = time (OFF, 2–250 ms, note
  values), FUNC + COLOR = pattern (UP, DOWN, RND, 1324, 1423, 4132, 4231, ROOT, TOP). Every chord note has its own
  envelope. Replaces the per-pattern strum on SETTINGS + SHAPE.
- **07 Load meter:** on / off with **RETRIG + BPM** (was SETTINGS + REVERB SEND).
- **08 Groove:** a new set of grooves: Boom Bap, Disco, Dancehall 1 / 2, Hip Hop, Jazz Rock, Perc 1–3, Soca.
- **09 Control All:** choose the tracks CONTROL ALL affects (hold TRACK, trig 1–6).
- **11 Fill 2 & Trig Conditions:** new conditions PTC / !PTC, LST / !LST, x:12, x:16 and a reordered list.
- **12 Track filter:** GATE + PLAY resets the filter of the selected track; GATE toggles on release.
- **14 Direct Pattern Jump:** the pattern selection latches (only PATTERN closes it); copy / paste / clear of a pattern
  keeps it open.

Unchanged: 02 hold-mute, 03 delay-notes, 10 trig-select, 13 lfo-amount.

### Tools and sources

- The generators are now readable ColdFire assembler text in Python (`src/v2/cfasm.py`), byte-identical to before.
- **No outside repositories needed to build.** The latching mute (01) and the scrolling names (core) are rebuilt here
  with the same behaviour as drumkilla's tweaks (own code; the tests compare both). The container code is included
  unchanged in `tools/vendor/` (drumkilla's `mtlib`, Modded-Cycles' `aplib_grow.py` and `crossflash.py`, MIT).
  `tools/build.py` needs only Python 3 and your firmware file; `--tweaks` is gone.
- **Flasher:** build and flash in the browser (`flasher/`, on the project page). It checks your official file, resolves
  the requirements of the chosen patches, builds the same files as `tools/build.py` byte for byte, and can send them
  over Web MIDI. Pure JavaScript, nothing is uploaded; `tests/check_flasher.mjs` compares it with `tools/build.py`.
- The MAIN OS grows by the core's payload area (64 KB).
- Patterns and sounds from v2.2.0 or the stock OS load as before. **Strum settings of v2.2 patterns are not carried
  over** (strum is now per sound).

## v2.2.0 (2026-10-30)

New features:

- **13 Track filter:** a warm, resonant 12 dB low-pass filter on every track, with its own envelope. Hold RETRIG +
  press GATE for the filter mode (the four knob LEDs light up), tap RETRIG to leave it. In the mode PITCH = cutoff,
  COLOR = resonance, SHAPE = envelope depth (bipolar), DECAY = envelope decay. Four real parameters on every machine:
  p-locks, LFO and velocity destinations, CC 74 / CC 71, saved with the sound. Cutoff 127 = off, bit-identical to no
  filter; on / off is crossfaded.
- **14 LFO Amount:** a new parameter per track (hold RETRIG + turn LFO SPEED) that scales how strongly the LFO depth
  acts, from 0 (no LFO) to 127 (full depth, the default and stock behaviour). p-lockable, LFO and velocity
  destination, saved with the sound.
- **15 Direct jump:** PATTERN, then FUNC + a trig key: the new pattern takes over within the next steps and plays on
  from the current position (per-track mode too). The selection stays open for the next jump. A trig key alone
  changes at the end of the pattern as before.

Updated:

- **00 Core:** sound slots for extra parameters (saved and loaded with the sound), p-locks and LFO / velocity
  destinations for parameters k 23–32, encoder slot 7 for the track filter. Used by 13 and 14.

Patches 01–12 write exactly the same bytes as in v2.1.0. Sounds and patterns from v2.1.0 or the stock OS load as
before: the new parameters start at their defaults (filter open, LFO Amount 127).

Docs: the project page and the README mark new features (NEW) and the core update (UPDATE).

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
