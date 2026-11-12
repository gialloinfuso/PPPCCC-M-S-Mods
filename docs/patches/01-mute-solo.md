# 01 · Mute: latching, solo and live notes

Patch id `mute-solo` · file [`patches/01-mute-solo.json`](../../patches/01-mute-solo.json) · 14 writes

Everything around muting in one patch: the **latching mute mode**,
**solo** inside that mode, and muted tracks that also stay silent for **live notes**.

## Controls

| Do this | Result |
|---|---|
| hold **TRACK** + tap **FUNC** | The mute mode latches: FUNC lights up, track keys toggle mutes without holding TRACK. |
| short tap on **FUNC** alone | Leaves the latched mute mode. |
| latched mode: **hold FUNC + track key** | Solo that track: it plays, all other tracks are muted. |
| the same again | Back to the mutes you had before the solo. |
| hold FUNC + another track key while soloed | Solo moves to that track; the saved mutes stay the ones from before the first solo. |
| track key without FUNC | Toggles that mute as usual and ends the solo (nothing is restored). |
| mute a track (any mute mode) | Pads, keyboard notes and incoming MIDI notes for that track are ignored too. |

## Good to know

- The latching mute behaves exactly like drumkilla's latching-mute tweak ([elektron-model-tweaks](https://github.com/drumkilla/elektron-model-tweaks), MIT), whose idea it is; it is rebuilt here as own code, so the build needs nothing from outside this repository. `test_latch.py` compares both.
- Holding FUNC long (about 0.7 s) or using it with another key (solo, FUNC + knob) does not leave the latched mode. TRACK, PATTERN and RETRIG work as usual while it is latched.
- Live mute drops only note-on; note-off still goes through, so no note can hang when you mute while holding it.
- Solo and live mute are unchanged since v1.0.0; in 2.3.0 they became one patch with the latching mute.

## What is stored

Nothing. The saved mutes live in RAM and are gone after power-off.

## Dependencies

- Requires: nothing.

## How it works

**Solo.** The mute view calls the firmware's mute-toggle function when you press a track key. The patch replaces
that one call. If the latching flag is set and FUNC is held, it saves the six mute states and sets them for a solo
instead. Called again for the same track, it writes the saved states back. In every other case it calls the original
toggle.

**Latching mute.** Three hooks in the mute view: its key function (vtable) keeps the view open when FUNC is released while
TRACK is held (latched) and closes it on a short tap of FUNC alone; the track-key function lets TRACK, PATTERN and RETRIG
through to the firmware while the mode is latched; the LED pass lights the FUNC LED.

**Live mute.** All live notes, from the pads or from MIDI IN, go through one firmware function. The patch hooks its
first instruction: for a note-on it reads the mute state of the note's track and returns early if the track is muted.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x40100c44`, `0x4002351a`, `0x400233a0`
- Code and data (unused sprite masks): `0x40148662` (288 B), `0x40148328` (114 B)
- RAM: `0x401487e0` (14 B, FUNC press time, FUNC used, latched flag)

## Source and tests

- Generator: `src/v2/g2_latch.py` (and gen_solo.py, gen_livemute.py)
- Tests: `test_latch.py`: the latching mute with the firmware's real key functions (latch, leave, long hold, FUNC used, track keys, LED; against drumkilla's tweak when its checkout is there). `test_modular.py`. The v1 tests of solo and live mute are in the v1.0.0 release.

## Status

Tested on a Model:Samples running the Cycles OS. Updated in v2.3.0 (latching mute included and rebuilt). Not yet tested on a real Model:Cycles.

← [00-core](00-core.md) · [all patches](../../README.md#patches) · [02-hold-mute](02-hold-mute.md) →
