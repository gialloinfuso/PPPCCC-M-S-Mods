# 10 · Control mode: CONTROL ALL relative or absolute

Patch id `control-mode` · file [`patches/10-control-mode.json`](../../patches/10-control-mode.json) · 9 writes

CONTROL ALL (hold TRACK and turn a knob) changes a parameter on all six tracks. The firmware does this
**relatively**: every track moves by the same amount from its own value. This patch adds **absolute** mode: all tracks
take the new value of the selected track. You switch between the two with a key combination.

## Controls

| Do this | Result |
|---|---|
| hold **TRACK** + tap **SETTINGS** | Switches Relative ↔ Absolute. The popup shows "Control All" and "Relative" or "Absolute". The settings menu does not open. |
| hold **TRACK** + turn a knob | Relative: every track moves by the same amount and stops at its limit. Absolute: all tracks get the value of the selected track. |
| hold **TRACK** + turn **LEVEL** | The same for the track volumes. |
| hold **FUNC + TRACK** + turn **LEVEL** | The same for pan. |

## Good to know

- Relative is the stock behaviour and the default.
- In absolute mode the selected track makes its step exactly as the firmware would, then the other tracks get its value, limited to their own range (e.g. Chord Shape).
- The humanize of patch 09 (TRACK + SETTINGS / MACHINE + Swing) and the trig selection of patch 11 follow the same setting.
- Switching only happens on a clean tap: if you turn a knob while holding SETTINGS, or hold SETTINGS long (save), nothing switches.

## What is stored

Device settings byte `0x404e9b5d` (`0x5a` = absolute, anything else = relative). The firmware saves its settings at power-off. v1.0.0 used this byte for the reverb effect; values left from it count as relative.

## Dependencies

- Requires: [00 core](00-core.md).

## How it works

The parameter page calls one firmware function for CONTROL ALL, through its vtable. The patch points that
entry to its own function: in relative mode it jumps to the original; in absolute mode it lets the firmware step the
selected track and then writes the result to the other five tracks with the firmware's own setter (which limits the
value and refreshes the display). For LEVEL and pan the main screen has its own loop over the tracks; two hooks at
the start of its volume and pan branches do the same there. The toggle is a key slot of the core: on a plain release of
SETTINGS with TRACK held it writes the setting.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x40100588`, `0x4001ab7a`, `0x4001aaec`
- Code and data (unused sprite masks): `0x40182b38` (376 B), `0x40182e28` (376 B)
- RAM (unused area behind the BSS): `0x4a33c3a8` (2 B, SETTINGS used since press, byte for COPY)
- Settings bytes: `0x404e9b5d (0x5a absolute, anything else relative)`

## Source and tests

- Generator: `src/v2/g2_control.py`
- Tests: `test_control.py`: the real CONTROL ALL loop, step and setter functions with real parameter descriptors (relative identical to stock for several knobs and limits, absolute), the real LEVEL / pan handler, the toggle in the real key handler, humanize. `--alone` with only the core.

## Status

Tested on a Model:Samples running the Cycles OS. Not yet tested on a real Model:Cycles.

← [09-groove](09-groove.md) · [all patches](../../README.md#features) · [11-trig-select](11-trig-select.md) →
