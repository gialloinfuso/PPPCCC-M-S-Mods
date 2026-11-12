# Emulator tests

```sh
pip install unicorn capstone numpy pillow
python3 tests/run_all.py <section_3_MAIN_OS.bin of the official Model:Cycles OS 1.13> [test ...] [-j N]
```

Needs a checkout of [Modded-Cycles](https://github.com/18nelli18/Modded-Cycles) in the repository root (emulator
rigs, free sprite masks). With [elektron-model-tweaks](https://github.com/drumkilla/elektron-model-tweaks) there too,
`test_latch.py` and `test_browserscroll.py` also check that the latching mute and the scrolling names behave exactly like
drumkilla's tweaks.
`run_all.py` regenerates all patches and the v1.0.0 reference patches into `build/testenv`, sets up the layout the
tests expect and runs them, two at a time (`-j` for more). The tests run the original firmware code in Unicorn, print
their checks (in German) and end with `GESAMT ok`; `run_all.py` ends with `all tests ok`.

| Test | Patches | What it checks |
|---|---|---|
| `test_core.py` | 00 | encoder dispatcher and slots, key slots, gesture helper, slow selection, pattern storage |
| `test_popup.py` | 00, 07 | popups drawn by the real render path with the real fonts, pixel for pixel |
| `test_dtab.py` | 00 | the moved and extended parameter descriptor table, every redirected reference |
| `test_smp12.py` | 00, 15 | TRACK + T1–T6, the attack (knob lookup, ramp after the VCA, sound slot), FUNC + COLOR on Grit |
| `test_mlbrowser.py [--alone]` | 00 | the multi-line browser with the real list view |
| `test_browserscroll.py` | 00 | the scrolling names against a model (steps, pauses, names that fit, new names) |
| `test_latch.py` | 01 | the latching mute with the real key functions of the mute view: latch, leave, long hold, FUNC used, track keys, LED |
| `test_levelpan.py [--alone]` | 00 | volume and pan as numbers on the main screen |
| `test_browserkeys.py` | 00 | RETRIG opens the save menu in the browser, the RT=MENU hint |
| `test_modular.py` | all | every patch alone and every pair with its requirements applies; each core patch alone handles its gestures and passes all others through |
| `test_fx_diff.py` | 04, 05 | reverb and delay effects bit-identical to v1.0.0, delay triplets with and without 03, gestures |
| `test_reverbs.py` | 04 | Hall / Room / Plate through the real mixer hook against a floating-point model |
| `test_strum.py` | 06 | strum timing and patterns on rebuilt CHORD voices, envelopes, retrigger |
| `test_mods_diff.py` | 07, 08 | load meter and groove code against v1.0.0; RETRIG + BPM in the real key handler; meter off after power-on |
| `test_groove_seq.py` | 00, 08 | real sequencer event builder: Swing identical to stock, every groove and humanize against a reference |
| `test_control.py [--alone]` | 09 | real CONTROL ALL loop, setter and step functions: relative = stock, absolute; LEVEL / pan; the toggle; the track selection; humanize |
| `test_trigselect.py [--alone]` | 10 | selection mode with the real held-step functions; all / none; PAGE; LED blink; p-locks, nudge, note / velocity / length in absolute mode |
| `test_fill2.py [--alone]` | 11 | real condition check against stock for all values, the new conditions, getter / setter, condition text and display mapping |
| `test_trackfilter.py [--alone]` | 00, 12 | the filter through the real audio hook against a floating-point model; cutoff 127 bit-identical; filter mode with the real key handler; sound load / save; p-locks; reset |
| `test_filterleds.py [--alone]` | 12 | the knob LEDs in the filter mode with the firmware's real LED function and knob-LED loop |
| `test_lfoamount.py [--alone]` | 00, 13 | the real LFO hook (depth scaled and restored, 127 bit-identical, self-modulation); knob lookup; sound load / save; p-locks |
| `test_directjump.py [--alone]` | 14 | the real sequencer interrupt: bit-identical to stock without a jump; direct jumps; the keys of the pattern selection, its window and observer; copy / paste / clear |
| `test_sampler.py [--alone]` | 15 | the sampler models against floating point, filters, aliasing, overview and waveform, sample locks, loading |
| `test_transfer.py` | 15 | the Transfer identity switch (identity answer, product number, message types) |
| `test_strings.py` | 16 | Vlvt against its floating-point model (`str_model.py`), chords, strum envelopes |
| `test_mono.py` | 17 | Monom against its floating-point model (`mono_model.py`) |
| `test_paramundo.py` | 18 | the undo countdown in the real parameter page function |
| `test_pad.py` | 19 | pad tracks: the real event builder and queue, grid keys, track selection keys, LEDs, MIDI |
| `test_cfasm.py` | – | the assembler: every instruction form against Capstone |

The flasher is checked separately, with Node 18 or newer:

```sh
node tests/check_flasher.mjs model-cycles_OS1.13.syx [model-cycles_OS1.13_for-model-samples.syx] [model-samples_OS1.13.syx]
```

It builds full and partial sets for both devices with `flasher/lib.js` and with `tools/build.py` and compares them
byte for byte; with the official Samples file it also checks the cross-flash.

`--alone` also runs the test on an image with only the core and that patch. `ramalias.py` maps the cached and
uncached RAM aliases onto one buffer; `rig.py` is the shared test bench.
