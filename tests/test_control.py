# control-mode (v2): CONTROL ALL relativ (Firmware) / absolut.
# 1. TRACK + Regler: Firmware-Schleife 0x4001d6e4 (Stock) gegen den Eintrag 0x40100588 des Images (CA), mit echten Firmware-
#    Funktionen fuer Schritt (vt[0x20] = 0x4000b7d6, vt[0x14]) und Setzen (0x4000b274, Deskriptoren aus dem ROM); nur die
#    Tabellen der Seite (vt[0x7c] Parameter unter dem Regler, vt[0x80] Objekt) und die Speicher-Funktionen des Objekts
#    (vt[0x18] erlaubt?, vt[0x1c] lesen, vt[0x5c] schreiben, vt[0x48]) sind nachgebaut.
#    Relativ (Byte 0, v1-Reste): Ergebnis und Aufrufe gleich wie Stock. Absolut: ausgewaehlter Track wie Stock, alle anderen
#    dessen neuer Wert (auf ihren Bereich geklemmt / auf erlaubte Werte gerundet).
# 2. TRACK + LEVEL (Lautstaerke) und FUNC + TRACK + LEVEL (Pan): echter Encoder-Handler des Hauptbildschirms 0x4001aa4e.
# 3. Umschalten: echter MainScreenView::consumeKeyEvent (Fall 13) mit dem Core: TRACK + SETTINGS kurz = umschalten (COPY in
#    den Einstellungsblock, Popup), kein Menue; ohne TRACK, nach einer Drehung, langes Halten, FUNC: wie bisher.
# 4. groove: TRACK + SETTINGS / MACHINE + Swing (Humanize aller Tracks) folgt dem Modus.
# Aufruf: test_control.py [--alone]   (--alone: nur core + control-mode)
import struct, sys
from rig import *
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'Modded-Cycles/tools/emu'))
from ramalias import map_ram
import g2_control as G

CM = V2SYM['control-mode']; CS = V2SYM['core']
ALONE = '--alone' in sys.argv                  # nur core + control-mode (ohne groove: Teil 4 entfaellt)
IMG = v2_image(['core', 'control-mode']) if ALONE else v2_image()
STK = v2_image(['core']) if ALONE else v2_image([i for i in V2_IDS if i != 'control-mode'])
ABS = C.CTRL_ABS
chk('Eintrag 0x40100588 (ParameterPageView vt[0x5c]): Stock 0x4001d6e4, Image CA',
    STK[0x40100588 - BASE:][:4] == struct.pack('>I', 0x4001D6E4) and IMG[0x40100588 - BASE:][:4] == struct.pack('>I', CM['CA']))
chk('Haken 0x4001ab7a / 0x4001aaec = jmp LV / jmp LP',
    IMG[0x4001AB7A - BASE:][:6] == C.jmp(CM['LV']) and IMG[0x4001AAEC - BASE:][:6] == C.jmp(CM['LP']))
chk('Slots: Encoder-Slot 5 = CME, Tasten-Slot 0 = CMK',
    IMG[CS['SLOTS'] + 4 * 5 - BASE:][:4] == struct.pack('>I', CM['CME']) and IMG[CS['KSLOTS'] - BASE:][:4] == struct.pack('>I', CM['CMK']))

# ------------------------------------------------------------------ Nachbau: Seite, Objekte
THIS, FVT, OBJ0, FPV, PROJ = 0x4F044000, 0x4F044100, 0x4F045000, 0x4F046000, 0x4F047000
ST = {n: 0x4E000200 + 0x10 * i for i, n in enumerate(['VT7C', 'VT80', 'ALLOW', 'NOTIFY', 'GET', 'VT48', 'SELA', 'SELB', 'SELC',
                                                       'F6E2', 'F73A', 'VGET', 'VSET'])}
KIT = PROJ + 0x74
SOUND = lambda t: KIT + 0x1F8 + 8 * t                   # 0x400097f0(kit, t)


class Bench:
    def __init__(s, img):
        e = s.e = Emu(img)
        s.val, s.vol, s.log, s.params, s.sel, s.step, s.bad = {}, [0] * 6, [], [0] * 6, 0, 0, set()
        e.u.mem_write(FVT, bytes(e.u.mem_read(0x4010052C, 0x100)))
        e.w32(FVT + 0x7C, ST['VT7C']); e.w32(FVT + 0x80, ST['VT80']); e.w32(THIS, FVT)
        e.u.mem_write(FPV, bytes(e.u.mem_read(0x400FD134, 0x80)))
        for k, n in ((0x18, 'ALLOW'), (0x1C, 'GET'), (0x5C, 'NOTIFY'), (0x48, 'VT48')): e.w32(FPV + k, ST[n])
        s.objs = [OBJ0 + 0x40 * t for t in range(6)] + [SOUND(t) for t in range(6)]
        for o in s.objs: e.w32(o, FPV); e.w32(o + 4, 0)
        for n, a in ST.items(): e.u.hook_add(UC_HOOK_CODE, s._st, begin=a, end=a, user_data=n)
        for a, n in ((C.SEL_A, 'SELA'), (C.SEL_B, 'SELB'), (C.SEL_C, 'SELC'), (0x4006F6E2, 'F6E2'), (0x4006F73A, 'F73A'),
                     (0x40009CA0, 'VGET'), (0x4000A3AE, 'VSET')):
            e.u.hook_add(UC_HOOK_CODE, s._st, begin=a, end=a, user_data=n)
    def _st(s, u, addr, size, n):
        e = s.e; sp = u.reg_read(mk.UC_M68K_REG_A7); arg = lambda i: e.r32(sp + 4 + 4 * i)
        sg = lambda v: struct.unpack('>i', struct.pack('>I', v))[0]
        r = 0
        if n == 'VT7C': s.log.append(('p', arg(1), arg(2), arg(3))); r = s.params[arg(3)]
        elif n == 'VT80': r = s.objs[arg(1)] if arg(2) != 0x1C else SOUND(arg(1))
        elif n == 'ALLOW': r = 0 if (arg(0), arg(1), sg(arg(2))) in s.bad else 1
        elif n == 'NOTIFY': s.val[(arg(0), arg(1))] = sg(arg(2)); s.log.append(('set', s.objs.index(arg(0)), arg(1), sg(arg(2)), arg(3), arg(4)))
        elif n == 'GET': r = s.val.get((arg(0), arg(1)), 0)
        elif n == 'VT48': s.log.append(('vt48', s.objs.index(arg(0)), arg(1)))
        elif n == 'SELA': r = PROJ
        elif n == 'SELB': r = 0x4F04F000
        elif n == 'SELC': r = s.sel
        elif n == 'F6E2': r = 1
        elif n == 'F73A': r = s.step
        elif n == 'VGET': r = s.vol[arg(1)]
        elif n == 'VSET':
            v = max(0, min(32512, sg(arg(2)))); s.vol[arg(1)] = v; s.log.append(('vol', arg(1), v, arg(3)))
        for x in (mk.UC_M68K_REG_D1, mk.UC_M68K_REG_A0, mk.UC_M68K_REG_A1): u.reg_write(x, 0xBAD0BAD0)
        u.reg_write(mk.UC_M68K_REG_D0, r & 0xffffffff)
        u.reg_write(mk.UC_M68K_REG_PC, e.r32(sp)); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
    def knob(s, mode, params, vals, sel, delta, held=(2,), enc=5):
        s.e.w8(C.CTRL_MODE, mode); s.params = params; s.sel = sel; s.log = []; s.e.held = set(held)
        s.val = {(s.objs[t], params[t]): v for t, v in enumerate(vals)}
        _, good = s.e.call(s.e.r32(0x40100588), THIS, enc, delta)
        return [s.val[(s.objs[t], params[t])] for t in range(6)], list(s.log), good
    def level(s, mode, vols, pans, sel, step, held):
        s.e.w8(C.CTRL_MODE, mode); s.sel = sel; s.step = step; s.log = []; s.e.held = set(held); s.vol = list(vols)
        s.val = {(SOUND(t), 0x1C): v for t, v in enumerate(pans)}
        d0, good = s.e.call(0x4001AA4E, 0x4F04E000, 0x4F04E100)
        return list(s.vol), [s.val[(SOUND(t), 0x1C)] for t in range(6)], list(s.log), d0 & 0xff, good


bs, bi = Bench(STK), Bench(IMG)
SHAPE = [47, 52, 57, 62, 67, 72]                 # SHAPE der 6 Maschinen (Chord Shape: 0..9472)
CASES = [('SHAPE, Track 1, +256', SHAPE, [1000, 30000, 9000, 16000, 500, 9000], 0, 256),
         ('SHAPE, Track 2, -2560', SHAPE, [1000, 30000, 9000, 16000, 500, 9000], 1, -2560),
         ('SHAPE, Track 4 am Anschlag oben, +5000', SHAPE, [1000, 30000, 9000, 32512, 500, 9472], 3, 5000),
         ('SHAPE, Track 6 (Chord), +768', SHAPE, [32000, 30000, 0, 16000, 500, 8000], 5, 768),
         ('PITCH (Halbtonraster), Track 3, +300', [42] * 6, [16384, 12000, 16384, 20000, 10240, 22528], 2, 300),
         ('DECAY, Track 5, -9000', [24] * 6, [100, 32512, 16000, 8000, 7000, 0], 4, -9000)]
lo_hi = lambda p: struct.unpack('>ii', STOCK[C.DESC(p) + 8 - BASE:][:8])
for name, ps, vals, sel, d in CASES:
    rs, ls, gs = bs.knob(0, ps, vals, sel, d)
    same = True
    for mode in (0, 1, 4, 0x5B):
        ri, li, gi = bi.knob(mode, ps, vals, sel, d); same &= ri == rs and li == ls and gi
    chk('%s: relativ (Byte 0, 1, 4, 0x5b) = Stock %s' % (name, rs), same and gs and rs != vals)
    ra, la, ga = bi.knob(ABS, ps, vals, sel, d)
    tgt = rs[sel]
    exp = [min(max(tgt, lo_hi(ps[t])[0]), lo_hi(ps[t])[1]) for t in range(6)]
    if ps[0] == 42: exp = [tgt] * 6
    chk('%s: absolut -> %s (ausgewaehlter wie Stock, Rest = dessen Wert, geklemmt), Register ok' % (name, ra), ra == exp and ga)
    sets = [x for x in la if x[0] == 'set']
    chk('   absolut: je Track ein Schreiben mit Track-Nummer, Flags 0 wie die Firmware-Schleife',
        sorted(x[4] for x in sets) == list(range(6)) and all(x[5] == 0 for x in sets))
# FUNC gehalten: Parameter-Abfrage mit FUNC = 1 (wie Firmware)
_, ls, _ = bs.knob(0, SHAPE, [0] * 6, 0, 256, held=(2, 1)); _, la, _ = bi.knob(ABS, SHAPE, [0] * 6, 0, 256, held=(2, 1))
chk('FUNC + TRACK: vt[0x7c] mit FUNC = 1 wie die Firmware', {x[2] for x in ls if x[0] == 'p'} == {1} == {x[2] for x in la if x[0] == 'p'})
# nicht erlaubter Zielwert: naechster erlaubter Wert des Tracks
bi.bad = {(bi.objs[2], SHAPE[2], 4096 + 256)}
ra, _, _ = bi.knob(ABS, SHAPE, [4096] * 6, 0, 256)
chk('absolut, Zielwert fuer Track 3 nicht erlaubt: naechster erlaubter Wert (%s)' % ra, ra[2] != 4352 and ra[2] in (4351, 4353) and ra[0] == 4352)
bi.bad = set()

# ------------------------------------------------------------------ 2. LEVEL / Pan im Hauptbildschirm
VOLS, PANS = [25600, 32512, 100, 12000, 0, 32000], [16384, 0, 32512, 8000, 20000, 16384]
for what, held in (('TRACK + LEVEL (Lautstaerke)', (2,)), ('FUNC + TRACK + LEVEL (Pan)', (2, 1)), ('LEVEL ohne TRACK', ()),
                   ('FUNC + LEVEL ohne TRACK', (1,))):
    for sel, step in ((0, 3), (2, -20), (5, 40)):
        vs, ps_, ls, d0s, gs = bs.level(0, VOLS, PANS, sel, step, held)
        same = all(bi.level(m, VOLS, PANS, sel, step, held) == (vs, ps_, ls, d0s, gs) for m in (0, 1, 3))
        chk('%s, Track %d, Schritt %+d: relativ = Stock (Lautst. %s, Pan %s)' % (what, sel + 1, step, vs, ps_), same and gs)
        va, pa, la, d0a, ga = bi.level(ABS, VOLS, PANS, sel, step, held)
        if 2 in held:
            if 1 in held: exp = (list(VOLS), [ps_[sel]] * 6)
            else: exp = ([vs[sel]] * 6, list(PANS))
        else: exp = (vs, ps_)
        chk('   absolut: %s, d0 und Register wie Stock' % ('alle = neuer Wert des ausgewaehlten' if 2 in held else 'wie Stock'),
            (va, pa) == exp and d0a == d0s and ga and (2 in held or la == ls))

# ------------------------------------------------------------------ 3. Umschalten: echter consumeKeyEvent, Fall 13
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN
PRESS, HOLD, LONG, REL, FREL = 0x1, 0x9, 0x29, 0x10, 0x12
SU = C.CM_SU
class MS:
    def __init__(s, im):
        u = s.u = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN); u.ctl_set_cpu_model(mk.UC_CPU_M68K_CFV4E)
        u.mem_map(0x40000000, 0x2330000); u.mem_map(0x42340000, 0xC0000); u.mem_write(BASE, im); map_ram(u)
        u.mem_map(0x4E000000, 0x1000); u.mem_map(0x4F000000, 0x40000); u.mem_map(0xFC070000, 0x1000)
        s.log, s.held, s.copies = [], set(), []
        stubs = {0x40039570: 'SAVE', 0x4001040e: 'QSAVE', 0x40077da8: 'OPEN', 0x400d807e: None, 0x400cf23c: None,
                 0x400cfd0e: None, 0x4006a96c: None, 0x400cf866: None, 0x400802e0: None, 0x400cf044: None,
                 0x400cf9a8: None, 0x4006b736: None, C.HELD: 'HELD', C.COPY: 'COPY'}
        def hk(uu, a, sz, _):
            sp = uu.reg_read(mk.UC_M68K_REG_A7); r32 = lambda x: struct.unpack('>I', bytes(uu.mem_read(x, 4)))[0]
            d0 = 0x4F020000 if a == 0x400802e0 else 0
            if a == C.HELD: d0 = 1 if r32(sp + 4) in s.held else 0
            elif a == C.COPY:
                dst, src, n = r32(sp + 4), r32(sp + 8), r32(sp + 12)
                uu.mem_write(dst, bytes(uu.mem_read(src, n))); s.copies.append((dst, src, n))
            elif stubs[a]: s.log.append(stubs[a])
            for x in (mk.UC_M68K_REG_D1, mk.UC_M68K_REG_A0, mk.UC_M68K_REG_A1): uu.reg_write(x, 0xBAD0BAD0)
            uu.reg_write(mk.UC_M68K_REG_D0, d0); uu.reg_write(mk.UC_M68K_REG_PC, r32(sp)); uu.reg_write(mk.UC_M68K_REG_A7, sp + 4)
        for a in stubs: u.hook_add(UC_HOOK_CODE, hk, begin=a, end=a)
        s.this, s.ev = 0x4F010000, 0x4F011000
        u.mem_write(s.this, bytes(0x200)); u.mem_write(s.this + 0x2C, struct.pack('>I', 0x4F012000))
        u.mem_write(0xFC07000C, struct.pack('>I', 1000))
    REGS = (mk.UC_M68K_REG_D2, mk.UC_M68K_REG_D3, mk.UC_M68K_REG_D4, mk.UC_M68K_REG_D5, mk.UC_M68K_REG_D6, mk.UC_M68K_REG_D7,
            mk.UC_M68K_REG_A2, mk.UC_M68K_REG_A3, mk.UC_M68K_REG_A4, mk.UC_M68K_REG_A5, mk.UC_M68K_REG_A6)
    def call(s, fn, *args, regs=None):
        sp = 0x4F030000; s.u.mem_write(sp, struct.pack('>I', 0x4E000000) + b''.join(struct.pack('>I', x & 0xffffffff) for x in args))
        s.u.reg_write(mk.UC_M68K_REG_A7, sp)
        for i, r in enumerate(s.REGS): s.u.reg_write(r, 0xC0DE0000 + i)
        for r, v in (regs or {}).items(): s.u.reg_write(r, v)
        s.u.emu_start(fn, 0x4E000000, count=300000)
        good = s.u.reg_read(mk.UC_M68K_REG_A7) == sp + 4 and all(
            s.u.reg_read(r) == 0xC0DE0000 + i for i, r in enumerate(s.REGS) if r not in (regs or {}))
        return s.u.reg_read(mk.UC_M68K_REG_D0), good
    def key(s, flags, held=(), code=13):
        s.held = set(held)
        s.call(0x4007238C, s.ev, code, flags, 1234, 0x7F); s.log.clear()
        d0, good = s.call(0x4001C0D2, s.this, s.ev); return list(s.log), good
    r8 = lambda s, a: s.u.mem_read(a, 1)[0]
    w8 = lambda s, a, v: s.u.mem_write(a, bytes([v]))
    r32 = lambda s, a: struct.unpack('>I', bytes(s.u.mem_read(a, 4)))[0]
    def popup(s):
        V = C.VARS; rd = lambda a: bytes(s.u.mem_read(a, 16)).split(b'\0')[0].decode()
        return (s.r32(V + C.V_KIND), rd(s.r32(V + C.V_VAL)), rd(s.r32(V + C.V_L1)), rd(s.r32(V + C.V_L2)))

m0 = MS(STOCK)
seq = [m0.key(PRESS, (2,))[0], m0.key(HOLD, (2,))[0], m0.key(REL, (2,))[0]]
chk('Stock: TRACK + SETTINGS kurz -> Menue wie ohne TRACK (%s)' % seq, seq == [[], [], ['OPEN']])
m = MS(IMG); m.w8(C.CTRL_MODE, 0)
res = []
for i in range(3):
    a = [m.key(PRESS, (2,)), m.key(HOLD, (2,)), m.key(REL, (2,))]
    res.append(([x[0] for x in a], all(x[1] for x in a), m.r8(C.CTRL_MODE), m.popup(), list(m.copies))); m.copies.clear()
chk('TRACK + SETTINGS kurz: kein Menue, umgeschaltet auf absolut (0x%02x), COPY(0x404e9b5d, Byte, 1), Popup %s' % (res[0][2], res[0][3],),
    res[0][0] == [[], [], []] and res[0][1] and res[0][2] == ABS and res[0][4] == [(C.CTRL_MODE, C.CM_SCR, 1)]
    and res[0][3] == (C.OV_TEXT, 'Absolute', 'Control', 'All'))
chk('nochmal: zurueck auf relativ (0), Popup %s ; und wieder absolut' % (res[1][3],),
    res[1][0] == [[], [], []] and res[1][2] == 0 and res[1][3][1] == 'Relative' and res[2][2] == ABS and res[1][1] and res[2][1])
for v in (1, 4):                                     # v1-Rest im Byte: gilt als relativ -> erstes Umschalten = absolut
    m.w8(C.CTRL_MODE, v); m.key(PRESS, (2,)); m.key(REL, (2,))
    chk('Byte %d (Rest aus v1) gilt als relativ: Umschalten -> absolut' % v, m.r8(C.CTRL_MODE) == ABS)
m.w8(C.CTRL_MODE, 0)
seq = [m.key(PRESS)[0], m.key(REL)[0]]
chk('SETTINGS ohne TRACK: Menue, Modus unveraendert', seq == [[], ['OPEN']] and m.r8(C.CTRL_MODE) == 0)
seq = [m.key(PRESS, (2,))[0], m.key(LONG, (2,))[0], m.key(REL, (2,))[0]]
chk('TRACK + SETTINGS lang: Projekt speichern wie ohne TRACK, kein Umschalten', seq == [[], [], ['SAVE']] and m.r8(C.CTRL_MODE) == 0)
seq = [m.key(PRESS, (2, 1))[0], m.key(FREL, (2, 1))[0]]
chk('FUNC + TRACK + SETTINGS: Muster speichern wie bisher, kein Umschalten', seq == [[], ['QSAVE']] and m.r8(C.CTRL_MODE) == 0)
# Drehung waehrend SETTINGS gehalten (kein eigener Gesten-Treffer): CME merkt sie, Loslassen schaltet nicht um
m.key(PRESS, (2,)); m.held = {2, 13}
m.u.mem_write(0x4F038000, struct.pack('>IIiI', 0, 0, 0, 0)); m.u.mem_write(0x4F038008, b'\x01')
d0, g = m.call(CM['CME'], regs={mk.UC_M68K_REG_A2: 0x4F038000})
seq = m.key(REL, (2,))[0]
chk('TRACK + SETTINGS + Drehung (keine Mod-Geste): CME = nicht meins (d0 %d), Loslassen -> Menue wie Firmware, kein Umschalten' % d0,
    d0 == 0 and g and seq == ['OPEN'] and m.r8(C.CTRL_MODE) == 0)
seq = [m.key(PRESS, (2,))[0], m.key(REL, (2,))[0]]
chk('danach wieder: TRACK + SETTINGS kurz schaltet um', seq == [[], []] and m.r8(C.CTRL_MODE) == ABS)
m.held = set(); d0, g = m.call(CM['CME'], regs={mk.UC_M68K_REG_A2: 0x4F038000})
chk('CME ohne SETTINGS: nichts gemerkt, d0 = 0', d0 == 0 and g and m.r8(SU) == 0)

# ------------------------------------------------------------------ 4. groove: Humanize aller Tracks
if ALONE: done()
e = Emu(IMG); e.w32(C.TIMER, 1000)
def sel(u, a_, z, _):
    sp = u.reg_read(mk.UC_M68K_REG_A7); u.reg_write(mk.UC_M68K_REG_D0, 2 if a_ == C.SEL_C else 0x4F050000)
    u.reg_write(mk.UC_M68K_REG_PC, e.r32(sp)); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
for t in (C.SEL_A, C.SEL_B, C.SEL_C): e.u.hook_add(UC_HOOK_CODE, sel, begin=t, end=t)
H0 = [10, 100, 50, 0, 95, 30]
for mode, held, off, exp in ((0, (13, 2), 40, [min(100, h + 5) for h in H0]), (ABS, (13, 2), 40, [55] * 6),
                             (ABS, (5, 2), 46, [55] * 6), (ABS, (13,), 40, H0[:2] + [55] + H0[3:])):
    e.w8(C.CTRL_MODE, mode); e.u.mem_write(e.hdr(40), bytes(H0 + H0))
    r = e.enc(C.ENC_SWING, 5, held)
    got = list(e.u.mem_read(e.hdr(off), 6)); other = list(e.u.mem_read(e.hdr(86 - off), 6))
    chk('Humanize %s, %s, Track 3 +5: %s' % ('Zeit' if off == 40 else 'Velocity', ('absolut' if mode else 'relativ') +
        (' mit TRACK' if 2 in held else ' ohne TRACK'), got), got == exp and other == H0 and r['skipped'] and r['regs'] and r['sp'])
done()
