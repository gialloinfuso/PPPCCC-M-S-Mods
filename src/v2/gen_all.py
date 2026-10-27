#!/usr/bin/env python3
"""Alle v2-Patches im Entwicklungsformat erzeugen (out/NN-name.json) und gemeinsam pruefen (Ueberlappung, old)."""
import json, sys, pathlib, importlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import common as C
import g2_core, g2_reverbfx, g2_delayfx, g2_strum, g2_loadmeter, g2_groove, g2_control, g2_trigselect, g2_fill2
import gen_solo, gen_livemute, gen_holdmute_113, gen_delaynotes_113

OUT = pathlib.Path(__file__).parent / 'out'


def independents(img):
    res = []
    for mod, num, pid in ((gen_solo, 1, 'mute-solo'), (gen_livemute, 2, 'live-mute'), (gen_holdmute_113, 3, 'hold-mute'),
                          (gen_delaynotes_113, 4, 'delay-notes')):
        r = mod.tweak(img); t = r[0] if isinstance(r, tuple) else r
        assert t['id'] == pid, t['id']; t['order'] = num
        res.append(t)
    return res


def all_patches(img):
    ps = independents(img)
    ps.append(g2_core.tweak(img))
    for mod in (g2_reverbfx, g2_delayfx, g2_strum, g2_loadmeter, g2_groove, g2_control, g2_trigselect, g2_fill2):
        ps.append(mod.tweak(img))
    return sorted(ps, key=lambda t: t['order'])


def check_combo(img, ps, lm=None):
    """Alle zusammen anwenden; Ueberlappung nur mit 'requires'. Rueckgabe: Image."""
    b = bytearray(img); used = []
    seq = ([lm] if lm else []) + ps
    for t in seq:
        for w in t['writes']:
            o, n = bytes.fromhex(w['old']), bytes.fromhex(w['new']); off = w['off']; end = off + max(len(o), len(n))
            for a0, b0, who in used:
                assert end <= a0 or off >= b0 or who in t.get('requires', []), (t['id'], hex(off + C.BASE), who)
            assert b[off:off + len(o)] == o, (t['id'], hex(off + C.BASE))
            b[off:off + len(n)] = n; used.append((off, end, t['id']))
    return bytes(b)


if __name__ == "__main__":
    img = C.stock()
    OUT.mkdir(exist_ok=True)
    ps = [C.annotate(t) for t in all_patches(img)]
    lm = json.load(open(C.ROOT / 'elektron-model-tweaks/tweaks/model-cycles_OS1.13/01-latching-mute.json'))
    full = check_combo(img, ps, lm)
    for t in ps:
        C.save(t, OUT / f"{t['order']:02d}-{t['id']}.json")
        print(f"{t['order']:02d} {t['id']:12s} {len(t['writes']):3d} writes  requires {t.get('requires', [])}")
    (OUT / 'full_section3.bin').write_bytes(full)
    print('ok, Gesamt-Image', len(full))
