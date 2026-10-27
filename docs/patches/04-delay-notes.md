# 04 · Delay Time as note values, exact triplets

Patch id `delay-notes` · file [`patches/04-delay-notes.json`](../../patches/04-delay-notes.json) · 6 writes

The Model:Cycles delay time is tempo-synced: a value *n* means *n*/128 of a whole note. This patch shows the
musical positions as note values, and makes the triplet positions exactly triplet length.

## Controls

| Do this | Result |
|---|---|
| turn **Delay Time** | At musical positions the display shows a note value instead of the number. |

### Shown values

| Even | Dotted | Triplets |
|---|---|---|
| 1/1, 1/2, 1/4, 1/8, /16, /32, /64 | 2., 4., 8., 16., 32. | 1T, 2T, 4T, 8T, 16T |

## Good to know

- A triplet cannot be expressed in 1/128 steps. At the five triplet positions the delay line gets the extra 1/3 or 2/3 step, so 1/8T is really 1/8T. All other values sound exactly as before.
- The delays of patch 06 use these exact triplets too when this patch is installed.
- Unchanged since v1.0.0.

## What is stored

Nothing new: Delay Time is saved in the kit as usual.

## Dependencies

- Requires: nothing.

## How it works

Two hooks. On the DSP side, one instruction in the delay-time calculation becomes a call that adds the missing
fraction at the triplet values. On the display side, the parameter text function of Delay Time prints a short label
for the musical positions.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x4004dfda`, `0x400581b8`
- Code and data (unused sprite masks): `0x4018d918` (328 B), `0x40170ad8` (184 B)

## Source and tests

- Generator: `src/gen_delaynotes_113.py` (code from gen_delaynotes.py)
- Tests: `test_delaynotes.py <image>`: delay length for all 128 values (only the 5 triplet values change), labels at the 17 positions, all other values unchanged, a tempo check.

## Status

Tested on a Model:Samples running the Cycles OS. Not yet tested on a real Model:Cycles.

← [03-hold-mute](03-hold-mute.md) · [all patches](../../README.md#features) · [05-reverb-fx](05-reverb-fx.md) →
