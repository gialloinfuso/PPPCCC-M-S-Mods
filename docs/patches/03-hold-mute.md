# 03 · Hold a pad to mute its track

Patch id `hold-mute` · file [`patches/03-hold-mute.json`](../../patches/03-hold-mute.json) · 8 writes

While the sequencer runs, holding a track pad mutes that track until you let go. That makes quick drop-outs
easy. A short tap still plays the sound.

## Controls

| Do this | Result |
|---|---|
| sequencer running: **hold T1–T6** (about 200 ms or longer) | The track is muted (the normal track mute: sequencer notes drop out, ringing sounds decay) until you release the pad. |
| sequencer running: tap a pad | The sound plays on release. |
| sequencer stopped | Pads play normally, on press. |

## Good to know

- If the track was already muted, holding and releasing its pad leaves it muted.
- Unchanged since v1.0.0.

## What is stored

Nothing.

## Dependencies

- Requires: nothing.

## How it works

The patch hooks pad press and pad release on the main screen, and the UI tick. When a pad is pressed while the
sequencer runs, the patch only notes the time. If the pad is still held after about 200 ms, the tick mutes the track.
On release, the patch undoes the mute it made, or plays the note if the pad was only tapped. If another mod already
uses the UI tick, the patch chains it: it reads the original jump target from the image and calls it.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x400081f2`, `0x4001d05e`, `0x4001d0fc`
- Code and data (unused sprite masks): `0x401699a8` (280 B), `0x4016aa28` (280 B)

## Source and tests

- Generator: `src/gen_holdmute_113.py` (code from gen_holdmute3.py)
- Tests: `test_holdmute_113.py` (19 checks).

## Status

Tested on a Model:Samples running the Cycles OS. Not yet tested on a real Model:Cycles.

← [02-live-mute](02-live-mute.md) · [all patches](../../README.md#features) · [04-delay-notes](04-delay-notes.md) →
