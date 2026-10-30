# Emulator tests

```sh
pip install unicorn capstone pillow
python3 tests/run_all.py <section_3_MAIN_OS.bin of the official Model:Cycles OS 1.13> [test ...]
```

Needs checkouts of [Modded-Cycles](https://github.com/18nelli18/Modded-Cycles) and
[elektron-model-tweaks](https://github.com/drumkilla/elektron-model-tweaks) in the repository root.
`run_all.py` regenerates the v2 patches and the v1.0.0 patches into `build/testenv`, sets up the layout the tests
expect and runs them all. The tests run the original firmware code in Unicorn and print their checks (in German).

| Test | Patches | What it checks |
|---|---|---|
| `test_solo.py` | 01 | solo, restore, solo on another track, FUNC not held, mode not latched |
| `test_livemute.py` | 02 | note-on/off on muted and unmuted tracks |
| `test_holdmute_113.py` | 03 | hold/tap with the sequencer running and stopped (19 checks) |
| `test_delaynotes.py` | 04 | delay length for all 128 values, labels |
| `test_core.py` | 00 | encoder dispatcher and slots, key slots, gesture helper, slow selection, pattern storage |
| `test_popup.py` | 00, 08 | popups drawn by the real render path with the real fonts, pixel for pixel against the firmware's own functions |
| `test_settings_key_113.py` | 00, 09 | real key chain and main-screen key handler: SETTINGS menu / save / quick save, MACHINE on release |
| `test_modular.py` | all | every combination of the core mods applies; each mod alone with the core handles its gestures and passes all others through |
| `test_fx_diff.py` | 05, 06 | reverb and delay effects bit-identical to v1.0.0, delay triplets with and without 04, gestures |
| `test_mods_diff.py` | 07, 08, 09 | strum, load meter and groove code against v1.0.0; gestures; meter off after power-on |
| `test_groove_seq.py` | 00, 09 | real sequencer event builder: Swing identical to stock, every groove and humanize against a reference; pattern load / new pattern |
| `test_control.py [--alone]` | 10 | real CONTROL ALL loop, setter and step functions: relative = stock, absolute; LEVEL / pan; the toggle in the real key handler; humanize |
| `test_trigselect.py [--alone]` | 11 | selection mode with the real held-step functions; all/none; PAGE; LED blink; p-locks, nudge, note/velocity/length in absolute mode |
| `test_fill2.py [--alone]` | 12 | real condition check against stock for all values, with and without fill and FUNC; real getter / setter, condition text and display mapping |
| `test_trackfilter.py [--alone]` | 00, 13 | the filter through the real audio hook against a floating-point model; cutoff 127 bit-identical; response, envelope, stability, cost; filter mode with the real key handler; sound load / save with the real functions; p-locks |
| `test_filterleds.py [--alone]` | 13 | the knob LEDs in the filter mode with the firmware's real LED function and knob-LED loop |
| `test_lfoamount.py [--alone]` | 00, 14 | the real LFO hook (depth scaled and restored, 127 bit-identical, self-modulation); knob lookup; sound load / save; p-locks |
| `test_directjump.py [--alone]` | 15 | the real sequencer interrupt: bit-identical to stock without a jump; direct jumps at many positions, per-track mode, MIDI program change; the keys of the pattern selection, its window and observer |

`--alone` runs the test on an image with only the core and that patch (12 and 15: only that patch). `ramalias.py` maps the cached and uncached
RAM aliases onto one buffer; `rig.py` is the shared test bench of the v2 tests.
