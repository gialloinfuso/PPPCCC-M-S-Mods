# 00 · Core: shared services for the mods

Patch id `core` · file [`patches/00-core.json`](../../patches/00-core.json) · 189 writes

The core holds everything that several patches share, so that each patch can be installed on its own. Most
patches need it (see "Dependencies" on their pages); `tools/build.py` and the flasher add it automatically.
It also brings a few improvements of its own, listed below.

## Controls

| Do this | Result |
|---|---|
| hold **FUNC** + turn **DECAY** | Amp **attack**, 0 to about 2 s, on every machine. A real parameter: p-lockable, LFO and velocity destination, saved with the sound. |
| **TRACK + T1…T6** | Selects the track. T1…T6 alone no longer select it (in the pattern selection they work as before). |
| hold **FUNC** + turn a knob on a parameter page | Moves in fine steps like the knob alone (the stock OS jumps in coarse steps), so FUNC + knob is free for extra parameters. |
| browser (presets, folders, samples) | Three names in the small font instead of one big name; a selected name that does not fit scrolls. |
| browser: **RETRIG** | Opens the save menu (Save Preset / Save Kit …), shown as "RT=MENU". FUNC no longer opens it. |
| main screen: turn **LEVEL/DATA** | Shows the selected track's volume as a number (0–127) instead of the speaker icon; FUNC + LEVEL shows pan. |
| short press **SETTINGS** | Opens the settings, as on the stock OS. |
| hold **SETTINGS** (half a second or longer), release without turning a knob | Saves the project. On the stock OS this happened while you were still holding; now it happens on release. |
| hold **SETTINGS** + turn a knob that a patch uses | The patch's function. Neither the settings menu nor the save happens. |

### What the core provides

| Service | Used by |
|---|---|
| Encoder gesture dispatcher with one slot per patch | 04–06, 08, 12, 15, 19 |
| Key slots (SETTINGS press / release, TRACK + trig) | 09, 19 |
| Value popups that look like the firmware's own parameter popup | most patches |
| SETTINGS / FUNC as modifier keys (no menu, no save after a gesture) | 04–09 |
| Slow selection: 4 detents per step | 04, 05, 08 |
| Pattern storage: header bytes 40–63 are saved and loaded with the pattern | 04, 05, 08, 19 |
| Sound slots, p-locks and LFO / velocity destinations for extra parameters | 06, 12, 13, 15–17 |
| Parameter descriptor table moved to the payload and extended to 96 entries | 06, 12, 13, 15–17 |
| 64 KB payload area appended to the MAIN OS, copied to RAM at start | 04, 06, 09, 15–17, 19 |

## Good to know

- Patterns and sounds from the stock OS or older versions load with every new value at its neutral setting (no effect, no strum, attack 0, filter open …).
- The scrolling names behave exactly like drumkilla's browser-scroll tweak (elektron-model-tweaks, MIT); rebuilt here as own code (the test compares both).
- Attack: idea from Model-TG by TinyGregAudio (MIT); own code. The extended descriptor table: idea and address list from Modded-Cycles notes 18–19 (MIT); own code.
- The multi-line browser and the volume / pan numbers are ports of Modded-Cycles' multiline-browser and level-pan-values (MIT; the latter after a mod by djd_oz), rewritten here with the same behaviour and pixels.

## What is stored

Pattern header bytes 40–63 (with the project; 60–63 hold the tag `PCv2`). Attack and the extra parameters of other patches: with the sound.

## Dependencies

- Requires: nothing.
- Needed by: [04](04-reverb-fx.md), [05](05-delay-fx.md), [06](06-strum.md), [07](07-load-meter.md), [08](08-groove.md), [09](09-control-mode.md), [10](10-trig-select.md), [12](12-track-filter.md), [13](13-lfo-amount.md), [15](15-sampler.md), [16](16-strings.md), [17](17-mono.md), [19](19-pad-mode.md).

## How it works

**Gestures.** The firmware's encoder dispatch calls the core first. The core asks each installed patch in turn
(one slot per patch). A patch answers "not mine", "handled" (the event is dropped) or "handled, pass on with zero
steps". Without patches every event goes through unchanged.

**Payload.** The core appends 64 KB to the MAIN OS and copies it to RAM at start (hook in the start-up code). Larger
patches (reverbs, machines, pad mode) keep their code and tables there, each in its own slot.

**Parameters.** The firmware's parameter descriptor table is copied into the payload and extended to 96 entries;
the core saves extra parameters with the sound (free bytes of the sound record), handles their p-locks and lets them be
chosen as LFO and velocity destinations.

**Attack.** A ramp after the firmware's VCA, restarted on every trig; the knob lookup returns the attack descriptor for
FUNC + DECAY.

**SETTINGS.** Three small hooks in the main screen's key handler: a long hold only marks the save, which then happens
on release; a gesture calls `consume` for SETTINGS, so its release opens nothing.

**Popups.** Drawn at the end of the view controller's render pass with the firmware's own frame, fill and text
functions and its fonts, so they sit on top of every screen for 1.5 s.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x400081b8`, `0x40076c88`, `0x4001c54c`, `0x4001c564`, `0x4001c5bc`, `0x4005b4b0`, `0x4006155e`, `0x4005aecc`, `0x4005afa0`, `0x4005b054`, `0x4005aa34`, `0x4005b998`, `0x4005baca`, `0x4001d36a`, `0x4005981e`, `0x4001e814`, `0x400a9430`, `0x400004b2`, `0x4000a94e`, `0x4000b214`, `0x4000b236`, `0x4000b3ec`, `0x4000b47e`, `0x4000b522`, `0x4000b662`, `0x4000b6f4`, `0x4000b790`, `0x4001d5ee`, `0x4001d902`, `0x4001e032`, `0x4001f32e`, `0x40022a84`, `0x40022b06`, `0x40029e88`, `0x4002b438`, `0x40046d64`, `0x4004e32e`, `0x4005a2de`, `0x4005a4f4`, `0x4005a516`, `0x4005a538`, `0x4005a562`, `0x4005a59a`, `0x4005a5d8`, `0x4005a60a`, `0x4005a634`, `0x4005a7bc`, `0x4005a7dc`, `0x4005a804`, `0x4005a826`, `0x4005a848`, `0x4005a86a`, `0x4005a67a`, `0x4005a77e`, `0x4005a78a`, `0x4000a93e`, `0x4000a95e`, `0x4000a984`, `0x4000aa52`, `0x4000b208`, `0x4000b22a`, `0x4000b3e4`, `0x4000b476`, `0x4000b51a`, `0x4000b65a`, `0x4000b6ec`, `0x4000b788`, `0x4000b946`, `0x4001d5e2`, `0x4001d8ee`, `0x4001d90e`, `0x4001e026`, `0x4001f326`, `0x40022a7c`, `0x40022afe`, `0x40029e78`, `0x40029e98`, `0x4002b430`, `0x40046d5c`, `0x4004e31e`, `0x4004e3ba`, `0x4005a368`, `0x4005a4e8`, `0x4005a52c`, `0x4005a556`, `0x4005a582`, `0x4005a5cc`, `0x4005a5fe`, `0x4005a628`, `0x4005a65c`, `0x4005a76a`, `0x4005a7aa`, `0x4005a7d0`, `0x4005a7f8`, `0x4005a81a`, `0x4005a83c`, `0x4005a85e`, `0x4004df40`, `0x4004dfa2`, `0x4005a50a`, `0x4005a340`, `0x40005f86`, `0x4001d8a8`, `0x4005a6d0`, `0x40100ee8`, `0x4001f81e`, `0x400a5588`, `0x400a55a4`, `0x400a5612`, `0x400a576e`, `0x4003f622`, `0x400406a8`, `0x4003f752`, `0x400a547c`, `0x400a54ac`, `0x400a54ca`, `0x400a5528`, `0x400a552c`, `0x400a5776`, `0x400a69b4`, `0x400a559e`, `0x40090f48`, `0x4001aa4e`, `0x4001b22a`, `0x4001aaba`, `0x400a6d80`, `0x400a5720`
- Code and data (unused sprite masks): `0x4018f4b4` (376 B), `0x4018dba8` (376 B), `0x4015c044` (720 B), `0x401835b8` (272 B), `0x40184808` (192 B), `0x40163a60` (108 B), `0x40167900` (108 B), `0x40167aa8` (108 B), `0x40168440` (108 B), `0x401688b4` (108 B), `0x40160d9c` (104 B), `0x40162ab4` (104 B), `0x4018f98c` (124 B), `0x4018fa84` (124 B), `0x4018fb7c` (124 B), `0x401907a4` (124 B), `0x40190a1c` (124 B), `0x40147f22` (174 B), `0x40194ad4` (124 B), `0x40195a7c` (124 B), `0x4015b820` (108 B), `0x4014b784` (108 B), `0x4015bf24` (108 B), `0x4014e608` (108 B), `0x40152f88` (108 B), `0x4015c9a4` (108 B), `0x40159a04` (108 B), `0x40159adc` (108 B), `0x4015fb6c` (108 B), `0x40163b38` (104 B)
- RAM: `0x4a33c380` (40 B, popup + key state (VARS)), `0x40162ab4` (80 B, attack: render params pointer, lookup slot, ramp state (in mask)), `0x4a33c3c0` (12 B, detent counter (SLOW)), `0x43000000` (65536 B, payload (slots: reverb-fx +0x0, control-mode +0x7000, pad-mode +0x7800, strings +0x8000, sampler +0xb000, core +0xc000, mono +0xe000), copied at start), `0x401485f0` (16 B, name id, offset, tick, pause)
- Settings bytes: `0x404e9b5d (control mode, written by control-mode: 0x5a absolute, anything else relative)`
- Pattern: header bytes 40..63 are copied on pattern load (without the PCv2 tag in 60..63: 52..59 cleared, tag set); new patterns: 40..59 = 0 + tag

## Source and tests

- Generator: `src/v2/g2_core.py` (parts: g2_mlbrowser.py, g2_browserscroll.py, g2_levelpan.py, g2_browserkeys.py, g2_dtab.py)
- Tests: `test_core.py`, `test_popup.py` (real render path and fonts, pixel for pixel), `test_dtab.py` (descriptor table), `test_smp12.py` (track keys, attack), `test_mlbrowser.py`, `test_levelpan.py`, `test_browserkeys.py`, `test_modular.py`.

## Status

Tested on a Model:Samples running the Cycles OS. Updated in v2.3.0. Not yet tested on a real Model:Cycles.

[all patches](../../README.md#patches) · [01-mute-solo](01-mute-solo.md) →
