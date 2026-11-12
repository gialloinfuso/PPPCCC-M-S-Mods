# strum (v2, smp23): Strum pro Spur im Sound fuer CHORD (Maschine 5) und Vlvt (7). Echter Firmware-Code im Emulator:
# Parameter-Suche, Anwendbarkeit, Knopf-Suche (FUNC + SHAPE / COLOR), Deskriptoren und Formatierer, Speichern im Sound-Satz,
# CHORD-Klang (ST am Ende des CHORD-Updates) gegen ein Python-Modell. Vlvt: test_strings (Modell str_model).
import random, struct
from rig import *
import g2_strum as G
import g2_lfoamount as LA

IMG = v2_image()
REF = v2_image([i for i in V2_IDS if i != 'strum'])
S, CS = V2SYM['strum'], V2SYM['core']
e1, e0 = Emu(IMG), Emu(REF)

# ---------------- 1 Parameter-Suche 0x4005a692 (Slot, Maschine)
bad = []
for slot in range(34):
    for m in range(9):
        a_, g1 = e1.call(0x4005A692, slot, m); w_, _ = e0.call(0x4005A692, slot, m)
        want = {(C.K_STIME, 5): 86, (C.K_SPAT, 5): 87, (C.K_STIME, 7): 88, (C.K_SPAT, 7): 89}.get((slot, m), w_)
        if a_ != want or not g1: bad.append((slot, m, a_, want))
chk('Parameter-Suche: k 24 / 27 auf CHORD = 86 / 87, auf Vlvt = 88 / 89, sonst wie ohne strum (Monom Glide / Noise) %s' % bad[:4], not bad)

# ---------------- 2 Deskriptoren 86..89
D = [struct.unpack('>14I', bytes(e1.u.mem_read(C.DTD(k), 0x38))) for k in range(86, 90)]
fx = [e1.r32(C.FMTX + 4 * (k - C.NDESC0)) for k in range(86, 90)]
chk('Deskriptoren 86..89: Feld 5, k 24 / 27, 0..127 / 0..8, Namen %s, Spender 1 / 2, Maschine 5 / 7, Formatierer TFMT / PFMT'
    % [e1.cstr(x[11]) for x in D],
    [x[:5] for x in D] == [(5, k, 0, top, 0) for k, top in ((24, 0x7F00), (27, (len(G.PATS) - 1) << 8)) * 2]
    and [e1.cstr(x[11]) for x in D] == ['Strum Time', 'Strum Pattern'] * 2 and [e1.cstr(x[13]) for x in D] == ['STIM', 'SPAT'] * 2
    and bytes(e1.u.mem_read(C.DONOR + 86 - C.NDESC0, 4)) == bytes([1, 2, 1, 2])
    and bytes(e1.u.mem_read(C.MACHMAP + 86 - C.NDESC0, 4)) == bytes([5, 5, 7, 7]) and fx == [S['TFMT'], S['PFMT']] * 2)
lk = [struct.unpack('>BBH', bytes(e1.u.mem_read(C.LKXT + 4 * (C.LKX_SLOT['strum'][0] + i), 4))) for i in range(4)]
chk('LKXT: %s' % lk, lk == [(5, 5, 86), (5, 4, 87), (7, 5, 88), (7, 4, 89)])

# Anwendbarkeit 0x4000aa9a(Objekt, Deskriptor): Objekt +4 -> Spur, vt +0x28 -> Sound (+38 Maschine) (wie test_strings)
OBJ, TRKO, VT, FN, SND = 0x4F04C000, 0x4F04C100, 0x4F04C200, 0x4F04C400, 0x4F04C500
def appl(e, m):
    e.w32(OBJ + 4, TRKO); e.w32(TRKO, VT); e.w32(VT + 0x28, FN)
    e.u.mem_write(FN, struct.pack('>HIH', 0x203C, SND, 0x4E75)); e.u.mem_write(SND + 38, bytes([m]))
    return [(e.call(0x4000AA9A, OBJ, k)[0] != 0) for k in range(96)]
bad = []
for m in range(9):
    a1, a0 = appl(e1, m), appl(e0, m)
    for k in range(96):
        want = (m == 5) if k in (86, 87) else (m == 7) if k in (88, 89) else a0[k]
        if a1[k] != want: bad.append((m, k, a1[k]))
chk('Anwendbarkeit: 86 / 87 nur auf CHORD, 88 / 89 nur auf Vlvt, alles andere wie ohne strum %s' % bad[:5], not bad)

# ---------------- 3 Knopf-Suche (echter Handler 0x4001e814 bis zum Firmware-Teil; Maschine der Spur gestubbt)
def emu_lk(img):
    e = Emu(img); e.mach = 0
    def body(u, a, z, _):
        sp = u.reg_read(mk.UC_M68K_REG_A7)
        u.reg_write(mk.UC_M68K_REG_D0, 50 + e.r32(sp + 0x3C)); u.reg_write(mk.UC_M68K_REG_PC, 0x4001E934)
    e.u.hook_add(UC_HOOK_CODE, body, begin=0x4001E81E, end=0x4001E81E)
    def mach(u, a, z, _):
        sp = u.reg_read(mk.UC_M68K_REG_A7); u.reg_write(mk.UC_M68K_REG_D0, e.mach)
        u.reg_write(mk.UC_M68K_REG_PC, e.r32(sp)); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
    e.u.hook_add(UC_HOOK_CODE, mach, begin=0x4001E318, end=0x4001E318)
    return e
k1, k0 = emu_lk(IMG), emu_lk(REF)
bad = []
for m in range(9):
    k1.mach = k0.mach = m
    for held in ((), (C.KEY_FUNC,)):
        k1.held = k0.held = set(held)
        for kn in range(16):
            for f in (0, 1):
                d1, g1 = k1.call(LA.LOOKUP, 0x4F042000, kn, f, -1); d0, _ = k0.call(LA.LOOKUP, 0x4F042000, kn, f, -1)
                want = {(5, 5): 86, (5, 4): 87, (7, 5): 88, (7, 4): 89}.get((m, kn), d0) if f else d0
                if d1 != want or not g1: bad.append((m, held, kn, f, d1, want))
chk('Knopf-Suche: FUNC + SHAPE / COLOR auf CHORD = 86 / 87, auf Vlvt = 88 / 89, alles andere wie ohne strum %s' % bad[:3], not bad)

# ---------------- 4 Formatierer (sprintf der Firmware) und Anzeige-Objekt (ST_AT setzt den Formatierer ein)
BUF = 0x4F04B800
def fmt(fn, v):
    e1.u.mem_write(BUF, bytes(32)); e1.call(fn, 0x4F04B700, v, BUF, count=200000); return e1.cstr(BUF)
# smp35: Abstand wie Delay Time mit Patch 04 (delay-notes): 0 = OFF, p = 1..127 -> Etikett oder p + 1; gegen den echten
# Formatierer von delay-notes im Image (Thunk 0x4004dfda mit dem Objekt der Delay Time, Deskriptor 37)
import importlib.util as _ilu
_sp = _ilu.spec_from_file_location('gdn', str(ROOT / 'solo' / 'gen_delaynotes.py')); _gdn = _ilu.module_from_spec(_sp)
sys.path.insert(0, str(ROOT / 'solo')); _sp.loader.exec_module(_gdn)
def dly(v):                                          # Etiketten: echter Code von delay-notes (Thunk -> Maske); Zahlen: Wert + 1
    if v not in _gdn.LABELS: return str(v + 1)       # (die Firmware zeigt Wert + 1, 0x4004dfda: +0x100, Zahlformatierer)
    e1.u.mem_write(BUF, bytes(32)); e1.call(0x4004DFDA, _gdn.THIS37, v << 8, BUF, count=200000); return e1.cstr(BUF)
tv = [fmt(S['TFMT'], v << 8) for v in range(128)]
want = ['OFF'] + [str((v * 250 + 55) // 110) for v in range(1, 111)] + [dly(p) for p in C.STRUM_NOTEP]
chk('smp36: Abstand 0 = OFF, 1..110 = ms (Zahl, 2..250), 111..127 = Notenwerte mit den Etiketten von delay-notes (echter Code) %s'
    % [(v, tv[v], want[v]) for v in range(128) if tv[v] != want[v]][:4],
    tv == want and want == [C.strum_text(v) for v in range(128)] and C.STRUM_LABELS == _gdn.LABELS
    and fmt(S['TFMT'], 0x7F80) == '1/1' and fmt(S['TFMT'], 0xFFFFFF00) == 'OFF' and len(C.STRUM_NOTEP) == 17)
from fractions import Fraction as _F
ok_len = all(_F(C.strum_units(p), 768) == _F(p + 1, 128) + (_F(1 if _gdn.TRIPLET_FIX[p] == 85 else 2, 3 * 128)
             if p in _gdn.TRIPLET_FIX else 0) for p in range(1, 128))
chk('Dauer der Notenwerte = Delay Time (p + 1) / 128 ganze Note, Triolen exakt (16T = 1/24 ... 1T = 2/3); ms: 250 ms = 3000 Achtel-Bloecke',
    ok_len and _F(C.strum_units(4), 768) == _F(1, 24) and _F(C.strum_units(84), 768) == _F(2, 3) and G.step8(110, 14400) == 3000
    and G.step8(110, 0) == 3000)
chk('/16 (Wert 115) bei 120 BPM = 1500 Achtel-Bloecke (125 ms); 1/1 bei 30 BPM ohne Ueberlauf',
    G.step8(115, 14400) == 1500 and G.step8(127, 3600) == C.STRUM_KC * 768 // 3600 and C.STRUM_KC * 768 < 2 ** 32)
pv = [fmt(S['PFMT'], v << 8) for v in range(11)]
chk('Pattern (smp37: + ROOT = 1-234, TOP = 4-123): %s' % pv, pv == list(G.PATS) + ['TOP', 'TOP']
    and G.RANKS[7] == (0, 1, 1, 1) and G.RANKS[8] == (1, 1, 1, 0))
ob = []
for d in (86, 87, 88, 89, 76):
    o, good = e1.call(0x4004DF40, d)
    ob.append((o, e1.r32(o + 0x20), e1.r32(o + 0x2C), good))
chk('ST_AT: Objekt 1 / 2 mit TFMT / PFMT (+0x2c = 0); 76 (Vlvt Octave Mix, kein FMTX) unveraendert %s' % [hex(x[1]) for x in ob],
    [x[0] for x in ob[:4]] == [0x40A71754 + 100 * i for i in (1, 2, 1, 2)] and [x[1] for x in ob[:4]] == [S['TFMT'], S['PFMT']] * 2
    and all(x[2] == 0 and x[3] for x in ob) and ob[4][1] not in (S['TFMT'], S['PFMT']))
sty = []
for d in (86, 87, 88, 89):
    o_ = 0x40A71754 + 100 * (1 + (d & 1)); e1.w32(o_ + 0x10, 0x40EA1494); e1.call(0x4004DF40, d); sty.append(e1.r32(o_ + 0x10))
o76 = e1.call(0x4004DF40, 76)[0]; s76 = e1.r32(o76 + 0x10); e1.w32(o76 + 0x10, 0x12345678); e1.call(0x4004DF40, 76)
chk('smp31: Darstellung (Objekt +0x10) der Firmware bleibt (STYX 0) fuer 86..89 und 76 %s'
    % [hex(x) for x in sty], sty == [0x40EA1494] * 4 and e1.r32(o76 + 0x10) == 0x12345678)

# ---------------- smp32: Schrift des Popup-Werts (0x4001d818, Haken 0x4001d8a8 -> PFONT) und alle Texte vollstaendig gezeichnet
def pfont(d):
    e1.u.reg_write(mk.UC_M68K_REG_D2, d); sp = STACK - 0x200; e1.u.reg_write(mk.UC_M68K_REG_A7, sp)
    e1.u.emu_start(0x4001D8A8, 0x4001D8AE, count=200)
    return e1.r32(e1.u.reg_read(mk.UC_M68K_REG_A7)), e1.u.reg_read(mk.UC_M68K_REG_A7) == sp - 4, e1.u.reg_read(mk.UC_M68K_REG_D2) == d
pf = [pfont(d) for d in (86, 87, 88, 89, 76, 45, 10)]
chk('Haken 0x4001d8a8 = jmp PFONT; Strum 86..89 schmale Schrift 0x40141b08, andere (76, 45, 10) die der Firmware 0x401429ec %s'
    % [hex(x[0]) for x in pf], IMG[0x4001D8A8 - BASE:][:6] == C.jmp(CS['PFONT'])
    and [x[0] for x in pf] == [C.FONT_NARROW] * 4 + [C.FONT_BIG] * 3 and all(x[1] and x[2] for x in pf))
BMP, DATA, FO, STR = 0x4F020400, 0x4F021000, 0x4F020600, 0x4F03F800
e1.call(0x400E7D50, count=2000000)
def draw(font, text):
    e1.u.mem_write(BMP, struct.pack('>IIIII', 0, 128, 64, 2, DATA)); e1.u.mem_write(DATA, bytes(1024))
    e1.u.mem_write(FO, bytes(64)); e1.call(0x40072260, FO, font, count=200000)
    e1.u.mem_write(STR, text.encode() + b'\0')
    e1.call(0x40071A04, BMP, FO, 0x60, 0x22, 2, 0x40124B58, STR, count=2000000)
    raw = bytes(e1.u.mem_read(DATA, 1024))
    cols = [x for x in range(128) if any(raw[(x * 2) * 4:(x * 2 + 2) * 4])]
    return raw, (cols[0], cols[-1]) if cols else None
def full(font, text):                                   # letztes Zeichen gezeichnet: anders als mit Leerzeichen dort, und links frei vom Namensfeld
    a, bb = draw(font, text); b, _ = draw(font, text[:-1] + ' '); return a != b and bb[0] >= 64 and bb[1] <= 127, bb
texts = [fmt(S['TFMT'], v << 8) for v in range(128)] + list(G.PATS)
rn = [full(C.FONT_NARROW, t) for t in texts]
rb = full(C.FONT_BIG, '1/12')
chk('Popup in der schmalen Schrift: alle Abstands- und Pattern-Texte vollstaendig, x 64..127 %s; grosse Schrift: 4. Zeichen von'
    ' 1/12 fehlt (Pips Foto) %s' % ([t for t, r in zip(texts, rn) if not r[0]], rb), all(r[0] for r in rn) and not rb[0])

# ---------------- 5 Sound-Satz: +80 / +81 <-> k 24 / 27 (Sound-Slot 3 des Cores, ATH)
e = Emu(IMG); RECB, SNDB = 0x4F040000, 0x4F040100
h = e.r32(CS['SSLOTS'] + 4 * C.SSLOT['core-attack'])
e.u.mem_write(RECB, bytes(100)); e.u.mem_write(SNDB, bytes(100))
for k, v in ((23, 0x5A00), (24, 0x7B00), (27, 0x0500)): e.u.mem_write(SNDB + 20 + 2 * k, struct.pack('>H', v))
e.call(h, regs={mk.UC_M68K_REG_A0: RECB, mk.UC_M68K_REG_A1: SNDB, mk.UC_M68K_REG_D1: 1})
sv = bytes(e.u.mem_read(RECB + 80, 7))
e.u.mem_write(SNDB, bytes(100)); e.call(h, regs={mk.UC_M68K_REG_A0: RECB, mk.UC_M68K_REG_A1: SNDB, mk.UC_M68K_REG_D1: 0})
ld = [struct.unpack('>H', bytes(e.u.mem_read(SNDB + 20 + 2 * k, 2)))[0] for k in (23, 24, 27)]
chk('Sound-Satz: speichern -> +80 = %#x, +81 = %#x, +86 = %#x; laden -> %s' % (sv[0], sv[1], sv[6], [hex(x) for x in ld]),
    h == CS['ATH'] and (sv[0], sv[1], sv[6]) == (0x7B, 0x05, 0x5A) and ld == [0x5A00, 0x7B00, 0x0500])

# ---------------- 6 CHORD: ST am Ende des CHORD-Updates gegen das Modell
chk('Haken: ST / G0F; Parameter-Suche 0x4005a6d0 = Core PSX (smp37), Eintraege von strum in PSXT',
    IMG[G.ST_HOOK - BASE:][:6] == C.jmp(S['ST']) and IMG[G.R_HOOK - BASE:][:6] == C.jsr(S['G0F'])
    and IMG[G.PS_HOOK - BASE:][:6] == C.jmp(CS['PSX'])
    and [struct.unpack('>BBH', IMG[C.PIMG(C.PSXT) + 4 * i - BASE:][:4]) for i in range(4)]
    == [(5, 24, 86), (5, 27, 87), (7, 24, 88), (7, 27, 89)])
VOICE0, VSTEP = 0x42308828, 0x31C
PARB = 0x4F049000
SAVED = [0xD2000002, 0xD3000003, 0xD4000004, 0xD5000005, 0x0, 0xA3000003, 0xA4000004]
es = Emu(IMG); es.u.mem_map(0x42300000, 0x30000)
M32 = 0xFFFFFFFF
def s32(x): x &= M32; return x - (1 << 32) if x & 0x80000000 else x
OWN = V2SYM['core']['OWN']
def run_st(voice, trig, gains, tm, pat, tempo, atk=0, m=0x80000000, gate=0, fst=1):
    u = es.u
    es.w32(C.TEMPO, tempo)
    u.mem_write(PARB, bytes(128)); u.mem_write(PARB + 2 * C.K_STIME, bytes([tm])); u.mem_write(PARB + 2 * C.K_SPAT, bytes([pat]))
    u.mem_write(PARB + 2 * C.K_EXT0, bytes([atk]))
    u.mem_write(voice + 0x38, struct.pack('>I', 1 if trig else 0)); u.mem_write(voice + 0x0C, struct.pack('>3i', *gains))
    es.w32(voice + 0x250, m); es.w32(voice + 0x24C, gate); es.w32(voice + 0x23C, fst)
    sp = 0x4F008000; sv = SAVED[:]; sv[4] = voice
    u.mem_write(sp, b'\xEE' * 8 + struct.pack('>7I', *sv) + struct.pack('>I', RET))
    u.reg_write(mk.UC_M68K_REG_A7, sp); u.reg_write(mk.UC_M68K_REG_A2, voice); u.reg_write(mk.UC_M68K_REG_A3, PARB)
    u.reg_write(mk.UC_M68K_REG_D6, 0xD6D6D6D6); u.reg_write(mk.UC_M68K_REG_D7, 0xD7D7D7D7)
    u.mem_write(OWN, bytes(6))
    u.emu_start(S['ST'], RET, count=20000)
    regs = [u.reg_read(r) for r in (mk.UC_M68K_REG_D2, mk.UC_M68K_REG_D3, mk.UC_M68K_REG_D4, mk.UC_M68K_REG_D5, mk.UC_M68K_REG_A2, mk.UC_M68K_REG_A3, mk.UC_M68K_REG_A4)]
    good = (regs == sv and u.reg_read(mk.UC_M68K_REG_A7) == sp + 40 and u.reg_read(mk.UC_M68K_REG_D6) == 0xD6D6D6D6
            and u.reg_read(mk.UC_M68K_REG_D7) == 0xD7D7D7D7 and u.reg_read(mk.UC_M68K_REG_PC) == RET)
    vi = (voice - VOICE0) // VSTEP if 0 <= voice - VOICE0 < 6 * VSTEP and (voice - VOICE0) % VSTEP == 0 else -1
    if vi >= 0:   # Spur-Huellkurve flach, Attack des Cores fuer die Spur aus
        good &= es.r32(voice + 0x250) == 0x80000000 and bytes(u.mem_read(OWN, 6)) == bytes(1 if k == vi else 0 for k in range(6))
    return list(struct.unpack('>3i', bytes(u.mem_read(voice + 0x0C, 12)))), es.r32(G.G0), good


FULL = 1 << 31
def emul(e, f):
    eh, el, fh, fl = e >> 16, e & 0xFFFF, f >> 16, f & 0xFFFF
    return (((eh * fl + el * fh) & M32) >> 15) + 2 * eh * fh & M32
def ainc(a):
    d = a * a * 96000 // 16129
    return FULL if d < 32 else ((FULL // d) << 5) & M32


class Model:
    def __init__(s):
        s.cnt = [0] * 6; s.rnk = [[0] * 4 for _ in range(6)]; s.rng = 0x2545F491
        s.stg = [[0] * 4 for _ in range(6)]; s.env = [[0] * 4 for _ in range(6)]
    def perm(s, p):
        if p > len(G.PATS) - 1: p = 0
        if p != G.P_RND: return list(G.RANKS[p])
        a = [0, 1, 2, 3]
        for j in (3, 2, 1):
            s.rng = (s.rng * 1664525 + 1013904223) & 0xFFFFFFFF
            r = ((s.rng >> 16) * (j + 1)) >> 16
            a[j], a[r] = a[r], a[j]
        return a
    def st(s, i, trig, gains, tm, pat, tempo, atk=0, m=0x80000000, gate=0, fst=1):
        if trig: s.cnt[i] = 0; s.rnk[i] = s.perm(pat); s.stg[i] = [0] * 4
        elif s.cnt[i] < 0xFFFF: s.cnt[i] += 1
        step = G.step8(tm, tempo); c = s.cnt[i]
        f = (-m) & M32
        held = gate != 0 and (c == 0 or fst != 1)
        g = list(gains); g0 = None; E, st = s.env[i], s.stg[i]
        for j in range(4):
            on = ((s.rnk[i][j] * step) & M32) >> 3; d = c - on
            if d < 0:
                x = E[j] - (E[j] >> 2); E[j] = x if x >= C.STRUM_FADE_MIN else 0; st[j] = 0   # smp39: ausblenden
            elif st[j] == 0:
                full = False
                if atk == 0:
                    if on == 0 or d >= 2: full = True
                    else: E[j] = 0x20000000 if d == 0 else 0x40000000
                else:
                    x = E[j] + ainc(atk)
                    if x >= FULL: full = True
                    else: E[j] = x
                if full: E[j] = FULL; st[j] = 1 if held else 2
            elif st[j] == 1:
                if not held: st[j] = 2
            else: E[j] = emul(E[j], f)
            e = E[j]
            if j == 0: g0 = 0x20000000 if e >= FULL else e >> 2
            elif e < FULL: g[j - 1] = s32((s32(g[j - 1]) >> 15) * (e >> 16))
        return g, g0


M = Model(); random.seed(23); same, regs, seen = True, True, set()
bad = []
DEC = [0x80000000, 0xFFFFFFFF, 0x85F830BF, 0x800A0F01, 0x8128BC79, 0xC0000000]
for bl in range(4000):
    if bl % 200 == 0:
        tm = random.choice([0, 1, 2, 5, 20, 60, 120, 121, 123, 125, 127, 200, 255]); pat = random.choice([0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9, 255])
        tempo = random.choice([14400, 3600, 36000, 0, 7777]); atk = random.choice([0, 0, 1, 5, 20, 64, 127, 200]); m = random.choice(DEC)
        gate = random.choice([0, 1])
    fst = random.choice([0, 1, 2]) if random.random() < 0.05 else (1 if not gate else 2)
    for i in range(6):
        trig = random.random() < 0.04; gains = [random.randint(-2**31, 2**31 - 1) for _ in range(3)]
        g, g0, good = run_st(VOICE0 + i * VSTEP, trig, gains, tm, pat, tempo, atk, m, gate, fst)
        w, w0 = M.st(i, trig, gains, tm, pat, tempo, atk, m, gate, fst)
        if (g, g0) != (list(w), w0): bad.append((bl, i, tm, pat, tempo, atk, hex(m), gate, fst, g, hex(g0), w, hex(w0))); same = False
        regs &= good
        if trig and pat in (2,): seen.add(tuple(es.u.mem_read(S['RNK'] + 4 * i, 4)))
chk('CHORD: 4000 Bloecke x 6 Stimmen wie das Modell (Abstand, Pattern, RND, Attack, Decay-Faktor, GATE halten / loslassen) %s' % bad[:1], same)
chk('CHORD: Epilog, Register (d6 / d7 unberuehrt), Stack ok; Spur-Decay flach (0x250 = 0x80000000), OWN der Spur gesetzt', regs)
chk('CHORD RND: %d verschiedene Reihenfolgen, alle Permutationen' % len(seen), len(seen) >= 12 and all(sorted(x) == [0, 1, 2, 3] for x in seen))
g, g0, good = run_st(0x4F000000, True, [5, 6, 7], 60, 0, 14400)
chk('Keine Stimme der Spuren (a2 ausserhalb): Pegel unveraendert, Grundton voll', g == [5, 6, 7] and g0 == 0x20000000 and good)
# Beispiel UP, Wert 111 (= /64, 12 Einheiten) bei Tempo 216000 (= 25 / 8 = 3.125 Bloecke je Rang), Attack 0, kein Decay:
# Op 1 / 2 / 3 bei Block 3 / 6 / 9, Grundton sofort voll
# smp39: Retrigger mit Strum: klingende Toene blenden vor ihrem Einsatz * 3/4 je Block aus (Pip: Knacken), nicht sofort 0
es.u.mem_write(G.M_ENV, struct.pack('>4I', *([0x80000000] * 4)) + bytes(80))
fd = []
for b in range(32):
    g, g0, _ = run_st(VOICE0, b == 0, [1 << 20] * 3, 115, 0, 180000)
    fd.append([x >> 4 for x in g])
want = [0x80000000]
for _ in range(32):
    x = want[-1] - (want[-1] >> 2); want.append(x if x >= C.STRUM_FADE_MIN else 0)
chk('Retrigger, Strum /16: Op 3 vor seinem Einsatz 1 -> 3/4 -> 9/16 ... (unter %#x aus), kein Sprung auf 0 %s'
    % (C.STRUM_FADE_MIN, [x[2] for x in fd[:8]]),
    [x[2] for x in fd] == [(32 * (w >> 16)) >> 4 for w in want[1:33]] and fd[0][2] > 0 and fd[28][2] == 0)
for i in range(6): run_st(VOICE0 + i * VSTEP, False, [1, 1, 1], 0, 0, 14400)
es.u.mem_write(G.M_ENV, bytes(96))                                   # smp39: vorige Toene still (sonst blenden sie erst aus)
on = []
for b in range(14):
    g, g0, _ = run_st(VOICE0, b == 0, [1 << 20] * 3, 111, 0, 216000)
    on.append(([x >> 18 for x in g], g0 >> 26))
chk('UP, Wert 111 (/64): Op 1..3 setzen bei 3 / 6 / 9 ein (1/4, 1/2, voll), Grundton sofort voll %s' % on[:10],
    [x[0] for x in on[2:11]] == [[0, 0, 0], [1, 0, 0], [2, 0, 0], [4, 0, 0], [4, 1, 0], [4, 2, 0], [4, 4, 0], [4, 4, 1], [4, 4, 2]]
    and all(x[1] == 8 for x in on))
# Decay je Ton: mit Strum klingt jeder Ton ab seinem Einsatz aus (Decay-Faktor 0x85f830bf), Strum 0 = alle gleich
def curve(tm, n=40):
    for i in range(6): run_st(VOICE0 + i * VSTEP, False, [1, 1, 1], 0, 0, 14400)
    es.u.mem_write(G.M_ENV, bytes(96))
    out = []
    for b in range(n):
        g, g0, _ = run_st(VOICE0, b == 0, [1 << 30] * 3, tm, 0, 180000, 0, 0x85F830BF)
        out.append([g0 << 2] + [x << 1 for x in g])
    return out
c0, c5 = curve(0), curve(115)
chk('Decay je Ton (Faktor 0x85f830bf): Strum 0 alle Toene gleich und fallend; Strum 115 (/16, 48 Einheiten, Tempo 180000: 15 Bloecke je Rang): Ton 2 setzt bei 15 ein und ist '
    'bei 30 lauter als der Grundton, Ton 4 bei 30 noch still', all(len({x >> 16 for x in r}) == 1 for r in c0)
    and all(c0[b][0] > c0[b + 1][0] for b in range(30)) and c5[14][1] == 0 and c5[15][1] > 0 and c5[30][1] > c5[30][0] and c5[30][3] == 0)
done()
