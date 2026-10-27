#!/usr/bin/env python3
"""Apply patches to a decompressed Model:Cycles OS 1.13 MAIN OS (section 3).

usage:
  python3 tools/apply_patches.py <section_3_MAIN_OS.bin> <out.bin> [--latching-mute <01-latching-mute.json>] <patch> ...
  python3 tools/apply_patches.py <section_3_MAIN_OS.bin> <out.bin> --latching-mute <01-latching-mute.json> --all

A <patch> is a file (patches/05-reverb-fx.json), a file name (05-reverb-fx) or an id (reverb-fx). Patches that a chosen
patch requires from this repository (e.g. core) are added automatically.

Two patch formats are accepted:
  * this repository's format: every write carries "len" + "old_sha256" (the original bytes are not published).
    Where a patch needs original firmware bytes inside its own code (the few instructions a hook moves out of the
    firmware, see "from_original"), "new" holds zeros there; they are copied from your input file and checked
    against a SHA-256, so no Elektron bytes are published;
  * drumkilla's elektron-model-tweaks format: every write carries the original bytes in "old"
    (needed for 01-latching-mute.json, which 01-mute-solo requires).

Every write is checked against the input before anything is changed, patches are applied in "order" (latching mute first),
"requires" must be met, writes may only overlap writes of a required patch, and the 32 bytes of the
update key at 0x401296b2 (the Model:Samples key of a cross-flash base) are never touched.
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PATCH_DIR = os.path.join(HERE, '..', 'patches')
VA0 = 0x40000400
KEY_OFF = 0x401296B2 - VA0


def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def manifest():
    return load(os.path.join(PATCH_DIR, 'manifest.json'))


def all_patches():
    return [os.path.join(PATCH_DIR, f) for f in manifest()['patches']]


def find(name):
    """Path of a patch given as path, file name (with or without .json) or id."""
    if os.path.isfile(name):
        return name
    for f in manifest()['patches']:
        p = os.path.join(PATCH_DIR, f)
        if name in (f, f[:-5], f[3:-5]) or load(p)['id'] == name:
            return p
    sys.exit(f"!! unknown patch: {name}")


def resolve(names):
    """Paths for the given names plus everything they require from this repository, in apply order."""
    by_id = {load(os.path.join(PATCH_DIR, f))['id']: os.path.join(PATCH_DIR, f) for f in manifest()['patches']}
    paths = [find(n) for n in names]
    have = {load(p)['id'] for p in paths}
    todo = list(paths)
    while todo:
        for r in load(todo.pop()).get('requires', []):
            if r not in have and r in by_id:
                print(f"  + {r} (required by the chosen patches)")
                have.add(r)
                paths.append(by_id[r])
                todo.append(by_id[r])
    return sorted(set(paths), key=lambda p: order_key(load(p)))


def order_key(t):
    """Apply order: drumkilla's latching mute first, then this repository's patches by "order"."""
    return (0, 0) if t['id'] == 'latching-mute' else (1, t['order'])


def sha256(b):
    return hashlib.sha256(bytes(b)).hexdigest()


def to_public(w):
    """Development write {off, old, new[, orig]} -> published write: the original bytes only as length + SHA-256; bytes
    of "new" that are original firmware bytes (orig = [[at, source offset, length], ...]) become zeros and are listed in
    "from_original". Used by the export and by src/regen.py."""
    old, new = bytes.fromhex(w['old']), bytearray.fromhex(w['new'])
    fo = []
    for at, src, n in w.get('orig', []):
        fo.append({'at': at, 'off': src, 'va': f"{src + VA0:#010x}", 'len': n, 'sha256': sha256(new[at:at + n])})
        new[at:at + n] = bytes(n)
    out = {'off': w['off'], 'va': f"{w['off'] + VA0:#010x}", 'len': len(old), 'old_sha256': sha256(old), 'new': new.hex()}
    if fo:
        out['from_original'] = fo
    return out


def new_bytes(w, src, pid):
    """The bytes a write puts in place; "from_original" parts are copied from the unpatched input src (SHA-256 checked)."""
    new = bytearray.fromhex(w['new'])
    for f in w.get('from_original', []):
        b = src[f['off']:f['off'] + f['len']]
        if sha256(b) != f['sha256']:
            raise ValueError(f"{pid}: unexpected original bytes at {f['off'] + VA0:#010x} - wrong base OS")
        new[f['at']:f['at'] + f['len']] = b
    return bytes(new)


def apply(img, patches):
    """img: bytes of section 3 (unpatched). patches: list of patch dicts. Returns the patched bytes; raises ValueError."""
    src = bytes(img)
    img = bytearray(img)
    patches = sorted(patches, key=order_key)
    have, used = set(), []
    for t in patches:
        pid = t['id']
        missing = [r for r in t.get('requires', []) if r not in have]
        if missing:
            raise ValueError(f"{pid}: requires {', '.join(missing)} (apply it too)")
        bad = [c for c in t.get('conflicts', []) if c in have]
        if bad:
            raise ValueError(f"{pid}: conflicts with {', '.join(bad)}")
        for w in t['writes']:
            off, new = w['off'], new_bytes(w, src, pid)
            if 'old' in w:
                old = bytes.fromhex(w['old'])
                ok = bytes(img[off:off + len(old)]) == old
                n = max(len(old), len(new))
            else:
                n = w['len']
                ok = hashlib.sha256(img[off:off + n]).hexdigest() == w['old_sha256'] and len(new) == n
            if not ok:
                raise ValueError(f"{pid}: unexpected bytes at {off + VA0:#010x} - wrong base OS, "
                                 "already patched, or a required patch is missing")
            end = off + n
            if off < KEY_OFF + 32 and end > KEY_OFF:
                raise ValueError(f"{pid}: would touch the update key")
            for a, b, who in used:
                if not (end <= a or off >= b or who in t.get('requires', [])):
                    raise ValueError(f"{pid}: write at {off + VA0:#010x} collides with {who}")
            img[off:off + len(new)] = new
            used.append((off, end, pid))
        have.add(pid)
    return bytes(img)


def parse_args(argv):
    if len(argv) < 3:
        sys.exit(__doc__)
    src, dst, rest = argv[0], argv[1], argv[2:]
    paths, lm = [], None
    i = 0
    while i < len(rest):
        if rest[i] == '--latching-mute':
            lm = rest[i + 1]
            i += 2
        elif rest[i] == '--all':
            paths += all_patches()
            i += 1
        else:
            paths.append(rest[i])
            i += 1
    paths = resolve(paths)
    if lm:
        paths.insert(0, lm)
    return src, dst, paths


def main():
    src, dst, paths = parse_args(sys.argv[1:])
    img = open(src, 'rb').read()
    m = manifest()
    base = hashlib.sha256(img).hexdigest()
    known = {b['section3_sha256']: b['name'] for b in m['bases']}
    print(f"base: {known.get(base, 'unknown MAIN OS (every write is still checked)')}")
    patches = [load(p) for p in paths]
    try:
        out = apply(img, patches)
    except ValueError as e:
        sys.exit(f"!! {e}. Nothing written.")
    for t in sorted(patches, key=order_key):
        print(f"  {t['id']:16s} {len(t['writes']):3d} writes")
    res = hashlib.sha256(out).hexdigest()
    ids = sorted(t['id'] for t in patches)
    for b in m['bases']:
        if b['section3_sha256'] == base and ids == sorted(m['full_set']):
            if res != b['full_set_result_sha256']:
                sys.exit("!! the result does not match the published SHA-256. Nothing written.")
            print("  result matches the published SHA-256 of the full set")
    open(dst, 'wb').write(out)
    print(f"ok: {dst}  sha256 {res}")


if __name__ == '__main__':
    main()
