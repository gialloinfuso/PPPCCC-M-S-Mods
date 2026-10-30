# Generators

The patches are hand-encoded ColdFire code, written by Python generators (class `A` in `gen_solo.py`: words, long
words, labels, branches; no assembler). Each generator checks that the hooked instructions in your image are the
expected originals and writes a development JSON with the original bytes (`old`). That JSON stays on your machine.
`regen.py` runs all generators and checks that the published `patches/*.json` are exactly what they produce.

**No Elektron bytes in the sources.** The generators never contain original firmware bytes:

- A hook check is a length plus a SHA-256 of the expected original bytes (`(6, '9bb3...')`), checked with `matches()`.
- Where a patch has to run instructions that its hook moved out of the firmware (or reuses a short firmware
  calculation, e.g. the delay time), the generator calls `a.orig(va, n)`: the bytes are read from your image, and their
  place is recorded in `ORIGS`. The published patch holds zeros there plus a `from_original` entry
  (`tools/apply_patches.py` `to_public`), and the build tool copies those bytes from your own firmware file.
- Firmware addresses (functions the patches call, tables they read) are used as plain numbers.

## v2 generators (`src/v2/`)

| Patch | Generator | Shared code from `src/` |
|---|---|---|
| 00 core | `g2_core.py` | |
| 01 mute-solo | `gen_solo.py` (unchanged since v1.0.0) | |
| 02 live-mute | `gen_livemute.py` (unchanged) | |
| 03 hold-mute | `gen_holdmute_113.py` (unchanged) | `gen_holdmute3.py` |
| 04 delay-notes | `gen_delaynotes_113.py` (unchanged) | `gen_delaynotes.py` |
| 05 reverb-fx | `g2_reverbfx.py` | `gen_chorus_113.py`, `gen_chorusfx.py`, `gen_chorus.py`, `gen_chorus3.py`, `gen_fx4.py`, `gen_phaser_113.py`, `gen_razer_113.py` |
| 06 delay-fx | `g2_delayfx.py` | `gen_fx4.py`, `gen_digidelay_113.py`, `gen_moddelay_113.py` |
| 07 strum | `g2_strum.py` | `gen_strum_113.py` |
| 08 load-meter | `g2_loadmeter.py` | `gen_loadmeter_113.py`, `gen_overlay_113.py` (pixel font) |
| 09 groove | `g2_groove.py` | `gen_groove_113.py`, `../grooves/grooves.json` |
| 10 control-mode | `g2_control.py` | |
| 11 trig-select | `g2_trigselect.py` | |
| 12 fill2 | `g2_fill2.py` | |
| 13 track-filter | `g2_trackfilter.py` | `v2/cfemac.py` (EMAC instructions) |
| 14 lfo-amount | `g2_lfoamount.py` | |
| 15 direct-jump | `g2_directjump.py` | |

`common.py` holds the firmware addresses, the pattern-header layout and the core's slot numbers. `gen_all.py` runs
every generator, checks that the whole set can be applied together (writes may only overlap a required patch) and
writes `v2/out/NN-id.json`.

The other files in `src/` are the v1.0.0 generators. v2 reuses their sound code byte for byte (the tests check this),
so they stay here as libraries.

## Running them

```sh
pip install capstone
git clone https://github.com/18nelli18/Modded-Cycles             # for tools/sprites.py
git clone https://github.com/drumkilla/elektron-model-tweaks     # for the latching-mute patch (overlap check)
python3 src/regen.py <section_3_MAIN_OS.bin of the official Model:Cycles OS 1.13>
```

`regen.py` builds the development layout the generators expect in `build/regen` (your image in `out/`, `src/` as
`solo/`, `src/v2/` as `v2/`) and must print `ok` for all 13 patches.

The comments in the generators are in German. They were written while developing, and they document every address
and decision.
