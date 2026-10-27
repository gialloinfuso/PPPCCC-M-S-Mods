# 11 · Trig select: a selection mode for trigs

Patch id `trig-select` · file [`patches/11-trig-select.json`](../../patches/11-trig-select.json) · 13 writes

Edit many trigs at once without holding them all down. In the selection mode you tap trigs to select them;
the selection stays while you turn knobs. The firmware then treats the selected trigs as if you held them, so
everything that works on held trigs works on the selection.

## Controls

| Do this | Result |
|---|---|
| **SETTINGS + PAGE** | Selection mode on / off. Popup "Trig Select On" / "Off". Off clears the selection. |
| in the mode: tap a trig key | Select / deselect that trig (only steps with a trig, a lock trig or p-locks). Trigs are not set or cleared. Selected trigs blink fast. |
| in the mode: **FUNC + PAGE** | Select all trigs of the track (up to the pattern length); again = none. |
| in the mode: **PAGE** | Change the page as usual; the selection stays. |
| turn a knob | P-locks on all selected trigs. |
| note / velocity / length, nudge | Change all selected trigs, as when holding them. |
| **REC** | "Copy N Trigs": copies all selected trigs with their locks into the clipboard. |
| **STOP** | "Paste N Trigs": pastes the copied trigs, starting at the first selected step, keeping their spacing. |
| **PLAY** | "Clear Locks": clears the p-locks of all selected trigs, as with held trigs. |

## Good to know

- With control mode **Absolute** (patch 10), all selected trigs take the value of the first selected trig after every change: p-locks, nudge, note, velocity and length. This also applies when you hold several trigs with your fingers. Relative is the firmware's behaviour: every trig keeps its own offset.
- To paste somewhere else: deselect all, select the step where the paste should start, press STOP. Or leave the mode and hold the destination trig + STOP as usual.
- With FUNC + PAGE up to 64 trigs can be selected and copied at once; with your fingers it is at most 16.

## What is stored

Nothing. The mode is off after power-on.

## Dependencies

- Requires: [00 core](00-core.md).

## How it works

The firmware keeps the held trig keys as a 64-bit mask in its UI state, together with a "held" flag and the first
held step. Everything that works on held trigs reads that mask: the p-lock functions of the parameter page, the trig
settings, nudge, and copy / paste / clear. The selection is simply written into that mask with the firmware's own
functions. The patch replaces the trig-key handler of the grid view (through its vtable) while the mode is on: trig keys
toggle bits instead of setting trigs, PAGE runs the firmware's page change with the mask hidden, FUNC + PAGE selects all.
A hook in the grid's LED loop makes the selected steps blink at 4 Hz. For absolute mode, the p-lock function of the
parameter page (vtable) and the trig-settings call are wrapped: after the firmware's change, every held step gets the
value of the first held step.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x40100af0`, `0x401005a0`, `0x4001c4a6`, `0x40021f56`, `0x40029d9a`
- Code and data (unused sprite masks): `0x40183118` (376 B), `0x40185018` (376 B), `0x40185968` (376 B), `0x40185c58` (376 B)
- RAM (unused area behind the BSS): `0x4a33c3ac` (4 B, selection mode on ('TSEL'))

## Source and tests

- Generator: `src/v2/g2_trigselect.py`
- Tests: `test_trigselect.py`: the real held-step functions on a UI state in memory, the real key event and core; mode on/off, select/deselect, all/none, pattern length, PAGE with the mask hidden, other keys, trig keys outside grid editing; the LED hook against stock; p-locks, nudge and note/velocity/length relative and absolute; random RAM after power-on = off. `--alone` with only the core.

## Status

Tested on a Model:Samples running the Cycles OS. New in v2.0.0; please report anything odd. Not yet tested on a real Model:Cycles.

← [10-control-mode](10-control-mode.md) · [all patches](../../README.md#features) · [12-fill2](12-fill2.md) →
