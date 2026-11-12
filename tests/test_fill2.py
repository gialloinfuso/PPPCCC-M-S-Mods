# fill2 (v2): zweiter FILL (PAGE + FUNC), Bedingungen FIL2 / !FIL2 (64 / 65); smp21: Reihenfolge A:B | Logik | Prozent,
# PTC / !PTC (66 / 67), LST / !LST (68 / 69), x:12 (70..81), x:16 (82..97). Gespeichert bleiben die Stock-Werte 0..63.
# 1. Echte Auswertung 0x400913f0 (Track, Step, gespeicherte Bedingung, a1) gegen Stock: 0..66, Fill aus/an, FUNC aus/an,
#    a1 = 0 und != 0. Ohne Fill 2 (FUNC los oder Fill aus) Ergebnis und Zustand (0x40fde800..0x40fde837) wie Stock fuer 0..63;
#    mit Fill 2: FILL still, !FILL spielt, Rest wie Stock. FIL2 spielt nur mit Fill 2, !FIL2 nur ohne. 66 wie Stock (spielt).
# 2. Echter Getter 0x40015fd0 / Setter 0x40016010: Byte 0..65 -> Position, Position -1..65 -> Byte, hin und zurueck gleich,
#    ausserhalb begrenzt; Stock unveraendert fuer 0..63.
# 3. Echter Text 0x4004a4ce (sprintf der Firmware) nach Position: FILL, !FILL, FIL2, !FIL2, PRE, ..., 8:8; 66 wie Stock > 63.
# 4. Anzeige 0x40050046: Grenze 65, Grundnamen nach Position, Negationszeichen ungerade bis 9, Prozent-Bereich 10..30.
# 5. Deskriptor 19 Max = 65 << 8.
# Aufruf: test_fill2.py [--alone]   (--alone: nur fill2)
import struct, sys
from rig import *
import g2_fill2 as G

ALONE = '--alone' in sys.argv
IMG = v2_image(['fill2'], latch=False) if ALONE else v2_image()
STK = STOCK if ALONE else v2_image([i for i in V2_IDS if i != 'fill2'])
S = V2SYM['fill2']
EVAL, TXT, SETTER = 0x400913F0, 0x4004A4CE, 0x40016010
ST0, ST1 = 0x40FDE800, 0x40FDE820
FB, FBIT = G.func_bit(STOCK)
chk('Haken 0x40091416 = jmp EV ; nop', IMG[G.EV_HOOK - BASE:][:8] == C.jmp(S['EV']) + b'\x4e\x71')
chk('FUNC-Taste = Bitmap-Byte %#x Bit %d (wie HELD 0x4007faf4)' % (FB, FBIT), (FB, FBIT) == (0x40F95745, 2))


def run_eval(img, cond, fill, func, a1, trk=2, seed=0):
    e = Emu(img)
    st = bytes((seed * 7 + i * 13 + 1) & 0xff for i in range(ST1 - ST0))
    st = bytearray(st)
    for i in range(6): st[0x12 + i] &= 1; st[0x0c + i] &= 1       # Fill-Merker 0/1
    e.u.mem_write(ST0, bytes(st[:0x1c])); e.u.mem_write(ST0 + 0x1c, struct.pack('>6I', *[(seed + 3 * i) % 37 for i in range(6)]))
    e.w8(0x40FDE818, fill)
    e.w8(FB, (1 << FBIT) if func else 0)
    flag = 0x4F04F000 if a1 else 0
    if a1: e.w32(flag, 0x01010101)
    d0, good = e.call(EVAL, trk, 5, cond, flag, count=100000)
    return d0 & 0xff, good, bytes(e.u.mem_read(ST0, 0x38))


CH = dict(pos=G.CPOS, len=G.CLEN, ch=G.CHAIN0, cur=G.CURPAT)
CHAINS = [  # (Position, Laenge, Kette, laufendes Pattern) -> (PTC, LST)
    (0, 1, [5], 5, (0, 0)),          # ein Pattern, kein Wechsel
    (-1, 1, [7], 5, (1, 1)),         # neu gewaehlt, wartet
    (-1, 1, [5], 5, (0, 0)),         # dasselbe neu gewaehlt
    (0, 2, [5, 9], 5, (0, 1)),       # Kette, naechstes anders
    (1, 2, [5, 9], 9, (0, 1)),       # Kette, letzter Eintrag -> zurueck zum ersten
    (0, 2, [5, 5], 5, (0, 0)),       # Kette aus demselben Pattern
    (-1, 3, [5, 8, 9], 5, (0, 0)),   # neue Kette, erstes = laufendes
]


def run_eval(img, cond, fill, func, a1, trk=2, seed=0, chain=None):
    e = Emu(img)
    st = bytes((seed * 7 + i * 13 + 1) & 0xff for i in range(ST1 - ST0))
    st = bytearray(st)
    for i in range(6): st[0x12 + i] &= 1; st[0x0c + i] &= 1       # Fill-Merker 0/1
    e.u.mem_write(ST0, bytes(st[:0x1c])); e.u.mem_write(ST0 + 0x1c, struct.pack('>6I', *[(seed + 3 * i) % 37 for i in range(6)]))
    e.w8(0x40FDE818, fill)
    e.w8(FB, (1 << FBIT) if func else 0)
    if chain:
        ps, ln, chn, cur = chain[:4]
        e.w32(G.CPOS, ps); e.w32(G.CLEN, ln); e.w32(G.CURPAT, cur)
        for i, x in enumerate(chn): e.w32(G.CHAIN0 + 8 * i, x); e.w32(G.CHAIN0 + 8 * i + 4, 0)
    flag = 0x4F04F000 if a1 else 0
    if a1: e.w32(flag, 0x01010101)
    d0, good = e.call(EVAL, trk, 5, cond, flag, count=100000)
    return d0 & 0xff, good, bytes(e.u.mem_read(ST0, 0x38))


bad = []
for cond in range(G.NCOND + 1):
    for fill in (0, 1):
        for func in (0, 1):
            for a1 in (0, 1):
                for seed in (0, 5, 11):
                    for ci, chain in enumerate(CHAINS if cond in (66, 67, 68, 69) else CHAINS[:1]):
                        m = run_eval(IMG, cond, fill, func, a1, seed=seed, chain=chain)
                        s = run_eval(STK, cond, fill, func, a1, seed=seed, chain=chain)
                        f2 = fill and func
                        if not m[1] or not s[1]:
                            bad.append(('regs', cond, fill, func, a1)); continue
                        if (cond <= 63 and not (f2 and cond <= 1)) or cond >= G.NCOND:
                            if m[0] != s[0] or m[2] != s[2]: bad.append(('stock', cond, fill, func, a1, m[0], s[0]))
                            continue
                        cnt = 0 if a1 else (seed + 3 * 2) % 37                # Durchlauf-Zaehler der Spur 2
                        if cond == 0: r = 1
                        elif cond == 1: r = 0
                        elif cond == 64: r = 0 if f2 else 1
                        elif cond == 65: r = 1 if f2 else 0
                        elif cond in (66, 67, 68, 69):
                            v = chain[4][0 if cond < 68 else 1]
                            r = (1 - v) if cond in (66, 68) else v
                        else:
                            b, aa = (12, cond - G.R12 + 1) if cond < G.R16 else (16, cond - G.R16 + 1)
                            r = 0 if cnt % b == aa - 1 else 1
                        if m[0] != r: bad.append(('d0', cond, fill, func, a1, ci, m[0], r)); continue
                        diff = [i for i in range(len(m[2])) if m[2][i] != s[2][i]]
                        if any(i not in (0x06 + 2, 0x00 + 2) for i in diff): bad.append(('state', cond, fill, func, a1, diff))
                        # Ergebnis fuer PRE wie die Firmware: a1 = 0 -> 0x40fde806[t], sonst 0x40fde800[t] = 1 / Ergebnis
chk('Auswertung: %d Bedingungen x Fill x FUNC x a1 x 3 Zustaende (PTC / LST x 7 Ketten), Register (%d Abweichungen)'
    % (G.NCOND + 1, len(bad)), not bad)
for b in bad[:8]: print('   ', b)
r = run_eval(IMG, G.R16 + 3, 0, 0, 0, trk=3, seed=1)
chk('x:16-Ergebnis landet in 0x40fde806[t] (fuer PRE)', r[2][0x06 + 3] == (0 if (1 + 9) % 16 == 3 else 1))

# Ergebnisbyte explizit
def res(cond, fill, func): return run_eval(IMG, cond, fill, func, 0)[0]
chk('PAGE allein: FILL spielt, !FILL still, FIL2 still, !FIL2 spielt',
    (res(0, 1, 0), res(1, 1, 0), res(64, 1, 0), res(65, 1, 0)) == (0, 1, 1, 0))
chk('PAGE + FUNC: FILL still, !FILL spielt, FIL2 spielt, !FIL2 still',
    (res(0, 1, 1), res(1, 1, 1), res(64, 1, 1), res(65, 1, 1)) == (1, 0, 0, 1))
chk('ohne Fill, FUNC gehalten: wie ohne FUNC',
    all(res(c, 0, 1) == res(c, 0, 0) for c in (0, 1, 64, 65)) and (res(64, 0, 0), res(65, 0, 0)) == (1, 0))
r = run_eval(IMG, 64, 1, 1, 0, trk=3)
chk('FIL2-Ergebnis landet in 0x40fde806[t] (fuer PRE) wie bei den anderen Bedingungen', r[2][0x06 + 3] == 0)


# ------------------------------------------------------------------ 2. Getter / Setter
OBJ, VT, DATA, CODE = 0x4F04C000, 0x4F04C100, 0x4F04D000, 0x4F04C200
GETTER = 0x40015FD0
def bench(img):
    e = Emu(img)
    e.w32(OBJ, VT); e.w32(VT + 0x28, CODE); e.w32(VT + 0x10, CODE + 8)
    e.u.mem_write(CODE, bytes.fromhex('203c') + struct.pack('>I', DATA) + bytes.fromhex('4e75') + bytes.fromhex('4e75'))
    e.u.mem_write(DATA + 0x204, b'\x55' * 64)
    return e
sb = lambda x: struct.unpack('b', bytes([x & 0xff]))[0]
def setter(img, v, step=7):
    e = bench(img); _, good = e.call(SETTER, OBJ, step, v, count=100000)
    return sb(e.r8(DATA + 0x204 + step)), good
def getter(img, raw, step=9):
    e = bench(img); e.w8(DATA + 0x204 + step, raw); d0, good = e.call(GETTER, OBJ, step, count=100000)
    return sb(d0), good
N = G.NCOND
gm = [getter(IMG, r) for r in range(-1, N)]
chk('Getter: Byte -1, 0..%d -> Position %s' % (N - 1, [x for x, _ in gm][:8]),
    [x for x, _ in gm] == [-1] + [G.pos(r) for r in range(N)] and all(g for _, g in gm))
chk('Getter Stock unveraendert (0..63)', [getter(STK, r)[0] for r in range(-1, 64)] == list(range(-1, 64)))
sm = [setter(IMG, p) for p in range(-1, N)]
chk('Setter: Position -1..%d -> Byte, hin und zurueck gleich' % (N - 1),
    [x for x, _ in sm] == [-1] + [G.stored(p) for p in range(N)] and all(g for _, g in sm)
    and all(G.pos(G.stored(p)) == p for p in range(N)))
chk('Setter begrenzt: 98, 100, 127 -> letzte Position (99%%); -5 -> -1',
    [setter(IMG, v)[0] for v in (98, 100, 127, -5)] == [G.ORDER[-1]] * 3 + [-1] and G.ORDER[-1] == 28)
chk('Reihenfolge: 1:2 zuerst, 8:8 an 34, x:12 / x:16 danach, FILL an 63, 1%% an 77',
    G.ORDER[0] == 29 and G.ORDER[34] == 63 and G.ORDER[35] == G.R12 and G.ORDER[47] == G.R16 and G.ORDER[63] == 0
    and G.ORDER[77] == 8)
e = bench(IMG); e.call(GETTER, OBJ, 70, count=100000)
chk('Getter Step > 63 -> -1 wie Stock', sb(e.call(GETTER, OBJ, 70, count=100000)[0]) == -1)

# ------------------------------------------------------------------ 3. Text
def txt(img, v):
    e = Emu(img); buf = 0x4F04F100
    e.u.mem_write(buf, b'\xee' * 16)
    _, good = e.call(TXT, 0, v, buf, count=200000)
    return e.cstr(buf), good
tm = [txt(IMG, c << 8) for c in range(N + 1)]
ts = [txt(STK, c << 8) for c in range(65)]
own = dict(zip(range(64, N), [n for n, _ in G.OWN]))
exp = [ts[G.stored(p)][0] if G.stored(p) < 64 else own[G.stored(p)] for p in range(N)] + [ts[64][0]]
chk('Liste: %s ... %s ... %s' % (', '.join(t for t, _ in tm[:4]), ', '.join(t for t, _ in tm[60:78]), ', '.join(t for t, _ in tm[-3:])),
    [t for t, _ in tm] == exp and all(g for _, g in tm) and [t for t, _ in tm[:3]] == ['1:2', '2:2', '1:3']
    and [t for t, _ in tm[63:77]] == ['FILL', '!FILL', 'FIL2', '!FIL2', 'PTC', '!PTC', 'PRE', '!PRE', 'NEI', '!NEI', '1st', '!1st', 'LST', '!LST']
    and tm[77][0] == '1%' and tm[97][0] == '99%' and tm[35][0] == '1:12' and tm[62][0] == '16:16')

# ------------------------------------------------------------------ 4. Anzeige
rd = lambda img, a, n=4: img[a - BASE:a - BASE + n]
cs = lambda img, a: img[a - BASE:a - BASE + 8].split(b'\0')[0].decode()
chk('Anzeige: moveq #97,d1 ; jsr BMAP (statt lea Grundnamen)', rd(IMG, G.DSP_LIM, 8) == bytes.fromhex('7261') + C.jsr(S['BMAP']))
def bentry(img, p):
    """wie die Anzeige: jsr BMAP ; move.l 0(a0,d2.l*4),d0 -> Zeiger auf den Grundnamen; d1, d2 muessen bleiben"""
    e = Emu(img); T = 0x4F04E000
    e.u.mem_write(T, C.jsr(S['BMAP']) + bytes.fromhex('20302c00' '4e75'))
    d0, good = e.call(T, regs={mk.UC_M68K_REG_D2: p, mk.UC_M68K_REG_D1: 0x41}, count=1000)
    return d0, good and e.u.reg_read(mk.UC_M68K_REG_D2) == p and e.u.reg_read(mk.UC_M68K_REG_D1) == 0x41
bs = struct.unpack('>72I', rd(STK, G.BASEN0, 288))
be = [bentry(IMG, p) for p in range(N + 4)]
ownb = dict(zip(range(64, N), [b for _, b in G.OWN]))
chk('Grundnamen nach Position: %s' % [cs(IMG, x) for x, _ in be[60:70]],
    all(g for _, g in be) and all(be[p][0] == bs[G.stored(p)] for p in range(N) if G.stored(p) < 64)
    and all(cs(IMG, be[p][0]) == ownb[G.stored(p)] for p in range(N) if G.stored(p) >= 64)
    and all(be[p][0] == struct.unpack('>I', rd(STK, G.BASEN0 + 4 * p))[0] for p in range(N, N + 4)))
chk('keine kopierte Firmware-Tabelle: eigene Zeiger nur fuer 64..97',
    struct.unpack('>%dI' % len(G.OWN), rd(IMG, S['OWNN'], 4 * len(G.OWN)))[:2] == (S['S_FIL2'], S['S_NFIL2']))
def flagrun(img, p):
    e = Emu(img); T = 0x4F04E000
    e.u.mem_write(T, C.jsr(S['PRC']) + bytes.fromhex('b280' '54c0' '4e75'))       # jsr PRC ; cmp.l d0,d1 ; scc.b d0
    d0, g1 = e.call(T, regs={mk.UC_M68K_REG_D2: p}, count=1000)
    n, g2 = e.call(S['NEGF'], regs={mk.UC_M68K_REG_D2: p}, count=1000)
    return (d0 & 0xff) == 0xff, n == 1, g1 and g2 and e.u.reg_read(mk.UC_M68K_REG_D2) == p & 0xFFFFFFFF
fl = [flagrun(IMG, p) for p in list(range(N)) + [N, 120, -1]]
chk('Prozent / Negationsstrich nach Position (FLAGS), Register',
    all(f[2] for f in fl) and all(fl[p][0] == (G.stored(p) in G.PRCS) and fl[p][1] == (G.stored(p) in G.NEGS) for p in range(N))
    and not any(f[0] or f[1] for f in fl[N:]))
chk('Haken Prozent (jsr PRC) und Negationsstrich (jsr NEGF ; tst.l d0 ; beq.b ; nop)',
    rd(IMG, G.PRC_AT, 6) == C.jsr(S['PRC'])
    and rd(IMG, G.NEG_LIM, 12) == C.jsr(S['NEGF']) + bytes.fromhex('4a80') + bytes([0x67, G.NEG_SKIP - G.NEG_LIM - 10]) + b'\x4e\x71')
names = [t for t, _ in tm]
chk('Namen mit ! = Negationsstrich, mit %% = Prozent',
    all(names[p].startswith('!') == (G.stored(p) in G.NEGS) for p in range(N))
    and all(names[p].endswith('%') == (G.stored(p) in G.PRCS) for p in range(N)))

# ------------------------------------------------------------------ 5. Deskriptor
chk('Deskriptor 19 (Trig Cond) Max %d' % struct.unpack('>I', rd(IMG, G.DESC_MAX))[0],
    struct.unpack('>I', rd(IMG, G.DESC_MAX))[0] == (G.NCOND - 1) << 8 and struct.unpack('>I', rd(STK, G.DESC_MAX))[0] == 63 << 8)
done()
