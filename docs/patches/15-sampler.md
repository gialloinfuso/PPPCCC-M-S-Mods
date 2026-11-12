# 15 · Grit: sampler machine

Patch id `sampler` · file [`patches/15-sampler.json`](../../patches/15-sampler.json) · 146 writes

A 7th machine, **Grit**: a deliberately simple sampler in the style of the Model:Samples, with the character of
classic vintage samplers. It plays samples from the +Drive (the Elektron sample format) and has six sound models.
Grit, Vlvt (16) and Monom (17) only work together: Vlvt needs Grit, Monom needs both.

## Controls

| Do this | Result |
|---|---|
| **MACHINES** | Grit is the 7th machine. |
| **FUNC + MACHINES** (browser) on a Grit track | Choose a sample file; the click (YES) puts it on the track, as on the Model:Samples. Hold a trig while choosing = sample lock. |
| **COLOR** | Sample start. |
| **SHAPE** | Sample length (part of the whole sample, limited at the end). |
| hold **FUNC** + turn **COLOR** | Moves start and end together. |
| **CONTOUR** | Model: CLEAN, SP, LM, MIRAGE, TX16W, MPC60 (see the table). |
| **PITCH**, **DECAY** | Pitch and amp decay, as usual; FUNC + DECAY = attack (core). |
| **PUNCH** key | Loop on / off. |
| **GATE** key | Reverse on / off. |
| turn COLOR or SHAPE | The display shows the waveform of the sample with lines at start and end (only while turning). |
| Device Config > **Transfer** | CYC / SMP: in SMP the device answers Elektron Transfer as a Model:Samples, so you can upload samples. Every start begins with CYC. |

### Models

| Model | Character |
|---|---|
| CLEAN | clean playback with interpolation |
| SP | 26 kHz fixed clock, drop-sample (no interpolation when pitching), 12 bit, hot input, 4-pole 12 kHz output filter |
| LM | 28 kHz clock that follows the pitch, 8-bit mu-law, 2-pole 11 kHz output filter |
| MIRAGE | 29.4 kHz clock that follows the pitch, raw 8-bit linear, +2 dB, 2-pole 8 kHz output filter with a little resonance |
| TX16W | 33.3 kHz fixed clock, drop-sample, 12-bit floating point (the step grows with the level), +1 dB, 2-pole 12.5 kHz |
| MPC60 | 40 kHz clock that follows the pitch, 12-bit floating point (non-linear conversion), +1.5 dB, 2-pole 15 kHz |

## Good to know

- A **sample lock** locks only the sample; every other parameter follows the track (real p-locks stay).
- The samples of the playing pattern (also all sample locks) are loaded ahead and kept in memory, up to 32; memory of samples no longer used is reused.
- Grit is mono. A short fade on every trig keeps long samples from clicking when they retrigger.
- After switching Transfer, reconnect Elektron Transfer. Never accept an OS update while the device answers as a Model:Samples.
- Transfer identity switch: method from Model-TG by TinyGregAudio (MIT); own code. Loading guards in the style of model27's sampler by durchgemacht (MIT).

## What is stored

The sample of a track is saved **with the sound** (its file id), start / length / model / loop / reverse like every parameter; sample locks with the pattern. The samples themselves stay on the +Drive.

## Dependencies

- Requires: [00 core](00-core.md).
- Needed by: [16](16-strings.md), [17](17-mono.md).

## How it works

**Machine.** The firmware's machine limits are raised from 6 to 7 (voice loop, parameter lookup, machine wheel,
MACHINES screen); the new machine gets its own name, icon, parameter rows and render function. Three free descriptors
become Start, Length and Model.

**Playback.** Samples are loaded in the UI task, 64 KB per frame, into memory the firmware does not use, and an overview
(min / max per column) is computed for the waveform display. The render function reads the sample at the track's
pitch; SP and LM resample on their own clock with band-limited edges, then run biquad reconstruction filters, all in
fixed point.

**Browser.** On a Grit track the preset browser lists sample files; choosing one stores its file id in the sound (via
the core's sound slot).

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x4005a6a6`, `0x4005a572`, `0x400147a4`, `0x400148aa`, `0x400148b2`, `0x400a25e0`, `0x400a7dba`, `0x400a7df4`, `0x400a26e8`, `0x40118646`, `0x4010e5e4`, `0x4005a2be`, `0x4005a322`, `0x4005a390`, `0x4005a6ba`, `0x4005a6f0`, `0x400a2614`, `0x400a7d6c`, `0x400a7e16`, `0x400a2638`, `0x4004df5c`, `0x4004df76`, `0x4001e8da`, `0x400a6602`, `0x400075f0`, `0x4010053c`, `0x400590ce`, `0x40084b8e`, `0x40084c14`, `0x4009249a`, `0x40094c9a`, `0x40032aee`
- Code and data (unused sprite masks): `0x40186238` (272 B), `0x4018b1a8` (272 B), `0x4018bcc8` (124 B), `0x40192ba4` (272 B), `0x40184988` (184 B), `0x4018d1b8` (376 B), `0x40168da4` (192 B), `0x4016bcd8` (192 B), `0x4016dab8` (192 B), `0x4016fae8` (192 B), `0x40177f28` (192 B), `0x40178708` (192 B), `0x40183408` (192 B), `0x40184c78` (192 B), `0x401792b0` (192 B), `0x40178fc0` (192 B), `0x40184af8` (192 B), `0x40187528` (192 B), `0x401876a8` (192 B), `0x40188f98` (192 B), `0x4018b9c8` (192 B), `0x4018a608` (192 B), `0x4018bb48` (192 B), `0x40170c48` (192 B), `0x40179430` (192 B), `0x40171a48` (192 B), `0x401795b0` (192 B), `0x40179b18` (192 B), `0x40172be8` (192 B), `0x4017c97c` (192 B), `0x4018cbc8` (192 B), `0x40190184` (192 B), `0x401736c8` (192 B), `0x401829b8` (192 B), `0x4018d038` (192 B), `0x4018d798` (192 B), `0x4018f80c` (192 B), `0x40190334` (192 B), `0x4019089c` (192 B), `0x4016fd60` (124 B), `0x40192a24` (192 B), `0x40172510` (124 B), `0x401837d8` (124 B), `0x401871a0` (124 B), `0x40189838` (124 B), `0x40161880` (108 B), `0x4018a510` (124 B), `0x40160a94` (108 B), `0x401617a8` (108 B), `0x401629dc` (108 B), `0x401698d0` (108 B), `0x401630e4` (104 B), `0x401638c0` (104 B)
- RAM: `0x4300be00` (512 B, loaded samples (payload)), `0x40186238` (224 B, machine rows (7)), `0x43801000` (49283072 B, sample memory (outside the image))

## Source and tests

- Generator: `src/v2/g2_sampler.py`
- Tests: `test_sampler.py`: integer model and biquads against floating point, saturation, filters, aliasing, overview, waveform against the real drawing calls, sample locks, loading; `test_transfer.py`: the identity answer, product number and message types in both modes; `test_smp12.py`; `--alone`.

## Status

Tested on a Model:Samples running the Cycles OS. New in v2.3.0. Not yet tested on a real Model:Cycles.

← [14-direct-jump](14-direct-jump.md) · [all patches](../../README.md#patches) · [16-strings](16-strings.md) →
