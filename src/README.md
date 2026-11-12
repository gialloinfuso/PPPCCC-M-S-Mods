# Generators

The patches are ColdFire code written as **assembler text inside Python**. Python fills in addresses and constants
(f-strings), `v2/cfasm.py` assembles the text (a small ColdFire assembler of my own, only ColdFire-valid forms, EMAC
instructions through `v2/cfemac.py`), and the generator writes the result into free memory. Each generator checks that
the hooked instructions in your image are the expected originals and writes a development JSON with the original
bytes (`old`). That JSON stays on your machine. `regen.py` runs all generators and checks that the published
`patches/*.json` are exactly what they produce.

A short example (`v2/g2_lfoamount.py`, the knob lookup of LFO Amount):

```python
asm(a, f'''
; ---------------- POST: d0 = descriptor of the firmware; LFO SPEED + RETRIG -> Amount
POST:   move.l  4(sp),d1
        cmpi.l  #{ENC_LFO},d1
        bne     out
        move.l  d0,-(sp)
        pea     {KEY_RETRIG}.w
        jsr     {C.HELD:#x}
        addq.l  #4,sp
        move.l  d0,d1
        move.l  (sp)+,d0
        tst.l   d1
        beq     out
        ...
out:    lea     16(sp),sp
        rts
''')
```

Directives: `orig VA,N` copies N original bytes from your image (see below), `dc.b` / `dc.w` / `dc.l` for data;
`bra.s` / `beq.s` for short branches; labels are local to a block, other names come from the generator.
`common.asm2(org, text, tail)` assembles twice so that data can follow the code.

**No Elektron bytes in the sources.** The generators never contain original firmware bytes:

- A hook check is a length plus a SHA-256 of the expected original bytes (`(6, '9bb3...')`), checked with `matches()`.
- Where a patch has to run instructions that its hook moved out of the firmware (or reuses a short firmware
  calculation, e.g. the delay time), the code says `orig VA,N`: the bytes are read from your image, and their place is
  recorded. The published patch holds zeros there plus a `from_original` entry (`tools/apply_patches.py`
  `to_public`), and the build tool copies those bytes from your own firmware file.
- Firmware addresses (functions the patches call, tables they read) are used as plain numbers.

## v2 generators (`src/v2/`)

| Patch | Generator | Shared code |
|---|---|---|
| 00 core | `g2_core.py` | `g2_dtab.py` (descriptor table), `g2_mlbrowser.py`, `g2_browserscroll.py` (scrolling names), `g2_levelpan.py`, `g2_browserkeys.py` |
| 01 mute-solo | `gen_all.py` (`mute_bundle`) | `g2_latch.py` (latching mute), `gen_solo.py`, `gen_livemute.py` (unchanged since v1.0.0) |
| 02 hold-mute | `gen_holdmute_113.py` (unchanged) | `gen_holdmute3.py` |
| 03 delay-notes | `gen_delaynotes_113.py` (unchanged) | `gen_delaynotes.py` |
| 04 reverb-fx | `g2_reverbfx.py` | `g2_reverbs.py` + `rv_algos.py` (Hall / Room / Plate), `gen_chorus_113.py`, `gen_chorusfx.py`, `gen_chorus.py`, `gen_chorus3.py`, `gen_fx4.py`, `gen_phaser_113.py`, `gen_razer_113.py` |
| 05 delay-fx | `g2_delayfx.py` | `gen_fx4.py`, `gen_digidelay_113.py`, `gen_moddelay_113.py` |
| 06 strum | `g2_strum.py` | `gen_strum_113.py` |
| 07 load-meter | `g2_loadmeter.py` | `gen_loadmeter_113.py`, `gen_overlay_113.py` (pixel font) |
| 08 groove | `g2_groove.py` | `gen_groove_113.py`, `groovetab.py`, `../grooves/grooves.json` |
| 09 control-mode | `g2_control.py` | |
| 10 trig-select | `g2_trigselect.py` | |
| 11 fill2 | `g2_fill2.py` | |
| 12 track-filter | `g2_trackfilter.py` | `cfemac.py` (EMAC instructions) |
| 13 lfo-amount | `g2_lfoamount.py` | |
| 14 direct-jump | `g2_directjump.py` | |
| 15 sampler | `g2_sampler.py` | `art/grit_klein.bmp` (machine icon) |
| 16 strings | `g2_strings.py` | `str_model.py` (floating-point model for the tests), `art/vlvt_klein.bmp` |
| 17 mono | `g2_mono.py` | `mono_tables.py`, `mono_model.py` (model for the tests), `art/monom_klein.bmp` |
| 18 param-undo | `g2_paramundo.py` | |
| 19 pad-mode | `g2_pad.py` | |

`common.py` holds the firmware addresses, the pattern-header layout and the core's slot numbers. `gen_all.py` runs
every generator, checks that the whole set can be applied together (writes may only overlap a required patch) and
writes `v2/out/NN-id.json`.

The other files in `src/` are the v1.0.0 generators. v2 reuses their sound code byte for byte (the tests check this),
so they stay here as libraries; they also build the v1 reference patches for the tests. Parts of them that only v1
uses are still hand-encoded words.

## Running them

```sh
pip install capstone pillow
git clone https://github.com/18nelli18/Modded-Cycles             # for tools/sprites.py
python3 src/regen.py <section_3_MAIN_OS.bin of the official Model:Cycles OS 1.13>
```

`regen.py` builds the development layout the generators expect in `build/regen` (your image in `out/`, `src/` as
`solo/`, `src/v2/` as `v2/`) and must print `ok` for all 20 patches.

The comments in the generators are in German. They were written while developing, and they document every address
and decision.
