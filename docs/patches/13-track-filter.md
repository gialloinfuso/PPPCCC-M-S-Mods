# 13 · Track filter: a 12 dB low-pass filter per track with envelope

Patch id `track-filter` · file [`patches/13-track-filter.json`](../../patches/13-track-filter.json) · 36 writes

A resonant 12 dB low-pass filter on every track, with its own envelope, after the machine and the track's volume and
distortion. It works on all six machines. A **filter mode** puts its four parameters on the knobs, so your hands stay
on the device.

## Controls

| Do this | Result |
|---|---|
| hold **RETRIG** + press **GATE** | Filter mode on. A popup shows "FILTER ON", and the LEDs of the four knobs light up. |
| tap **RETRIG** | Filter mode off ("FILTER OFF"). |
| in the filter mode: **PITCH** | Cutoff, 20 Hz to 20 kHz. 127 = filter off. |
| in the filter mode: **COLOR** | Resonance (Q 0.5 to 5). |
| in the filter mode: **SHAPE** | Envelope depth, bipolar: right opens the filter on every trig, left closes it, middle = OFF. |
| in the filter mode: **DECAY** | Envelope decay, about 5 ms to 5 s. |
| hold a trig in the filter mode + turn a knob | p-locks the filter parameter on that trig. |

GATE on its own does what it always did. Holding RETRIG and turning a knob (for example RETRIG + LFO SPEED for the LFO
Amount of patch 14) does not end the filter mode; only a short tap of RETRIG does.

## Good to know

- **Cutoff 127 = off.** At 127, with the envelope not pulling the cutoff down, the track is bit-for-bit what it was
  without the patch. Switching between on and off is crossfaded over about 5 ms, so there is no click.
- Once the filter is on, it stays on even when cutoff + envelope go above 127 (it then sits at about 20 kHz).
- The filter is warm rather than screaming: the resonance is capped per cutoff (full from 80 Hz to 2 kHz, gentler
  above, no bass drone below) and the input is softly saturated.
- The four parameters are **real parameters** of every machine: they can be p-locked, chosen as **LFO destination**
  and **velocity destination**, and the cutoff and resonance answer **CC 74** and **CC 71**.
- Sounds from the stock OS or older versions load with the filter open (cutoff 127, resonance 0, envelope OFF).

## What is stored

Cutoff, resonance, envelope depth and decay are saved **with the sound** (and so with the kit and the project), like
every machine parameter; their p-locks are saved with the pattern.

## Dependencies

- Requires: [00 core](00-core.md) (sound slots for the four extra parameters, popups).

## How it works

**Sound.** After the firmware's Volume + Distortion stage the patch runs a trapezoidal state-variable filter
(after Zavalishin, *The Art of VA Filter Design*) on each track's mono buffer, 32 samples per block, in fixed point on
the EMAC. The coefficients come from tables (cutoff, Q, Q cap, decay) and are updated once per block from the
firmware's smoothed parameter words, so LFO, p-locks and velocity modulation are already included. The envelope
restarts at 1 on every trig of the track and decays exponentially.

**Parameters.** Descriptors 1–4 (unused "Error" entries of the firmware's parameter table) become Filter Cutoff, Filter
Reso, Filter Env and Filter Decay, parameters k 28–31 of every machine. The core saves them with the sound and handles
their p-locks and LFO / velocity destinations.

**Filter mode.** A hook on GATE in the main screen's key handler switches the mode on while RETRIG is held; a hook on
RETRIG switches it off on a short tap. In the mode, the parameter page's knob lookup returns the filter descriptors for
PITCH, DECAY, COLOR and SHAPE, and the main screen claims the four knob LEDs at the start of each frame.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x40059852`, `0x401005a8`, `0x4001ca9c`, `0x4001c4ba`, `0x40021e0e`
- Descriptors 1–4 of the parameter table (`0x4010dd18`…)
- Code and data (unused sprite masks): `0x40172a68` (192 B), `0x40172608` (376 B), `0x40179730` (376 B), `0x4014ab5c` (280 B), `0x401601fc` (280 B), `0x401625bc` (280 B), `0x401784e8` (272 B), `0x401780a8` (272 B), `0x40163fb8` (280 B), `0x40165fec` (192 B), `0x4014b5b4` (108 B), `0x4016616c` (280 B), `0x40166760` (280 B)
- RAM (in a sprite mask): `0x40173848` (252 B, filter state per track and filter mode)
- Core: encoder slot 7, sound slot 0

## Source and tests

- Generator: `src/v2/g2_trackfilter.py` (EMAC instructions: `src/v2/cfemac.py`)
- Tests: `test_trackfilter.py`: the filter through the real hook against a floating-point model of the same equations; cutoff 127 bit-identical; frequency response, envelope, stability at full resonance and full scale, registers / MACSR / accumulators, cost; knob mapping, filter mode with the real key handler and popup, saving and loading with the real functions, p-locks. `test_filterleds.py`: the knob LEDs with the firmware's real LED function and knob-LED loop. Both also `--alone` (only the core and this patch).

## Status

Tested on a Model:Samples running the Cycles OS. New in v2.2.0. Not yet tested on a real Model:Cycles.

← [12-fill2](12-fill2.md) · [all patches](../../README.md#features) · [14-lfo-amount](14-lfo-amount.md) →
