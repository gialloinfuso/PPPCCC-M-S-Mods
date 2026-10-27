# 07 · Chord Strum

Patch id `strum` · file [`patches/07-strum.json`](../../patches/07-strum.json) · 7 writes

The CHORD machine plays its notes one after another, like a strummed guitar, instead of all at once.

## Controls

| Do this | Result |
|---|---|
| hold **SETTINGS** + turn **SHAPE** | Strum −80 … 80; popup "Strum". |
| 0 | All notes at once (stock). |
| right (1 … 80) | Low to high; the value is the time between two notes in ms. |
| left (−1 … −80) | High to low. |

## Good to know

- One value per pattern for every CHORD track in it.
- The root note is delayed too, so the order is complete.

## What is stored

**In the pattern**: header byte 56 (signed; other values count as 0).

## Dependencies

- Requires: [00 core](00-core.md).

## How it works

A hook at the end of the CHORD voice update keeps a counter per voice from the moment the voice is triggered.
Each operator's level stays at 0 until its turn comes. A second hook does the same for the root note's fixed level
when it is rendered. The strum value is read from the running pattern.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x400ab240`, `0x400ab2d2`
- Code and data (unused sprite masks): `0x40192734` (376 B), `0x4018d4a8` (376 B)
- RAM (unused area behind the BSS): `0x4233c360` (24 B, voice counters), `0x4233c378` (4 B, root note level)
- Pattern: header byte 56: strum, signed -80..80

## Source and tests

- Generator: `src/v2/g2_strum.py` (gen_strum_113.py)
- Tests: `test_mods_diff.py`: strum code against v1.0.0 on rebuilt voices, gestures.

## Status

Tested on a Model:Samples running the Cycles OS. Not yet tested on a real Model:Cycles.

← [06-delay-fx](06-delay-fx.md) · [all patches](../../README.md#features) · [08-load-meter](08-load-meter.md) →
