# 04 · Reverb FX: Chorus I / II, Phaser, RAZR, Hall, Room, Plate

Patch id `reverb-fx` · file [`patches/04-reverb-fx.json`](../../patches/04-reverb-fx.json) · 25 writes

Seven effects for the reverb slot: a lush stereo chorus with two modes in the style of classic 80s polysynth
choruses, a 4-stage phaser in the style of classic phaser pedals, RAZR, a dark, gritty lo-fi reverb that feeds a
phaser, and three reverbs of their own, **Hall**, **Room** and **Plate**. The reverb send of every track feeds the
chosen effect, and the reverb knobs control it.

## Controls

| Do this | Result |
|---|---|
| hold **TRACK** + turn **Reverb Size** | Reverb → Chorus I → Chorus II → Phaser → RAZR → Hall → Room → Plate (left goes back). 4 detents per step; the parameter names change at once. |
| Reverb Send (per track) | How much of the track goes into the effect (RAZR: mix). |
| Reverb Size | Chorus: speed · Phaser: speed, 0.1–6 Hz · RAZR: reverb length · Hall / Room / Plate: decay. |
| Reverb Tone | Chorus: depth · Phaser: color · RAZR: phaser speed, 0.05–4.9 Hz (0 = lo-fi reverb only) · Hall / Room / Plate: damping. |

## Good to know

- Chorus, Phaser and RAZR are bit-identical to v1.0.0.
- **v2.3.1: less CPU load, same sound.** The chorus keeps its buffer in cached memory (about half the load); Hall, Room and Plate run 8–11 % fewer instructions per block. The output is bit-for-bit the same as in v2.3.0.
- Hall, Room and Plate are own algorithms in the style of the Dragonfly Reverbs (Hall: late reverb network, Room: early reflections + diffuse tail, Plate: in the style of the Dattorro plate). No code was taken. Their code and tables live in the core's payload area.
- RAZR is about 9.5 dB louder than the plain reverb (measured with noise), so it sits with the other effects.
- TRACK + any other knob is still CONTROL ALL.

## What is stored

**In the pattern** (saved with the project): header byte 52 (0 Reverb, 1 Chorus I, 2 Chorus II, 3 Phaser, 4 RAZR, 5 Hall, 6 Room, 7 Plate). Every pattern can have its own effect; changing patterns switches it.

## Dependencies

- Requires: [00 core](00-core.md).

## How it works

The mixer's call of the reverb is redirected. Once per audio block the patch reads the effect byte of the
running pattern, sets the parameter names and runs the chosen effect on the reverb input, or calls the original
reverb. The chorus uses an 8 KB ring buffer, the phaser four all-pass stages per channel; RAZR runs the firmware
reverb with its own dark parameter block, a half-rate sample-and-hold for the grit, and the phaser engine with its own
coefficient table. All state lives in RAM areas the firmware leaves unused, through the cached address range (v2.3.1: the chorus too; only the CPU uses these areas). Hall, Room and Plate run from the core's payload area with their
own delay memory.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x40056a2c`
- Code and data (unused sprite masks): `0x40171bc8` (184 B), `0x4016ea78` (208 B), `0x401728f8` (184 B), `0x40179140` (184 B), `0x4015f50c` (280 B), `0x4018af88` (272 B), `0x4018ff64` (272 B), `0x40185648` (184 B), `0x401857f8` (184 B), `0x4016f7d0` (124 B), `0x4016cae8` (1024 B)
- RAM: `0x4233a000` (8240 B, chorus state + ring), `0x4233c100` (56 B, phaser state), `0x4233c180` (56 B, RAZR phaser state), `0x4233c200` (4 B, RAZR reverb parameters), `0x4233c210` (256 B, RAZR buffer), `0x4233c3fc` (1 B, mode mirror), `0x43000000` (21352 B, payload (code, tables), copied at start), `0x43100000` (1024 B, Hall / Room / Plate state), `0x43110000` (102912 B, Hall / Room / Plate delay lines)
- Pattern: header byte 52: 0 Reverb, 1 Chorus I, 2 Chorus II, 3 Phaser, 4 RAZR, 5 Hall, 6 Room, 7 Plate

## Source and tests

- Generator: `src/v2/g2_reverbfx.py` (Hall / Room / Plate: g2_reverbs.py, model rv_algos.py; sound code from gen_chorus_113.py, gen_chorus3.py, gen_fx4.py, gen_phaser_113.py, gen_razer_113.py)
- Tests: `test_fx_diff.py`: chorus, phaser and RAZR output bit-identical to v1.0.0; the gesture and its storage. `test_reverbs.py`: Hall / Room / Plate through the real mixer hook against a floating-point model. `test_modular.py`. `prof_fx.py` (no test): load profile of every effect.

## Status

Tested on a Model:Samples running the Cycles OS. Updated in v2.3.0 (Hall, Room, Plate) and v2.3.1 (less CPU load). Not yet tested on a real Model:Cycles.

← [03-delay-notes](03-delay-notes.md) · [all patches](../../README.md#patches) · [05-delay-fx](05-delay-fx.md) →
