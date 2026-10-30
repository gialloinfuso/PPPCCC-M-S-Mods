# 15 · Direct jump: change the pattern at once and keep the position

Patch id `direct-jump` · file [`patches/15-direct-jump.json`](../../patches/15-direct-jump.json) · 15 writes

On the stock OS a new pattern starts when the current one has reached its end. With a direct jump the new pattern
takes over right away, within the next steps, and plays on from the position the old pattern was at. Good for live
sets: jump between variations without waiting and without losing the groove.

## Controls

| Do this | Result |
|---|---|
| press **PATTERN**, then **FUNC + a trig key** | Direct jump to that pattern. The selection stays open, so you can jump again right away. |
| press **PATTERN**, then a trig key (without FUNC) | Normal pattern change at the end of the pattern, as on the stock OS. |
| hold **PATTERN** + **FUNC + a trig key** | Direct jump; the selection stays open after you let go of PATTERN. |
| FUNC + a trig key with the sequencer stopped | The same as a trig key alone. |

## Good to know

- The new pattern starts at the position the old one was at (modulo the new pattern's length), so a jump from step 9
  of a 16-step pattern continues at step 10 of the new one.
- In per-track mode every track keeps its own position, modulo its length in the new pattern.
- The jump also sends the MIDI program change, as a normal pattern change does.
- Without FUNC, everything is exactly as on the stock OS. Other uses of FUNC (mutes, latching mute, solo) are not
  affected.

## What is stored

Nothing.

## Dependencies

- Requires: nothing.

## How it works

**The request.** In the pattern selection, the firmware already checks FUNC when a trig key is pressed but does
nothing with it. The patch hooks that place: with FUNC and the sequencer running it calls the firmware's own pattern
choice (the same as releasing the trig key) and sets a request flag.

**The change.** On tick 0 of every step the sequencer checks whether a pattern change is due. The patch hooks that
check: with a request, the change happens now, with the start position set to the current master step (modulo the new
length). The firmware already computes every track's position from this start position; on the stock OS it is always
0. Right after the change, a second hook sets each track's start step to its own next step, so per-track mode keeps
running seamlessly.

**Keeping the selection open.** Four small hooks in the pattern selection, its window and its observer keep FUNC from
closing the selection, and keep it open after a direct jump. A normal trig key press clears the flag, so everything
else behaves as on the stock OS.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x40020c84`, `0x4005563e`, `0x40055898`, `0x40020aa6`, `0x40024b12`, `0x40024bd0`, `0x40020df0`
- Code and data (unused sprite masks): `0x4015943c` (192 B), `0x40168a84` (192 B), `0x4014af84` (108 B), `0x4014b05c` (108 B)
- RAM (in a sprite mask): `0x4015943c` (16 B, jump request, saved track steps, keep-open flag)

## Source and tests

- Generator: `src/v2/g2_directjump.py`
- Tests: `test_directjump.py`: the real sequencer interrupt in the emulator, with patterns in RAM as in the firmware: without a request bit-identical to stock after every tick (also normal changes and per-track mode); direct jumps at many positions (change within two steps, tracks continue without a gap, MIDI program change); per-track mode with different lengths and speeds; the key path in the pattern selection, its window and its observer (FUNC, keep-open, normal trig key); `--alone` with only this patch.

## Status

Tested on a Model:Samples running the Cycles OS. New in v2.2.0. Not yet tested on a real Model:Cycles.

← [14-lfo-amount](14-lfo-amount.md) · [all patches](../../README.md#features)
