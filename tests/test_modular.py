# Modularitaet (v2): jede Kombination der Core-Mods laesst sich anwenden (nur Ueberlappung mit 'core'), jede Mod allein mit
# dem Core funktioniert (eigene Geste wird behandelt, fremde Gesten gehen unveraendert durch), unabhaengige Mods (01..04, 12)
# ohne Core.
import itertools, struct
from rig import *

MODS = ['reverb-fx', 'delay-fx', 'strum', 'load-meter', 'groove', 'control-mode', 'trig-select', 'track-filter', 'lfo-amount']
GEST = {'reverb-fx': [(14, {2})], 'delay-fx': [(15, {2})], 'strum': [(5, {13})], 'load-meter': [(9, {13})], 'groove': [(12, {1})],
        'control-mode': [], 'trig-select': [], 'track-filter': [], 'lfo-amount': []}   # control-mode: Encoder-Slot merkt nur SETTINGS-Drehungen, behandelt nichts
EXTRA = {'delay-fx': [(8, {13})], 'groove': [(12, {13}), (12, {5})]}


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
            ['mute-solo', 'live-mute', 'hold-mute', 'delay-notes', 'fill2', 'direct-jump']):
    okc, why = combo_ok(ind); chk('unabhaengig ohne Core: %s %s' % (ind, why), okc)
for m in MODS:
    chk('%s verlangt den Core (requires)' % m, V2P[m].get('requires') == ['core'])

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
done()
