# 14 · Direct Pattern Jump

Patch id `direct-jump` · file [`patches/14-direct-jump.json`](../../patches/14-direct-jump.json) · 21 writes

On the stock OS a new pattern starts when the current one has reached its end. With a direct jump the new pattern
takes over right away, within the next steps, and plays on from the position the old pattern was at. Good for live
sets: jump between variations without waiting and without losing the groove. The pattern selection also latches.

## Controls

| Do this | Result |
|---|---|
| press **PATTERN** | The pattern selection opens and stays open (no timeout). Press PATTERN again to close it. |
| in the selection: **FUNC + a trig key** | Direct jump to that pattern. The selection stays open, so you can jump again right away. |
| in the selection: a trig key (without FUNC) | Normal pattern change at the end of the pattern, as on the stock OS. The selection stays open. |
| in the selection: trig + **REC / STOP / PLAY** | Copy / paste / clear a pattern, as on the stock OS; the selection stays open and the message shows on top of it. |
| FUNC + a trig key with the sequencer stopped | The same as a trig key alone. |

## Good to know

- The new pattern starts at the position the old one was at (modulo the new pattern's length), so a jump from step 9 of a 16-step pattern continues at step 10 of the new one.
- In per-track mode every track keeps its own position, modulo its length in the new pattern.
- The jump also sends the MIDI program change, as a normal pattern change does.
- Other uses of FUNC (mutes, latching mute, solo) are not affected.

## What is stored

Nothing.

## Dependencies

- Requires: nothing.

## How it works

**The request.** In the pattern selection, the firmware already checks FUNC when a trig key is pressed but does
nothing with it. The patch hooks that place: with FUNC and the sequencer running it calls the firmware's own pattern
choice and sets a request flag.

**The change.** On tick 0 of every step the sequencer checks whether a pattern change is due. The patch hooks that
check: with a request, the change happens now, with the start position set to the current master step (modulo the new
length). Right after the change, a second hook sets each track's start step to its own next step, so per-track mode keeps
running seamlessly.

**Latched selection.** Small hooks in the pattern selection, its window and its observer keep the selection open until
PATTERN is pressed again. The copy / paste / clear messages are shown with the window's own overlay tag cleared, so
they no longer close it.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x40020c84`, `0x4005563e`, `0x40055898`, `0x40020aa6`, `0x40024b12`, `0x40024bd0`, `0x40020df0`, `0x401011b0`, `0x40020f14`, `0x40020fb8`, `0x4002113e`
- Code and data (unused sprite masks): `0x4015943c` (192 B), `0x40168a84` (192 B), `0x4014af84` (108 B), `0x4014b05c` (108 B), `0x40168c4c` (104 B)
- RAM: `0x4015943c` (16 B, jump request, fix flag, saved track steps, keep-open flag)

## Source and tests

- Generator: `src/v2/g2_directjump.py`
- Tests: `test_directjump.py`: the real sequencer interrupt: without a request bit-identical to stock; direct jumps at many positions, per-track mode, MIDI program change; the keys of the pattern selection, its window and observer; copy / paste / clear with the real overlay code; `--alone`.

## Status

Tested on a Model:Samples running the Cycles OS. Updated in v2.3.0 (latched selection). Not yet tested on a real Model:Cycles.

← [13-lfo-amount](13-lfo-amount.md) · [all patches](../../README.md#patches) · [15-sampler](15-sampler.md) →
