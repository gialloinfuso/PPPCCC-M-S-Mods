# 12 · Per Track LP Filter + Env Amt & Latched Filter Mode

Patch id `track-filter` · file [`patches/12-track-filter.json`](../../patches/12-track-filter.json) · 39 writes

A resonant 12 dB low-pass filter on every track, with its own envelope, after the machine and the track's volume
and distortion; per track also as a steeper 24 dB filter. It works on every machine. A **filter mode** puts its four parameters on the knobs, so your hands stay
on the device.

## Controls

| Do this | Result |
|---|---|
| hold **RETRIG** + press **GATE** | Filter mode on. A popup shows "FILTER ON", and the LEDs of the four knobs light up. |
| tap **RETRIG** | Filter mode off ("FILTER OFF"). |
| in the filter mode: **PITCH** | Cutoff, 20 Hz to 20 kHz. 127 = filter off. |
| in the filter mode: **COLOR** | Resonance (Q 0.5 to 5). |
| in the filter mode: **SHAPE** | Envelope amount, bipolar: right opens the filter on every trig, left closes it, middle = OFF. |
| in the filter mode: **DECAY** | Envelope decay, about 5 ms to 5 s. |
| hold a trig in the filter mode + turn a knob | p-locks the filter parameter on that trig. |
| in the filter mode: **FUNC** + **GATE** | 12 dB ↔ 24 dB for the selected track (popup "FILTER 12dB" / "FILTER 24dB"). |
| hold **GATE** + press **PLAY** | Filter reset of the selected track: cutoff 127, resonance 0, envelope centre, decay 64, 12 dB (p-locks stay). |

## Good to know

- GATE toggles the gate on **release**, so GATE + PLAY does not toggle it.
- **24 dB** (v2.3.1): a second filter stage at the same cutoff, clean (Q 0.707, no saturation), after the resonant first stage. The resonance stays that of the first stage. In the filter mode, FUNC + GATE no longer opens the click menu; outside the filter mode FUNC + GATE works as always. With the filter off (cutoff 127) the track stays bit-identical in 24 dB too.
- Holding RETRIG and turning a knob (for example RETRIG + LFO SPEED for the LFO Amount of patch 13) does not end the filter mode; only a short tap of RETRIG does.
- **Cutoff 127 = off.** At 127, with the envelope not pulling the cutoff down, the track is bit-for-bit what it was without the patch. Switching on and off is crossfaded over about 5 ms, so there is no click.
- Once the filter is on, it stays on even when cutoff + envelope go above 127 (it then sits at about 20 kHz).
- The filter is warm rather than screaming: the resonance is capped per cutoff and the input is softly saturated.
- The four parameters are **real parameters** of every machine: p-lockable, **LFO** and **velocity destinations**; cutoff and resonance answer **CC 74** and **CC 71**.
- Sounds from the stock OS or older versions load with the filter open.

## What is stored

Cutoff, resonance, envelope amount and decay are saved **with the sound**; their p-locks with the pattern.
12 / 24 dB is saved **in the pattern**, per track (header byte 58, bits 0–5 = tracks 1–6; a new pattern starts at 12 dB).

## Dependencies

- Requires: [00 core](00-core.md).

## How it works

**Sound.** After the firmware's Volume + Distortion stage the patch runs a trapezoidal state-variable filter
(after Zavalishin, *The Art of VA Filter Design*) on each track's buffer, 32 samples per block, in fixed point on the
EMAC. The coefficients come from tables (cutoff, Q, Q cap, decay) and are updated once per block from the firmware's
smoothed parameter words, so LFO, p-locks and velocity modulation are already included. The envelope restarts at 1 on
every trig of the track and decays exponentially.

**24 dB.** The second stage is the same filter structure with a fixed Q of 0.707, linear, using the cutoff coefficient
of the first stage. It runs only for tracks set to 24 dB and is crossfaded like switching the filter on. Its code and
state live in the core's payload area (slot `track-filter`), since the sprite masks are full.

**Parameters.** Four descriptors become Filter Cutoff, Filter Reso, Filter Env and Filter Decay, parameters k 28–31 of
every machine. The core saves them with the sound and handles their p-locks and LFO / velocity destinations.

**Filter mode.** A hook on GATE in the main screen's key handler switches the mode on while RETRIG is held; a hook on
RETRIG switches it off on a short tap. In the mode, the parameter page's knob lookup returns the filter descriptors for
PITCH, DECAY, COLOR and SHAPE, and the main screen claims the four knob LEDs at the start of each frame.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x40059852`, `0x401005a8`, `0x4001ca9c`, `0x4001c4ba`, `0x40021e0e`, `0x4001c326`, `0x400243d6`
- Code and data (unused sprite masks): `0x40172a68` (192 B), `0x40172608` (376 B), `0x40179730` (376 B), `0x4014ab5c` (280 B), `0x401601fc` (280 B), `0x401625bc` (280 B), `0x401784e8` (272 B), `0x401780a8` (272 B), `0x40163fb8` (280 B), `0x40165fec` (192 B), `0x4014b5b4` (108 B), `0x4016616c` (280 B), `0x40166760` (280 B), `0x40173848` (272 B)
- RAM: `0x40173848` (252 B, filter state + mode), `0x43006000` (760 B, payload slot 'track-filter': code of the 24 dB stage), `0x43006e00` (240 B, state of the 24 dB stage)
- Pattern: header byte 58: 24 dB per track (bits 0–5)

## Source and tests

- Generator: `src/v2/g2_trackfilter.py` (EMAC instructions: cfemac.py)
- Tests: `test_trackfilter.py`: the filter through the real hook against a floating-point model; cutoff 127 bit-identical; response, envelope, stability, cost; the 24 dB stage, its switch and storage; filter mode with the real key handler; saving and loading with the real functions; p-locks; reset. `test_filterleds.py`: the knob LEDs. Both also `--alone`.

## Status

Tested on a Model:Samples running the Cycles OS. Updated in v2.3.0 (reset, GATE on release) and v2.3.1 (24 dB). Not yet tested on a real Model:Cycles.

← [11-fill2](11-fill2.md) · [all patches](../../README.md#patches) · [13-lfo-amount](13-lfo-amount.md) →
