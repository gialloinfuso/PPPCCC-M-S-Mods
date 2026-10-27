# 09 · Grooves and humanize

Patch id `groove` · file [`patches/09-groove.json`](../../patches/09-groove.json) · 19 writes

A groove template shifts and accents the steps. Each track's Swing sets how strongly that track follows the
groove. On top, humanize adds random timing and velocity per track. Everything is stored in the pattern.

## Controls

| Do this | Result |
|---|---|
| hold **FUNC** + turn **Swing** | Groove: Swing → Boom Bap → Disco → Reggae → Bongo → Caixixi → Highlife → Kuduro; 4 detents per step, the popup shows the name. |
| **Swing** (per track) | Amount of the groove on this track: minimum = straight, maximum = the full groove, timing and accents. With "Swing" selected it is the stock swing. |
| hold **SETTINGS** + turn **Swing** | Humanize timing 0–100 of the selected track; popup "Hum Time / Track". |
| hold **MACHINE** + turn **Swing** | Humanize velocity 0–100 of the selected track; popup "Hum Vel / Track". |
| hold **TRACK** as well | All six tracks at once; popup "… / All". Relative or absolute, as set with patch 10. |

### The grooves

| # | Name | Length | Character |
|---|---|---|---|
| 0 | Swing | – | the firmware's own swing |
| 1 | Boom Bap | 1 bar | laid-back hip-hop 16ths |
| 2 | Disco | 1 bar | live-feel disco 16ths |
| 3 | Reggae | 4 bars | displaced accents, loose feel |
| 4 | Bongo | 4 bars | bongo 16ths |
| 5 | Caixixi | 1 bar | shaker accents |
| 6 | Highlife | 2 bars | clave accents |
| 7 | Kuduro | 2 bars | displaced 8th-note triplet accents |

## Good to know

- At 100, humanize timing moves a note up to ±0.15 step (about ±19 ms at 120 BPM); humanize velocity changes it by up to about ±29 %.
- Humanize works on top of every groove, including Swing.
- **MACHINE opens its menu on release** instead of on press, so it can be used as a modifier. After a MACHINE + Swing gesture the menu does not open. FUNC + MACHINE is unchanged.
- NUDGE is unchanged.

## What is stored

**In the pattern**: header byte 55 = groove (0–7), bytes 40–45 = humanize timing of tracks 1–6, 46–51 = humanize velocity of tracks 1–6 (0–100; other values count as 0).

## Dependencies

- Requires: [00 core](00-core.md).

## How it works

The sequencer's event builder adds the swing offset in one place. The patch replaces that with its own routine.
For groove 0 it does what the firmware does. For a table groove it adds offset × Swing/30 and scales the velocity
toward the groove accent. Then it adds humanize: a random value scaled by the track's timing and velocity amounts.
The groove tables are 64 steps of offset (1/256 step) and accent velocity (`grooves/grooves.json`).

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x40054af8`, `0x4001ca1e`
- Code and data (unused sprite masks): `0x4014b85c` (280 B), `0x4014d74c` (280 B), `0x401542f8` (280 B), `0x401548b4` (280 B), `0x4015b8f8` (280 B), `0x4016f8c8` (272 B), `0x40171f30` (376 B), `0x4015f38c` (192 B)
- RAM (unused area behind the BSS): `0x4a33c3a4` (4 B, MACHINE pressed (in core VARS))
- Pattern: header bytes 40..45 humanize timing, 46..51 humanize velocity, 55 groove 0..7

## Source and tests

- Generator: `src/v2/g2_groove.py` (gen_groove_113.py, tables: grooves/grooves.json, made with midgroove.py)
- Tests: `test_groove_seq.py`: real event builder (Modded-Cycles' seqrig); Swing bit-identical to stock; every table groove at several swing and velocity values; humanize against a reference model; pattern load and new pattern. `test_mods_diff.py`: gestures. `test_control.py`: humanize with TRACK in both control modes.

## Status

Tested on a Model:Samples running the Cycles OS. Not yet tested on a real Model:Cycles.

← [08-load-meter](08-load-meter.md) · [all patches](../../README.md#features) · [10-control-mode](10-control-mode.md) →
