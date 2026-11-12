# 11 · Fill 2 & Trig Conditions

Patch id `fill2` · file [`patches/11-fill2.json`](../../patches/11-fill2.json) · 22 writes

A second fill and new trig conditions. Hold PAGE for the fill as usual, then also hold FUNC: as long as both
are held, Fill 2 replaces Fill 1. The conditions **FIL2** / **!FIL2** belong to it, and **PTC** / **!PTC** and
**LST** / **!LST** react to pattern changes. The list of conditions is reordered so related conditions sit together.

## Controls

| Do this | Result |
|---|---|
| hold **PAGE** | Fill (Fill 1), as on the stock OS. |
| hold **PAGE**, then also hold **FUNC** | Fill 2 instead of Fill 1, as long as both are held. Let go of FUNC: back to Fill 1. |
| fill latched with **TRACK + PAGE**, then hold **FUNC** | Fill 2 while FUNC is held. |
| choose a trig condition | The list: --- · 1:2 … 8:8 · 1:12 … 12:12 · 1:16 … 16:16 · FILL !FILL FIL2 !FIL2 PTC !PTC PRE !PRE NEI !NEI 1st !1st LST !LST · 1% … 99%. |

### The new conditions

| Condition | Plays when |
|---|---|
| FIL2 / !FIL2 | Fill 2 is on / is not on (during Fill 2, FILL trigs are silent and !FILL trigs play) |
| PTC / !PTC | a newly chosen pattern is waiting to take over / is not (chains do not count) |
| LST / !LST | this is / is not the last pass before another pattern (also in chains) |
| x:12, x:16 | like A:B of the firmware, with 12 and 16 passes |

## Good to know

- All stock conditions keep their stored values, so patterns from the stock OS or older versions load unchanged. The new conditions are saved as new values (64–97); on a firmware without this patch those trigs always play.
- Copy and paste of trigs (also with patch 10) keeps the new conditions.

## What is stored

The condition of each trig, saved with the pattern like every trig condition.

## Dependencies

- Requires: nothing.

## How it works

**Sequencer.** The firmware checks each trig's condition in one function. The patch hooks its range check: Fill 2
is active when the fill flag is set (PAGE, or TRACK + PAGE latched) and FUNC is held, read from the firmware's key
bitmap. FIL2 and !FIL2 are decided there; during Fill 2, FILL and !FILL are answered as if no fill were active. All
other conditions go to the firmware unchanged.

**The list.** FIL2 / !FIL2 are stored as values 64 and 65, behind the stock values 0–63. So that the conditions appear in the
new order, the getter and setter of the condition byte translate between the stored value and the position in
the list with two tables; the limits 63 become
97. The two displays of the condition still take their names from the firmware's own tables: the patch only maps the
position to the stored value, and FIL2 / !FIL2 come from two pointers of its own. The negation mark and the
percentage display follow the new positions.

**New conditions (v2.3).** PTC reads the firmware's "next pattern" state, LST computes whether the next pass belongs to
another pattern (as the firmware's chain logic does), x:12 and x:16 use the firmware's per-track pass counter. The
order of the list comes from two small tables (position ↔ stored value); the names still come from the firmware's
own tables.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x40091416`, `0x40015ff6`, `0x4001605a`, `0x4004a4f6`, `0x400500a8`, `0x400500da`, `0x4005010c`
- Code and data (unused sprite masks): `0x40189930` (376 B), `0x4018a220` (376 B), `0x4018cd48` (376 B), `0x40184df8` (272 B), `0x40185308` (272 B)

## Source and tests

- Generator: `src/v2/g2_fill2.py`
- Tests: `test_fill2.py`: the real condition check against stock for all 98 values with and without fill and FUNC; the real getter and setter (round trip, limits); the real condition text (sprintf) for every position; the display mapping, negation mark and percent range; `--alone` with only this patch.

## Status

Tested on a Model:Samples running the Cycles OS. Updated in v2.3.0 (PTC, LST, x:12, x:16, new order). Not yet tested on a real Model:Cycles.

← [10-trig-select](10-trig-select.md) · [all patches](../../README.md#patches) · [12-track-filter](12-track-filter.md) →
