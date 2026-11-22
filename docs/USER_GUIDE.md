# User guide

All controls of the full build on one page. Every patch has its own page with details under [patches/](patches/).

## Modifier keys

| Modifier | Used for |
|---|---|
| **TRACK** + knob | Stock: CONTROL ALL (relative or absolute, patch 09). Added: **effect selection** on Reverb Size and Delay Time. |
| **TRACK** + **SETTINGS** (tap) | Switch CONTROL ALL relative ↔ absolute. |
| **TRACK** + trig 1–6 | Add / remove a track for CONTROL ALL. |
| **TRACK** + **T1–T6** | Select the track (T1–T6 alone no longer do). |
| **TRACK** + **FUNC** (tap) | Latching mute mode. |
| **TRACK** + **RETRIG** (+ trig 1–6) | Show (switch) pad tracks. |
| **FUNC** + knob | Extra parameters: DECAY = attack, SHAPE / COLOR = strum (CHORD, Vlvt), PITCH = glide and CONTOUR = noise (Monom), COLOR = move start and end (Grit), DELAY SEND = delay speed, Swing = groove. Other knobs move in fine steps. |
| **SETTINGS** + knob | Humanize timing (Swing). |
| **SETTINGS** + **PAGE** | Trig selection mode on / off. |
| **PAGE** (held) + **FUNC** | Fill 2 instead of Fill 1. |
| **MACHINE** + Swing | Humanize velocity. |
| **RETRIG** + **GATE** | Track filter mode on (tap RETRIG = off). |
| **RETRIG** + LFO SPEED | LFO Amount. |
| **RETRIG** + **BPM** | Load meter on / off. |
| **FUNC** + **GATE** (filter mode) | Track filter 12 dB ↔ 24 dB for the selected track. |
| **GATE** + **PLAY** | Filter reset of the selected track. |
| **PATTERN**, then **FUNC** + trig key | Direct jump to that pattern. |

A short press of SETTINGS still opens the settings, FUNC + SETTINGS still quick-saves, and holding SETTINGS alone
still saves the project (on release now). After a SETTINGS gesture neither the menu nor the save happens. MACHINE
opens its menu on release now, not on press. In the browser, RETRIG opens the save menu (RT=MENU).

## Mutes

| Do this | Result | Patch |
|---|---|---|
| hold **TRACK**, tap **FUNC** | latching mute mode (FUNC lights up); tap FUNC alone to leave it | [01](patches/01-mute-solo.md) |
| in that mode: hold **FUNC** + track key | solo that track; again = previous mutes back | [01](patches/01-mute-solo.md) |
| mute a track | pads and MIDI notes for that track are silent too | [01](patches/01-mute-solo.md) |
| sequencer running: hold **T1–T6** | the track is muted until you let go; a tap still plays | [02](patches/02-hold-mute.md) |

## Effects

Reverb slot (hold **TRACK** + turn **Reverb Size**, 4 detents per step), [04](patches/04-reverb-fx.md):

| Effect | Send | Size | Tone |
|---|---|---|---|
| Reverb (stock) | send | size | tone |
| Chorus I / Chorus II | send | speed | depth |
| Phaser | send | speed | color |
| RAZR | mix | length | phaser speed (0 = reverb only) |
| Hall / Room / Plate | send | decay | damping |

Delay slot (hold **TRACK** + turn **Delay Time**, 4 detents per step), [05](patches/05-delay-fx.md):

| Effect | What it is |
|---|---|
| Delay (stock) | Delay Time shows note values, triplets are exact ([03](patches/03-delay-notes.md)) |
| Digital | bright, clean, up to 5.4 s |
| VIBDEL | vibrato delay |
| CHODEL | chorus delay |

**FUNC + DELAY SEND** = modulation speed of VIBDEL / CHODEL.

## Machines

| Machine | PITCH | DECAY | COLOR | SHAPE | SWEEP | CONTOUR | FUNC + | Patch |
|---|---|---|---|---|---|---|---|---|
| **Grit** (7th) | pitch | amp decay | sample start | sample length | – | model CLEAN / SP / LM / MIRAGE / TX16W / MPC60 | COLOR = move start + end; PUNCH = loop, GATE = reverse | [15](patches/15-sampler.md) |
| **Vlvt** (8th) | pitch | amp decay | 8' / 4' mix | chord | tone | ensemble | SHAPE / COLOR = strum | [16](patches/16-strings.md) |
| **Monom** (9th) | pitch | amp decay | wave | timbre | sub | drive | PITCH = glide, CONTOUR = noise | [17](patches/17-mono.md) |

On every machine **FUNC + DECAY** = attack (core). **GATE** works on Vlvt and Monom as on CHORD and TONE (hold while the
trig or note lasts); on Grit it is reverse. Grit: choose samples with **FUNC + MACHINES** (browser); upload them
with Elektron Transfer after switching Device Config > Transfer to SMP (every start begins with CYC). Grit, Vlvt and
Monom only work together.

## Chords, grooves, load

| Do this | Result | Patch |
|---|---|---|
| CHORD / Vlvt track: **FUNC + SHAPE** | strum time: OFF, 2–250 ms, note values in tempo | [06](patches/06-strum.md) |
| CHORD / Vlvt track: **FUNC + COLOR** | strum pattern: UP, DOWN, RND, 1324, 1423, 4132, 4231, ROOT, TOP | [06](patches/06-strum.md) |
| **RETRIG + BPM** | load meter on / off | [07](patches/07-load-meter.md) |
| **FUNC + Swing** | groove: Swing, Boom Bap, Disco, Dancehall 1 / 2, Hip Hop, Jazz Rock, Perc 1–3, Soca | [08](patches/08-groove.md) |
| **Swing** | amount of the groove on this track | [08](patches/08-groove.md) |
| **SETTINGS + Swing** | humanize timing of the selected track (0–100) | [08](patches/08-groove.md) |
| **MACHINE + Swing** | humanize velocity of the selected track (0–100) | [08](patches/08-groove.md) |
| **TRACK + SETTINGS / MACHINE + Swing** | the same for all tracks | [08](patches/08-groove.md) |

## CONTROL ALL, trig selection and pads

| Do this | Result | Patch |
|---|---|---|
| hold **TRACK** + tap **SETTINGS** | CONTROL ALL: Relative (stock) ↔ Absolute | [09](patches/09-control-mode.md) |
| hold **TRACK** + turn a knob / **LEVEL** / **FUNC + LEVEL** | relative: all tracks move by the same amount · absolute: all tracks get the selected track's value | [09](patches/09-control-mode.md) |
| hold **TRACK** (+ trig 1–6) | show (add / remove) the tracks CONTROL ALL affects | [09](patches/09-control-mode.md) |
| **SETTINGS + PAGE** | trig selection mode on / off | [10](patches/10-trig-select.md) |
| in the mode: tap a trig | select / deselect it (selected trigs blink fast) | [10](patches/10-trig-select.md) |
| in the mode: **FUNC + PAGE** | all trigs of the track / none | [10](patches/10-trig-select.md) |
| with a selection: knobs, note / velocity / length, nudge | change all selected trigs (absolute mode: all get the first one's value) | [10](patches/10-trig-select.md) |
| with a selection: **REC** / **STOP** / **PLAY** | copy the selected trigs / paste from the first selected step / clear their locks | [10](patches/10-trig-select.md) |
| hold **TRACK + RETRIG** + trig 1–6 | pad mode on / off for that track | [19](patches/19-pad-mode.md) |
| pad track: tap a trig · **FUNC** + trig | play that step · add / clear it | [19](patches/19-pad-mode.md) |
| turn a knob, then **BACK** | undo, for three times as long as before | [18](patches/18-param-undo.md) |

Every new value shows a popup in the firmware's style while you turn.

## Fills and trig conditions

| Do this | Result | Patch |
|---|---|---|
| hold **PAGE** | Fill (Fill 1), as on the stock OS | |
| hold **PAGE**, then also **FUNC** | Fill 2 instead of Fill 1, as long as both are held | [11](patches/11-fill2.md) |
| fill latched with **TRACK + PAGE**, then hold **FUNC** | Fill 2 while FUNC is held | [11](patches/11-fill2.md) |
| trig condition **FIL2** / **!FIL2** | plays only in Fill 2 / except in Fill 2; during Fill 2, FILL is silent and !FILL plays | [11](patches/11-fill2.md) |
| trig condition **PTC** / **!PTC** | plays while a newly chosen pattern is waiting / while not | [11](patches/11-fill2.md) |
| trig condition **LST** / **!LST** | plays in the last pass before another pattern / in the others | [11](patches/11-fill2.md) |
| trig condition **x:12**, **x:16** | like A:B, with 12 or 16 passes | [11](patches/11-fill2.md) |

## Track filter and LFO amount

| Do this | Result | Patch |
|---|---|---|
| hold **RETRIG** + press **GATE** | filter mode on ("FILTER ON", the four knob LEDs light up) | [12](patches/12-track-filter.md) |
| tap **RETRIG** | filter mode off | [12](patches/12-track-filter.md) |
| in the filter mode: **PITCH** / **COLOR** / **SHAPE** / **DECAY** | cutoff (127 = off) / resonance / envelope amount (bipolar, middle = off) / envelope decay | [12](patches/12-track-filter.md) |
| hold a trig in the filter mode + turn one of them | p-lock the filter | [12](patches/12-track-filter.md) |
| in the filter mode: **FUNC** + **GATE** | 12 dB ↔ 24 dB for the selected track (popup FILTER 12dB / 24dB) | [12](patches/12-track-filter.md) |
| hold **GATE** + press **PLAY** | reset the filter of the selected track (also back to 12 dB) | [12](patches/12-track-filter.md) |
| CC 74 / CC 71 | filter cutoff / resonance | [12](patches/12-track-filter.md) |
| hold **RETRIG** + turn **LFO SPEED** | LFO Amount of the track: 0 = no LFO … 127 = full depth (default) | [13](patches/13-lfo-amount.md) |

The filter parameters, LFO Amount, attack, strum and the extra machine parameters are real parameters: choose them as
LFO destination or velocity destination in the usual menus.

## Patterns

| Do this | Result | Patch |
|---|---|---|
| **PATTERN** | pattern selection on; it stays open until PATTERN again | [14](patches/14-direct-jump.md) |
| in the selection: **FUNC** + trig key | jump to that pattern now and keep the position | [14](patches/14-direct-jump.md) |
| in the selection: trig key | change at the end of the pattern (stock) | |

## What is saved where

| Setting | Where |
|---|---|
| reverb-slot effect, delay-slot effect, delay speed, groove, humanize, pad tracks, filter 12 / 24 dB per track | **in each pattern** (saved with the project) |
| CONTROL ALL relative / absolute | device settings |
| trig conditions (also the new ones) | in the pattern, like every trig |
| attack, strum time / pattern, filter, LFO Amount, Grit sample and settings, Vlvt / Monom parameters | **in the sound** (kit, project), p-locks in the pattern |
| load meter, trig selection, solo memory, filter mode, CONTROL ALL track selection, Transfer CYC / SMP | not saved |

The firmware writes its device settings **when you switch off**. A USB OS update restarts without saving them, so
after switching the control mode, switch off once before you flash.
