# 01 · Solo in latching mute mode

Patch id `mute-solo` · file [`patches/01-mute-solo.json`](../../patches/01-mute-solo.json) · 4 writes

Solo one track for a moment, then return to exactly the mutes you had before. Solo works inside the
**latching mute mode** from drumkilla's latching-mute patch: hold **TRK** and tap **FUNC**, and the FUNC key lights
up to show the mode.

## Controls

| Do this | Result |
|---|---|
| Latching mute mode + **hold FUNC + track key** | Solo that track: it plays, all other tracks are muted. |
| the same again | Back to the mutes you had before the solo. |
| hold FUNC + another track key while soloed | Solo moves to that track; the saved mutes stay the ones from before the first solo. |
| track key without FUNC | Toggles that mute as usual and ends the solo (nothing is restored). |

## Good to know

- Without the latching mode (the stock hold-TRK mute), FUNC + track key behaves as before.
- Unchanged since v1.0.0.

## What is stored

Nothing. The saved mutes live in RAM and are gone after power-off.

## Dependencies

- Requires: drumkilla's [latching mute](https://github.com/drumkilla/elektron-model-tweaks).

## How it works

The mute view calls the firmware's mute-toggle function when you press a track key. The patch replaces that one
call. If the latching flag is set and FUNC is held, it saves the six mute states and sets them for a solo instead. If
it is called again for the same track, it writes the saved states back. In every other case it calls the original
toggle.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x40023550`
- Code and data (unused sprite masks): `0x40167c50` (280 B)

## Source and tests

- Generator: `src/gen_solo.py`
- Tests: `test_solo.py`: solo, restore, solo on another track, FUNC not held, mode not latched, plain press clears the solo; registers and stack are preserved.

## Status

Tested on a Model:Samples running the Cycles OS. Not yet tested on a real Model:Cycles.

← [00-core](00-core.md) · [all patches](../../README.md#features) · [02-live-mute](02-live-mute.md) →
