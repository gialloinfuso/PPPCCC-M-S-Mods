# 08 · Audio load meter

Patch id `load-meter` · file [`patches/08-load-meter.json`](../../patches/08-load-meter.json) · 8 writes

Shows how much of the time the audio engine needs, so you can see how close a combination of effects is to
the limit. When the load is high, the controls get sluggish because the UI only gets what the audio engine leaves.

## Controls

| Do this | Result |
|---|---|
| hold **SETTINGS** + turn **REVERB SEND** right | Meter on: a small box "LOAD peak/average" in percent of the audio block time, updated every 0.5 s. |
| … left | Meter off. |

### Measured on a Model:Samples (peak/average)

| Setup | Load |
|---|---|
| idle, stock effects | 82 / 76 |
| VIBDEL | 83 / 78 |
| CHODEL | 85 / 80 |
| VIBDEL + RAZR | 87 / 83 |
| CHODEL + RAZR | 89 / 85 |

## Good to know

- The stock firmware already needs about three quarters of the time.
- When the meter is off, the probe costs one compare per block.

## What is stored

Nothing; the meter is always off after power-on.

## Dependencies

- Requires: [00 core](00-core.md).

## How it works

The interrupt's call of the audio function is wrapped: the probe reads a hardware timer before and after,
keeps the maximum and the sum over 750 blocks (about 0.5 s), and turns them into percent of one block (90112 timer
ticks). The on/off state lives in RAM that the firmware does not clear at start-up, so the meter only counts as on
when a 32-bit key word is set.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x40059382`
- Code and data (unused sprite masks): `0x4016b6f8` (376 B), `0x4016b9e8` (376 B), `0x40152d38` (192 B)
- RAM (unused area behind the BSS): `0x4a33c3d0` (36 B, meter state + text)

## Source and tests

- Generator: `src/v2/g2_loadmeter.py` (gen_loadmeter_113.py, gen_overlay_113.py)
- Tests: `test_mods_diff.py`: measurement and text against v1.0.0, gestures, random RAM content after power-on = off. `test_popup.py`: the box drawn pixel for pixel.

## Status

Tested on a Model:Samples running the Cycles OS. Not yet tested on a real Model:Cycles.

← [07-strum](07-strum.md) · [all patches](../../README.md#features) · [09-groove](09-groove.md) →
