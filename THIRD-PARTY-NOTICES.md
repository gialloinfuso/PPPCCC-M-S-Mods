# Third-party notices

All code in this repository is my own. These projects made it possible:

- **elektron-model-tweaks** by drumkilla (https://github.com/drumkilla/elektron-model-tweaks), MIT.
  - The **latching mute** (part of patch 01) and the **scrolling browser names** (part of the core, patch 00) follow
    drumkilla's tweaks `01-latching-mute` and `03-browser-scroll`: same behaviour, same free memory areas, rebuilt here
    as own code (`src/v2/g2_latch.py`, `src/v2/g2_browserscroll.py`). `tests/test_latch.py` and
    `tests/test_browserscroll.py` compare them with drumkilla's tweaks when his repository is checked out.
  - `mtlib/` and `tweak.py` are included **unchanged** in `tools/vendor/` (with drumkilla's license and the license of
    elektron-firmware-tool, which mtlib is based on); `tools/build.py` uses them to unpack, repack and check the
    firmware container.
  - The flasher (`flasher/lib.js`) contains a JavaScript port of mtlib's container code (unpack, repack, checksums).
  - Pad mode (patch 19) plays a step the way drumkilla's trig-preview tweak does (idea; own code).
- **Modded-Cycles** by 18nelli18 and contributors (https://github.com/18nelli18/Modded-Cycles), MIT.
  - Firmware research notes (OS 1.13 addresses, the chord engine, the pattern header, the audio load measurement, the
    audio hook after Volume + Distortion, free descriptors and sound record bytes, the LFO call, the machine limits and
    the descriptor table). The code here is my own.
  - The **multi-line browser** and the **volume / pan numbers** of the core are ports of Modded-Cycles'
    `multiline-browser` (notes/40; idea and first addresses from a community script) and `level-pan-values`
    (notes/44; after the mod by djd_oz): same behaviour, values and pixels, rewritten in this repository's assembler.
  - The method of reusing unused sprite masks as free code memory (`tools/sprites.py`).
  - `tools/aplib_grow.py` (compresses the MAIN OS after the core has appended its payload area) and
    `tools/crossflash.py` (the Cycles OS for a Model:Samples) are included **unchanged** in `tools/vendor/`, with the
    Modded-Cycles license. The flasher contains JavaScript ports of both (repack with growth, the cross-flash).
  - The emulator rigs used by the tests (`tools/emu/mcengine.py`, `seqrig.py`, the exact EMAC emulation `emac.py`, the
    key-chain rig).
  - The emulator rigs and the sprite-mask list are used by the tests and generators from a checkout of Modded-Cycles
    and are not copied here.
- **model27** by durchgemacht (https://durchgemacht.github.io/model27/), MIT, based on Modded-Cycles: the idea of the
  CONTROL ALL track selection (patch 09) and the loading guards of its sampler (patch 15). Own code.
- **Model-TG** by TinyGregAudio, MIT: the idea of the amp attack on FUNC + DECAY (core) and the method of the Transfer
  identity switch (patch 15). Own code.
- **string-machine** by jpcima (after the model by Peter Whiting), BSL-1.0: the inspiration for Vlvt (patch 16).
  No code was taken.
- **Dragonfly Reverbs** by Michael Willis, GPL-3.0: the style of Hall and Room (patch 04); Plate follows Jon Dattorro,
  "Effect Design, Part 1" (JAES 1997). No code was taken, only the kind of structure.
- **Vadim Zavalishin**, *The Art of VA Filter Design*: the state-variable filter of patch 12.
- **elektron-firmware-tool** by Marcel Bierling (https://github.com/mischa85/elektron-firmware-tool), MIT. The firmware
  container format, which mtlib is based on. It was also used to extract and repack images during development.
- **Unicorn**, **Capstone**, **NumPy**, **Pillow**. Used by the tests and generators; installed with pip and not
  included here.
- **Elektron:** Model:Cycles and Model:Samples are products of Elektron Music Machines. This project is not affiliated
  with or endorsed by Elektron. No Elektron firmware and no Elektron code is distributed here. The patch files contain
  only the new bytes and SHA-256 checksums of the bytes they replace. Where a patch's code needs original firmware
  bytes (instructions a hook moves), the patch file has a placeholder and a SHA-256; `tools/build.py` copies those
  bytes from your own firmware file.
