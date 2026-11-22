# 05 · Delay FX: Digital Delay, Vibrato Delay / Chorus Delay (VIBDEL / CHODEL)

Patch id `delay-fx` · file [`patches/05-delay-fx.json`](../../patches/05-delay-fx.json) · 17 writes

Three delays for the delay slot. **Digital** is the opposite of the dark stock delay: bright and clean, up to
5.4 s, every repeat a little thinner in the lows. **VIBDEL** and **CHODEL** are modulated delays in the spirit of
classic analog delays with modulation.

## Controls

| Do this | Result |
|---|---|
| hold **TRACK** + turn **Delay Time** | Delay → Digital → VIBDEL → CHODEL (left goes back). 4 detents per step; the parameter names change. |
| hold **FUNC** + turn **DELAY SEND** | Modulation speed 0–127 of VIBDEL / CHODEL; popup "VIBDEL Speed" or "CHODEL Speed". |
| Delay Time / Feedback / Send | As usual. Delay Time follows the tempo, with the note values and exact triplets of patch 03 when it is installed. |

### The delays

| | Digital | VIBDEL | CHODEL |
|---|---|---|---|
| Sound | bright, clean | vibrato on the delay; the feedback is modulated too, so the repeats get more and more wobbly | a clean repeat plus a chorused one, left and right moving in opposite directions |
| Filters in the feedback | high-pass ~240 Hz, low-pass ~12.8 kHz | low-pass ~5 kHz, high-pass ~90 Hz | low-pass ~5 kHz, high-pass ~90 Hz |
| Depth / speed | – | ±0.75 ms, 0.5–9.9 Hz | ±2 ms, 0.1–3 Hz |

## Good to know

- The sound is bit-identical to v1.0.0 (patches 07 and 09 there).
- The modulated delays compute their LFO once per audio block and keep their state in cached RAM, to keep the audio load low.
- **v2.3.1: less CPU load, same sound.** Digital, VIBDEL and CHODEL read the delay line through the cache; only the write goes to the uncached address, as before. CHODEL made six uncached memory accesses per sample, now one. The output is bit-for-bit the same.

## What is stored

**In the pattern**: header byte 53 = delay type (0 Delay, 1 Digital, 2 VIBDEL, 3 CHODEL), byte 54 = speed (stored XOR 64, so a new pattern starts at 64).

## Dependencies

- Requires: [00 core](00-core.md).

## How it works

Two hooks in the mixer: the delay call and the write DMA of the delay line. Once per audio block the patch reads
the type and speed of the running pattern, sets the parameter names and runs its own delay loop in its half of the
delay memory, or jumps straight to the firmware's delay. The delay time is computed like the firmware's; if patch 03
is installed (detected at run time), its exact triplets are used.

The delay line (`0x4a400000`, 8 bytes per frame) is written through the uncached address, so the memory is always current
for the firmware's DMA and when switching types. Since v2.3.1 the read heads use the cached alias of the same memory
(`0x42400000`): every read head is at least 32 frames behind the write head, so a cache line only ever holds finished
frames, and it could only go stale after a full turn of the ring (5.4 s).

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x4005699c`, `0x40056a3c`
- Code and data (unused sprite masks): `0x40185f48` (272 B), `0x40160e6c` (280 B), `0x4018a788` (1024 B), `0x401904b4` (376 B), `0x4018fc74` (376 B), `0x40160b6c` (280 B), `0x40160864` (280 B)
- RAM: `0x4233c140` (20 B, digital delay state), `0x4233c320` (56 B, VIBDEL/CHODEL state), `0x4233c3fd` (2 B, type + speed mirror)
- Pattern: header byte 53: 0 Delay, 1 Digital, 2 VIBDEL, 3 CHODEL; byte 54: speed XOR 64

## Source and tests

- Generator: `src/v2/g2_delayfx.py` (sound code from gen_fx4.py, gen_digidelay_113.py, gen_moddelay_113.py)
- Tests: `test_fx_diff.py`: all three delays bit-identical to v1.0.0, delay time with and without patch 03, gestures. `test_modular.py`.

## Status

Tested on a Model:Samples running the Cycles OS. Updated in v2.3.0 (speed on FUNC + DELAY SEND) and v2.3.1 (less CPU load). Not yet tested on a real Model:Cycles.

← [04-reverb-fx](04-reverb-fx.md) · [all patches](../../README.md#patches) · [06-strum](06-strum.md) →
