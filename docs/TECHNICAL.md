# Technical reference

For people who want to check the patches, combine them with other mods, or build on them. Addresses are virtual
addresses of the Model:Cycles OS 1.13 MAIN OS; VA = file offset of section 3 + `0x40000400`.

## Platform

- CPU: ColdFire V4e (68k family, big-endian). No instruction may be longer than 6 bytes; the generators check this
  with Capstone (`check_cf`), because Unicorn and Capstone also accept longer 68k encodings.
- The code is hand-encoded in Python (class `A` in `src/gen_solo.py`: words, long words, labels, branches). No assembler.
- Audio runs in an interrupt, in blocks of 90112 ticks of the timer at `0xFC07000C` (135.168 MHz). The stock OS
  already uses about 77 % of that time, so every effect is written to keep instructions per block and uncached
  memory accesses low.

## Patch format

`patches/NN-name.json`:

| Field | Meaning |
|---|---|
| `id`, `order` | name and apply order |
| `requires`, `conflicts` | ids that must be applied too / cannot be combined |
| `writes[]` | `off` (offset in section 3), `va`, `len`, `old_sha256` (SHA-256 of the `len` original bytes), `new` (hex) |
| `writes[].from_original` | places in `new` that must hold original firmware bytes: `at` (offset in `new`), `off` / `va` (source), `len`, `sha256`; `new` has zeros there |
| `hooks` | where the patch hooks into the firmware (an instruction or a vtable entry) |
| `memory` | code memory (sprite masks) and RAM it uses; `ram: true` = RAM |
| `settings`, `pattern` | bytes it stores |
| `symbols`, `params` | entry points and constants of the generated code (for tests and other mods) |

**No Elektron bytes.** The patch files and the generators contain no original firmware bytes. Where a hook moves
original instructions into a patch's own code (or a patch reuses a short firmware calculation, the delay time), the
write lists them in `from_original` and holds zeros there; `tools/apply_patches.py` copies them from the unpatched
input file and checks their SHA-256. In the generators they come from the image too (`A.orig`), and every hook check
is a length plus a SHA-256 (`matches`).

A write may overlap a write of a patch listed in `requires`: every core mod writes its handler address into a slot
of the core's tables, so its `old_sha256` checks the core's empty slot. `patches/manifest.json` lists the patches, the
known base images and the SHA-256 of the full-set result.

## The core (patch 00)

Everything that more than one mod needs lives in the core, so every other mod only needs the core.

**Gesture dispatcher.** The encoder event dispatch (`0x400081b8`) calls `CED`. It calls the handler in each of the 8
slots (`SLOTS`), with `a2` = encoder event (`+4` encoder number, `+8` steps as a signed byte), C calling convention.
The handler returns `d0` = 0 (not mine, ask the next slot), 1 (handled, drop the event) or 2 (handled, pass the event
on with 0 steps, so the firmware shows its own parameter popup). Without a handler every event passes unchanged.

| Slot | Mod |
|---|---|
| 0 | 05 reverb-fx |
| 1 | 06 delay-fx |
| 2 | 07 strum |
| 3 | 08 load-meter |
| 4 | 09 groove |
| 5 | 10 control-mode |
| 6 | 11 trig-select (reserved, not used) |

**Key slots.** `KCALL` calls the handlers in `KSLOTS` on the first press of SETTINGS on the main screen (`d1` = 0)
and on its release without FUNC and without a long hold (`d1` = 1), `a0` = key event. A handler that returns
`d0` ≠ 0 on release keeps the settings menu from opening. Slot 0: control-mode.

**Helpers.** `GEST(d0 = key)` consumes the modifier key (its release opens nothing) and clears the long-hold mark;
`SLOW` / `MODESW` turn encoder steps into one value step per 4 detents (reset after 0.4 s or on a change of
direction) and write a pattern byte; `OVS(d0 kind, d1 value, a0 line 1, a1 line 2)` shows a popup for 1.5 s:

| Kind | Shows |
|---|---|
| 0 | nothing (hide) |
| 1 | number `d1` in the firmware's big value font |
| 2 | text at `d1` |
| 3 | own draw function at `a0` (the load meter) |

The popup is drawn by `OVT` at the end of the view controller's render pass, with the firmware's frame, fill and
text functions and its fonts (names `0x40ea14d4`, value digits `0x40ea14e4`), so it sits on top of every screen.

**SETTINGS as a modifier.** The stock OS starts "save project" after holding SETTINGS for half a second. The core
only marks it and saves on release, unless a gesture used SETTINGS in between.

**Pattern storage.** The 64-byte pattern header (pattern + `0x77B2`) is only partly copied by the stock loader (fields
0–28 and 38). The core copies bytes 40–63 on pattern load (`HL`) and clears 40–59 for a new pattern (`HI`); bytes
60–63 hold the tag `PCv2`. A pattern without the tag (stock OS, v1.0.0) keeps 40–51 (humanize, as in v1.0.0) and
gets 52–59 = 0.

| Bytes | Patch | Values |
|---|---|---|
| 40–45 | 09 groove | humanize timing, tracks 1–6, 0–100 |
| 46–51 | 09 groove | humanize velocity, tracks 1–6, 0–100 |
| 52 | 05 reverb-fx | 0 Reverb, 1 Chorus I, 2 Chorus II, 3 Phaser, 4 RAZR |
| 53 | 06 delay-fx | 0 Delay, 1 Digital, 2 VIBDEL, 3 CHODEL |
| 54 | 06 delay-fx | modulation speed XOR 64 |
| 55 | 09 groove | groove 0–7 |
| 56 | 07 strum | strum, signed −80…80 |
| 57–59 | – | free |
| 60–63 | 00 core | tag `PCv2` |

Invalid values count as 0. The effects read their pattern byte once per audio block, so changing patterns switches
the effect at once.

**Device settings.** One byte in the firmware's settings block (saved at power-off, unused by the stock OS):
`0x404e9b5d` = control mode (`0x5a` absolute, anything else relative). It is defined by the core and written only by
10 control-mode; 09 and 11 read it.

**State after power-on.** The RAM behind the BSS is not cleared at start-up. Every on/off state there is therefore
a 32-bit key word (load meter `LDON`, trig select `TSEL`, popup `OVL2`), never "≠ 0".

## Free memory

**Code** goes into sprite masks the OS never uses (method and list from Modded-Cycles, `tools/sprites.py`). The
reference to each mask is redirected, so the firmware does not draw from it any more.

**RAM:** the area behind the BSS, `0x423380b0..0x4233ffff`, is unused by the stock OS (DMA buffers start at
`0x42340000`). Its uncached mirror is `0x4A33xxxx`. Audio state uses the cached alias `0x4233xxxx` (only the
CPU touches it); state shared with the UI uses the uncached alias. 06 delay-fx also uses the upper half of the
firmware's delay line (`0x4a400000`), which the stock delay does not reach.

| Address | Size | Kind | Patch | Use |
|---|---|---|---|---|
| `0x4014b85c` | 280 | mask | 09 groove |  |
| `0x4014d74c` | 280 | mask | 09 groove |  |
| `0x40152d38` | 192 | mask | 08 load-meter |  |
| `0x401542f8` | 280 | mask | 09 groove |  |
| `0x401548b4` | 280 | mask | 09 groove |  |
| `0x4015b8f8` | 280 | mask | 09 groove |  |
| `0x4015c044` | 720 | mask | 00 core |  |
| `0x4015f38c` | 192 | mask | 09 groove |  |
| `0x4015f50c` | 280 | mask | 05 reverb-fx |  |
| `0x40160864` | 280 | mask | 06 delay-fx |  |
| `0x40160b6c` | 280 | mask | 06 delay-fx |  |
| `0x40160e6c` | 280 | mask | 06 delay-fx |  |
| `0x40167c50` | 280 | mask | 01 mute-solo |  |
| `0x401696a0` | 62 | mask | 02 live-mute |  |
| `0x401699a8` | 280 | mask | 03 hold-mute | press hook + UI tick |
| `0x4016aa28` | 280 | mask | 03 hold-mute | release hook + state |
| `0x4016b6f8` | 376 | mask | 08 load-meter |  |
| `0x4016b9e8` | 376 | mask | 08 load-meter |  |
| `0x4016cae8` | 1024 | mask | 05 reverb-fx |  |
| `0x4016ea78` | 208 | mask | 05 reverb-fx |  |
| `0x4016f7d0` | 124 | mask | 05 reverb-fx |  |
| `0x4016f8c8` | 272 | mask | 09 groove |  |
| `0x40170ad8` | 184 | mask | 04 delay-notes | DSP triplets |
| `0x40171bc8` | 184 | mask | 05 reverb-fx |  |
| `0x40171f30` | 376 | mask | 09 groove |  |
| `0x401728f8` | 184 | mask | 05 reverb-fx |  |
| `0x40179140` | 184 | mask | 05 reverb-fx |  |
| `0x40182b38` | 376 | mask | 10 control-mode |  |
| `0x40182e28` | 376 | mask | 10 control-mode |  |
| `0x40183118` | 376 | mask | 11 trig-select |  |
| `0x40185018` | 376 | mask | 11 trig-select |  |
| `0x40185648` | 184 | mask | 05 reverb-fx |  |
| `0x401857f8` | 184 | mask | 05 reverb-fx |  |
| `0x40185968` | 376 | mask | 11 trig-select |  |
| `0x40185c58` | 376 | mask | 11 trig-select |  |
| `0x40185f48` | 272 | mask | 06 delay-fx |  |
| `0x40189930` | 376 | mask | 12 fill2 |  |
| `0x4018a788` | 1024 | mask | 06 delay-fx |  |
| `0x4018af88` | 272 | mask | 05 reverb-fx |  |
| `0x4018d4a8` | 376 | mask | 07 strum |  |
| `0x4018d918` | 328 | mask | 04 delay-notes | display + table |
| `0x4018dba8` | 376 | mask | 00 core |  |
| `0x4018f4b4` | 376 | mask | 00 core |  |
| `0x4018fc74` | 376 | mask | 06 delay-fx |  |
| `0x4018ff64` | 272 | mask | 05 reverb-fx |  |
| `0x401904b4` | 376 | mask | 06 delay-fx |  |
| `0x40192734` | 376 | mask | 07 strum |  |
| `0x4233c100` | 56 | RAM | 05 reverb-fx | phaser state |
| `0x4233c140` | 20 | RAM | 06 delay-fx | digital delay state |
| `0x4233c180` | 56 | RAM | 05 reverb-fx | RAZR phaser state |
| `0x4233c200` | 4 | RAM | 05 reverb-fx | RAZR reverb parameters |
| `0x4233c210` | 256 | RAM | 05 reverb-fx | RAZR buffer |
| `0x4233c320` | 56 | RAM | 06 delay-fx | VIBDEL/CHODEL state |
| `0x4233c360` | 24 | RAM | 07 strum | voice counters |
| `0x4233c378` | 4 | RAM | 07 strum | root note level |
| `0x4233c3fc` | 1 | RAM | 05 reverb-fx | mode mirror |
| `0x4233c3fd` | 2 | RAM | 06 delay-fx | type + speed mirror |
| `0x4a33a000` | 8240 | RAM | 05 reverb-fx | chorus state + ring |
| `0x4a33c380` | 40 | RAM | 00 core | popup + key state (VARS) |
| `0x4a33c3a4` | 4 | RAM | 09 groove | MACHINE pressed (in core VARS) |
| `0x4a33c3a8` | 2 | RAM | 10 control-mode | SETTINGS used since press, byte for COPY |
| `0x4a33c3ac` | 4 | RAM | 11 trig-select | selection mode on ('TSEL') |
| `0x4a33c3c0` | 12 | RAM | 00 core | detent counter (SLOW) |
| `0x4a33c3d0` | 36 | RAM | 08 load-meter | meter state + text |

## Hooks

| Hook | Firmware function | Patch |
|---|---|---|
| `0x400081b8` | encoder event dispatch (gesture dispatcher) | 00 core |
| `0x40076c88` | end of the view controller render pass (popups) | 00 core |
| `0x4001c54c` | main screen key handler, SETTINGS press | 00 core |
| `0x4001c564` | main screen key handler, SETTINGS long hold | 00 core |
| `0x4001c5bc` | main screen key handler, SETTINGS release | 00 core |
| `0x4005b4b0` | pattern load: header copy | 00 core |
| `0x4006155e` | new pattern: header init | 00 core |
| `0x40023550` | mute view: call of the mute toggle | 01 mute-solo |
| `0x4005894a` | live note function (pads and MIDI IN), first instruction | 02 live-mute |
| `0x400081f2` | UI tick (30 Hz) | 03 hold-mute |
| `0x4001d05e` | pad note-on on the main screen | 03 hold-mute |
| `0x4001d0fc` | pad note-off on the main screen | 03 hold-mute |
| `0x4004dfda` | Delay Time display text | 04 delay-notes |
| `0x400581b8` | delay-time calculation (DSP) | 04 delay-notes |
| `0x40056a2c` | mixer: call of the reverb | 05 reverb-fx |
| `0x4005699c` | mixer: call of the delay | 06 delay-fx |
| `0x40056a3c` | mixer: write DMA of the delay line | 06 delay-fx |
| `0x400ab240` | CHORD voice update, end | 07 strum |
| `0x400ab2d2` | CHORD root note level | 07 strum |
| `0x40059382` | audio interrupt: call of the audio function | 08 load-meter |
| `0x40054af8` | sequencer event builder: swing addition | 09 groove |
| `0x4001ca1e` | main screen key handler, MACHINE | 09 groove |
| `0x40100588` | ParameterPageView vtable +0x5c: CONTROL ALL (vtable entry) | 10 control-mode |
| `0x4001ab7a` | main screen LEVEL handler: volume branch | 10 control-mode |
| `0x4001aaec` | main screen LEVEL handler: pan branch | 10 control-mode |
| `0x40100af0` | PatternGridView vtable +0x08: consumeKeyEvent (vtable entry) | 11 trig-select |
| `0x401005a0` | ParameterPageView vtable +0x74: change p-locks of held steps (vtable entry) | 11 trig-select |
| `0x4001c4a6` | main screen key handler, PAGE: FUNC check | 11 trig-select |
| `0x40021f56` | grid LED loop: state of one step | 11 trig-select |
| `0x40029d9a` | NoteVelocityView: call of the held-trig settings change | 11 trig-select |
| `0x40091416` | sequencer trig-condition check: range check | 12 fill2 |
| `0x40015ff6` | trig-condition getter: read the byte | 12 fill2 |
| `0x4001605a` | trig-condition setter: store the byte | 12 fill2 |
| `0x4004a4f6` | trig-condition text: name table | 12 fill2 |
| `0x400500a8` | trig-condition display: base-name table | 12 fill2 |

No two patches hook the same place, so every combination can be applied (`tests/test_modular.py` applies all of
them). Optional couplings are detected at run time, never required: 06 uses the exact triplets of 04 if its DSP
hook is there; 09 and 11 read the control-mode byte of the core.

## Combining with other mods

Every patch lists its hooks and memory, so you can check for collisions (the idea of a shared mod standard).
Known conflicts with Modded-Cycles mods: `model-tg` / `model-tg-st` (01) and `level-pan-values` (03), from v1.0.0.
These Modded-Cycles mods use the same free memory: `trig-hold` (the sprite mask of 00), `chord-keys` (pattern header
40–63 and the masks of 10 and 11) and `sample-preview` (the masks of 11). Other combinations were not checked.
`tools/apply_patches.py` stops on any overlap that is not declared in `requires`.

## Tests

`tests/run_all.py` runs the original firmware code in Unicorn: the real key chain and key handlers, the real render
path with the real fonts, the real sequencer event builder (Modded-Cycles' `seqrig`), the real CONTROL ALL and
held-step functions, and the effect code against v1.0.0. Each test prints its checks (`ok` / `FAIL`, texts in
German); `run_all.py` sums them up. See [tests/README.md](../tests/README.md).
