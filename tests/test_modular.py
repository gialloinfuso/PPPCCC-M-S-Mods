# Modularitaet (v2): jede Kombination der Core-Mods laesst sich anwenden (nur Ueberlappung mit 'core'), jede Mod allein mit
# dem Core funktioniert (eigene Geste wird behandelt, fremde Gesten gehen unveraendert durch), unabhaengige Mods (01..04, 12)
# ohne Core.
import itertools, struct
from rig import *

MODS = ['reverb-fx', 'delay-fx', 'strum', 'load-meter', 'groove', 'control-mode', 'trig-select', 'track-filter', 'lfo-amount', 'sampler', 'pad-mode']   # smp40: + pad-mode
GEST = {'reverb-fx': [(14, {2})], 'delay-fx': [(15, {2})], 'strum': [], 'load-meter': [], 'groove': [(12, {1})],
        'control-mode': [], 'trig-select': [], 'track-filter': [], 'lfo-amount': [], 'sampler': [], 'pad-mode': []}   # control-mode: Encoder-Slot merkt nur SETTINGS-Drehungen, behandelt nichts
EXTRA = {'delay-fx': [(8, {1})], 'groove': [(12, {13}), (12, {5})]}


def combo_ok(ids):
    b = bytearray(apply(STOCK, LATCH)); used = []
    for pid in sorted(ids, key=lambda i: V2P[i]['order']):
        t = V2P[pid]
        for w in t['writes']:
            o, n = bytes.fromhex(w['old']), bytes.fromhex(w['new']); off = w['off']; end = off + max(len(o), len(n))
            for a0, b0, who in used:
                if not (end <= a0 or off >= b0 or who in t.get('requires', [])): return False, f'{pid} ueberlappt {who}'
            if b[off:off + len(o)] != o: return False, f'{pid}: old passt nicht bei {off + BASE:#x}'
            b[off:off + len(n)] = n; used.append((off, end, pid))
    return True, ''

bad = []
for k in range(len(MODS) + 1):
    for c in itertools.combinations(MODS, k):
        for f2 in ([], ['fill2']):
            okc, why = combo_ok(['core', 'mute-solo', 'live-mute', 'hold-mute', 'delay-notes'] + list(c) + f2)
            if not okc: bad.append((c, why))
            okc, why = combo_ok(['core'] + list(c) + f2)
            if not okc: bad.append((c, why))
chk('alle %d Kombinationen' % (2 ** len(MODS)) + ' der Core-Mods (mit und ohne 01..04, mit und ohne 12) anwendbar, Ueberlappung nur mit dem Core %s'
    % bad[:2], not bad)
for ind in (['live-mute'], ['hold-mute'], ['delay-notes'], ['mute-solo'], ['fill2'], ['direct-jump'],
            ['multiline-browser'], ['browser-scroll'], ['level-pan-values'], ['multiline-browser', 'browser-scroll', 'level-pan-values'],
            ['mute-solo', 'live-mute', 'hold-mute', 'delay-notes', 'fill2', 'direct-jump'], ['param-undo'],
            ['mute-solo', 'live-mute', 'hold-mute', 'delay-notes', 'fill2', 'direct-jump', 'param-undo']):
    okc, why = combo_ok(ind); chk('unabhaengig ohne Core: %s %s' % (ind, why), okc)
UI3 = ['multiline-browser', 'browser-scroll', 'level-pan-values', 'browser-keys']   # Teile des Core (smp40: + browser-keys)
bad = []
for k in range(len(UI3) + 1):
    for c in itertools.combinations(UI3, k):
        for base in (['core'], ['core'] + MODS, ['mute-solo', 'live-mute', 'hold-mute', 'delay-notes', 'fill2', 'direct-jump', 'param-undo'], V2_IDS):
            okc, why = combo_ok(sorted(set(base) | set(c)))
            if not okc: bad.append((c, why))
chk('Patches 17-19 in jeder Teilmenge mit Core, allen Core-Mods, 01..04/12/13 und allem anwendbar %s' % bad[:2], not bad)
for m in MODS:
    chk('%s verlangt den Core (requires)' % m, V2P[m].get('requires') == ['core'])
# smp14: strings (8. Maschine) baut auf dem Sampler auf: mit jeder Teilmenge der Core-Mods, die den Sampler enthaelt
chk('strings verlangt Core und Sampler (requires)', V2P['strings'].get('requires') == ['core', 'sampler'])
bad = []
for k in range(len(MODS)):
    for c in itertools.combinations([x for x in MODS if x != 'sampler'], k):
        for f2 in ([], ['fill2']):
            okc, why = combo_ok(['core', 'sampler', 'strings'] + list(c) + f2)
            if not okc: bad.append((c, why))
chk('strings mit Core + Sampler und allen %d Teilmengen der anderen Core-Mods anwendbar %s' % (2 ** (len(MODS) - 1), bad[:2]), not bad)
okc, why = combo_ok(['core', 'strings'])
chk('strings ohne Sampler: nicht anwendbar (%s)' % why, not okc)
chk('mono verlangt Core, Sampler und Strings (requires)', V2P['mono'].get('requires') == ['core', 'sampler', 'strings'])
bad = []
for k in range(len(MODS)):
    for c in itertools.combinations([x for x in MODS if x != 'sampler'], k):
        okc, why = combo_ok(['core', 'sampler', 'strings', 'mono'] + list(c))
        if not okc: bad.append((c, why))
chk('mono mit Core + Sampler + Strings und allen %d Teilmengen der anderen Core-Mods anwendbar %s' % (2 ** (len(MODS) - 1), bad[:2]), not bad)
okc, why = combo_ok(['core', 'sampler', 'mono'])
chk('mono ohne Strings: nicht anwendbar (%s)' % why, not okc)

# ---- jede Mod allein mit dem Core
for m in MODS:
    e = Emu(v2_image(['core', m])); e.w32(C.TIMER, 1000); e.u.mem_write(C.ACC, bytes(12))
    e.u.mem_write(e.hdr(40), bytes(24))
    own = GEST[m] + EXTRA.get(m, [])
    if m == 'groove':                                    # ausgewaehlter Track (Humanize)
        def sel(u, a_, z, _):
            sp = u.reg_read(mk.UC_M68K_REG_A7); u.reg_write(mk.UC_M68K_REG_D0, 1 if a_ == C.SEL_C else 0x4F050000)
            u.reg_write(mk.UC_M68K_REG_PC, e.r32(sp)); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
        for t in (C.SEL_A, C.SEL_B, C.SEL_C): e.u.hook_add(UC_HOOK_CODE, sel, begin=t, end=t)
    handled = all((lambda r: (r['skipped'] or r['passed'] == 0) and r['sp'] and r['regs'])(e.enc(enc, 1, held)) for enc, held in own)
    foreign = [(enc, held) for x in MODS if x != m for enc, held in GEST[x] + EXTRA.get(x, []) if (enc, held) not in own]
    passed = all((lambda r: r['passed'] == 1 and r['sp'] and r['regs'] and not r['consumed'])(e.enc(enc, 1, held)) for enc, held in foreign)
    hdr = bytes(e.u.mem_read(e.hdr(40), 24))
    chk('%-10s allein mit Core: eigene Gesten behandelt, %d fremde Gesten unveraendert durch, Pattern-Bytes %s' %
        (m, len(foreign), hdr.hex()[:34]), handled and passed)
# ---- smp40 (Pip: Flasher mit freier Auswahl): die echten Patch-Dateien out/NN-*.json, wie sie ein Flasher anwenden wuerde
# (ohne latching-mute-Datei; requires automatisch dazu). Ueberlappung / old ist eine Eigenschaft von Paaren: gehen jede Mod
# allein und jedes Paar (je mit Abhaengigkeiten), geht jede Auswahl.
OUTP = {}
for f in sorted((V2 / 'out').glob('[0-9][0-9]-*.json')):
    t = json.load(open(f)); OUTP[t['id']] = t
def closure(ids):
    out, todo = [], list(ids)
    while todo:
        i = todo.pop()
        if i in out: continue
        out.append(i); todo += OUTP[i].get('requires', [])
    return sorted(out, key=lambda i: OUTP[i]['order'])
def apply_out(ids):
    b = bytearray(STOCK); used = []
    for pid in closure(ids):
        t = OUTP[pid]
        for w in t['writes']:
            o, n = bytes.fromhex(w['old']), bytes.fromhex(w['new']); off = w['off']; end = off + max(len(o), len(n))
            for a0, b0, who in used:
                if not (end <= a0 or off >= b0 or who in t.get('requires', [])): return f'{pid} ueberlappt {who} bei {off + BASE:#x}'
            if b[off:off + len(o)] != o: return f'{pid}: old passt nicht bei {off + BASE:#x}'
            b[off:off + len(n)] = n; used.append((off, end, pid))
    return None
ids = sorted(OUTP, key=lambda i: OUTP[i]['order'])
bad = [(a, b, why) for a, b in itertools.combinations_with_replacement(ids, 2) for why in [apply_out([a, b])] if why]
chk('Patch-Dateien (%d, Nummern %s): jede allein und alle %d Paare mit Abhaengigkeiten anwendbar, ohne latching-mute-Datei %s'
    % (len(ids), ''.join('%02d' % OUTP[i]['order'] for i in ids[:3]) + '..', len(ids) * (len(ids) + 1) // 2, bad[:2]),
    not bad and [OUTP[i]['order'] for i in ids] == list(range(len(ids))))
chk('Abhaengigkeiten: Core-Mods verlangen nur den Core; Vlvt + Grit, Monom + Grit + Vlvt; 01-03, 11, 14, 18 frei %s'
    % {i: OUTP[i].get('requires', []) for i in ids if OUTP[i].get('requires')},
    all(OUTP[i].get('requires', []) in ([], ['core']) for i in ids if i not in ('strings', 'mono'))
    and OUTP['strings']['requires'] == ['core', 'sampler'] and OUTP['mono']['requires'] == ['core', 'sampler', 'strings']
    and not any(OUTP[i].get('requires') for i in ('mute-solo', 'hold-mute', 'delay-notes', 'fill2', 'direct-jump', 'param-undo')))
done()
