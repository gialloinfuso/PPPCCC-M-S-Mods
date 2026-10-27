# 05 · Reverb FX: Chorus I / II, Phaser, Reverb-Phaser (RAZR)

Patch id `reverb-fx` · file [`patches/05-reverb-fx.json`](../../patches/05-reverb-fx.json) · 24 writes

Four effects for the reverb slot: a lush stereo chorus with two modes in the style of classic 80s polysynth
choruses, a 4-stage phaser in the style of classic phaser pedals, and RAZR, a dark, gritty lo-fi reverb that feeds a
phaser. The reverb send of every track feeds the chosen effect, and the reverb knobs control it.

## Controls

| Do this | Result |
|---|---|
| hold **TRACK** + turn **Reverb Size** | Reverb → Chorus I → Chorus II → Phaser → RAZR (left goes back). 4 detents per step; the parameter names change at once. |
| Reverb Send (per track) | How much of the track goes into the effect (RAZR: mix). |
| Reverb Size | Chorus: speed · Phaser: speed, 0.1–6 Hz · RAZR: reverb length. |
| Reverb Tone | Chorus: depth · Phaser: color · RAZR: phaser speed, 0.05–4.9 Hz (0 = lo-fi reverb only). |

## Good to know

- The sound is bit-identical to v1.0.0 (patches 05, 06 and 08 there).
- RAZR is about 9.5 dB louder than the plain reverb (measured with noise), so it sits with the other effects.
- TRACK + any other knob is still CONTROL ALL.

## What is stored

**In the pattern** (saved with the project): header byte 52 (0 Reverb, 1 Chorus I, 2 Chorus II, 3 Phaser, 4 RAZR). Every pattern can have its own effect; changing patterns switches it.

## Dependencies

- Requires: [00 core](00-core.md).

## How it works

The mixer's call of the reverb is redirected. Once per audio block the patch reads the effect byte of the
running pattern, sets the parameter names and runs the chosen effect on the reverb input, or calls the original
reverb. The chorus uses an 8 KB ring buffer, the phaser four all-pass stages per channel; RAZR runs the firmware
reverb with its own dark parameter block, a half-rate sample-and-hold for the grit, and the phaser engine with its own
coefficient table. All state lives in RAM areas the firmware leaves unused.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x40056a2c`
- Code and data (unused sprite masks): `0x40171bc8` (184 B), `0x4016ea78` (208 B), `0x401728f8` (184 B), `0x40179140` (184 B), `0x4015f50c` (280 B), `0x4018af88` (272 B), `0x4018ff64` (272 B), `0x40185648` (184 B), `0x401857f8` (184 B), `0x4016f7d0` (124 B), `0x4016cae8` (1024 B)
- RAM (unused area behind the BSS): `0x4a33a000` (8240 B, chorus state + ring), `0x4233c100` (56 B, phaser state), `0x4233c180` (56 B, RAZR phaser state), `0x4233c200` (4 B, RAZR reverb parameters), `0x4233c210` (256 B, RAZR buffer), `0x4233c3fc` (1 B, mode mirror)
- Pattern: header byte 52: 0 Reverb, 1 Chorus I, 2 Chorus II, 3 Phaser, 4 RAZR

## Source and tests

- Generator: `src/v2/g2_reverbfx.py` (sound code from gen_chorus_113.py, gen_chorus3.py, gen_fx4.py, gen_phaser_113.py, gen_razer_113.py)
- Tests: `test_fx_diff.py`: chorus, phaser and RAZR output bit-identical to v1.0.0; the gesture and its storage. `test_modular.py`.

## Status

Tested on a Model:Samples running the Cycles OS. Not yet tested on a real Model:Cycles.

← [04-delay-notes](04-delay-notes.md) · [all patches](../../README.md#features) · [06-delay-fx](06-delay-fx.md) →
