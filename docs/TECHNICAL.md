# Technical reference

For people who want to check the patches, combine them with other mods, or build on them. Addresses are virtual
addresses of the Model:Cycles OS 1.13 MAIN OS; VA = file offset of section 3 + `0x40000400`.

## Platform

- CPU: ColdFire V4e (68k family, big-endian). No instruction may be longer than 6 bytes; the generators check this
  with Capstone (`check_cf`), because Unicorn and Capstone also accept longer 68k encodings.
- The code is ColdFire assembler text in the Python generators, assembled by `src/v2/cfasm.py` (own code); EMAC
  instructions through `src/v2/cfemac.py`.
- Audio runs in an interrupt, in blocks of 90112 ticks of the timer at `0xFC07000C` (135.168 MHz). The stock OS
  already uses about 77 % of that time, so every effect is written to keep instructions per block and uncached
  memory accesses low.

## Patch format

`patches/NN-name.json`:

| Field | Meaning |
|---|---|
| `id`, `order` | name and apply order |
| `requires`, `conflicts` | ids that must be applied too / cannot be combined |
| `writes[]` | `off` (offset in section 3), `va`, `len`, `old_sha256` (SHA-256 of the `len` original bytes), `new` (hex); `len` 0 at the end of the image = append (the core's payload area) |
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

Everything that more than one patch needs lives in the core, so most patches only need the core.

**Payload area.** The core appends 64 KB to the MAIN OS (file offset `0x1a9d40`, so the image grows to 1809728 bytes)
and copies it to `0x43000000` at start (hook `0x400004b2`). Larger patches keep code and tables there in their own
slots: 04 (Hall / Room / Plate), 06, 09, 15–17, 19. Their RAM state lives behind it (`0x43180000`…).

**Descriptor table.** The firmware's parameter descriptor table is copied into the payload and extended to 96 entries;
every reference to it is redirected (most of the core's hooks). Extra parameters get their own descriptors there: the
attack (core), strum (06), the filter (12), LFO Amount (13), Grit's start / length / model (15), Monom's parameters (17).

**Gesture dispatcher.** The encoder event dispatch (`0x400081b8`) calls `CED`. It calls the handler in each of the 8
slots (`SLOTS`), with `a2` = encoder event (`+4` encoder number, `+8` steps as a signed byte), C calling convention.
The handler returns `d0` = 0 (not mine, ask the next slot), 1 (handled, drop the event) or 2 (handled, pass the event
on with 0 steps, so the firmware shows its own parameter popup). Without a handler every event passes unchanged.

| Slot | Mod |
|---|---|
| 0 | 04 reverb-fx |
| 1 | 05 delay-fx |
| 2 | 06 strum |
| 3 | 07 load-meter |
| 4 | 08 groove |
| 5 | 09 control-mode |
| 6 | 10 trig-select (reserved, not used) |
| 7 | 12 track-filter |
| 8 | 15 sampler |

**Key slots.** `KCALL` calls the handlers in `KSLOTS` on the first press of SETTINGS on the main screen (`d1` = 0)
and on its release without FUNC and without a long hold (`d1` = 1), `a0` = key event. A handler that returns
`d0` ≠ 0 on release keeps the settings menu from opening. Slot 0: control-mode.

**Sound slots (v2.2.0).** The stock OS saves and loads parameters k 0–22 of a sound. The core hooks the start of the
sound load function (`0x4005aecc`) and of both save functions (`0x4005afa0`, record version 2; `0x4005b054`, version 1),
lets the firmware do its part and then calls the handlers in `SSLOTS` with `a0` = record, `a1` = sound, `d1` = 0 load /
1 save. A handler may change `d0`/`d1`/`a0`/`a1`. The core itself stores the LFO and velocity destination when it is
one of k 23–32 (record bytes 82 / 83) and extends the firmware's table parameter k -> p-lock index to k 0–32 (`PTAB`,
and back with the hook `0x4005aa34`), so extra parameters can be p-locked. Sounds without these bytes (stock OS) load
the extra parameters at their defaults.

| Sound slot | Patch | Sound record bytes |
|---|---|---|
| 0 | 12 track-filter | 64 / 65 (envelope, decay), 88–91 (cutoff, resonance) |
| 1 | 13 lfo-amount | 84 (LFO Amount) |
| 2 | 15 sampler | 76–79 (sample file id) |
| 3 | 00 core | attack |
| 4 | 17 mono | 80 / 81 (glide, noise) |
| – | 00 core | 82 / 83 (LFO / velocity destination k 23–32) |

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
| 40–45 | 08 groove | humanize timing, tracks 1–6, 0–100 |
| 46–51 | 08 groove | humanize velocity, tracks 1–6, 0–100 |
| 52 | 04 reverb-fx | 0 Reverb, 1 Chorus I, 2 Chorus II, 3 Phaser, 4 RAZR, 5 Hall, 6 Room, 7 Plate |
| 53 | 05 delay-fx | 0 Delay, 1 Digital, 2 VIBDEL, 3 CHODEL |
| 54 | 05 delay-fx | modulation speed XOR 64 |
| 55 | 08 groove | groove 0–10 |
| 56 | – | free (the per-pattern strum of v2.2; strum is per sound now) |
| 57 | 19 pad-mode | pad tracks, bits 0–5 |
| 58–59 | – | free |
| 60–63 | 00 core | tag `PCv2` |

Invalid values count as 0. The effects read their pattern byte once per audio block, so changing patterns switches
the effect at once.

**Device settings.** One byte in the firmware's settings block (saved at power-off, unused by the stock OS):
`0x404e9b5d` = control mode (`0x5a` absolute, anything else relative). It is defined by the core and written only by
09 control-mode; 08 and 10 read it.

**State after power-on.** The RAM behind the BSS is not cleared at start-up. Every on/off state there is therefore
a 32-bit key word (load meter `LDON`, trig select `TSEL`, popup `OVL2`, filter mode `FLT1`, direct jump `DJMP`),
never "≠ 0".

**Extra parameters.** Patches 12 and 13 turn unused "Error" entries of the firmware's parameter table into real
parameters: descriptors 1–4 = Filter Cutoff / Reso / Env / Decay (k 28–31), descriptor 5 = LFO Amount (k 32);
descriptor 6 = attack (k 23, core).

## Free memory

**Code** goes into sprite masks the OS never uses (method and list from Modded-Cycles, `tools/sprites.py`). The
reference to each mask is redirected, so the firmware does not draw from it any more.

**RAM:** the area behind the BSS, `0x423380b0..0x4233ffff`, is unused by the stock OS (DMA buffers start at
`0x42340000`). Its uncached mirror is `0x4A33xxxx`. Audio state uses the cached alias `0x4233xxxx` (only the
CPU touches it); state shared with the UI uses the uncached alias. 05 delay-fx also uses the upper half of the
firmware's delay line (`0x4a400000`), which the stock delay does not reach.

| Address | Size | Kind | Patch | Use |
|---|---|---|---|---|
| `0x40147f22` | 174 | mask | 00 core | code (unused 0xff area) |
| `0x40148328` | 114 | mask | 01 mute-solo | code (unused 0xff area) |
| `0x401485f0` | 16 | RAM | 00 core | name id, offset, tick, pause |
| `0x40148662` | 288 | mask | 01 mute-solo | code (unused 0xff area) |
| `0x401487e0` | 14 | RAM | 01 mute-solo | FUNC press time, FUNC used, latched flag |
| `0x4014a890` | 108 | mask | 13 lfo-amount |  |
| `0x4014aa34` | 108 | mask | 13 lfo-amount |  |
| `0x4014aa5c` | 24 | RAM | 13 lfo-amount | depth backup + amount per track |
| `0x4014ab5c` | 280 | mask | 12 track-filter |  |
| `0x4014af84` | 108 | mask | 14 direct-jump |  |
| `0x4014b05c` | 108 | mask | 14 direct-jump |  |
| `0x4014b5b4` | 108 | mask | 12 track-filter |  |
| `0x4014b784` | 108 | mask | 00 core |  |
| `0x4014b85c` | 280 | mask | 08 groove |  |
| `0x4014d74c` | 280 | mask | 08 groove |  |
| `0x4014e608` | 108 | mask | 00 core |  |
| `0x40152d38` | 192 | mask | 07 load-meter |  |
| `0x40152f88` | 108 | mask | 00 core |  |
| `0x401542f8` | 280 | mask | 08 groove |  |
| `0x401548b4` | 280 | mask | 08 groove |  |
| `0x401592bc` | 192 | mask | 13 lfo-amount |  |
| `0x4015943c` | 16 | RAM | 14 direct-jump | jump request, fix flag, saved track steps, keep-open flag |
| `0x4015943c` | 192 | mask | 14 direct-jump |  |
| `0x40159a04` | 108 | mask | 00 core |  |
| `0x40159adc` | 108 | mask | 00 core |  |
| `0x4015b820` | 108 | mask | 00 core |  |
| `0x4015b8f8` | 280 | mask | 08 groove |  |
| `0x4015bf24` | 108 | mask | 00 core |  |
| `0x4015c044` | 720 | mask | 00 core |  |
| `0x4015c9a4` | 108 | mask | 00 core |  |
| `0x4015f38c` | 192 | mask | 08 groove |  |
| `0x4015f50c` | 280 | mask | 04 reverb-fx |  |
| `0x4015fb6c` | 108 | mask | 00 core |  |
| `0x401601fc` | 280 | mask | 12 track-filter |  |
| `0x40160864` | 280 | mask | 05 delay-fx |  |
| `0x40160a94` | 108 | mask | 15 sampler |  |
| `0x40160b6c` | 280 | mask | 05 delay-fx |  |
| `0x40160d9c` | 104 | mask | 00 core |  |
| `0x40160e6c` | 280 | mask | 05 delay-fx |  |
| `0x401617a8` | 108 | mask | 15 sampler |  |
| `0x40161880` | 108 | mask | 15 sampler |  |
| `0x401625bc` | 280 | mask | 12 track-filter |  |
| `0x401629dc` | 108 | mask | 15 sampler |  |
| `0x40162ab4` | 80 | RAM | 00 core | attack: render params pointer, lookup slot, ramp state (in mask) |
| `0x40162ab4` | 104 | mask | 00 core |  |
| `0x401630e4` | 104 | mask | 15 sampler |  |
| `0x401638c0` | 104 | mask | 15 sampler |  |
| `0x40163990` | 104 | mask | 06 strum |  |
| `0x40163a60` | 108 | mask | 00 core |  |
| `0x40163b38` | 104 | mask | 00 core |  |
| `0x40163fb8` | 280 | mask | 12 track-filter |  |
| `0x40165fec` | 192 | mask | 12 track-filter |  |
| `0x4016616c` | 280 | mask | 12 track-filter |  |
| `0x40166690` | 104 | mask | 06 strum |  |
| `0x40166760` | 280 | mask | 12 track-filter |  |
| `0x40167900` | 108 | mask | 00 core |  |
| `0x401679d8` | 104 | mask | 06 strum |  |
| `0x40167aa8` | 108 | mask | 00 core |  |
| `0x40167b80` | 104 | mask | 06 strum |  |
| `0x40168440` | 108 | mask | 00 core |  |
| `0x401688b4` | 108 | mask | 00 core |  |
| `0x40168a84` | 192 | mask | 14 direct-jump |  |
| `0x40168c4c` | 104 | mask | 14 direct-jump |  |
| `0x40168da4` | 192 | mask | 15 sampler |  |
| `0x40168fb4` | 104 | mask | 06 strum |  |
| `0x401698d0` | 108 | mask | 15 sampler |  |
| `0x401699a8` | 280 | mask | 02 hold-mute | press hook + UI tick |
| `0x4016aa28` | 280 | mask | 02 hold-mute | release hook + state |
| `0x4016b6f8` | 376 | mask | 07 load-meter |  |
| `0x4016b9e8` | 376 | mask | 07 load-meter |  |
| `0x4016bcd8` | 192 | mask | 15 sampler |  |
| `0x4016cae8` | 1024 | mask | 04 reverb-fx |  |
| `0x4016dab8` | 192 | mask | 15 sampler |  |
| `0x4016ea78` | 208 | mask | 04 reverb-fx |  |
| `0x4016f7d0` | 124 | mask | 04 reverb-fx |  |
| `0x4016f8c8` | 272 | mask | 08 groove |  |
| `0x4016fae8` | 192 | mask | 15 sampler |  |
| `0x4016fd60` | 124 | mask | 15 sampler |  |
| `0x40170ad8` | 184 | mask | 03 delay-notes | DSP triplets |
| `0x40170c48` | 192 | mask | 15 sampler |  |
| `0x40171a48` | 192 | mask | 15 sampler |  |
| `0x40171bc8` | 184 | mask | 04 reverb-fx |  |
| `0x40171f30` | 376 | mask | 08 groove |  |
| `0x40172510` | 124 | mask | 15 sampler |  |
| `0x40172608` | 376 | mask | 12 track-filter |  |
| `0x401728f8` | 184 | mask | 04 reverb-fx |  |
| `0x40172a68` | 192 | mask | 12 track-filter |  |
| `0x40172be8` | 192 | mask | 15 sampler |  |
| `0x401736c8` | 192 | mask | 15 sampler |  |
| `0x40173848` | 252 | RAM | 12 track-filter | filter state + mode |
| `0x40173848` | 272 | mask | 12 track-filter |  |
| `0x40177f28` | 192 | mask | 15 sampler |  |
| `0x401780a8` | 272 | mask | 12 track-filter |  |
| `0x401784e8` | 272 | mask | 12 track-filter |  |
| `0x40178708` | 192 | mask | 15 sampler |  |
| `0x40178888` | 124 | mask | 18 param-undo |  |
| `0x40178fc0` | 192 | mask | 15 sampler |  |
| `0x40179140` | 184 | mask | 04 reverb-fx |  |
| `0x401792b0` | 192 | mask | 15 sampler |  |
| `0x40179430` | 192 | mask | 15 sampler |  |
| `0x401795b0` | 192 | mask | 15 sampler |  |
| `0x40179730` | 376 | mask | 12 track-filter |  |
| `0x40179b18` | 192 | mask | 15 sampler |  |
| `0x40179c98` | 104 | mask | 06 strum |  |
| `0x4017a4d4` | 124 | mask | 06 strum |  |
| `0x4017c97c` | 192 | mask | 15 sampler |  |
| `0x401829b8` | 192 | mask | 15 sampler |  |
| `0x40182b38` | 376 | mask | 09 control-mode |  |
| `0x40182e28` | 376 | mask | 09 control-mode |  |
| `0x40183118` | 376 | mask | 10 trig-select |  |
| `0x40183408` | 192 | mask | 15 sampler |  |
| `0x401835b8` | 272 | mask | 00 core |  |
| `0x401837d8` | 124 | mask | 15 sampler |  |
| `0x40184808` | 192 | mask | 00 core |  |
| `0x40184988` | 184 | mask | 15 sampler |  |
| `0x40184af8` | 192 | mask | 15 sampler |  |
| `0x40184c78` | 192 | mask | 15 sampler |  |
| `0x40184df8` | 272 | mask | 11 fill2 |  |
| `0x40185018` | 376 | mask | 10 trig-select |  |
| `0x40185308` | 272 | mask | 11 fill2 |  |
| `0x40185648` | 184 | mask | 04 reverb-fx |  |
| `0x401857f8` | 184 | mask | 04 reverb-fx |  |
| `0x40185968` | 376 | mask | 10 trig-select |  |
| `0x40185c58` | 376 | mask | 10 trig-select |  |
| `0x40185f48` | 272 | mask | 05 delay-fx |  |
| `0x40186168` | 104 | mask | 08 groove |  |
| `0x40186238` | 224 | RAM | 15 sampler | machine rows (7) |
| `0x40186238` | 272 | mask | 15 sampler |  |
| `0x401871a0` | 124 | mask | 15 sampler |  |
| `0x40187528` | 192 | mask | 15 sampler |  |
| `0x401876a8` | 192 | mask | 15 sampler |  |
| `0x40188f98` | 192 | mask | 15 sampler |  |
| `0x40189618` | 272 | mask | 06 strum |  |
| `0x40189838` | 124 | mask | 15 sampler |  |
| `0x40189930` | 376 | mask | 11 fill2 |  |
| `0x4018a220` | 376 | mask | 11 fill2 |  |
| `0x4018a510` | 124 | mask | 15 sampler |  |
| `0x4018a608` | 192 | mask | 15 sampler |  |
| `0x4018a788` | 1024 | mask | 05 delay-fx |  |
| `0x4018af88` | 272 | mask | 04 reverb-fx |  |
| `0x4018b1a8` | 272 | mask | 15 sampler |  |
| `0x4018b9c8` | 192 | mask | 15 sampler |  |
| `0x4018bb48` | 192 | mask | 15 sampler |  |
| `0x4018bcc8` | 124 | mask | 15 sampler |  |
| `0x4018cbc8` | 192 | mask | 15 sampler |  |
| `0x4018cd48` | 376 | mask | 11 fill2 |  |
| `0x4018d038` | 192 | mask | 15 sampler |  |
| `0x4018d1b8` | 376 | mask | 15 sampler |  |
| `0x4018d4a8` | 376 | mask | 06 strum |  |
| `0x4018d798` | 192 | mask | 15 sampler |  |
| `0x4018d918` | 328 | mask | 03 delay-notes | display + table |
| `0x4018dba8` | 376 | mask | 00 core |  |
| `0x4018f4b4` | 376 | mask | 00 core |  |
| `0x4018f80c` | 192 | mask | 15 sampler |  |
| `0x4018f98c` | 124 | mask | 00 core |  |
| `0x4018fa84` | 124 | mask | 00 core |  |
| `0x4018fb7c` | 124 | mask | 00 core |  |
| `0x4018fc74` | 376 | mask | 05 delay-fx |  |
| `0x4018ff64` | 272 | mask | 04 reverb-fx |  |
| `0x40190184` | 192 | mask | 15 sampler |  |
| `0x40190334` | 192 | mask | 15 sampler |  |
| `0x401904b4` | 376 | mask | 05 delay-fx |  |
| `0x401907a4` | 124 | mask | 00 core |  |
| `0x4019089c` | 192 | mask | 15 sampler |  |
| `0x40190a1c` | 124 | mask | 00 core |  |
| `0x40192734` | 376 | mask | 06 strum |  |
| `0x40192a24` | 192 | mask | 15 sampler |  |
| `0x40192ba4` | 272 | mask | 15 sampler |  |
| `0x40194ad4` | 124 | mask | 00 core |  |
| `0x40195a7c` | 124 | mask | 00 core |  |
| `0x4233c100` | 56 | RAM | 04 reverb-fx | phaser state |
| `0x4233c140` | 20 | RAM | 05 delay-fx | digital delay state |
| `0x4233c180` | 56 | RAM | 04 reverb-fx | RAZR phaser state |
| `0x4233c200` | 4 | RAM | 04 reverb-fx | RAZR reverb parameters |
| `0x4233c210` | 256 | RAM | 04 reverb-fx | RAZR buffer |
| `0x4233c320` | 56 | RAM | 05 delay-fx | VIBDEL/CHODEL state |
| `0x4233c378` | 4 | RAM | 06 strum | root note level |
| `0x4233c3fc` | 1 | RAM | 04 reverb-fx | mode mirror |
| `0x4233c3fd` | 2 | RAM | 05 delay-fx | type + speed mirror |
| `0x43000000` | 20996 | RAM | 04 reverb-fx | payload (code, tables), copied at start |
| `0x43000000` | 65536 | RAM | 00 core | payload (slots: reverb-fx +0x0, control-mode +0x7000, pad-mode +0x7800, strings +0x8000, sampler +0xb000, core +0xc000, mono +0xe000), copied at start |
| `0x430077fc` | 1 | RAM | 09 control-mode | Control All track selection (0 at start = all tracks) |
| `0x43008000` | 9278 | RAM | 16 strings | payload slot 'strings' (code, tables) |
| `0x4300be00` | 512 | RAM | 15 sampler | loaded samples (payload) |
| `0x4300e000` | 7940 | RAM | 17 mono | payload slot 'mono' (code, tables) |
| `0x43100000` | 1024 | RAM | 04 reverb-fx | Hall / Room / Plate state |
| `0x43110000` | 102912 | RAM | 04 reverb-fx | Hall / Room / Plate delay lines |
| `0x43180000` | 27648 | RAM | 16 strings | state + ensemble ring per track |
| `0x431a0000` | 3072 | RAM | 17 mono | state per track |
| `0x43801000` | 49283072 | RAM | 15 sampler | sample memory (outside the image) |
| `0x4a33a000` | 8240 | RAM | 04 reverb-fx | chorus state + ring |
| `0x4a33c380` | 40 | RAM | 00 core | popup + key state (VARS) |
| `0x4a33c3a4` | 4 | RAM | 08 groove | MACHINE pressed (in core VARS) |
| `0x4a33c3a8` | 2 | RAM | 09 control-mode | SETTINGS used since press, byte for COPY |
| `0x4a33c3ac` | 4 | RAM | 10 trig-select | selection mode on ('TSEL') |
| `0x4a33c3c0` | 12 | RAM | 00 core | detent counter (SLOW) |
| `0x4a33c3d0` | 36 | RAM | 07 load-meter | meter state + text |

## Hooks

Named hooks with the firmware function they replace; every patch file lists all of its hooks under `hooks` (the core
also redirects every reference to the parameter descriptor table, the machines 15–17 every machine limit and table).

| Hook | Firmware function | Patch |
|---|---|---|
| `0x400081b8` | encoder event dispatch (gesture dispatcher) | 00 core |
| `0x40076c88` | end of the view controller render pass (popups) | 00 core |
| `0x4001c54c` | main screen key handler, SETTINGS press | 00 core |
| `0x4001c564` | main screen key handler, SETTINGS long hold | 00 core |
| `0x4001c5bc` | main screen key handler, SETTINGS release | 00 core |
| `0x4005b4b0` | pattern load: header copy | 00 core |
| `0x4006155e` | new pattern: header init | 00 core |
| `0x4005aecc` | sound load (record -> sound): start of the function | 00 core |
| `0x4005afa0` | sound save, record version 2: start of the function | 00 core |
| `0x4005b054` | sound save, record version 1: start of the function | 00 core |
| `0x4005aa34` | p-lock index -> parameter k | 00 core |
| `0x4005b998` | parameter k -> p-lock index: table reference | 00 core |
| `0x4005baca` | parameter k -> p-lock index: table reference (second) | 00 core |
| `0x4001d36a` | main screen: T1-T6 select the track | 00 core |
| `0x4005981e` | audio function: voice render call (attack ramp) | 00 core |
| `0x4001e814` | knob -> descriptor lookup: prologue | 00 core |
| `0x400a9430` | amp envelope: VCA (attack) | 00 core |
| `0x400004b2` | start-up code: copy of the payload area to RAM | 00 core |
| `0x40005f86` | LED set function (LED filter) | 00 core |
| `0x4005a6d0` | parameter search (machine-specific descriptors) | 00 core |
| `0x400a559e` | browser row: text draw call (scrolling names) | 00 core |
| `0x400a5720` | browser hint text (RT=MENU) | 00 core |
| 105 more | references to the descriptor table and machine tables | 00 core |
| `0x40100c44` | MuteView vtable: key event (latching mute) | 01 mute-solo |
| `0x4002351a` | MuteView track keys: key -> track (latching mute) | 01 mute-solo |
| `0x400233a0` | MuteView LED pass: LED controller (FUNC LED) | 01 mute-solo |
| `0x400081f2` | UI tick (30 Hz) | 02 hold-mute |
| `0x4001d05e` | pad note-on on the main screen | 02 hold-mute |
| `0x4001d0fc` | pad note-off on the main screen | 02 hold-mute |
| `0x4004dfda` | Delay Time display text | 03 delay-notes |
| `0x400581b8` | delay-time calculation (DSP) | 03 delay-notes |
| `0x40056a2c` | mixer: call of the reverb | 04 reverb-fx |
| `0x4005699c` | mixer: call of the delay | 05 delay-fx |
| `0x40056a3c` | mixer: write DMA of the delay line | 05 delay-fx |
| `0x400ab240` | CHORD voice update, end | 06 strum |
| `0x400ab2d2` | CHORD root note level | 06 strum |
| `0x40059382` | audio interrupt: call of the audio function | 07 load-meter |
| `0x4001c1ce` | main screen key handler, BPM (tempo menu) | 07 load-meter |
| `0x40054af8` | sequencer event builder: swing addition | 08 groove |
| `0x4001ca1e` | main screen key handler, MACHINE | 08 groove |
| `0x40100588` | ParameterPageView vtable +0x5c: CONTROL ALL (vtable entry) | 09 control-mode |
| `0x4001ab7a` | main screen LEVEL handler: volume branch | 09 control-mode |
| `0x4001aaec` | main screen LEVEL handler: pan branch | 09 control-mode |
| `0x40100f24` | TrackSelectionView vtable: key event (vtable entry) | 09 control-mode |
| `0x40021ec2` | PatternGridView frame: trig LEDs (CONTROL ALL / pad selection) | 09 control-mode |
| `0x40100af0` | PatternGridView vtable +0x08: consumeKeyEvent (vtable entry) | 10 trig-select |
| `0x401005a0` | ParameterPageView vtable +0x74: change p-locks of held steps (vtable entry) | 10 trig-select |
| `0x4001c4a6` | main screen key handler, PAGE: FUNC check | 10 trig-select |
| `0x40021f56` | grid LED loop: state of one step | 10 trig-select |
| `0x40029d9a` | NoteVelocityView: call of the held-trig settings change | 10 trig-select |
| `0x40091416` | sequencer trig-condition check: range check | 11 fill2 |
| `0x40015ff6` | trig-condition getter: read the byte | 11 fill2 |
| `0x4001605a` | trig-condition setter: store the byte | 11 fill2 |
| `0x4004a4f6` | trig-condition text: name table | 11 fill2 |
| `0x400500a8` | trig-condition display: base-name table | 11 fill2 |
| `0x400500da` | trig-condition display: percent range | 11 fill2 |
| `0x4005010c` | trig-condition display: negation mark | 11 fill2 |
| `0x40059852` | audio function: call of Volume + Distortion (the filter runs after it) | 12 track-filter |
| `0x401005a8` | ParameterPageView vtable slot 124: knob -> descriptor (vtable entry) | 12 track-filter |
| `0x4001ca9c` | main screen key handler, GATE | 12 track-filter |
| `0x4001c4ba` | main screen key handler, RETRIG | 12 track-filter |
| `0x40021e0e` | PatternGridView frame: start (knob LEDs) | 12 track-filter |
| `0x4001c326` | main screen key handler, PLAY (GATE + PLAY) | 12 track-filter |
| `0x400243d6` | TrackSelectionView key handler: PLAY branch | 12 track-filter |
| `0x400597c6` | audio function: call of the track LFOs | 13 lfo-amount |
| `0x40020c84` | pattern selection: trig key pressed, FUNC check | 14 direct-jump |
| `0x4005563e` | sequencer, tick 0: pattern change due? | 14 direct-jump |
| `0x40055898` | sequencer, tick 0: track start steps after a change | 14 direct-jump |
| `0x40020aa6` | pattern selection key dispatcher: FUNC | 14 direct-jump |
| `0x40024b12` | pattern window key handler: FUNC | 14 direct-jump |
| `0x40024bd0` | pattern window key handler: trig key (completion + close) | 14 direct-jump |
| `0x40020df0` | pattern selection: last trig key released | 14 direct-jump |
| `0x401011b0` | pattern selection window vtable (latched selection) | 14 direct-jump |
| `0x40020f14` | pattern selection: copy pattern (popup) | 14 direct-jump |
| `0x40020fb8` | pattern selection: clear pattern (hold dialog) | 14 direct-jump |
| `0x4002113e` | pattern selection: paste pattern (hold dialog) | 14 direct-jump |
| `0x400147a4` | set machine: limit | 15 sampler |
| `0x400a25e0` | MACHINES screen: number of machines | 15 sampler |
| `0x400a7dba` | voice loop: machine limit | 15 sampler |
| `0x400a2614` | machine names | 15 sampler |
| `0x400a2638` | machine images | 15 sampler |
| `0x4001e8da` | knob vector of the machines | 15 sampler |
| `0x400075f0` | UI task frame (sample loading) | 15 sampler |
| `0x4010053c` | ParameterPageView vtable: draw (waveform) | 15 sampler |
| `0x40084b8e` | Transfer identity answer | 15 sampler |
| `0x40084c14` | Transfer product number | 15 sampler |
| `0x4009249a` | incoming Transfer message type | 15 sampler |
| `0x40094c9a` | outgoing Transfer message type | 15 sampler |
| `0x40032aee` | Device Config menu (Transfer row) | 15 sampler |
| 19 more | references to the descriptor table and machine tables | 15 sampler |
| `0x400147a4` | set machine: limit | 16 strings |
| `0x400a25e0` | MACHINES screen: number of machines | 16 strings |
| `0x400a7dba` | voice loop: machine limit | 16 strings |
| `0x400a2614` | machine names | 16 strings |
| `0x4001e8da` | knob vector of the machines | 16 strings |
| `0x400a2638` | machine images | 16 strings |
| 17 more | references to the descriptor table and machine tables | 16 strings |
| `0x400147a4` | set machine: limit | 17 mono |
| `0x400a25e0` | MACHINES screen: number of machines | 17 mono |
| `0x400a7dba` | voice loop: machine limit | 17 mono |
| `0x400a2614` | machine names | 17 mono |
| `0x4001e8da` | knob vector of the machines | 17 mono |
| `0x400a2638` | machine images | 17 mono |
| 17 more | references to the descriptor table and machine tables | 17 mono |
| `0x4001f760` | ParameterPageView: undo countdown after a knob turn | 18 param-undo |
| `0x40022c22` | PatternGridView consumeKeyEvent: trig pressed without FUNC | 19 pad-mode |
| `0x40022cda` | PatternGridView consumeKeyEvent: FUNC + trig | 19 pad-mode |
| `0x400548ce` | sequencer event builder: start | 19 pad-mode |
| `0x400ff9cc` | KeyboardView vtable (chromatic keys on pad tracks) | 19 pad-mode |
| 2 more | see the patch file | 19 pad-mode |

Only patches that require each other hook the same place (15–17 raise the same machine limits one after another, and
every core patch writes its handler into a slot of the core), so every combination can be applied
(`tests/test_modular.py` applies every patch alone and every pair). Optional couplings are detected at run time, never
required: 05 uses the exact triplets of 03 if its DSP hook is there; 08 and 10 read the control-mode byte of the core;
turning a knob while RETRIG is held (13) does not end the filter mode of 12; RETRIG with TRACK (19) is used up.

## Combining with other mods

Every patch lists its hooks and memory, so you can check for collisions (the idea of a shared mod standard).
This collection uses a lot of the free memory (sprite masks, RAM behind the BSS, the descriptor table, the payload
area), so most other mods will collide with it; combinations with mods of other collections were not checked.
`tools/apply_patches.py` stops on any overlap that is not declared in `requires`.

## Tests

`tests/run_all.py` runs the original firmware code in Unicorn: the real key chain and key handlers, the real render
path with the real fonts, the real sequencer event builder (Modded-Cycles' `seqrig`), the real CONTROL ALL and
held-step functions, the real sequencer interrupt (direct jump), the real sound load / save functions, the machines
against floating-point models, and the effect code against v1.0.0. The EMAC (filter) is emulated exactly with Modded-Cycles' `emac.py`. Each test prints its checks (`ok` / `FAIL`, texts in
German); `run_all.py` sums them up. See [tests/README.md](../tests/README.md).
