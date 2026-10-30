# User guide

All controls of the full build on one page. Every patch has its own page with details under [patches/](patches/).

## Modifier keys

| Modifier | Used for |
|---|---|
| **TRACK** + knob | Stock: CONTROL ALL (relative or absolute, patch 10). Added: **effect selection** on Reverb Size and Delay Time. |
| **TRACK** + **SETTINGS** (tap) | Switch CONTROL ALL relative ↔ absolute. |
| **SETTINGS** + knob | Delay speed, strum, load meter, humanize timing. |
| **SETTINGS** + **PAGE** | Trig selection mode on / off. |
| **PAGE** (held) + **FUNC** | Fill 2 instead of Fill 1. |
| **MACHINE** + Swing | Humanize velocity. |
| **FUNC** + Swing | Groove selection. |
| **RETRIG** + **GATE** | Track filter mode on (tap RETRIG = off). |
| **RETRIG** + LFO SPEED | LFO Amount. |
| **PATTERN**, then **FUNC** + trig key | Direct jump to that pattern. |

A short press of SETTINGS still opens the settings, FUNC + SETTINGS still quick-saves, and holding SETTINGS alone
still saves the project (on release now). After a SETTINGS gesture neither the menu nor the save happens. MACHINE
opens its menu on release now, not on press.

## Mutes

| Do this | Result | Patch |
|---|---|---|
| hold **TRK**, tap **FUNC** | latching mute mode (FUNC lights up) | drumkilla's latching mute |
| in that mode: hold **FUNC** + track key | solo that track; again = previous mutes back | [01](patches/01-mute-solo.md) |
| mute a track | pads and MIDI notes for that track are silent too | [02](patches/02-live-mute.md) |
| sequencer running: hold **T1–T6** | the track is muted until you let go; a tap still plays | [03](patches/03-hold-mute.md) |

## Effects

Reverb slot (hold **TRACK** + turn **Reverb Size**, 4 detents per step), [05](patches/05-reverb-fx.md):

| Effect | Send | Size | Tone |
|---|---|---|---|
| Reverb (stock) | send | size | tone |
| Chorus I / Chorus II | send | speed | depth |
| Phaser | send | speed | color |
| RAZR | mix | length | phaser speed (0 = reverb only) |

Delay slot (hold **TRACK** + turn **Delay Time**, 4 detents per step), [06](patches/06-delay-fx.md):

| Effect | What it is |
|---|---|
| Delay (stock) | Delay Time shows note values, triplets are exact ([04](patches/04-delay-notes.md)) |
| Digital | bright, clean, up to 5.4 s |
| VIBDEL | vibrato delay |
| CHODEL | chorus delay |

**SETTINGS + DELAY SEND** = modulation speed of VIBDEL / CHODEL.

## Chords, grooves, load

| Do this | Result | Patch |
|---|---|---|
| **SETTINGS + SHAPE** | strum −80…80 ms between chord notes (right = up, left = down) | [07](patches/07-strum.md) |
| **SETTINGS + REVERB SEND** right / left | load meter on / off | [08](patches/08-load-meter.md) |
| **FUNC + Swing** | groove: Swing, Boom Bap, Disco, Reggae, Bongo, Caixixi, Highlife, Kuduro | [09](patches/09-groove.md) |
| **Swing** | amount of the groove on this track | [09](patches/09-groove.md) |
| **SETTINGS + Swing** | humanize timing of the selected track (0–100) | [09](patches/09-groove.md) |
| **MACHINE + Swing** | humanize velocity of the selected track (0–100) | [09](patches/09-groove.md) |
| **TRACK + SETTINGS / MACHINE + Swing** | the same for all tracks | [09](patches/09-groove.md) |

## CONTROL ALL and trig selection

| Do this | Result | Patch |
|---|---|---|
| hold **TRACK** + tap **SETTINGS** | CONTROL ALL: Relative (stock) ↔ Absolute | [10](patches/10-control-mode.md) |
| hold **TRACK** + turn a knob / **LEVEL** / **FUNC + LEVEL** | relative: all tracks move by the same amount · absolute: all tracks get the selected track's value | [10](patches/10-control-mode.md) |
| **SETTINGS + PAGE** | trig selection mode on / off | [11](patches/11-trig-select.md) |
| in the mode: tap a trig | select / deselect it (selected trigs blink fast) | [11](patches/11-trig-select.md) |
| in the mode: **FUNC + PAGE** | all trigs of the track / none | [11](patches/11-trig-select.md) |
| with a selection: knobs, note / velocity / length, nudge | change all selected trigs (absolute mode: all get the first one's value) | [11](patches/11-trig-select.md) |
| with a selection: **REC** / **STOP** / **PLAY** | copy the selected trigs / paste from the first selected step / clear their locks | [11](patches/11-trig-select.md) |

Every new value shows a popup in the firmware's style while you turn.

## Fills

| Do this | Result | Patch |
|---|---|---|
| hold **PAGE** | Fill (Fill 1), as on the stock OS | |
| hold **PAGE**, then also **FUNC** | Fill 2 instead of Fill 1, as long as both are held | [12](patches/12-fill2.md) |
| fill latched with **TRACK + PAGE**, then hold **FUNC** | Fill 2 while FUNC is held | [12](patches/12-fill2.md) |
| trig condition **FIL2** / **!FIL2** (right after FILL / !FILL) | plays only in Fill 2 / plays except in Fill 2; during Fill 2, FILL is silent and !FILL plays | [12](patches/12-fill2.md) |

## Track filter and LFO amount

| Do this | Result | Patch |
|---|---|---|
| hold **RETRIG** + press **GATE** | filter mode on ("FILTER ON", the four knob LEDs light up) | [13](patches/13-track-filter.md) |
| tap **RETRIG** | filter mode off | [13](patches/13-track-filter.md) |
| in the filter mode: **PITCH** / **COLOR** / **SHAPE** / **DECAY** | cutoff (127 = off) / resonance / envelope depth (bipolar, middle = off) / envelope decay | [13](patches/13-track-filter.md) |
| hold a trig in the filter mode + turn one of them | p-lock the filter | [13](patches/13-track-filter.md) |
| CC 74 / CC 71 | filter cutoff / resonance | [13](patches/13-track-filter.md) |
| hold **RETRIG** + turn **LFO SPEED** | LFO Amount of the track: 0 = no LFO … 127 = full depth (default) | [14](patches/14-lfo-amount.md) |

The filter parameters and LFO Amount are real parameters: choose them as LFO destination or velocity destination in
the usual menus.

## Patterns

| Do this | Result | Patch |
|---|---|---|
| **PATTERN**, then **FUNC** + trig key | jump to that pattern now and keep the position; the selection stays open | [15](patches/15-direct-jump.md) |
| **PATTERN**, then trig key | change at the end of the pattern (stock) | |

## What is saved where

| Setting | Where |
|---|---|
| reverb-slot effect, delay-slot effect, delay speed, strum, groove, humanize | **in each pattern** (saved with the project) |
| CONTROL ALL relative / absolute | device settings |
| trig conditions (also FIL2 / !FIL2) | in the pattern, like every trig |
| filter cutoff / resonance / envelope / decay, LFO Amount | **in the sound** (kit, project), p-locks in the pattern |
| load meter, trig selection, solo memory, filter mode | not saved (off after power-on) |

The firmware writes its device settings **when you switch off**. A USB OS update restarts without saving them, so
after switching the control mode, switch off once before you flash.
