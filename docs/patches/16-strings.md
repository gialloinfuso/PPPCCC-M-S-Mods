# 16 · Vlvt: string machine

Patch id `strings` · file [`patches/16-strings.json`](../../patches/16-strings.json) · 36 writes

An 8th machine, **Vlvt**: a string ensemble in the style of a Solina. Two sawtooth layers per note (8' and 4'),
a tone control and a lush three-tap ensemble. It plays chords like the CHORD machine. Needs Grit (patch 15).

## Controls

| Do this | Result |
|---|---|
| **MACHINES** | Vlvt is the 8th machine. |
| **SHAPE** | Chord: the same list and names as CHORD. 0 = mono, 1 / 2 = unison of 2 / 4 slightly detuned notes. |
| **COLOR** | Octave mix 8' / 4' (0 = only 8', 64 = both, 127 = only 4'). |
| **SWEEP** | Tone (low-pass 800 Hz to 9.7 kHz after a 110 Hz high-pass). |
| **CONTOUR** | Ensemble: 0 = off, 127 = full (3 modulated taps, LFOs 0.62 / 5.9 Hz). |
| **DECAY** / **FUNC + DECAY** | Amp decay / attack. |
| **GATE** key | Gate on: every chord note holds at full level while the trig (or the MIDI note) lasts, then decays — as on CHORD. |
| **FUNC + SHAPE** / **FUNC + COLOR** | Strum time / pattern (with patch 06). |

## Good to know

- The oscillators run freely (no phase reset on a trig), as on the original.
- With patch 06 every chord note has its own envelope from its strum onset: attack, hold while GATE, decay.
- Idea: string-machine by jpcima, after the model by Peter Whiting; own code, nothing taken.

## What is stored

With the sound, like every parameter.

## Dependencies

- Requires: [00 core](00-core.md), [15 sampler](15-sampler.md).
- Needed by: [17](17-mono.md).

## How it works

The machine limits are raised from 7 to 8; Vlvt uses the parameter descriptors of the CHORD machine (so ranges,
defaults and chord names are the firmware's) with its own long names. The sound runs per track in 32-sample blocks:
band-limited sawtooth pairs (polyBLEP), the tone filter (TPT low-pass), and an ensemble of three modulated delay taps.
The envelope of each chord note holds while the firmware's gate of the voice is on and not yet released (the same check
as CHORD with strum). Code and tables live in the core's payload area; the state of each track in RAM.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x4005a6a6`, `0x400147a4`, `0x400148aa`, `0x400148b2`, `0x400a25e0`, `0x400a7dba`, `0x400a7df4`, `0x400a26e8`, `0x400a26a2`, `0x40118647`, `0x4010e5e4`, `0x4005a2be`, `0x4005a322`, `0x4005a390`, `0x4005a6ba`, `0x4005a6f0`, `0x400a2614`, `0x400a7d6c`, `0x400a7e16`, `0x4004df5c`, `0x4004df76`, `0x4001e8da`, `0x400a2638`
- RAM: `0x43008000` (9350 B, payload slot 'strings' (code, tables)), `0x43180000` (27648 B, state + ensemble ring per track)

## Source and tests

- Generator: `src/v2/g2_strings.py` (model: str_model.py)
- Tests: `test_strings.py`: oscillators, tone filter and ensemble against a floating-point model (`str_model.py`), chords, strum envelopes, GATE (hold and release), retrigger without a click.

## Status

Tested on a Model:Samples running the Cycles OS. New in v2.3.0. Not yet tested on a real Model:Cycles.

← [15-sampler](15-sampler.md) · [all patches](../../README.md#patches) · [17-mono](17-mono.md) →
