# Third-party tools (unchanged copies)

So that the build works on its own, even if the original repositories change or disappear, these files are copied here
**unchanged** from their projects. Both are MIT licensed; their license files are next to them. They contain no
Elektron code or firmware bytes (only SHA-256 checksums of the official files).

- **drumkilla/elektron-model-tweaks** (https://github.com/drumkilla/elektron-model-tweaks, MIT, Copyright (c) 2026
  drumkilla): `mtlib/` (SysEx transport, container, aPLib; based on elektron-firmware-tool by Marcel Bierling, MIT) and
  `tweak.py` (`tools/build.py` uses its `read_firmware` and `verify`).
- **18nelli18/Modded-Cycles** (https://github.com/18nelli18/Modded-Cycles, MIT, Copyright (c) 2026 18nelli18 and
  Modded-Cycles contributors): `aplib_grow.py` (compresses the MAIN OS after the core has appended its payload area) and
  `crossflash.py` (the Cycles OS for a Model:Samples, `python3 tools/vendor/crossflash.py ...`; comments in French).

| File | From | SHA-256 (first 16) |
|---|---|---|
| `mtlib/__init__.py` | `drumkilla/elektron-model-tweaks/mtlib/__init__.py` | `e3b0c44298fc1c14` |
| `mtlib/aplib.py` | `drumkilla/elektron-model-tweaks/mtlib/aplib.py` | `3c886017d85839c7` |
| `mtlib/container.py` | `drumkilla/elektron-model-tweaks/mtlib/container.py` | `fd5eca79319cf5a3` |
| `mtlib/syx.py` | `drumkilla/elektron-model-tweaks/mtlib/syx.py` | `8f223c2155fb45ee` |
| `mtlib/LICENSE` | `drumkilla/elektron-model-tweaks/LICENSE` | `2b2390f7ab2be71d` |
| `mtlib/LICENSE-elektron-firmware-tool` | `18nelli18/Modded-Cycles/tools/mtlib/LICENSE-elektron-firmware-tool` | `35ae461c853f9849` |
| `tweak.py` | `drumkilla/elektron-model-tweaks/tweak.py` | `4b3add1611a95c6d` |
| `LICENSE-elektron-model-tweaks` | `drumkilla/elektron-model-tweaks/LICENSE` | `2b2390f7ab2be71d` |
| `aplib_grow.py` | `18nelli18/Modded-Cycles/tools/aplib_grow.py` | `5fe263da1959ef1e` |
| `crossflash.py` | `18nelli18/Modded-Cycles/tools/crossflash.py` | `88403be43f4a02b8` |
| `LICENSE-Modded-Cycles` | `18nelli18/Modded-Cycles/LICENSE` | `909b87820909a5c3` |
