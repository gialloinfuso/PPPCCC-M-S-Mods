# 14 · LFO Amount: how strongly the LFO depth acts

Patch id `lfo-amount` · file [`patches/14-lfo-amount.json`](../../patches/14-lfo-amount.json) · 10 writes

A new parameter per track, **LFO Amount** (0–127), that sits behind the LFO depth. Depth stays the largest swing of
the LFO; Amount says how much of it is used: 0 = the LFO does nothing, 127 = the depth works fully (the default, and
exactly the stock behaviour). Amount does not change the LFO settings themselves, so you can fade an LFO in and out
without losing its depth.

## Controls

| Do this | Result |
|---|---|
| hold **RETRIG** + turn **LFO SPEED** | LFO Amount of the track. The firmware's own popup shows "LFO Amount". |
| turn **LFO SPEED** without RETRIG | LFO Speed, as before. |
| hold a trig + **RETRIG** + turn **LFO SPEED** | p-locks the Amount on that trig. |

## Good to know

- Amount is a **real parameter**: it can be p-locked and chosen as **velocity destination** and as **LFO
  destination**. The LFO can even modulate its own Amount (this acts one audio block, 0.67 ms, later).
- At 127 the LFO is bit-for-bit the stock LFO.
- Sounds from the stock OS or older versions load with Amount 127.

## What is stored

LFO Amount is saved **with the sound** (and so with the kit and the project); its p-locks are saved with the pattern.

## Dependencies

- Requires: [00 core](00-core.md) (sound slot, p-locks and LFO / velocity destination for parameter k 32).

## How it works

The firmware calls one function per block that runs the LFOs of all tracks. The patch hooks that call: before it, the
depth of each track is scaled towards the middle by Amount / 127; after it, the depth is put back and the Amount
(now including its own modulation) is remembered for the next block. Descriptor 5 (an unused "Error" entry of the
parameter table) becomes "LFO Amount", parameter k 32. The parameter page's knob lookup returns it for the LFO SPEED
knob while RETRIG is held.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x4001e814`, `0x400597c6`
- Descriptor 5 of the parameter table (`0x4010ddf8`)
- Code and data (unused sprite masks): `0x4014a890` (108 B), `0x401592bc` (192 B), `0x4014aa34` (108 B)
- RAM (in a sprite mask): `0x4014aa5c` (24 B, depth backup and Amount per track)
- Core: sound slot 1

## Source and tests

- Generator: `src/v2/g2_lfoamount.py`
- Tests: `test_lfoamount.py`: the real hook with the LFO call (depth scaled for the LFO and restored after it, 127 bit-identical, self-modulation one block later, registers and stack); the knob lookup (only LFO SPEED + RETRIG); saving and loading with the real functions (old sounds = 127); p-locks; `--alone` with only the core and this patch.

## Status

Tested on a Model:Samples running the Cycles OS. New in v2.2.0. Not yet tested on a real Model:Cycles.

← [13-track-filter](13-track-filter.md) · [all patches](../../README.md#features) · [15-direct-jump](15-direct-jump.md) →
