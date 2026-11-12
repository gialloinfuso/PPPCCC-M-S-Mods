# Building the firmware

No firmware is distributed here. You build it from your own copy of the official Model:Cycles OS 1.13, either in the
[flasher](https://gialloinfuso.github.io/PPPCCC-M-S-Mods/flasher/) (in the browser) or with `tools/build.py`.

The flasher (`flasher/`) is a JavaScript port of the same steps and builds byte-identical files
(`node tests/check_flasher.mjs model-cycles_OS1.13.syx` compares it with `tools/build.py`). It runs completely in the
browser; no file is uploaded. It can also send the file over Web MIDI (Chrome, Edge, Opera on a desktop computer).

`tools/build.py` refuses any other input. It checks every write against the original bytes (SHA-256), fills the few
placeholders for original instructions that hooks move from your own file (SHA-256 checked too) and checks the
complete MAIN OS against the published result. It unpacks every output file again and re-checks it: packet
checksums, content checksum, section sums, HMAC, and that the MAIN OS is identical to the patched image.

## What you need

- Python 3.8 or newer (no extra packages for building)
- `model-cycles_OS1.13.syx`, the official file from elektron.se
  (SHA-256 `44fe586269631a0ca7da25a3383fc6733c314809505fc3cc52f1e0ed9800640c`)
- nothing else: the container code is in `tools/vendor/` (unchanged MIT copies: `mtlib` and `tweak.py` from
  [drumkilla/elektron-model-tweaks](https://github.com/drumkilla/elektron-model-tweaks), `aplib_grow.py` and
  `crossflash.py` from [18nelli18/Modded-Cycles](https://github.com/18nelli18/Modded-Cycles); see
  [tools/vendor/README.md](../tools/vendor/README.md))

```sh
git clone https://github.com/gialloinfuso/PPPCCC-M-S-Mods
cd PPPCCC-M-S-Mods
```

(or download the ZIP and unpack it).

## Model:Cycles

```sh
python3 tools/build.py --in model-cycles_OS1.13.syx --out cycles-mods
```

This writes `cycles-mods_cyc-os.syx`. Send it like any OS update: in the start-up menu (hold **FUNC** while switching
on, then OS UPGRADE) or from the running OS, with Elektron Transfer or another SysEx tool.

> Not yet tested on a real Model:Cycles. The MAIN OS is the same image that runs on my Model:Samples, apart from
> the 32 bytes of the update key, which no patch touches.

## Model:Samples

A Model:Samples needs the Cycles OS in a Model:Samples container. That container includes a change to the update key,
so the Samples OS can still be flashed back over USB. Modded-Cycles makes this file from your two official files:

```sh
python3 tools/vendor/crossflash.py --cycles model-cycles_OS1.13.syx \
        --samples model-samples_OS1.13.syx --to samples -o cycles-for-samples.syx
python3 tools/build.py --in cycles-for-samples.syx --out cycles-mods --smp
```

This writes two files with the same MAIN OS:

- `cycles-mods_smp-os.syx`: the Model:Samples container. Use it for the **first** flash, from the Samples OS or the
  start-up menu.
- `cycles-mods_cyc-os.syx`: the same OS in the Cycles transport. Use it for later updates on a Model:Samples that already
  runs a Cycles OS with the Samples key (from Modded-Cycles or an earlier build of this repository).

Leave out `--smp` if you only need the `_cyc-os` file. Modded-Cycles' notes/41 explains how to go back to the
official Samples OS (`crossflash.py --back-samples`).

## Choosing patches

By default every patch in `patches/manifest.json` is applied. To build only some of them, list them by id, by file
name or as a path; what they need is added:

```sh
python3 tools/build.py --in model-cycles_OS1.13.syx --out my-mods mute-solo hold-mute reverb-fx groove trig-select
```

| Patch | id | Needs |
|---|---|---|
| 00 | `core` | – |
| 01 | `mute-solo` | – |
| 02 | `hold-mute` | – |
| 03 | `delay-notes` | – |
| 04 | `reverb-fx` | core |
| 05 | `delay-fx` | core (uses the exact triplets of 03 when it is installed) |
| 06 | `strum` | core |
| 07 | `load-meter` | core |
| 08 | `groove` | core (humanize with TRACK follows 09 when it is installed) |
| 09 | `control-mode` | core |
| 10 | `trig-select` | core (absolute mode follows 09 when it is installed) |
| 11 | `fill2` | – |
| 12 | `track-filter` | core |
| 13 | `lfo-amount` | core |
| 14 | `direct-jump` | – |
| 15 | `sampler` | core |
| 16 | `strings` | core, sampler |
| 17 | `mono` | core, sampler, strings |
| 18 | `param-undo` | – |
| 19 | `pad-mode` | core |

Every combination can be applied together; the tool checks this and stops on any collision. The published full-set
checksum is only checked when you build the full set. Single writes are always checked.

## Working with a MAIN OS image directly

If you extract section 3 yourself (for example with elektron-firmware-tool), `tools/apply_patches.py` patches the
raw image:

```sh
python3 tools/apply_patches.py section_3_MAIN_OS.bin patched.bin --all
python3 tools/apply_patches.py section_3_MAIN_OS.bin patched.bin reverb-fx trig-select   # core is added
```

The result is 65536 bytes longer than the input when the core is included (its payload area). Known inputs and the
expected result of the full set (00 to 19):

| MAIN OS | SHA-256 of the input | SHA-256 of the result |
|---|---|---|
| official Model:Cycles OS 1.13 | `cc99d4f0175d34d1e91d046e6ec85a5e8ab58ab9edbb3c24406acd48cb99ee98` | `2d3a8276c2f2cc416dabfb060a8defcff72c8ec09dc69b6c858850d51ac213d4` |
| Cycles OS for Model:Samples (cross-flash) | `b6fbc48f7d7d07cecae3859e07270fa2298f393e8afa2643144bdb4efc317aad` | `51ab3bd08c5a9cc9543537e05eb725ebe2b70a719d73300cf8c0fb6e6657239b` |

## Rebuilding the patches and running the tests

You do not need this to build the firmware.

```sh
pip install unicorn capstone numpy pillow
git clone https://github.com/18nelli18/Modded-Cycles   # in the repository root: free sprite masks, emulator rigs
# extract section 3 of the official Model:Cycles OS 1.13, e.g. with elektron-firmware-tool:
elektron-firmware-tool -i model-cycles_OS1.13.syx -d 3 -o base
python3 src/regen.py base/section_3_MAIN_OS.bin       # runs every generator, compares with patches/
python3 tests/run_all.py base/section_3_MAIN_OS.bin   # runs every emulator test (takes a while)
```

`regen.py` must print `ok` for all 20 patches. That shows the published bytes come from the sources in `src/` and
the groove tables in `grooves/grooves.json`. `run_all.py` must end with `all tests ok`.
