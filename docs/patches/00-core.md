# 00 · Core: shared services for the modular mods

Patch id `core` · file [`patches/00-core.json`](../../patches/00-core.json) · 13 writes

The core holds everything that several mods share, so that each mod can be installed on its own. On its own it
changes almost nothing you would notice; patches 05–11 need it. `tools/build.py` adds it automatically when you choose
one of them.

## Controls

| Do this | Result |
|---|---|
| short press **SETTINGS** | Opens the settings, as on the stock OS. |
| hold **SETTINGS** (half a second or longer), release without turning a knob | Saves the project. On the stock OS this happened while you were still holding; now it happens on release. |
| hold **SETTINGS** + turn a knob that a mod uses | The mod's function. Neither the settings menu nor the save happens. |
| **FUNC + SETTINGS** | Quick save of pattern/kit, as on the stock OS. |

### What the core provides

| Service | Used by |
|---|---|
| Encoder gesture dispatcher with one slot per mod (8 slots) | 05–10 |
| Key slots for SETTINGS press / release | 10 |
| Value popups that look like the firmware's own parameter popup | 06–11 |
| SETTINGS as a modifier key (no menu, no save after a gesture) | 06–11 |
| Slow selection: 4 detents per step | 05, 06, 09 |
| Pattern storage: header bytes 40–63 are saved and loaded with the pattern | 05, 06, 07, 09 |
| The control-mode setting (relative / absolute) | 09, 10, 11 |

## Good to know

- Patterns from the stock OS or from v1.0.0 have no core tag. When such a pattern is loaded, the bytes the v2 mods use (52–59) start at 0, so the pattern plays with the stock reverb and delay, Swing and no strum. Humanize (40–51) is kept, as in v1.0.0.
- A new pattern starts with all v2 values at 0.

## What is stored

Pattern header bytes 40–63 (saved with the project). 60–63 hold the tag `PCv2`.

## Dependencies

- Requires: nothing.
- Needed by: [05](05-reverb-fx.md), [06](06-delay-fx.md), [07](07-strum.md), [08](08-load-meter.md), [09](09-groove.md), [10](10-control-mode.md), [11](11-trig-select.md).

## How it works

**Gestures.** The firmware's encoder dispatch calls the core first. The core asks each installed mod in turn
(one slot per mod). A mod answers "not mine", "handled" (the event is dropped) or "handled, pass on with zero
steps". Without mods every event goes through unchanged.

**SETTINGS.** Three small hooks in the main screen's key handler: a long hold only marks the save, which then
happens on release; a mod gesture calls `consume` for SETTINGS, so its release opens nothing. The key slots let a mod
react to the press and to a plain release.

**Popups.** Drawn at the end of the view controller's render pass with the firmware's own frame, fill and text
functions and its fonts, so they sit on top of every screen for 1.5 s.

**Pattern storage.** The stock loader copies only some fields of the 64-byte pattern header. The core adds the copy
of bytes 40–63 when a pattern is loaded, and clears them for a new pattern.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x400081b8`, `0x40076c88`, `0x4001c54c`, `0x4001c564`, `0x4001c5bc`, `0x4005b4b0`, `0x4006155e`
- Code and data (unused sprite masks): `0x4018f4b4` (376 B), `0x4018dba8` (376 B), `0x4015c044` (720 B)
- RAM (unused area behind the BSS): `0x4a33c380` (40 B, popup + key state (VARS)), `0x4a33c3c0` (12 B, detent counter (SLOW))
- Settings bytes: `0x404e9b5d (control mode, written by control-mode: 0x5a absolute, anything else relative)`
- Pattern: header bytes 40..63 are copied on pattern load (without the PCv2 tag in 60..63: 52..59 cleared, tag set); new patterns: 40..59 = 0 + tag

## Source and tests

- Generator: `src/v2/g2_core.py`
- Tests: `test_core.py` (dispatcher, slots, key slots, gestures, slow selection, pattern storage), `test_popup.py` (real render path and fonts, pixel for pixel), `test_settings_key_113.py` (real key chain), `test_modular.py`.

## Status

Tested on a Model:Samples running the Cycles OS. Not yet tested on a real Model:Cycles.

[all patches](../../README.md#features) · [01-mute-solo](01-mute-solo.md) →
