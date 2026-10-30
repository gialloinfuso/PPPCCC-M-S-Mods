# Third-party notices

- **elektron-model-tweaks** by drumkilla (https://github.com/drumkilla/elektron-model-tweaks), MIT.
  - The **latching mute** patch (`tweaks/model-cycles_OS1.13/01-latching-mute.json`) is drumkilla's work. Patch 01 (solo)
    builds on it, and `tools/build.py` applies it first.
  - `tools/build.py` imports drumkilla's `mtlib` and `tweak.py` from your checkout, to unpack, repack and check the
    firmware container.
  - Neither file is copied into this repository.
- **Modded-Cycles** by 18nelli18 and contributors (https://github.com/18nelli18/Modded-Cycles), MIT.
  - Firmware research notes (OS 1.13 addresses, the chord engine, the pattern header, the audio load measurement;
    for 13 track-filter the audio hook after Volume + Distortion, the free descriptors 1–4 and their sound record bytes
    (notes/47); for 14 lfo-amount the LFO call and its depth word (notes/56)). The code of 13 and 14 is my own.
  - The method of reusing unused sprite masks as free code memory (`tools/sprites.py`).
  - The emulator rigs used by the tests (`tools/emu/mcengine.py`, `seqrig.py`, the exact EMAC emulation `emac.py`, the
    key-chain rig from `test_trig_hold.py`).
  - The cross-flash that runs the Cycles OS on a Model:Samples (`tools/crossflash.py --to samples`).
  - All of these are used from your own checkout and are not copied here.
- **elektron-firmware-tool** by Marcel Bierling (https://github.com/mischa85/elektron-firmware-tool), MIT. The firmware
  container format, which mtlib is based on. It was also used to extract and repack images during development.
- **Unicorn** and **Capstone** (GPL-2.0 / BSD). The emulator and disassembler used by the tests and generators. They are
  installed with pip and not included here.
- **Elektron:** Model:Cycles and Model:Samples are products of Elektron Music Machines. This project is not affiliated
  with or endorsed by Elektron. No Elektron firmware and no Elektron code is distributed here. The patch files contain
  only the new bytes and SHA-256 checksums of the bytes they replace. Where a patch's code needs original firmware
  bytes (instructions a hook moves), the patch file has a placeholder and a SHA-256; `tools/build.py` copies those
  bytes from your own firmware file.
