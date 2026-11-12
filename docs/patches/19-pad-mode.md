# 19 · Pad Mode

Patch id `pad-mode` · file [`patches/19-pad-mode.json`](../../patches/19-pad-mode.json) · 9 writes

Turn a track into a **pad track**: the sequencer leaves it alone and the trig keys play its steps — with their
p-locks, note, length and sample lock. Great for one-shots, fills and finger drumming with prepared sounds, especially
on Grit tracks.

## Controls

| Do this | Result |
|---|---|
| hold **TRACK** + **RETRIG** | Trig LEDs 1–6 show the pad tracks (blinking). |
| hold **TRACK** + **RETRIG** + press **trig 1–6** | Pad mode on / off for that track (popup "Pad Mode"). |
| on a pad track: tap **trig 1–16** | Plays that step of the page shown, with its p-locks, note, length and sample lock, regardless of its condition and probability. |
| on a pad track: hold a trig + turn a knob | Edits the step's p-lock, as usual. |
| on a pad track: **FUNC + trig** | Adds or clears the trig (a tap no longer toggles it). |
| MIDI notes 36–51 on the pad track's channel | Play trigs 1–16 of the page shown, with the note's velocity. The trig keys send these notes. |

## Good to know

- The sequencer plays nothing on pad tracks. Muted pad tracks stay silent.
- On a pad track the trig LEDs show its steps also without REC; there is no chromatic keyboard on pad tracks.
- RETRIG is used up while TRACK is held, so it does not end the filter mode of patch 12.
- Playing a step: idea from drumkilla's trig-preview tweak (elektron-model-tweaks, MIT); own code.

## What is stored

**In the pattern**: header byte 57, bits 0–5 (one per track). Old and new patterns start with no pad tracks.

## Dependencies

- Requires: [00 core](00-core.md).

## How it works

**Sequencer.** A hook at the start of the firmware's event builder skips pad tracks unless the event comes from a
trig key. **Playing.** The grid's trig-key handler is hooked: on a pad track a press builds the step's event with the
firmware's own event builder (probability 100, no condition) and puts it in the event queue. **Selection.** The track
selection view's keys go through a core slot. **MIDI.** Notes 36–51 on a pad track's channel are turned into step
presses; the trig keys send the matching notes.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x40022c22`, `0x40022cda`, `0x400548ce`, `0x400ff9cc`, `0x40021e28`, `0x400819fc`

## Source and tests

- Generator: `src/v2/g2_pad.py`
- Tests: `test_pad.py`: the real event builder and queue, the grid key handler, the track selection keys, LEDs, MIDI in / out.

## Status

Tested on a Model:Samples running the Cycles OS. New in v2.3.0. Not yet tested on a real Model:Cycles.

← [18-param-undo](18-param-undo.md) · [all patches](../../README.md#patches)
