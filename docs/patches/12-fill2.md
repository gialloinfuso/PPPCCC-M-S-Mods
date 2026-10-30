# 12 · Fill 2: a second fill with its own trig conditions

Patch id `fill2` · file [`patches/12-fill2.json`](../../patches/12-fill2.json) · 14 writes

A second fill. Hold PAGE for the fill as usual, then also hold FUNC: as long as both are held, Fill 2 replaces
Fill 1. Two new trig conditions belong to it, **FIL2** and **!FIL2**. In the list of conditions they come right after
FILL and !FILL.

## Controls

| Do this | Result |
|---|---|
| hold **PAGE** | Fill (Fill 1), as on the stock OS. |
| hold **PAGE**, then also hold **FUNC** | Fill 2 instead of Fill 1, as long as both are held. Let go of FUNC: back to Fill 1. |
| fill latched with **TRACK + PAGE**, then hold **FUNC** | Fill 2 while FUNC is held. |
| choose a trig condition (where FILL and !FILL are) | The list is FILL, !FILL, **FIL2**, **!FIL2**, PRE, !PRE, … 8:8. |

### Which trigs play

| Condition | no fill | Fill 1 (PAGE) | Fill 2 (PAGE + FUNC) |
|---|---|---|---|
| FILL | – | plays | – |
| !FILL | plays | – | plays |
| FIL2 | – | – | plays |
| !FIL2 | plays | plays | – |

## Good to know

- During Fill 2, Fill 1 counts as off: FILL trigs are silent and !FILL trigs play.
- All stock conditions keep their values, so patterns from the stock OS or older versions load unchanged. FIL2 and !FIL2 are saved as two new condition values; on a firmware without this patch those trigs always play.
- Copy and paste of trigs (also with trig select, patch 11) keeps FIL2 / !FIL2.

## What is stored

The condition of each trig, saved with the pattern like every trig condition.

## Dependencies

- Requires: nothing.

## How it works

**Sequencer.** The firmware checks each trig's condition in one function. The patch hooks its range check: Fill 2
is active when the fill flag is set (PAGE, or TRACK + PAGE latched) and FUNC is held, read from the firmware's key
bitmap. FIL2 and !FIL2 are decided there; during Fill 2, FILL and !FILL are answered as if no fill were active. All
other conditions go to the firmware unchanged.

**The list.** The new conditions are stored as values 64 and 65, behind the stock values 0–63. So that they appear right
after FILL / !FILL, the getter and setter of the condition byte translate between the stored value and the position in
the list (positions 2 and 3 are FIL2 / !FIL2, the stock values from PRE on move two places down); the limits 63 become
65. The two displays of the condition still take their names from the firmware's own tables: the patch only maps the
position to the stored value, and FIL2 / !FIL2 come from two pointers of its own. The negation mark and the
percentage display follow the new positions.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x40091416`, `0x40015ff6`, `0x4001605a`, `0x4004a4f6`, `0x400500a8`
- Code and data (unused sprite masks): `0x40189930` (376 B)

## Source and tests

- Generator: `src/v2/g2_fill2.py`
- Tests: `test_fill2.py`: the real condition check against stock for all 67 values with and without fill and FUNC; the real getter and setter (round trip, limits); the real condition text (sprintf) for every position; the display mapping, negation mark and percent range; `--alone` with only this patch.

## Status

Tested on a Model:Samples running the Cycles OS. New in v2.1.0. Not yet tested on a real Model:Cycles.

← [11-trig-select](11-trig-select.md) · [all patches](../../README.md#features) · [13-track-filter](13-track-filter.md) →
