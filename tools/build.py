#!/usr/bin/env python3
"""Build a modded .syx from your own official firmware file.

usage:
  python3 tools/build.py --tweaks <elektron-model-tweaks checkout> --in <firmware.syx> --out <name> [--smp] [patch ...]

  --tweaks   a checkout of https://github.com/drumkilla/elektron-model-tweaks. Its mtlib (MIT) unpacks and
             repacks the firmware container, and its tweaks/model-cycles_OS1.13/01-latching-mute.json is
             applied first (01-mute-solo needs it).
  --in       either the official model-cycles_OS1.13.syx (for a Model:Cycles), or the Cycles OS for a
             Model:Samples made with Modded-Cycles' tools/crossflash.py --to samples (see docs/BUILD.md).
  --out      output name, without extension.
  --smp      Samples input only: also write <name>_smp-os.syx (Model:Samples container, for the start-up menu).
  patch      the patches to apply: a file, a file name (05-reverb-fx) or an id (reverb-fx); default: all patches in
             patches/manifest.json. Patches a chosen one requires (e.g. 00-core) are added automatically.

Output:
  Model:Cycles input  -> <name>_cyc-os.syx (send it like any Model:Cycles OS update)
  Model:Samples input -> <name>_cyc-os.syx (for a Model:Samples that already runs a Cycles OS with the Samples
                         key, e.g. from Modded-Cycles), and with --smp also <name>_smp-os.syx.
Every output file is unpacked again and checked (packet checksums, content checksum, section sums, HMAC,
section 3 identical to the patched image).
"""
import argparse
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import apply_patches  # noqa: E402

CYCLES = 0x11


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument('--tweaks', required=True)
    ap.add_argument('--in', dest='src', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--smp', action='store_true')
    ap.add_argument('patches', nargs='*')
    a = ap.parse_args()

    sys.path.insert(0, os.path.abspath(a.tweaks))
    try:
        import tweak as mt      # drumkilla's tweak.py: read_firmware, build, verify
        from mtlib import aplib, container
        from mtlib.syx import unwrap, wrap, BYTES_PER_MSG
    except ImportError:
        sys.exit("!! --tweaks must point to a checkout of drumkilla/elektron-model-tweaks")

    fw = mt.read_firmware(a.src)
    m = apply_patches.manifest()
    base = hashlib.sha256(fw['main_os']).hexdigest()
    bases = {b['section3_sha256']: b for b in m['bases']}
    if base not in bases:
        sys.exit("!! this MAIN OS is neither the official Model:Cycles OS 1.13 nor its Model:Samples cross-flash")
    b = bases[base]
    print(f"input: {b['name']}")

    lm = os.path.join(a.tweaks, 'tweaks', 'model-cycles_OS1.13', '01-latching-mute.json')
    paths = [lm] + (apply_patches.resolve(a.patches) if a.patches else apply_patches.all_patches())
    patches = [apply_patches.load(p) for p in paths]
    try:
        img = apply_patches.apply(fw['main_os'], patches)
    except ValueError as e:
        sys.exit(f"!! {e}")
    for t in sorted(patches, key=apply_patches.order_key):
        print(f"  {t['id']:16s} {len(t['writes']):3d} writes")
    res = hashlib.sha256(img).hexdigest()
    if sorted(t['id'] for t in patches) == sorted(m['full_set']):
        assert res == b['full_set_result_sha256'], "result differs from the published SHA-256"
        print("  section 3 matches the published SHA-256 of the full set")

    dirty = bytearray(len(img))
    for i, (x, y) in enumerate(zip(fw['main_os'], img)):
        if x != y:
            dirty[i] = 1
    smp = mt.build(fw, img, dirty)               # same container and product as the input
    outs = []
    if b['target'] == 'cycles':
        outs.append((f"{a.out}_cyc-os.syx", smp))
    else:
        stream, info = unwrap(smp)
        outs.append((f"{a.out}_cyc-os.syx", wrap(stream, CYCLES, info['start_seq'])))
        if a.smp:
            outs.append((f"{a.out}_smp-os.syx", smp))
    for name, raw in outs:
        open(name, 'wb').write(raw)
        ok = mt.verify(name, quiet=True)
        chk = mt.read_firmware(name)['main_os'] == img
        if not (ok and chk):
            os.remove(name)
            sys.exit(f"!! {name} failed the check, removed")
        print(f"ok: {name}  sha256 {hashlib.sha256(raw).hexdigest()}")


if __name__ == '__main__':
    main()
