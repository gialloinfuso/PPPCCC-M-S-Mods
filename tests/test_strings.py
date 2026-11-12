# strings (v2, Patch 20, smp14): 8. Maschine 'Strng'. Echter Firmware-Code im Emulator wie test_sampler (statische
# Initialisierung, Zeilen-Konstruktor, Stimmen-Schleife), Vergleich mit dem Image ohne strings.
# 1. Anmeldung: Zeilen (8), Parameter-Suche, Maschinen-Saetze, Knopf -> Deskriptor, MACHINES-Bilder + 8 Positionen, Namen,
#    Grenzen, update / render, Anwendbarkeit (0x4000aa9a), lange Namen (0x4000b22a), Rad / Setzen mit dem echten Code.
# 2. Stimme gegen das Ganzzahl-Modell (str_model): Akkorde, Unisono, Mono, COLOR / SWEEP / CONTOUR, PITCH / Noten, Strum,
#    Wechsel; Vollaussteuerung, kein Knacken an Bloecken, Kosten; Maschinen 0..6 unveraendert.
# 3. Hoerbeispiel (Ausgang vor dem VCA, mit einfacher Huellkurve) als WAV, wenn ein Pfad angegeben ist.
# Aufruf: test_strings.py [--wav pfad]
import math, random, struct, sys, wave
from rig import *
import g2_strings as G
import g2_sampler as SM
import str_model as SMOD
import cfemac
sys.path.insert(0, str(ROOT / 'Modded-Cycles' / 'tools' / 'emu'))
import emac as MEMAC

NOMONO = [i for i in V2_IDS if i != 'mono']           # smp18: mono (9. Maschine) baut auf strings auf: eigener Test
IMG = v2_image(NOMONO)
REF = v2_image([i for i in NOMONO if i != 'strings'])
S, SS = V2SYM['strings'], V2SYM['sampler']
SM.build(); G.build()
OPS = cfemac.ops()
WAV = sys.argv[sys.argv.index('--wav') + 1] if '--wav' in sys.argv else None
TASK = 0x4F04F800


def boot(img, emac=False):
    e = Emu(img)
    e.u.mem_map(0x42300000, 0x30000)
    e.u.mem_map(0x43800000, 0x800000)
    e.u.mem_map(0x422F0000, 0x10000)
    e.w32(SM.RUNNING, TASK)
    if emac:
        m = MEMAC.EMAC(e.u); m.install(OPS); e.mac = m
    e.call(0x4000045C, count=2000000)
    e.call(0x400DE244, count=20000000)
    e.call(0x4005A274, count=5000000)
    for t in range(6):
        e.w32(0x42308828 + 0x31C * t + 0x318, 0x8000BD98 + 0x30 * t)
    return e


def r32s(e, a, n): return list(struct.unpack('>%dI' % n, bytes(e.u.mem_read(a, 4 * n))))


# ---------------- 1 Anmeldung
e1, e0 = boot(IMG), boot(REF)
rows0, rows1 = r32s(e0, SS['ROWS7'], 56), r32s(e1, S['ROWS8'], 64)
chk('Zeilen 0..6 wie ohne strings (Grit in 6), Zeile 7 = Decay 75, -, eigene 76..79 (Konstruktor): %s' % rows1[56:],
    rows1[:56] == rows0 and rows1[56:] == [75, 0, 76, 77, 78, 79, 0, 0])
D = [struct.unpack('>14I', bytes(e1.u.mem_read(C.DTD(k), 0x38))) for k in range(76, 80)]
chk('Eigene Deskriptoren 76..79 in der Tabelle des Cores: Feld 6, Slot 11..14, Bereiche / Defaults, Namen %s' % [e1.cstr(x[11]) for x in D],
    [x[:5] for x in D] == [(6, sl, 0, top, df) for _, _, sl, top, df, _, _ in G.KNOBS] and [e1.cstr(x[11]) for x in D] == list(G.NAMES_L)
    and [e1.cstr(x[13]) for x in D] == [x[1] for x in G.KNOBS]
    and bytes(e1.u.mem_read(C.DONOR, 4)) == bytes([71, 72, 73, 74]) and bytes(e1.u.mem_read(C.MACHMAP, 4)) == bytes([7] * 4))
chk('Verweise auf die Zeilen: alle 5 auf die Nutzlast', all(e1.r32(v) == S['ROWS8'] for v in SM.ROW_REFS))
bad = []
for slot in range(34):
    for m in range(8):
        a_, _ = e1.call(0x4005A692, slot, m)
        want = e0.call(0x4005A692, slot, m)[0] if m < 7 else {11: 76, 12: 77, 13: 78, 14: 79, 18: 75, C.K_STIME: 88, C.K_SPAT: 89}.get(slot, e0.call(0x4005A692, slot, 5)[0] if not 11 <= slot <= 14 else 0)
        if a_ != want: bad.append((slot, m, a_, want))
chk('Parameter-Suche (Slot 0..33, Maschine 0..7): 0..6 wie ohne strings, Vlvt = 76..79, Decay 75, Strum 88 / 89 %s' % bad[:4], not bad)
bad = [i for i in range(96) if e1.call(0x4005A556, i)[0] != (e0.call(0x4005A556, i)[0] or 76 <= i <= 79)]
chk('"Deskriptor einer Maschine?" unveraendert, dazu 76..79 %s' % bad, not bad)
recs0 = [r32s(e0, e0.call(0x4004DF5C, n)[0], 19) for n in range(8)]
recs1 = [r32s(e1, e1.call(0x4004DF5C, n)[0], 19) for n in range(9)]
r9 = recs1[8]
chk('Maschinen-Saetze 0..7 wie ohne strings; 8 = eigener (R9) aus dem von CHORD, 71..74 -> 76..79: %s' % r9[2:8],
    recs1[:8] == recs0 and e1.call(0x4004DF5C, 8)[0] == S['R9'] and r9[:2] == recs0[6][:2]
    and r9[2:] == [{71: 76, 72: 77, 73: 78, 74: 79}.get(x, x) for x in recs0[6][2:]] and e1.r8(S['R9'] + 76) == 1)
of = [e1.call(0x4004DF76, m)[0] for m in range(9)]; of0 = [e0.call(0x4004DF76, m)[0] for m in range(9)]
chk('Satz der Maschine: 0..6 wie ohne strings, 7 = R9, 8 wie ohne %s' % [hex(x) for x in of],
    of[:7] == of0[:7] and of[7] == S['R9'] and of[8] == of0[8])
def knobs(e, m):
    VW = 0x4F047000; VEC = 0x4F047800
    e.u.mem_write(VEC, struct.pack('>6I', *range(1, 7))); e.w32(VW + 0x68, VEC)
    out = []
    for kn in range(2, 16):
        for f in (0, 1):
            d0, good = e.call(0x4001E814, VW, kn, f, -1, count=200000)
            out.append(d0 if good else 'X')
    return out
for e in (e0, e1):
    for t, v in ((0x4001E318, None), (0x4006B736, 0), (0x400CF9A8, 0x4F046000)):
        e.u.hook_add(UC_HOOK_CODE, lambda u, a, z, _, e=e, v=v: (u.reg_write(mk.UC_M68K_REG_D0, e.mach if v is None else v),
                     u.reg_write(mk.UC_M68K_REG_PC, e.r32(u.reg_read(mk.UC_M68K_REG_A7))),
                     u.reg_write(mk.UC_M68K_REG_A7, u.reg_read(mk.UC_M68K_REG_A7) + 4)), begin=t, end=t)
kk = {}
for m in range(8):
    e0.mach = e1.mach = m
    kk[m] = (knobs(e0, m), knobs(e1, m))
chk('Knoepfe der Maschinen 0..6 wie ohne strings', all(kk[m][0] == kk[m][1] for m in range(7)))
chk('Knoepfe Vlvt = die von CHORD mit 76..79, FUNC + SHAPE / COLOR Strum 88 / 89: %s' % kk[7][1][0:12:2], kk[7][1] == [{71: 76, 72: 77, 73: 78, 74: 79, 86: 88, 87: 89}.get(x, x) for x in kk[5][0]])
def images(img, m):
    e = Emu(img); calls = []
    e.u.mem_write(0x4F048000, bytes(0x400)); e.w32(SM.ICON_A, 0x4F048000); e.w32(SM.ICON_B, 0x4F048200)
    def spr(u, a, z, _):
        sp = u.reg_read(mk.UC_M68K_REG_A7); calls.append(tuple(e.r32(sp + 4 + 4 * i) for i in range(5)))
        u.reg_write(mk.UC_M68K_REG_PC, e.r32(sp)); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
    e.u.hook_add(UC_HOOK_CODE, spr, begin=SM.SPRITE, end=SM.SPRITE)
    sp = STACK - 0x400; e.u.mem_write(sp, bytes(0x100)); e.u.reg_write(mk.UC_M68K_REG_A7, sp)
    e.u.reg_write(mk.UC_M68K_REG_D3, m); e.u.reg_write(mk.UC_M68K_REG_D4, m); e.u.reg_write(mk.UC_M68K_REG_D2, 0x4F049000)
    e.u.emu_start(0x400A2638, 0x400A2680, count=10000)
    return calls, e.u.reg_read(mk.UC_M68K_REG_A7) - sp, e.u.reg_read(mk.UC_M68K_REG_D3)
ok_ = all(images(IMG, m) == images(REF, m) for m in range(7))
c7, d7_, r7 = images(IMG, 7); c5, d5_, _ = images(REF, 5)
chk('MACHINES-Bilder: 0..6 wie ohne strings; Vlvt = grosses Bild von CHORD + eigenes Icon (VBM), Stapel wie die Firmware, d3 (Maschine) bleibt 7',
    ok_ and c7[0] == c5[0] and c7[1] == c5[1][:1] + (S['VBM'],) + c5[1][2:] and d7_ == d5_ and r7 == 7 and len(c7) == 2
    and r32s(e1, S['VBM'], 6) == [C.BITMAP_VT, 34, 34, 2, S['VICON'], SM.ICON_MASK]
    and bytes(e1.u.mem_read(S['VICON'], 272)) == C.icon(G.ICON_FILE)[2])
def marks(img, cur):
    e = Emu(img); xs = []
    def dr(u, a, z, _):
        sp = u.reg_read(mk.UC_M68K_REG_A7); xs.append((e.r32(sp + 8), a == 0x40070EFC))
        u.reg_write(mk.UC_M68K_REG_PC, e.r32(sp)); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
    for t in (0x40070C4E, 0x40070EFC): e.u.hook_add(UC_HOOK_CODE, dr, begin=t, end=t)
    sp = STACK - 0x400; e.u.mem_write(sp, bytes(0x100)); e.u.reg_write(mk.UC_M68K_REG_A7, sp)
    e.u.reg_write(mk.UC_M68K_REG_D3, cur); e.u.reg_write(mk.UC_M68K_REG_D2, 0x4F049000)
    e.u.emu_start(0x400A26A2, 0x400A26F2, count=20000)
    return xs
mk8, mk7 = marks(IMG, 7), marks(REF, 6)
chk('MACHINES: 8 Positionen ab x = 73 (Abstand 7, letzte bei %d < 128), die 8. gefuellt (Strng); ohne strings 7 ab 80'
    % mk8[-1][0], [x for x, _ in mk8] == [73 - 4 + 7 * i for i in range(8)] and [f for _, f in mk8] == [False] * 7 + [True]
    and [x for x, _ in mk7] == [80 - 4 + 7 * i for i in range(7)])
nm = [e1.cstr(e1.r32(S['NAMES8'] + 4 * i)) for i in range(8)]
chk('Namen der Maschinen: %s; Verweis 0x400a2614 auf die neue Tabelle' % nm,
    nm == ['Kick', 'Snare', 'Metal', 'Perc', 'Tone', 'Chord', 'Grit', 'Vlvt'] and e1.r32(SM.NAMES_REF) == S['NAMES8'])
chk('Grenzen: Algorithm bis 7, Stimmen-Schleife / Rad / Setzen / Bild / Suche bis 7, 8 Positionen, Byte 7 der Maschinen-Tabelle',
    e1.r32(SM.ALG_MAX) == 0x700 and all(IMG[va - BASE:va - BASE + 2] == struct.pack('>H', n + 1) for va, _, n in SM.BOUNDS if va in G.B7)
    and IMG[0x4005A340 - BASE:0x4005A342 - BASE] == REF[0x4005A340 - BASE:0x4005A342 - BASE]
    and IMG[0x4005A572 - BASE:0x4005A574 - BASE] == REF[0x4005A572 - BASE:0x4005A574 - BASE] and IMG[G.MAP7 - BASE] == 7
    and IMG[G.MAP7 - 1 - BASE] == 6)
upd, rnd = r32s(e1, S['UPD8'], 8), r32s(e1, S['RND8'], 8)
chk('update / render: 0..6 wie ohne strings, 7 = Strng; Verweise der Stimmen-Schleife',
    upd[:7] == r32s(e0, SS['UPD7'], 7) and rnd[:7] == r32s(e0, SS['RND7'], 7) and upd[7] == S['SUPD8'] and rnd[7] == S['SRND8']
    and e1.r32(SM.UPD_REF) == S['UPD8'] and e1.r32(SM.RND_REF) == S['RND8'])
# Anwendbarkeit 0x4000aa9a(Objekt, Deskriptor): Objekt +4 -> Spur, vt +0x28 -> Sound (+38 Maschine)
OBJ, TRKO, VT, FN, SND = 0x4F04C000, 0x4F04C100, 0x4F04C200, 0x4F04C400, 0x4F04C500
def appl(e, m):
    e.w32(OBJ + 4, TRKO); e.w32(TRKO, VT); e.w32(VT + 0x28, FN)
    e.u.mem_write(FN, struct.pack('>HIH', 0x203C, SND, 0x4E75)); e.u.mem_write(SND + 38, bytes([m]))
    out = []
    for k in range(96):
        d0, good = e.call(0x4000AA9A, OBJ, k)
        out.append((d0 != 0, good))
    return out
bad = []
for m in range(8):
    a1, a0 = appl(e1, m), appl(e0, m)
    for k in range(96):
        want = (a0[k][0] if k < 76 or k >= 86 else False) or (m == 7 and 76 <= k <= 79) or (m == 7 and k in (88, 89))
        if a1[k][0] != want or not a1[k][1]: bad.append((m, k))
chk('Anwendbarkeit (96 Deskriptoren x 8 Maschinen): 0..75 wie ohne strings, 76..79 / 88 / 89 nur auf Vlvt, 86.. sonst wie ohne strings, Rest nie, Register ok %s' % bad[:5], not bad)
def lname(e, m, k, track=2):
    KIT = 0x4F04D000; e.w32(SM.KITP, KIT); e.w32(SM.ACT_TRACK, track)
    e.u.mem_write(KIT, bytes(700)); e.u.mem_write(KIT + 28 + 100 * track + 38, bytes([m]))
    d0, good = e.call(0x4000B22A, 0x4F04C000, k)
    return e.cstr(d0), good
ln1 = [lname(e1, 7, k) for k in (70, 71, 72, 73, 74, 75, 10, 76, 77, 78, 79, 80, 95, 96)]
ln0 = [lname(e0, 7, k) for k in (70, 71, 72, 73, 74, 75, 10)]
chk('Lange Namen (Firmware-Zugriff 0x4000b22a ueber die Tabelle): 0..75 wie ohne strings, 76..79 %s, 80 / 95 Error, 96 = 0'
    % [x for x, _ in ln1[7:11]], ln1[:7] == ln0 and [x for x, _ in ln1[7:11]] == list(G.NAMES_L) and ln1[11][0] == ln1[12][0] == ln0[0][0].__class__('Error')
    and ln1[13][0] == 'Error' and all(g for _, g in ln1) and max(len(w) for n in G.NAMES_L for w in n.split()) <= 8)
# Rad / Setzen mit dem echten Code (wie test_sampler)
TRK, TVT, TSND, TCODE, THIS = 0x4F04E000, 0x4F04E100, 0x4F04E400, 0x4F04E800, 0x4F04EC00
def track_emu(img, machine):
    e = boot(img)
    e.w32(TRK, TVT)
    e.u.mem_write(TCODE, struct.pack('>HIH', 0x203C, TSND, 0x4E75) + struct.pack('>HH', 0x7000, 0x4E75))
    for k in range(16): e.w32(TVT + 4 * k, TCODE + (0 if k == 10 else 8))
    snd = bytearray(b'\x55' * 100); snd[38:40] = struct.pack('>H', machine << 8); e.u.mem_write(TSND, bytes(snd))
    for k in range(6): e.w32(THIS + 0x70 + 4 * k, 0xFFFFFFFF)
    rets = {0x400CF866: 0x4F04F000, 0x4000EB90: 0x4F04F000, 0x40012412: 0, 0x400CF9A8: 0x4F04F000, 0x4006BDFE: 0,
            0x4000EB9C: 0x4F04F000, 0x40009C1A: TRK, 0x400F44C6: 0, 0x4001416C: 0, 0x40013126: 0}
    for a_, v in rets.items():
        e.u.hook_add(UC_HOOK_CODE, lambda u, a, z, _, v=v: (u.reg_write(mk.UC_M68K_REG_D0, v),
                     u.reg_write(mk.UC_M68K_REG_PC, e.r32(u.reg_read(mk.UC_M68K_REG_A7))),
                     u.reg_write(mk.UC_M68K_REG_A7, u.reg_read(mk.UC_M68K_REG_A7) + 4)), begin=a_, end=a_)
    return e
def mach(e): return e.r8(TSND + 38)
def wheel_seq(img, steps, start=4):
    e = track_emu(img, start); out = []; ok = True
    for st in steps:
        try:
            _, good = e.call(0x400A2712, THIS, st, 0, 0, count=2000000)
        except Exception:
            good = False
        ok &= good; out.append(mach(e))
    return e, out, ok
e7, seq7, ok7 = wheel_seq(IMG, [1, 1, 1, 1, 1, -1, 1, -1, -1])
e6, seq6, ok6 = wheel_seq(REF, [1, 1, 1, 1, 1, -1, 1, -1, -1])
chk('MACHINES-Rad (echter Code, TONE +1 x5, -1, +1, -1 x2): %s, ohne strings %s' % (seq7, seq6),
    seq7 == [5, 6, 7, 7, 7, 6, 7, 6, 5] and seq6 == [5, 6, 6, 6, 6, 5, 6, 5, 4] and ok7 and ok6)
w = lambda b, k: struct.unpack('>H', b[20 + 2 * k:22 + 2 * k])[0]
e = track_emu(IMG, 5); e.call(0x4001477E, TRK, 7, 0, 0, count=2000000); sd7 = bytes(e.u.mem_read(TSND, 100))
e = track_emu(REF, 4); e.call(0x4001477E, TRK, 5, 0, 0, count=2000000); sd5 = bytes(e.u.mem_read(TSND, 100))
chk('  Defaults von Vlvt = eigene (COLOR %#x, SHAPE %#x, SWEEP %#x, CONTOUR %#x), Decay von CHORD %#x'
    % tuple(w(sd7, k) for k in (11, 12, 13, 14, 18)), sd7[38] == 7 and [w(sd7, k) for k in (11, 12, 13, 14)] == [x[4] for x in G.KNOBS]
    and w(sd7, 18) == w(sd5, 18))
bad = []
for a_ in range(8):
    for b_ in range(8):
        res = []
        for img in (IMG, REF):
            e = track_emu(img, a_ if img is IMG or a_ < 7 else 5)
            try:
                _, good = e.call(0x4001477E, TRK, b_, 0, 0, count=2000000)
            except Exception:
                good = False
            res.append((good, bytes(e.u.mem_read(TSND, 100))))
        (g1, s1), (g0, s0) = res
        if not g1 or (a_ < 7 and b_ < 7 and (s1 != s0 or not g0)) or s1[38] != b_:
            bad.append((a_, b_))
chk('Setzen 0x4001477e fuer alle Wechsel 0..7 -> 0..7: 0..6 wie ohne strings, Strng hin und zurueck %s' % bad[:6], not bad)

# ---------------- 2 Stimme (Stimmen-Schleife der Firmware; Amp-Huellkurve / VCA gestubbt, Ausgang davor mitgeschrieben)
PAR, OUT, PMOD = 0x4F04A000, 0x80001858, 0x80001830
DEF = {10: 0x4000, 11: 0x2000, 12: 0x0300, 13: 0x2B00, 14: 0x1800, 15: 0, 16: 0, 17: 0x4000, 18: 0x4000, C.K_EXT0: 0, C.K_STIME: 0, C.K_SPAT: 0}
ST = lambda tm, pat=0: {C.K_STIME: tm << 8, C.K_SPAT: pat << 8}                 # smp23: Strum k 24 / 27 im Sound
RAMS = lambda t: 0x43180000 + 0x1200 * t                                         # Zustand der Spur (G.RAM, G.TSTR)


def vloop(img, blocks, par=None, notes=None, trig_at=(1,), tempo=14400, per_block=None, machines=(7, 7, 7, 7, 7, 7), count_ins=False, perms=None,
          fst=None, g24c=None):
    e = boot(img, emac=True)
    caught = {t: [] for t in range(6)}
    for t_ in (SM.AMPENV, SM.VCA):
        e.u.mem_write(t_, b'\x4e\x75')
        def cb(u, a, z, _, t_=t_):
            sp = u.reg_read(mk.UC_M68K_REG_A7)
            if t_ == SM.VCA:
                v = e.r32(sp + 8); tr = (v - 0x42308828) // 0x31C
                caught[tr].append(list(struct.unpack('>32i', bytes(e.u.mem_read(e.r32(sp + 4), 128)))))
        e.u.hook_add(UC_HOOK_CODE, cb, begin=t_, end=t_)
    for f in SM.UPD_ORIG + SM.RND_ORIG:
        e.u.mem_write(f, b'\x4e\x75')
    e.w32(C.TEMPO, tempo)
    for t in range(6):
        p = PAR + 14 + 66 * t
        vals = dict(DEF); vals[9] = machines[t] << 8
        vals.update((par or {}).get(t, {}))
        for k, v in vals.items(): e.u.mem_write(p + 2 * k, struct.pack('>H', v & 0xffff))
        e.w32(PMOD + 4 * t, (notes or {}).get(t, 60 << 16))
    n_ins = [0]
    if count_ins:
        e.u.hook_add(UC_HOOK_CODE, lambda u, a, z, _: n_ins.__setitem__(0, n_ins[0] + 1), begin=G.ORG, end=G.ORG + G.ROOM)
    cnt = []
    for b in range(blocks):
        e.u.mem_write(OUT, bytes(6 * 128))
        trig = 0x3F if (b in trig_at and b >= 2) or b == 0 else 0      # Block 0: Trig = Maschinenwechsel der Stimme (setzt sie zurueck)
        for t, kv in ((per_block or {}).get(b) or {}).items():
            for k, v in kv.items():
                if k == 'note': e.w32(PMOD + 4 * t, v)
                else: e.u.mem_write(PAR + 14 + 66 * t + 2 * k, struct.pack('>H', v & 0xffff))
        if fst is not None:                                                 # smp44: Stufe der Firmware (+0x23c; AMPENV ist gestummt)
            for t in range(6): e.w32(0x42308828 + 0x31C * t + 0x23C, fst(b))
        e.mac.macsr = 0xA0
        n0 = n_ins[0]
        d0, good = e.call(0x400A7D4A, OUT, PAR, trig, 0, count=4000000)
        cnt.append(n_ins[0] - n0)
        assert good
        if g24c is not None: g24c.append([e.r32(0x42308828 + 0x31C * t + 0x24C) for t in range(6)])
        if perms is not None and b >= 1:                                    # Raenge nach dem Block (RND: was der Code gemischt hat)
            for t in range(6): perms[t].append(list(e.u.mem_read(RAMS(t) + G.T['PERM'], 4)))
    return e, caught, cnt


def model_run(blocks, par=None, notes=None, trig_at=(1,), tempo=14400, per_block=None, track=0, perms=None, fst=None):
    v = SMOD.Voice(STOCK, track)
    pr = dict(DEF); pr.update((par or {}).get(track, {}))
    note = (notes or {}).get(track, 60 << 16)
    out = []
    for b in range(blocks):                              # Block 0: Maschinenwechsel der Stimme (die Firmware setzt sie zurueck, kein update / render)
        for k, x in ((per_block or {}).get(b) or {}).get(track, {}).items():
            if k == 'note': note = x
            else: pr[k] = x
        if b == 0: continue
        # Die Stimmen-Schleife legt den Trig-Wunsch eines Blocks erst im naechsten Block an die Stimme (+0x38): Block 0 (Wechsel
        # der Maschine) -> Trig in Block 1, Wunsch in b >= 2 -> Trig in b + 1 (der Pruefstand setzt in Block 1 keinen Wunsch)
        g = (pr.get(16, 0) >> 8) & 0xFF; g = g - 256 if g > 127 else g
        v.update(pr, note, b == 1 or (b - 1 >= 2 and (b - 1) in trig_at), tempo, perms[track][b - 1] if perms else None,
                 g, fst(b) if fst else 0)
        out.append(v.render())
    return out, v


def cmp(nm, blocks, **kw):
    pm = {t: [] for t in range(6)}
    e, caught, _ = vloop(IMG, blocks, perms=pm, **kw)
    ok_, err = True, 0
    for t in (0, 3):
        ref, _ = model_run(blocks, track=t, perms=pm, **{k: v for k, v in kw.items() if k != 'machines'})
        got = caught[t]
        if len(got) != blocks - 1 or len(ref) != blocks - 1: ok_ = False; continue
        err = max(err, max(abs(a - b) for x, y in zip(got, ref) for a, b in zip(x, y)))
    pk = max(abs(a) for x in caught[0] for a in x) / 2 ** 31
    chk('%s: %d Bloecke, Spur 1 / 4 gegen das Modell (groesste Abweichung %d LSB), Spitze %.3f' % (nm, blocks, err, pk), ok_ and err <= 64)
    return caught


P0 = {t: {} for t in range(6)}
cmp('Standard (CHORD-Defaults: Moll, COLOR 32, SWEEP 43, CONTOUR 24)', 60)
cmp('Mono, COLOR 0, Ensemble aus', 40, par={t: {12: 0, 11: 0, 14: 0} for t in range(6)})
cmp('Unisono x4, COLOR 127 (nur 4\'), hell, Ensemble voll', 50, par={t: {12: 0x200, 11: 0x7F00, 13: 0x7F00, 14: 0x7F00} for t in range(6)})
cmp('Maj7 (SHAPE 10), Note 36 / 96, PITCH +12, FINE', 40, par={t: {12: 0xA00, 10: 0x4C00, 17: 0x4800} for t in range(6)},
    notes={t: (36 if t < 3 else 96) << 16 for t in range(6)})
cmp('Strum 40 (83 ms) UP, Trig bei 1 und 30', 70, par={t: ST(40, 0) for t in range(6)}, trig_at=(1, 30))
cmp('Strum 20 DOWN, Unisono x2 (fehlende Toene uebersprungen)', 60, par={t: {**ST(20, 1), 12: 0x100} for t in range(6)})
cmp('Strum /64 (Wert 111, Tempo 120) 4132', 110, par={t: ST(111, 5) for t in range(6)})
cmp('Strum 1/32 (Tempo 300) 1423, Unisono x2', 90, par={t: {**ST(124, 4), 12: 0x100} for t in range(6)}, tempo=36000)
cmp('Strum 10 ms 1324, Abstand p-lock im Spiel', 70, par={t: ST(5, 3) for t in range(6)}, per_block={30: {t: ST(30, 3) for t in range(6)}})
cmp('Strum RND 16, Trigs bei 1, 20, 40, 60', 80, par={t: ST(16, 2) for t in range(6)}, trig_at=(1, 20, 40, 60))
pm = {t: [] for t in range(6)}
vloop(IMG, 100, par={t: ST(16, 2) for t in range(6)}, trig_at=tuple(range(1, 100, 4)), perms=pm)
seen = {tuple(x) for t in range(6) for x in pm[t]}
chk('RND: Raenge immer eine Permutation, %d verschiedene Reihenfolgen aus 6 x 25 Trigs' % len(seen),
    all(sorted(x) == [0, 1, 2, 3] for x in seen) and len(seen) >= 12)
pm = {t: [] for t in range(6)}
NP = len(C.STRUM_PATS); PS6 = (0, 1, 4, 7, 8, 9)                     # smp37: 7 = ROOT (1-234), 8 = TOP (4-123)
vloop(IMG, 6, par={t: ST(16, p) for t, p in enumerate(PS6)}, perms=pm)
chk('Pattern -> Raenge wie die Tabelle (ROOT / TOP, Wert > %d = UP) %s' % (NP - 1, [pm[t][-1] for t in range(6)]),
    all(pm[t][-1] == list(C.STRUM_RANKS[p if p < NP else 0]) for t, p in enumerate(PS6)) and pm[3][-1] == [0, 1, 1, 1] and pm[4][-1] == [1, 1, 1, 0])
cmp('Strum 60 ms ROOT / TOP', 70, par={t: ST(29, 7 + (t & 1)) for t in range(6)})
cmp('smp24 Huellkurve je Ton: Decay 20, Strum 30 UP', 120, par={t: {**ST(30, 0), 18: 0x1400} for t in range(6)})
cmp('smp24 Huellkurve je Ton: Attack 40, Decay 90, Strum 12 DOWN, Trigs 1 / 70', 140, par={t: {**ST(12, 1), C.K_EXT0: 0x2800, 18: 0x5A00} for t in range(6)},
    trig_at=(1, 70))
cmp('smp24 Huellkurve je Ton: Attack 127, Decay 0, ohne Strum', 60, par={t: {C.K_EXT0: 0x7F00, 18: 0} for t in range(6)})
cmp('Strum 1/16 bei Tempo 0 (= alle zusammen), Wert 200 (= 1/8T) bei 30 BPM', 40, par={t: ST(126 if t < 3 else 200, 0) for t in range(6)}, tempo=0)
cmp('Wechsel im Spiel: SHAPE 37 -> 0 -> 20, COLOR, SWEEP, CONTOUR 0 -> 127 -> 0, Note', 80,
    per_block={10: {t: {12: 0x2500} for t in range(6)}, 25: {t: {12: 0, 11: 0x7F00, 14: 0x7F00} for t in range(6)},
               40: {t: {12: 0x1400, 13: 0x0000, 'note': 48 << 16} for t in range(6)}, 55: {t: {14: 0, 13: 0x7F00} for t in range(6)}})
# Vollaussteuerung: 4 Toene gleichphasig ist nicht moeglich (Phasen versetzt); hohe Werte fuer alles -> keine Spruenge
# smp44: GATE (Byte 32 = k 16): Akkordtoene halten nach dem Attack, bis die Firmware loslaesst (Stufe +0x23c = 1), dann Decay
REL = lambda r: (lambda b: 1 if b >= r else 2)
g24 = []
vloop(IMG, 4, par={t: {16: (t & 1) << 8} for t in range(6)}, g24c=g24)
chk('smp44 GATE: die Stimmen-Schleife legt GATE an die Stimme (+0x24c), Vlvt loescht es nicht mehr: %s' % g24[-1], [x != 0 for x in g24[-1]] == [False, True] * 3)
cmp('smp44 GATE an, Decay 20, Strum 30 UP, losgelassen bei 60', 120, par={t: {**ST(30, 0), 16: 0x100, 18: 0x1400} for t in range(6)}, fst=REL(60))
cmp('smp44 GATE an, Attack 40, Decay 90, Strum 12 DOWN, los bei 50, neuer Trig 70 (Stufe 0), los bei 100', 140,
    par={t: {**ST(12, 1), 16: 0x100, C.K_EXT0: 0x2800, 18: 0x5A00} for t in range(6)}, trig_at=(1, 70),
    fst=lambda b: 1 if 50 <= b < 71 or b >= 100 else (0 if b in (71, 72) else 2))
cmp('smp44 GATE an, ohne Strum, nie losgelassen', 80, par={t: {16: 0x100, 18: 0x1400} for t in range(6)}, fst=lambda b: 2)
cmp('smp44 GATE an, Strum 1/16 (Wert 126), losgelassen im Strum (Block 3)', 60, par={t: {**ST(126, 0), 16: 0x100, 18: 0x2000} for t in range(6)},
    fst=REL(3))
cmp('smp44 GATE an im Spiel ein / aus (p-lock), Decay 30', 100, par={t: {18: 0x1E00} for t in range(6)}, trig_at=(1, 40, 70),
    per_block={30: {t: {16: 0x100} for t in range(6)}, 60: {t: {16: 0} for t in range(6)}}, fst=REL(55))
_, cg, _ = vloop(IMG, 80, par={t: {16: (t & 1) << 8, 18: 0x1400} for t in range(6)}, fst=lambda b: 2)
lv = lambda t, b: max(abs(x) for x in cg[t][b])
chk('smp44 GATE haelt: Block 70 Spur ohne GATE %.4f, mit GATE %.4f (Block 10: %.4f / %.4f)' % (lv(0, 70) / 2 ** 31, lv(1, 70) / 2 ** 31,
    lv(0, 10) / 2 ** 31, lv(1, 10) / 2 ** 31), lv(1, 70) > 0.6 * lv(1, 10) and lv(0, 70) < 0.25 * lv(0, 10))
cc = cmp('Vollaussteuerung: Fifths, Note 108, COLOR 64, SWEEP 127, CONTOUR 127', 40,
         par={t: {12: 0x2500, 11: 0x4000, 13: 0x7F00, 14: 0x7F00} for t in range(6)}, notes={t: 108 << 16 for t in range(6)})
# Bloecke: keine Unstetigkeit an den Grenzen (2. Differenz an der Grenze nicht groesser als im Block)
e, caught, _ = vloop(IMG, 40, par={t: {12: 0, 11: 0, 13: 0x2000, 14: 0x4000} for t in range(6)}, notes={t: 48 << 16 for t in range(6)})
y = [a for x in caught[0][5:] for a in x]
d2 = [abs(y[i - 1] - 2 * y[i] + y[i + 1]) for i in range(1, len(y) - 1)]
inb = max(d2[i] for i in range(len(d2)) if (i + 1) % 32 not in (0, 31)); at = max(d2[i] for i in range(len(d2)) if (i + 1) % 32 in (0, 31))
chk('Mono 48, dunkel: an den Blockgrenzen keine Spruenge (2. Differenz %.2e, im Block %.2e)' % (at / 2 ** 31, inb / 2 ** 31), at <= 1.5 * inb)
# Spektrum: Saegezahn bandbegrenzt (polyBLEP): Spiegelungen deutlich unter dem Grundton
import numpy as np
e, caught, _ = vloop(IMG, 160, par={t: {12: 0, 11: 0, 13: 0x7F00, 14: 0} for t in range(6)}, notes={t: 100 << 16 for t in range(6)})
y = np.array([a for x in caught[0][10:] for a in x], float) / 2 ** 31
f0 = 440 * 2 ** ((100 - 69) / 12)
spec = np.abs(np.fft.rfft(y * np.hanning(len(y)))); fr = np.fft.rfftfreq(len(y), 1 / 48000)
harm = [abs(f - round(f / f0) * f0) < 30 for f in fr]
pk0 = spec[np.argmin(abs(fr - f0))]
alias = max(spec[i] for i in range(len(fr)) if not harm[i] and fr[i] > 200)
chk('Note 100 (%.0f Hz), Mono 8\', offen: Spiegelungen %.1f dB unter dem Grundton' % (f0, 20 * math.log10(pk0 / alias)), 20 * math.log10(pk0 / alias) > 40)
# Ensemble wirkt: Hullkurve der Amplitude eines Sinus-aehnlichen Tons schwankt mit CONTOUR 127, nicht mit 0
def wobble(c):
    e, caught, _ = vloop(IMG, 1500, par={t: {12: 0, 11: 0, 13: 0x0000, 14: c, 18: 0x7F00} for t in range(6)}, notes={t: 69 << 16 for t in range(6)})
    y = np.array([a for x in caught[0][20:] for a in x], float)
    env = np.array([np.sqrt(np.mean(y[i:i + 2400] ** 2)) for i in range(0, len(y) - 2400, 2400)])   # 22 Perioden von 440 Hz
    x = np.arange(len(env)); env = env / np.exp(np.polyval(np.polyfit(x, np.log(env), 1), x))   # smp24: Decay je Ton herausrechnen
    return (max(env) - min(env)) / np.mean(env)
w0, w1 = wobble(0), wobble(0x7F00)
chk('Ensemble: Pegelschwankung (Schwebung) bei CONTOUR 0 %.3f, bei 127 %.3f' % (w0, w1), w0 < 0.02 and w1 > 0.05)
# andere Maschinen unberuehrt: Stimmen-Schleife ruft fuer 0..6 dieselben update / render wie ohne strings
def dispatch(img):
    e = boot(img, emac=True); tr = []
    fs = list(SM.UPD_ORIG + SM.RND_ORIG) + [SS['SUPD'], SS['SRND']]
    for f in fs:
        e.u.mem_write(f, b'\x4e\x75')
        def cb(u, a, z, _, f=f):
            sp = u.reg_read(mk.UC_M68K_REG_A7); tr.append((f,) + tuple(e.r32(sp + 4 + 4 * i) for i in range(3)))
        e.u.hook_add(UC_HOOK_CODE, cb, begin=f, end=f)
    for b in range(9):
        for t in range(6):
            e.u.mem_write(PAR + 14 + 66 * t + 18, struct.pack('>H', ((t + b // 3) % 7) << 8))
        e.mac.macsr = 0xA0; e.call(0x400A7D4A, OUT, PAR, 0x3F if b % 3 == 0 else 0, 0, count=2000000)
    return tr
t1, t0 = dispatch(IMG), dispatch(REF)
chk('Stimmen-Schleife, Maschinen 0..6 (auch Wechsel): %d Aufrufe wie ohne strings' % len(t1), t1 == t0 and len(t1) == 9 * 12)
# Kosten
for nm, par in (('Akkord 4 Toene, 8\' + 4\', Ensemble', {t: {12: 0x300, 11: 0x4000, 14: 0x4000} for t in range(6)}),
                ('Mono, nur 8\', ohne Ensemble', {t: {12: 0, 11: 0, 14: 0} for t in range(6)}),
                ('Standard (CHORD-Defaults)', None)):
    e, caught, cnt = vloop(IMG, 6, par=par, count_ins=True)
    per = max(cnt[2:]) / 6
    chk('Kosten %s: %d Befehle je Spur und Block (ohne Huellkurve / VCA)' % (nm, per), per < 7500)
    if nm.startswith('Standard'): COST = per

# ---------------- 3 Hoerbeispiel
if WAV:
    seq = [('Standard: Moll, COLOR 32, SWEEP 43, CONTOUR 24', {}, 57, 0),
           ('Ensemble aus', {14: 0}, 57, 0), ('Ensemble voll', {14: 0x7F00}, 57, 0),
           ('Maj7, 8\'+4\', hell, Ensemble voll', {12: 0xA00, 11: 0x4000, 13: 0x5A00, 14: 0x7F00}, 60, 0),
           ('m7, Strum 60 ms UP', {12: 0x700, 11: 0x6000, 13: 0x3C00, 14: 0x7F00, **ST(29, 0)}, 55, 0),
           ('m7, Strum 1/32 DOWN', {12: 0x700, 11: 0x6000, 13: 0x3C00, 14: 0x7F00, **ST(124, 1)}, 55, 0),
           ('Mono tief, nur 8\'', {12: 0, 11: 0, 13: 0x2000, 14: 0x7F00}, 43, 0),
           ('Unisono x4, 4\'', {12: 0x200, 11: 0x7F00, 13: 0x4000, 14: 0x6000}, 62, 0)]
    pcm = []
    for nm, p, note, sr in seq:
        nb = int(2.4 * 48000 / 32)
        e, caught, _ = vloop(IMG, nb, par={0: p}, notes={0: note << 16})
        y = np.array([a for x in caught[0] for a in x], float) / 2 ** 31
        t = np.arange(len(y)) / 48000
        env = np.minimum(1, t / 0.25) * np.where(t < 1.8, 1, np.exp(-(t - 1.8) * 7))
        pcm.append(y * env); pcm.append(np.zeros(int(0.35 * 48000)))
    y = np.concatenate(pcm)
    with wave.open(WAV, 'wb') as wv:
        wv.setnchannels(1); wv.setsampwidth(2); wv.setframerate(48000)
        wv.writeframes(np.int16(np.clip(y, -1, 1) * 32767).tobytes())
    print('WAV', WAV, '%.1f s, Spitze %.2f' % (len(y) / 48000, max(abs(y))))
chk('smp41: Vlvt ruft nach dem VCA DCK des Samplers (Uebergang beim neuen Akkord)', IMG.count(b'\x4e\xb9' + struct.pack('>I', V2SYM['sampler']['DCK'])) == 2)
done()
