# 18 · Parameter undo: 3x longer

Patch id `param-undo` · file [`patches/18-param-undo.json`](../../patches/18-param-undo.json) · 3 writes

After you turn a knob, the firmware shows the old and the new value; while that popup is shown, **BACK** undoes the
change. This patch keeps the popup three times as long, so there is time to undo.

## Controls

| Do this | Result |
|---|---|
| turn a knob | The popup "old → new" stays for 180 instead of 60 ticks. |
| **BACK** while it is shown | Undoes the change, as on the stock OS. |

## Good to know

- After BACK the restored value shows briefly, as before.
- Turning another knob replaces the popup and the undo, as before.

## What is stored

Nothing.

## Dependencies

- Requires: nothing.

## How it works

When a knob is turned, the parameter page sets a countdown of 60 ticks; at 0 it closes the popup and drops the undo.
180 does not fit the original instruction, so the patch replaces it with a call that sets 180.

### Hooks and memory

Addresses are virtual addresses of the OS 1.13 MAIN OS (file offset + 0x40000400).

- Hooks (original instruction or vtable entry replaced): `0x4001f760`
- Code and data (unused sprite masks): `0x40178888` (124 B)

## Source and tests

- Generator: `src/v2/g2_paramundo.py`
- Tests: `test_paramundo.py`: the real parameter page function with the countdown.

## Status

Tested on a Model:Samples running the Cycles OS. New in v2.3.0. Not yet tested on a real Model:Cycles.

← [17-mono](17-mono.md) · [all patches](../../README.md#patches) · [19-pad-mode](19-pad-mode.md) →
