# 06 · Strum for CHORD and Vlvt

Patch id `strum` · file [`patches/06-strum.json`](../../patches/06-strum.json) · 50 writes

CHORD tracks (and Vlvt tracks, patch 16) play their chord notes one after another, like a strummed guitar,
instead of all at once. Time and pattern are set **per track** and saved with the sound.

## Controls

| Do this | Result |
|---|---|
| hold **FUNC** + turn **SHAPE** | Strum time: OFF (all notes together), 2–250 ms between two notes, then note values /64 … 1/1 in tempo. |
| hold **FUNC** + turn **COLOR** | Strum pattern (see the table). |
| hold a trig + FUNC + SHAPE / COLOR | p-locks the strum on that trig. |

### Strum patterns

| Name | Order of the four chord notes |
|---|---|
| UP | low to high |
| DOWN | high to low |
| RND | a new random order on every trig |
| 1324, 1423, 4132, 4231 | the given order (1 = lowest note) |
| ROOT | the lowest note, then the other three together |
| TOP | the highest note, then the other three together |

## Good to know

- Every chord note has its own envelope from its strum onset: attack (FUNC + DECAY, from the core), hold while GATE, decay (DECAY).
- Chords with fewer notes skip the missing ones.
- Strum time and pattern are real parameters: p-lockable, LFO and velocity destinations.
- The global strum of v2.2 (SETTINGS + SHAPE, one value per pattern) is replaced by this.

## What is stored

**With the sound** (and so with the kit and the project); p-locks with the pattern.

## Dependencies

- Requires: [00 core](00-core.md).

## How it works

A hook at the end of the CHORD voice update keeps a counter per voice from the moment the voice is triggered.
Each operator starts its own envelope when its turn in the pattern comes; until then it fades out what was still
ringing (no click). Two descriptors in the core's table become "Strum" and "Strum Pattern" on CHORD and Vlvt tracks;
the core saves them with the sound.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x400ab240`, `0x400ab2d2`
- Code and data (unused sprite masks): `0x40192734` (376 B), `0x4017a4d4` (124 B), `0x40163990` (104 B), `0x40189618` (272 B), `0x40166690` (104 B), `0x40168fb4` (104 B), `0x401679d8` (104 B), `0x40179c98` (104 B), `0x40167b80` (104 B), `0x4018d4a8` (376 B)
- RAM: `0x4233c378` (4 B, root note level)

## Source and tests

- Generator: `src/v2/g2_strum.py` (gen_strum_113.py)
- Tests: `test_strum.py`: strum timing and patterns on rebuilt voices against a model, envelopes, retrigger without a click. `test_modular.py`.

## Status

Tested on a Model:Samples running the Cycles OS. Updated in v2.3.0 (per track, patterns, FUNC keys). Not yet tested on a real Model:Cycles.

← [05-delay-fx](05-delay-fx.md) · [all patches](../../README.md#patches) · [07-load-meter](07-load-meter.md) →
