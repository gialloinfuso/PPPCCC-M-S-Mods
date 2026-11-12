# 13 · LFO Amount

Patch id `lfo-amount` · file [`patches/13-lfo-amount.json`](../../patches/13-lfo-amount.json) · 10 writes

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

- Amount is a **real parameter**: p-lockable, **velocity destination** and **LFO destination**. The LFO can even modulate its own Amount (this acts one audio block, 0.67 ms, later).
- At 127 the LFO is bit-for-bit the stock LFO.
- Sounds from the stock OS or older versions load with Amount 127.

## What is stored

LFO Amount is saved **with the sound**; its p-locks with the pattern.

## Dependencies

- Requires: [00 core](00-core.md).

## How it works

The firmware calls one function per block that runs the LFOs of all tracks. The patch hooks that call: before it,
the depth of each track is scaled towards the middle by Amount / 127; after it, the depth is put back and the Amount
(now including its own modulation) is remembered for the next block. A free descriptor becomes "LFO Amount",
parameter k 32. The knob lookup returns it for the LFO SPEED knob while RETRIG is held.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x400597c6`
- Code and data (unused sprite masks): `0x4014a890` (108 B), `0x401592bc` (192 B), `0x4014aa34` (108 B)
- RAM: `0x4014aa5c` (24 B, depth backup + amount per track)

## Source and tests

- Generator: `src/v2/g2_lfoamount.py`
- Tests: `test_lfoamount.py`: the real hook with the LFO call (scaled and restored, 127 bit-identical, self-modulation one block later); the knob lookup; saving and loading; p-locks; `--alone`.

## Status

Tested on a Model:Samples running the Cycles OS. Not yet tested on a real Model:Cycles.

← [12-track-filter](12-track-filter.md) · [all patches](../../README.md#patches) · [14-direct-jump](14-direct-jump.md) →
