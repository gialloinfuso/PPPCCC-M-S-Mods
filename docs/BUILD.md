# Building the firmware

No firmware is distributed here. You build it from your own copy of the official Model:Cycles OS 1.13.
`tools/build.py` refuses any other input. It checks every write against the original bytes (SHA-256), fills the
few placeholders for original instructions that hooks move from your own file (SHA-256 checked too) and checks the
complete MAIN OS against the published result. It unpacks every output file again and re-checks it: packet
checksums, content checksum, section sums, HMAC, and that the MAIN OS is identical to the patched image.

## What you need

- Python 3.8 or newer (no extra packages for building)
- `model-cycles_OS1.13.syx`, the official file from elektron.se
  (SHA-256 `44fe586269631a0ca7da25a3383fc6733c314809505fc3cc52f1e0ed9800640c`)
- a checkout of [drumkilla/elektron-model-tweaks](https://github.com/drumkilla/elektron-model-tweaks). It provides
  `mtlib` (container, compression, signatures) and the latching-mute patch that patch 01 needs.

```sh
git clone https://github.com/gialloinfuso/PPPCCC-M-S-Mods
cd PPPCCC-M-S-Mods
git clone https://github.com/drumkilla/elektron-model-tweaks
```

## Model:Cycles

```sh
python3 tools/build.py --tweaks elektron-model-tweaks --in model-cycles_OS1.13.syx --out cycles-mods
```

This writes `cycles-mods_cyc-os.syx`. Send it like any OS update: in the start-up menu (hold **FUNC** while switching
on, then OS UPGRADE) or from the running OS, with Elektron Transfer or another SysEx tool.

> Not yet tested on a real Model:Cycles. The MAIN OS is the same image that runs on my Model:Samples, apart from
> the 32 bytes of the update key, which no patch touches.

## Model:Samples

A Model:Samples needs the Cycles OS in a Model:Samples container. That container includes a change to the update key,
so the Samples OS can still be flashed back over USB. Modded-Cycles makes this file from your two official files:

```sh
git clone https://github.com/18nelli18/Modded-Cycles
python3 Modded-Cycles/tools/crossflash.py --cycles model-cycles_OS1.13.syx \
        --samples model-samples_OS1.13.syx --to samples -o cycles-for-samples.syx
python3 tools/build.py --tweaks elektron-model-tweaks --in cycles-for-samples.syx --out cycles-mods --smp
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
name or as a path:

```sh
python3 tools/build.py --tweaks elektron-model-tweaks --in model-cycles_OS1.13.syx --out my-mods \
        live-mute hold-mute reverb-fx groove trig-select
```

| Patch | id | Needs |
|---|---|---|
| 00 | `core` | – |
| 01 | `mute-solo` | drumkilla's latching mute (`build.py` always applies it) |
| 02 | `live-mute` | – |
| 03 | `hold-mute` | – |
| 04 | `delay-notes` | – |
| 05 | `reverb-fx` | core |
| 06 | `delay-fx` | core (uses the exact triplets of 04 when it is installed) |
| 07 | `strum` | core |
| 08 | `load-meter` | core |
| 09 | `groove` | core (humanize with TRACK follows 10 when it is installed) |
| 10 | `control-mode` | core |
| 11 | `trig-select` | core (absolute mode follows 10 when it is installed) |

The core is added automatically when a chosen patch needs it. Every combination can be applied together; the tool
checks this and stops on any collision. The published full-set checksum is only checked when you build the full set.
Single writes are always checked.

## Working with a MAIN OS image directly

If you extract section 3 yourself (for example with elektron-firmware-tool), `tools/apply_patches.py` patches the
raw image:

```sh
python3 tools/apply_patches.py section_3_MAIN_OS.bin patched.bin \
        --latching-mute elektron-model-tweaks/tweaks/model-cycles_OS1.13/01-latching-mute.json --all
python3 tools/apply_patches.py section_3_MAIN_OS.bin patched.bin reverb-fx trig-select   # core is added
```

Known inputs and the expected result of the full set (latching mute + 00 to 11):

| MAIN OS | SHA-256 of the input | SHA-256 of the result |
|---|---|---|
| official Model:Cycles OS 1.13 | `cc99d4f0175d34d1e91d046e6ec85a5e8ab58ab9edbb3c24406acd48cb99ee98` | `86b3462ebfe4c1e47fd773cb6073b0f80dbe6faee33487440b67a72c8106f40d` |
| Cycles OS for Model:Samples (cross-flash) | `b6fbc48f7d7d07cecae3859e07270fa2298f393e8afa2643144bdb4efc317aad` | `50bc19330ae1a9edc079c785982e40c7fd76964912980cfff49a78b7d567c3a4` |

## Rebuilding the patches and running the tests

You do not need this to build the firmware.

```sh
pip install unicorn capstone pillow
git clone https://github.com/18nelli18/Modded-Cycles          # in the repository root
git clone https://github.com/drumkilla/elektron-model-tweaks  # (already there if you built the firmware)
# extract section 3 of the official Model:Cycles OS 1.13, e.g. with elektron-firmware-tool:
elektron-firmware-tool -i model-cycles_OS1.13.syx -d 3 -o base
python3 src/regen.py base/section_3_MAIN_OS.bin       # runs every generator, compares with patches/
python3 tests/run_all.py base/section_3_MAIN_OS.bin   # runs every emulator test
```

`regen.py` must print `ok` for all 13 patches. That shows the published bytes come from the sources in `src/` and
the groove tables in `grooves/grooves.json`. `run_all.py` must end with `all tests ok`.
