# 02 · Mute also applies to live notes

Patch id `live-mute` · file [`patches/02-live-mute.json`](../../patches/02-live-mute.json) · 3 writes

On the stock OS a muted track still plays when you hit its pad or send it a MIDI note. With this patch a muted
track stays silent for those too.

## Controls

| Do this | Result |
|---|---|
| mute a track (any mute mode) | Pads, keyboard notes and incoming MIDI notes for that track are ignored. |

## Good to know

- Only note-on is dropped. Note-off still goes through, so no note can hang when you mute while holding it.
- Unchanged since v1.0.0.

## What is stored

Nothing.

## Dependencies

- Requires: nothing.

## How it works

All live notes, from the pads or from MIDI IN, go through one firmware function. The patch hooks its first
instruction: for a note-on it reads the mute state of the note's track and returns early if the track is muted.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x4005894a`
- Code and data (unused sprite masks): `0x401696a0` (62 B)

## Source and tests

- Generator: `src/gen_livemute.py`
- Tests: `test_livemute.py`: note-on on a muted and an unmuted track, note-off on a muted track, registers and stack.

## Status

Tested on a Model:Samples running the Cycles OS. Not yet tested on a real Model:Cycles.

← [01-mute-solo](01-mute-solo.md) · [all patches](../../README.md#features) · [03-hold-mute](03-hold-mute.md) →
