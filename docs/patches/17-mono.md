# 17 · Monom: monophonic synth machine

Patch id `mono` · file [`patches/17-mono.json`](../../patches/17-mono.json) · 44 writes

A 9th machine, **Monom**: a monophonic synth in the spirit of the SH-101, Minimoog, Pro-One and MS-20 — warm and
imperfect. Use the track filter (patch 12) as its filter. Needs Grit and Vlvt (patches 15, 16).

## Controls

| Do this | Result |
|---|---|
| **MACHINES** | Monom is the 9th machine. |
| **COLOR** | Wave: SAW, SQR, PWM, S+P (saw + square), TRI (with wavefolding), SYNC (hard sync), DTN (detuned second saw), RING. |
| **SHAPE** | Timbre of the wave (SAW: rounds the peak, SQR: pulse width 50–5 %, PWM: centre of the pulse width, S+P: square amount, TRI: folding, SYNC: slave frequency, DTN: 0–30 cents, RING: ratio 0.5–4). |
| **SWEEP** | Sub oscillator (square one octave down). |
| **CONTOUR** | Drive (asymmetric saturation). |
| **FUNC + PITCH** | Glide (from the last note, on every trig). |
| **FUNC + CONTOUR** | Noise. |
| **DECAY** / **FUNC + DECAY** | Amp decay / attack. |

## Good to know

- Analog character: two slow drift LFOs per oscillator, a random detune per note, free-running phases, a sub with its own drift, a warm fixed low-pass, a quiet noise floor.
- Band-limited oscillators (polyBLEP; sync with a BLEP at the reset).

## What is stored

With the sound, like every parameter (glide and noise via the core's sound slot).

## Dependencies

- Requires: [00 core](00-core.md), [15 sampler](15-sampler.md), [16 strings](16-strings.md).

## How it works

The machine limits are raised from 8 to 9; Monom gets six descriptors in the core's table (four on the machine
knobs, glide and noise as FUNC extras like attack). The sound runs per track in 32-sample blocks; code and tables live
in the core's payload area.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x4005a6a6`, `0x400147a4`, `0x400148aa`, `0x400148b2`, `0x400a25e0`, `0x400a7dba`, `0x400a7df4`, `0x400a26e8`, `0x400a26e6`, `0x400a7dc4`, `0x4010e5e4`, `0x4005a2be`, `0x4005a322`, `0x4005a390`, `0x4005a6ba`, `0x4005a6f0`, `0x400a2614`, `0x400a7d6c`, `0x400a7e16`, `0x4004df5c`, `0x4004df76`, `0x4001e8da`, `0x400a2638`
- RAM: `0x4300e000` (7940 B, payload slot 'mono' (code, tables)), `0x431a0000` (3072 B, state per track)

## Source and tests

- Generator: `src/v2/g2_mono.py` (model: mono_model.py, constants: mono_tables.py)
- Tests: `test_mono.py`: every wave against a floating-point model (`mono_model.py`), glide, noise, drive, drift, aliasing.

## Status

Tested on a Model:Samples running the Cycles OS. New in v2.3.0. Not yet tested on a real Model:Cycles.

← [16-strings](16-strings.md) · [all patches](../../README.md#patches) · [18-param-undo](18-param-undo.md) →
