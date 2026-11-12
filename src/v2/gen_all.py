#!/usr/bin/env python3
"""Alle v2-Patches im Entwicklungsformat erzeugen (out/NN-name.json) und gemeinsam pruefen (Ueberlappung, old)."""
import json, sys, pathlib, importlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import common as C
import g2_core, g2_reverbfx, g2_delayfx, g2_strum, g2_loadmeter, g2_groove, g2_control, g2_trigselect, g2_fill2, g2_trackfilter, g2_lfoamount, g2_directjump, g2_sampler, g2_mlbrowser, g2_browserscroll, g2_levelpan, g2_strings, g2_mono, g2_browserkeys, g2_paramundo, g2_pad
import gen_solo, gen_livemute, gen_holdmute_113, gen_delaynotes_113, g2_latch

OUT = pathlib.Path(__file__).parent / 'out'


def independents(img):
    res = {}
    for mod, num, pid in ((gen_solo, 1, 'mute-solo'), (gen_livemute, 2, 'live-mute'), (gen_holdmute_113, 3, 'hold-mute'),
                          (gen_delaynotes_113, 4, 'delay-notes')):
        r = mod.tweak(img); t = r[0] if isinstance(r, tuple) else r
        assert t['id'] == pid, t['id']; t['order'] = num
        res[pid] = t
    res['mute-solo'] = mute_bundle(res['mute-solo'], res.pop('live-mute'), g2_latch.tweak(img))
    return list(res.values())


def mute_bundle(t, live, lm):
    """smp40 (Pip 11.11.2026): 01 mute-solo enthaelt latching-mute und live-mute; Writes tragen 'part' (Tests trennen sie
    wieder). v2.3 (12.11.): latching-mute ist eigener Code (g2_latch.py, Verhalten wie drumkillas Tweak, MIT)."""
    assert not live.get('requires'), live['id']
    t = dict(t)
    t['writes'] = ([dict(w, part='latching-mute') for w in lm['writes']] + t['writes']
                   + [dict(w, part='live-mute') for w in live['writes']])
    t['requires'] = [r for r in t.get('requires', []) if r != 'latching-mute']
    if not t['requires']:
        del t['requires']
    t['name'] = 'Mute: latching, solo, live notes'
    t['description'] = ["Hold TRK and tap FUNC: the mute mode latches (FUNC lights up); a short tap on FUNC alone leaves it.",
                        "In the latched mute mode: hold FUNC + track key = solo; again = previous mute state back.",
                        "Muted tracks also mute live notes (keys, MIDI in).",
                        "Latching mute: behaviour as in drumkilla's tweak (elektron-model-tweaks, MIT); own code.",
                        "Erzeugt von gen_solo.py, gen_livemute.py (v2/gen_all.py: mute_bundle)."]
    t['parts'] = [{'id': 'latching-mute', 'name': lm['name'], 'description': lm['description'], 'credit': 'idea: drumkilla (MIT)'},
                  {'id': 'live-mute', 'name': live['name'], 'description': live['description'], 'params': live.get('params', {})}]
    for k, v in live.get('symbols', {}).items():
        assert k not in t.setdefault('symbols', {}), k; t['symbols'][k] = v
    for k, v in lm['symbols'].items():
        t['symbols']['latch_' + k if k != 'latch_flag' else k] = v
    t['hooks'] = lm['hooks'] + t.get('hooks', []) + live.get('hooks', [])
    t['memory'] = lm['memory'] + t.get('memory', []) + live.get('memory', [])
    return t


def all_patches(img):
    ps = independents(img)
    ps.append(g2_core.tweak(img))
    for mod in (g2_reverbfx, g2_delayfx, g2_strum, g2_loadmeter, g2_groove, g2_control, g2_trigselect, g2_fill2, g2_trackfilter, g2_lfoamount, g2_directjump, g2_sampler, g2_mlbrowser, g2_browserscroll, g2_levelpan, g2_strings, g2_mono, g2_browserkeys, g2_paramundo, g2_pad):
        ps.append(mod.tweak(img))
    return sorted(ps, key=lambda t: t['order'])


# smp8 (Pip 02.11.2026): mehrzeiliger Browser, scrollende Namen, Volume / Pan als Zahlen sind keine eigenen Patches,
# sondern Teil des Core (eigene Generatoren bleiben; die Writes tragen 'part' fuer Tests und Doku).
FOLD = ('multiline-browser', 'browser-scroll', 'level-pan-values', 'browser-keys')   # smp40: browser-keys (Pip) auch im Core


def fold_core(ps):
    core = next(t for t in ps if t['id'] == 'core')
    core.setdefault('parts', [])
    for t in [t for t in ps if t['id'] in FOLD]:
        assert not t.get('requires'), t['id']
        for w in t['writes']:
            core['writes'].append(dict(w, part=t['id']))
        for k, v in t.get('symbols', {}).items():
            assert k not in core['symbols'], (t['id'], k); core['symbols'][k] = v
        core['hooks'] += t.get('hooks', []); core['memory'] += t.get('memory', [])
        core['parts'].append({'id': t['id'], 'name': t['name'], 'description': t['description'], 'params': t.get('params', {})})
        core['description'] = core['description'][:-1] + ['Includes: ' + t['name'] + ' - ' + t['description'][0]] + core['description'][-1:]
        ps.remove(t)
    return ps


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


# smp40 (Pip 11.11.2026): Nummern lueckenlos nach dem Zusammenlegen (live-mute in 01, browser-keys im Core)
ORDER = ['core', 'mute-solo', 'hold-mute', 'delay-notes', 'reverb-fx', 'delay-fx', 'strum', 'load-meter', 'groove', 'control-mode',
         'trig-select', 'fill2', 'track-filter', 'lfo-amount', 'direct-jump', 'sampler', 'strings', 'mono', 'param-undo', 'pad-mode']


def renumber(ps):
    assert sorted(t['id'] for t in ps) == sorted(ORDER), sorted(t['id'] for t in ps)
    for t in ps:
        t['order'] = ORDER.index(t['id'])
    return sorted(ps, key=lambda t: t['order'])


if __name__ == "__main__":
    img = C.stock()
    OUT.mkdir(exist_ok=True)
    ps = renumber(fold_core([C.annotate(t) for t in all_patches(img)]))
    for f in OUT.glob('[0-9][0-9]-*.json'):
        f.unlink()
    full = check_combo(img, ps)                      # smp40: latching-mute steckt in mute-solo
    for t in ps:
        C.save(t, OUT / f"{t['order']:02d}-{t['id']}.json")
        print(f"{t['order']:02d} {t['id']:12s} {len(t['writes']):3d} writes  requires {t.get('requires', [])}")
    (OUT / 'full_section3.bin').write_bytes(full)
    print('ok, Gesamt-Image', len(full))
