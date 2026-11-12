#!/usr/bin/env python3
"""Build a modded .syx from your own official firmware file.

usage:
  python3 tools/build.py --in <firmware.syx> --out <name> [--smp] [patch ...]

Needs only Python 3. The container code comes with this repository (tools/vendor/, unchanged MIT copies:
drumkilla's mtlib and tweak.py to unpack, repack and check the firmware, Modded-Cycles' aplib_grow.py to compress the
MAIN OS after the core has appended its payload area).

  --in       either the official model-cycles_OS1.13.syx (for a Model:Cycles), or the Cycles OS for a
             Model:Samples made with Modded-Cycles' tools/crossflash.py --to samples (see docs/BUILD.md).
  --out      output name, without extension.
  --smp      Samples input only: also write <name>_smp-os.syx (Model:Samples container, for the start-up menu).
  patch      the patches to apply: a file, a file name (04-reverb-fx) or an id (reverb-fx); default: all patches in
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
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import apply_patches  # noqa: E402

CYCLES = 0x11


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument('--in', dest='src', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--smp', action='store_true')
    ap.add_argument('patches', nargs='*')
    a = ap.parse_args()

    sys.path.insert(0, os.path.join(HERE, 'vendor'))
    import tweak as mt          # drumkilla's tweak.py (MIT): read_firmware, verify
    from mtlib import container
    from mtlib.syx import unwrap, wrap, BYTES_PER_MSG
    import aplib_grow           # Modded-Cycles (MIT): aPLib repack of a MAIN OS that got longer

    fw = mt.read_firmware(a.src)
    m = apply_patches.manifest()
    base = hashlib.sha256(fw['main_os']).hexdigest()
    bases = {b['section3_sha256']: b for b in m['bases']}
    if base not in bases:
        sys.exit("!! this MAIN OS is neither the official Model:Cycles OS 1.13 nor its Model:Samples cross-flash")
    b = bases[base]
    print(f"input: {b['name']}")

    paths = apply_patches.resolve(a.patches) if a.patches else apply_patches.all_patches()
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

    n0 = len(fw['main_os'])
    dirty = bytearray(len(img))
    for i, (x, y) in enumerate(zip(fw['main_os'], img)):
        if x != y:
            dirty[i] = 1
    dirty[n0:] = b'\x01' * (len(img) - n0)
    # same container and product as the input; section 3 recompressed (changed and appended bytes)
    stream = aplib_grow.repack_grow(img, fw['ops'], dirty, n0)
    c = fw['cont']
    msg, expect = c['blob'][:-container.DIGEST_LEN], c['blob'][-container.DIGEST_LEN:]
    key = container.find_key(fw['plain'], msg, expect)
    if key is None:
        sys.exit("!! could not recover the container key from this firmware")
    blob = container.rebuild(c, {3: stream}, key)
    smp = wrap(container.build_stream(blob, BYTES_PER_MSG), fw['info']['product'], fw['info']['start_seq'])
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
