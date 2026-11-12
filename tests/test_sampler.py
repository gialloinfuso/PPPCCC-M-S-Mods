# sampler (v2, Patch 16): 7. Maschine 'Sampl'. Echter Firmware-Code im Emulator (statische Initialisierung 0x400de244,
# Zeilen-Konstruktor 0x4005a274, Stimmen-Schleife 0x400a7d4a), Vergleich mit dem Image ohne sampler.
# 1. Anmeldung: Zeilen, Parameter-Suche (Slot, Maschine), 'Maschine?', Maschinen-Saetze, Knopf -> Deskriptor, MACHINES-Bild,
#    Formatierer des Modells.
# 2. Stimme: Clean (lineare Interpolation) bitgenau, Modelle SP / LM gegen ein Ganzzahl-Modell des Rasters + Biquads in float;
#    Loop, Reverse, Start / Length, Ende, Vollaussteuerung, Filter-Entwurf, Spiegeltoene, CONTOUR -> Modell, Kosten;
#    die anderen 5 Spuren (Maschinen 0..5) bitgleich zum Image ohne sampler.
# 3. Laden (Dateisystem gestubbt): Kopf, Mono / Stereo, Tabelle, Uebersicht, Fehl-Ring, Browser-Wahl zuerst, Spuren des Kits.
# 4. Browser: Sampl-Spur + Sample -> eigener Sound (shared_ptr), Kennung, Name; Preset / andere Spur -> Firmware.
# 5. Sound speichern / laden: Kennung ueber den Sound-Slot des Cores.  6. Maschinenwechsel mit dem echten Code.
# 7. Wellenform beim Drehen von Start / Length (echte Zeichenfunktionen) und alle Faelle, in denen die Firmware zeichnet.
# 8. Sample-Lock nur fuer das Sample (SLK, Stimme mit OVR, Laden der Lock-Samples).  9. Browser: Cursor setzt das Sample (KCUR).
# Aufruf: test_sampler.py [--alone]   (--alone: nur Core + sampler)
import math, random, struct, sys
from rig import *
import g2_sampler as G
import cfemac
sys.path.insert(0, str(ROOT / 'Modded-Cycles' / 'tools' / 'emu'))
import emac as MEMAC

ALONE = '--alone' in sys.argv
NOSTR = [i for i in V2_IDS if i not in ('strings', 'mono')]        # smp14: strings (8. Maschine) baut auf dem Sampler auf: eigener Test
IMG = v2_image(['core', 'sampler'], latch=False) if ALONE else v2_image(NOSTR)
REF = v2_image(['core'], latch=False) if ALONE else v2_image([i for i in NOSTR if i != 'sampler'])
S = V2SYM['sampler']
G.build()
OPS = cfemac.ops()
# Jeder Aufruf (Firmware und eigener Code) muss d2-d7 / a2-a6 und den Stapel erhalten (C-Aufrufkonvention der Firmware)
BADCALL = []
_call = Emu.call
def _chk_call(s, entry, *a, **k):
    d0, good = _call(s, entry, *a, **k)
    if not good: BADCALL.append(hex(entry))
    return d0, good
Emu.call = _chk_call
TASK = 0x4F04F800                                     # die laufende Task (Attrappe)


def boot(img, emac=False):
    e = Emu(img)
    e.u.mem_map(0x42300000, 0x30000)                  # Stimmen
    e.u.mem_map(0x43800000, 0x800000)                 # Arbeitsbereich + Anfang des Sample-Speichers (8 MB)
    e.u.mem_map(0x422F0000, 0x10000)                  # laufende Task (0x422fef30)
    e.w32(G.RUNNING, TASK)
    if emac:
        m = MEMAC.EMAC(e.u); m.install(OPS); e.mac = m
    e.call(0x4000045C, count=2000000)                 # SRAM aus dem Image (Tabellen der Klangerzeugung)
    e.call(0x400DE244, count=20000000)                # statische Initialisierung (Maschinen-Saetze, UI-Objekte)
    e.call(0x4005A274, count=5000000)                 # Zeilen-Konstruktor
    for t in range(6):                                # Stimmen: SRAM-Puffer wie beim Start der Klangerzeugung
        e.w32(0x42308828 + 0x31C * t + 0x318, 0x8000BD98 + 0x30 * t)
    return e


def r32s(e, a, n): return list(struct.unpack('>%dI' % n, bytes(e.u.mem_read(a, 4 * n))))


# ---------------- 1 Anmeldung
e1, e0 = boot(IMG), boot(REF)
rows0, rows1 = r32s(e0, G.ROWS, 48), r32s(e1, S['ROWS7'], 56)
chk('Zeilen 0..5 wie ohne sampler, Zeile 6 = Decay 24, -, Start 10, Length 11, Filter 12, Modell 13: %s' % rows1[48:],
    rows1[:48] == rows0 and rows1[48:] == [24, 0, 10, 11, 12, 13, 0, 0])
chk('Verweise auf die Zeilen: alle 5 auf die Maske', all(e1.r32(v) == S['ROWS7'] for v in G.ROW_REFS))
bad = []
for slot in range(34):
    for m in range(7):
        a_, _ = e1.call(0x4005A692, slot, m); b_, _ = e0.call(0x4005A692, slot, m)
        want = b_ if m < 6 else {11: 10, 12: 11, 13: 12, 14: 13, 18: 24}.get(slot, b_ if not 11 <= slot <= 14 else 0)
        if a_ != want: bad.append((slot, m, a_, want))
chk('Parameter-Suche (Slot 0..33, Maschine 0..6): 0..5 wie ohne sampler, Sampl: Start / Length / Modell / Decay %s' % bad[:4], not bad)
bad = [i for i in range(80) if e1.call(0x4005A556, i)[0] != (e0.call(0x4005A556, i)[0] or i in (10, 11, 12, 13))]
chk('"Deskriptor einer Maschine?" wie ohne sampler, dazu 10, 11, 13 %s' % bad, not bad)
recs0 = [r32s(e0, e0.call(0x4004DF5C, n)[0], 19) for n in range(7)]
recs1 = [r32s(e1, e1.call(0x4004DF5C, n)[0], 19) for n in range(8)]
r8 = recs1[7]
chk('Maschinen-Saetze 0..6 wie ohne sampler; 7 = Sampl: %s' % r8[2:],
    recs1[:7] == recs0 and r8[2:] == [42, 24, 10, 11, 12, 13] + recs0[2][8:] and e1.call(0x4004DF5C, 7)[0] == S['R8'])
chk('  Texte des Sampl-Satzes = die von SNARE (Kopier-Konstruktor)', r8[:2] == recs0[2][:2])
of = [e1.call(0x4004DF76, m)[0] for m in range(8)]; of0 = [e0.call(0x4004DF76, m)[0] for m in range(8)]
chk('Satz der Maschine: 0..5 wie ohne sampler, 6 = Sampl, 7 wie ohne %s' % [hex(x) for x in of],
    of[:6] == of0[:6] and of[6] == S['R8'] and of[7] == of0[7])
objs = lambda e, i: (e.r32(G.OBJ_BASE + 100 * i + 32), e.r32(G.OBJ_BASE + 100 * i + 44))
chk('UI-Objekte 10, 11 wie SNARE 51, 52; 13 = eigener Formatierer, 12 (Filter) = Formatierer OFF der Firmware',
    [objs(e1, i) for i in (10, 11)] == [objs(e1, i) for i in (51, 52)] and objs(e1, 13) == (S['MFMT'], 0) and objs(e1, 12) == (G.FMT_OFF, 0))
BUF = 0x4F04B800
fm = []
for w in (0, 0x100, 0x200, 0x17F, 0x7F00, 0xFFFFFF00):
    e1.u.mem_write(BUF, bytes(32)); e1.call(S['MFMT'], 0x4F04B700, w, BUF, count=200000); fm.append(e1.cstr(BUF))
chk('Formatierer des Modells (sprintf der Firmware): %s' % fm, fm == ['CLN', 'SP', 'LM', 'SP', G.MSHORT[-1], 'CLN'] and len(G.MSHORT) == G.NMOD and max(map(len, G.MSHORT)) <= 3)
# Knopf -> Deskriptor (0x4001e814): Maschine der Spur gestubbt (0x4001e318), kein Trig gehalten (0x4006b736 -> 0)
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
for m in range(7):
    e0.mach = e1.mach = m
    kk[m] = (knobs(e0, m), knobs(e1, m))
chk('Knoepfe der Maschinen 0..5 wie ohne sampler', all(kk[m][0] == kk[m][1] for m in range(6)))
k6 = kk[6][1][0::2]
chk('Knoepfe Sampl: PITCH 42, DECAY 24, COLOR 10, SHAPE 11, SWEEP 12, CONTOUR 13 (ohne sampler alles 0: %s) -> %s'
    % (kk[6][0][0:12:2], k6[:6]), k6[:6] == [42, 24, 10, 11, 12, 13] and k6[6:] == kk[2][1][0::2][6:])
# MACHINES-Bild ab 0x400a2638 (Bilder der Maschine), Halt 0x400a2680; Text-Argumente (28 B) liegen auf dem Stapel
def images(img, m):
    e = Emu(img); calls = []
    e.u.mem_write(0x4F048000, bytes(0x400)); e.w32(G.ICON_A, 0x4F048000); e.w32(G.ICON_B, 0x4F048200)
    def spr(u, a, z, _):
        sp = u.reg_read(mk.UC_M68K_REG_A7); calls.append(tuple(e.r32(sp + 4 + 4 * i) for i in range(5)))
        u.reg_write(mk.UC_M68K_REG_PC, e.r32(sp)); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
    e.u.hook_add(UC_HOOK_CODE, spr, begin=G.SPRITE, end=G.SPRITE)
    sp = STACK - 0x400; e.u.mem_write(sp, bytes(0x100)); e.u.reg_write(mk.UC_M68K_REG_A7, sp)
    e.u.reg_write(mk.UC_M68K_REG_D3, m); e.u.reg_write(mk.UC_M68K_REG_D4, m); e.u.reg_write(mk.UC_M68K_REG_D2, 0x4F049000)
    e.u.emu_start(0x400A2638, 0x400A2680, count=10000)
    return calls, e.u.reg_read(mk.UC_M68K_REG_A7) - sp
ok = all(images(IMG, m) == images(REF, m) for m in range(6))
c6, dsp = images(IMG, 6); c1, dsp1 = images(REF, 1)
gw, gh, gpic = C.icon(G.ICON_FILE)
chk('MACHINES-Bilder: 0..5 wie ohne sampler; Grit = grosses Bild von SNARE + eigenes Icon (Bitmap-Objekt GBM, Stapel %+d wie die Firmware)' % dsp,
    ok and c6[0] == c1[0] and c6[1] == c1[1][:1] + (S['GBM'],) + c1[1][2:] and dsp == dsp1 and len(c6) == 2)
chk('  Icon-Objekt GBM: Vtable der Bitmap-Klasse, 34 x 34, 2 Langworte je Spalte, Bild = Pips Grafik, Maske der Firmware',
    r32s(e1, S['GBM'], 6) == [C.BITMAP_VT, 34, 34, 2, S['GICON'], G.ICON_MASK] and bytes(e1.u.mem_read(S['GICON'], 272)) == gpic
    and (gw, gh) == (34, 34) and sum(bin(b).count('1') for b in gpic) > 200)
nm = [e1.cstr(e1.r32(S['NAMES7'] + 4 * i)) for i in range(7)]
chk('Namen der Maschinen: %s; Verweis 0x400a2614 auf die neue Tabelle' % nm,
    nm == ['Kick', 'Snare', 'Metal', 'Perc', 'Tone', 'Chord', 'Grit'] and e1.r32(G.NAMES_REF) == S['NAMES7'])
chk('Grenzen: Algorithm bis 6, Stimmen-Schleife / Rad / Setzen / Bild bis 6, 7 Positionen, Byte 6 der Maschinen-Tabelle',
    e1.r32(G.ALG_MAX) == 0x600 and all(IMG[va - BASE:va - BASE + 2] == struct.pack('>H', n) for va, _, n in G.BOUNDS)
    and IMG[G.MAP6 - BASE] == 6)
d = [struct.unpack('>14I', IMG[G.DESC0 + G.DSTRIDE * k - BASE:][:0x38]) for k in (10, 11, 13, 12)]
chk('Deskriptoren 10 / 11 / 13 / 12: Maschine 6, Slot 11 / 12 / 14 / 13, 0..127 / 0..127 / 0..%d / 0..127, Default 0 / 127 / 0 / 64, ohne CC; Namen %s'
    % (G.NMOD - 1, [e1.cstr(x[11]) for x in d]),
    [x[:5] for x in d] == [(6, 11, 0, 0x7F00, 0), (6, 12, 0, 0x7F00, 0x7F00), (6, 14, 0, (G.NMOD - 1) << 8, 0), (6, 13, 0, 0x7F00, 0x4000)] and all(x[6] == 0xFFFFFFFF for x in d)
    and [e1.cstr(x[11]) for x in d] == ['Sample Start', 'Sample End', 'Model', 'Filter'] and [e1.cstr(x[13]) for x in d][2] == 'MODL')
upd, rnd = r32s(e1, S['UPD7'], 7), r32s(e1, S['RND7'], 7)
chk('update / render: 0..5 = Firmware-Tabelle, 6 = Sampl; Verweise der Stimmen-Schleife',
    upd[:6] == list(G.UPD_ORIG) == r32s(e1, G.UPD_TAB, 6) and rnd[:6] == list(G.RND_ORIG) == r32s(e1, G.RND_TAB, 6)
    and upd[6] == S['SUPD'] and rnd[6] == S['SRND'] and e1.r32(G.UPD_REF) == S['UPD7'] and e1.r32(G.RND_REF) == S['RND7'])

# ---------------- 2 Stimme (Stimmen-Schleife der Firmware; Amp-Huellkurve / VCA gestubbt, Ausgang davor mitgeschrieben)
PAR, OUT, PMOD = 0x4F04A000, 0x80001858, 0x80001830
POOL = G.POOL0
SID = 0x12345679


KITV = 0x4F04D800                                    # Kit der Klangerzeugung (0x800017e4 -> Kit, Sound t = +28 + 100 t)
SID2, POOL2 = 0x2345678B, G.POOL0 + 0x40000


def kit_audio(e, machines, ids):
    e.w32(G.KITA, KITV); e.u.mem_write(KITV, bytes(28 + 600))
    for t in range(6):
        e.u.mem_write(KITV + 28 + 100 * t + 38, bytes([machines[t]])); e.w32(KITV + 28 + 100 * t + G.O_ID, ids[t])


def vloop(img, machines, blocks, smp=None, par=None, notes=None, trig_at=(0,), stub_amp=True, seed=3, smp2=None, ovr=None, per_block=None, hooks=()):
    e = boot(img, emac=True)
    pass                   # Stimmen zuruecksetzen
    caught = []
    if stub_amp:
        for t in (G.AMPENV, G.VCA):
            e.u.mem_write(t, b'\x4e\x75')
            def cb(u, a, z, _, t=t):
                sp = u.reg_read(mk.UC_M68K_REG_A7)
                if t == G.VCA: caught.append(list(struct.unpack('>32i', bytes(e.u.mem_read(e.r32(sp + 4), 128)))))
            e.u.hook_add(UC_HOOK_CODE, cb, begin=t, end=t)
    for a_, fn in hooks: e.u.hook_add(UC_HOOK_CODE, fn, begin=a_, end=a_)
    for f in G.UPD_ORIG + G.RND_ORIG:                  # Maschinen 0..5 der Firmware: hier nicht gebraucht
        e.u.mem_write(f, b'\x4e\x75')
    if smp is not None:
        data = struct.pack('>%dh' % len(smp), *smp) + bytes(32)
        e.u.mem_write(POOL, data)
        e.u.mem_write(S['TAB'], struct.pack('>4I', SID, POOL, len(smp), 65536))
    for t in range(6):
        p = PAR + 14 + 66 * t
        vals = {9: machines[t] << 8, 10: 0x4000, 11: 0, 12: 0x7F00, 13: 0x4000, 14: 0, 15: 0, 16: 0, 17: 0x4000, 18: 0x7F00}
        vals.update((par or {}).get(t, {}))
        for k, v in vals.items(): e.u.mem_write(p + 2 * k, struct.pack('>H', v & 0xffff))
        e.w32(PMOD + 4 * t, ((notes or {}).get(t, 60)) << 16)
        e.w32(G.TGT0 + 66 * t + 2 * G.K_ID, SID if machines[t] == 6 else 0)
    kit_audio(e, machines, [SID if m == 6 else 0 for m in machines])
    if smp2 is not None:
        e.u.mem_write(POOL2, struct.pack('>%dh' % len(smp2), *smp2) + bytes(32))
        e.u.mem_write(S['TAB'] + 16, struct.pack('>4I', SID2, POOL2, len(smp2), 65536))
    for t, v in (ovr or {}).items(): e.w32(S['OVR'] + 4 * t, v)
    outs = []
    rnd = random.Random(seed)
    for b in range(blocks):
        e.u.mem_write(OUT, bytes(6 * 128))
        trig = 0x3F if b in trig_at else 0
        for t, kv in ((per_block or {}).get(b) or {}).items():
            for k, v in kv.items(): e.u.mem_write(PAR + 14 + 66 * t + 2 * k, struct.pack('>H', v & 0xffff))
        e.mac.macsr = 0xA0
        d0, good = e.call(0x400A7D4A, OUT, PAR, trig, 0, count=2000000)
        outs.append([list(struct.unpack('>32i', bytes(e.u.mem_read(OUT + 128 * t, 128)))) for t in range(6)])
    return e, outs, caught


# Sample: Rampe + Sinus (16 Bit)
N = 3000
SMP = [int(12000 * math.sin(2 * math.pi * i / 37.0) + (i % 500) * 30 - 7500) for i in range(N)]
# Stimmen-Schleife fuer die Maschinen 0..5: dieselben update / render mit denselben Argumenten wie ohne sampler (die
# Klangerzeugung der Firmware selbst laeuft im Emulator nicht exakt: EMAC mit Laden)
def dispatch(img):
    e = boot(img, emac=True); pass; tr = []
    for f in G.UPD_ORIG + G.RND_ORIG:
        e.u.mem_write(f, b'\x4e\x75')                 # rts; der Haken schreibt vorher mit
        def cb(u, a, z, _, f=f):
            sp = u.reg_read(mk.UC_M68K_REG_A7); tr.append((f,) + tuple(e.r32(sp + 4 + 4 * i) for i in range(3)))
        e.u.hook_add(UC_HOOK_CODE, cb, begin=f, end=f)
    for b in range(8):
        for t, m in enumerate([0, 1, 2, 3, 4, 5]):
            e.u.mem_write(PAR + 14 + 66 * t + 18, struct.pack('>H', ((m + b // 3) % 6) << 8))
        e.mac.macsr = 0xA0; e.call(0x400A7D4A, OUT, PAR, 0x3F if b % 3 == 0 else 0, 0, count=2000000)
    return tr
t1, t0 = dispatch(IMG), dispatch(REF)
chk('Stimmen-Schleife, Maschinen 0..5 (auch Wechsel): %d Aufrufe wie ohne sampler' % len(t1), t1 == t0 and len(t1) == 8 * 12)


def model_clean(smp, st, span, inc16, loop, rev, n):
    """Spiegel des sauberen Wegs (Ganzzahl): Position 32.16, lineare Interpolation"""
    pos = st + span - 1 if rev else st; frac = 0; out = []; play = True
    inc = -inc16 if rev else inc16
    inci, incf = (inc >> 16), (inc & 0xffff) << 16
    s = smp + [0] * 16
    for _ in range(n):
        if not play: out.append(0); continue
        while not (0 <= pos - st < span):
            if not loop: play = False; break
            pos += -span if pos - st >= 0 else span
        if not play: out.append(0); continue
        s0, s1 = s[pos], s[pos + 1]
        d = (s1 - s0) >> 1
        f15 = ((frac >> 16) & 0xffff) >> 1
        dd = ((d + 0x8000) & 0xffff) - 0x8000
        y = s0 + ((dd * f15) >> 14)
        out.append(((y & 0xffff) << 16) - (1 << 32 if y & 0x8000 else 0))
        frac += incf; carry = frac >> 32; frac &= 0xffffffff
        pos += inci + carry
    return out


def s32l(xs): return [(x & 0xffffffff) - (1 << 32) if x & 0x80000000 else x for x in xs]


def track0(outs, caught, blocks):
    return [x for b in range(blocks) for x in caught[b]]


for nm, par, loop, rev in (('vorwaerts', {}, 0, 0), ('Start 32, Length 40', {11: 0x2000, 12: 0x2800}, 0, 0),
                           ('Loop', {11: 0x1000, 12: 0x0400, 15: 0x100}, 1, 0), ('Reverse', {16: 0x100}, 0, 1),
                           ('Reverse + Loop', {11: 0x3000, 12: 0x0300, 15: 0x100, 16: 0x100}, 1, 1)):
    for note in (60, 67, 48, 84):
        e, outs, caught = vloop(IMG, [6, 0, 0, 0, 0, 0], 30, smp=SMP, par={0: par}, notes={0: note})
        got = [x for c in caught for x in c]                  # ab dem Block nach dem Trig (dann liest die Schleife die Maschine)
        st = N * ((par.get(11, 0)) >> 8) // 127
        span = max(1, N * ((par.get(12, 0x7F00)) >> 8) // 127 - st)          # smp12: SHAPE = Ende, Laenge = Ende - Start
        semis = note - 60; ratio = 2 ** (semis / 12)
        inc16 = e.r32(0x42308828 + G.V['INCF']) >> 16 | (e.r32(0x42308828 + G.V['INCI']) & 0xffff) << 16
        if rev: inc16 = (-inc16) & 0xffffffff
        inc16 = inc16 - (1 << 32) if inc16 & 0x80000000 else inc16
        want = model_clean(SMP, st, span, abs(inc16), loop, rev, len(got))
        okm = got == want
        chk('sauber, %s, Note %d: Schritt %.4f (soll %.4f), Ausgang = Modell %s' % (nm, note, abs(inc16) / 65536, ratio,
            okm or [(i, got[i], want[i]) for i in range(len(got)) if got[i] != want[i]][:2]),
            okm and abs(abs(inc16) / 65536 / ratio - 1) < 2e-3)
# Modelle (smp4): CONTOUR = Modell (0 Clean, 1 SP, 2 LM). Ganzzahl-Modell des Rasters (= Code), Biquads in float
s32 = lambda x: (x & 0xffffffff) - (1 << 32) if x & 0x80000000 else x & 0xffffffff
s16 = lambda x: (x & 0xffff) - (1 << 16) if x & 0x8000 else x & 0xffff
SEGT = G.segt()


def row_of(m):
    b = G.model_row(G.MODELS[m])
    r16, fl, g, pg, msk, nst, _ = struct.unpack_from('>HHHHIHH', b)
    st = [tuple(s32(x) / 2 ** 31 for x in struct.unpack_from('>3i', b, 16 + 12 * i)) for i in range(nst)]
    return dict(R16=r16, MF=fl, GAIN=g, PG=pg, MASK=s32(msk), ST=[(b0, 2 * a1h, a2) for b0, a1h, a2 in st])


def mulaw(x, seg=0):
    m = -x if x < 0 else x; sh = SEGT[seg * G.SEGS + (m >> 8)]
    q = min(((m + ((1 << sh) >> 1)) >> sh) << sh, 32767)
    return -q if x < 0 else q


def model_raster(smp, v, n, loop=False, rev=False, pre=None, raw=None):
    """Ganzzahl-Spiegel von SRAS / SRK / SRKQ / SRK2 / JMU / SRB: Ausgang Q30 vor den Biquads"""
    st, span, tinc, kinv = v['ST'], v['SPAN'], v['TINC'], v['KINV']
    inci, incf = s32(v['INCI']), v['INCF']; gain, mask, pg = s16(v['GAIN']), s32(v['MASK']), s16(v['PG'])
    mf, q8 = v['MF'], v['Q8']
    pos, frac, ph, held, P = st + (span - 1 if rev else 0), 0, 0xffffffff, 0, 0
    out = []
    sm = list(smp) + [0] * 64
    for _ in range(n):
        frac += incf; pos += inci + (frac >> 32); frac &= 0xffffffff
        z = held + P; P = 0
        ph += tinc
        if ph >> 32:
            ph &= 0xffffffff
            while True:
                rel = pos - st
                if 0 <= rel < span: break
                if not loop: break
                pos += -span if rel >= 0 else span
            if not 0 <= pos - st < span:
                held = P = 0; inci = incf = tinc = 0
            else:
                w = ((ph >> 16) * kinv & 0xffffffff) >> 16
                off = (w * ((inci * 65536 + (incf >> 16)) >> 6)) >> 10
                pf = frac - ((off & 0xffff) << 16); pp = pos - (off >> 16) - (1 if pf < 0 else 0); pf &= 0xffffffff
                rel = pp - st
                if rel < 0 or rel >= span: pp = st + (0 if rel < 0 else span - 1); pf = 0; rel = pp - st
                if mf >> G.MF_GRID & 1 and rel <= 0xfffff0:
                    r8 = (rel << 8 | pf >> 24) + (q8 >> 1); r8 -= r8 % q8
                    pp = st + (r8 >> 8); pf = (r8 & 0xff) << 24
                s0, s1 = sm[pp], sm[pp + 1]
                x = s0 + (s16((s1 - s0) >> 1) * ((pf >> 16) >> 1) >> 14)
                if pre is not None: x = pre(len(out), s16(x), raw)   # SWEEP am Anfang der Kette (smp8): Wert aus dem Filter
                x = (s16(x) * gain) >> 8
                x = max(-32768, min(32767, x))
                x = mulaw(x, G.MODELS[v['VIN']].get('seg', 0) if 'VIN' in v else 0) if mf >> G.MF_MULAW & 1 else x & mask
                x = s16(x) * pg
                d = (x - held) >> 15; held = x
                z = s32(z + d * ((w * w & 0xffffffff) >> 18))
                P = -(d * (((65535 - w) ** 2 & 0xffffffff) >> 18))
        out.append(z)
    return out


def biquads(z, stages):
    """Direktform I je Stufe (Q30-Bereich), letzte Stufe * 2 mit Saettigung"""
    x = [v / 2 ** 31 for v in z]
    for b0, a1, a2 in stages:
        x1 = x2 = y1 = y2 = 0.0; y = []
        for xi in x:
            yi = b0 * xi + 2 * b0 * x1 + b0 * x2 - a1 * y1 - a2 * y2
            x2, x1, y2, y1 = x1, xi, y1, yi; y.append(yi)
        x = y
    return [max(-1.0, min(1.0 - 2 ** -31, 2 * v)) for v in x]


VOX = lambda e: {k: e.r32(0x42308828 + x) for k, x in G.V.items()}
MODS = tuple((i, G.MODELS[i]['name']) for i in range(1, G.NMOD))
MW = {i: i << 8 for i in range(1, G.NMOD)}
for m, nm in MODS:
    rw = row_of(m)
    for note in (60, 67, 48):
        e, outs, caught = vloop(IMG, [6, 0, 0, 0, 0, 0], 20, smp=SMP, par={0: {14: MW[m], 18: 0x7F00}}, notes={0: note})
        got = [x for c_ in caught for x in c_]
        v = VOX(e)
        q8 = (65536 << 8) // rw['R16']
        tfix = (65536 << 24) // q8
        ratio = 2 ** ((note - 60) / 12)
        want_t = tfix if not rw['MF'] & 1 else min(rw['R16'] * ratio * 65536, 0xFFFFFFFF)   # ueber 48 kHz: jedes Sample
        vok = (v['VIN'], v['MF'], v['GAIN'], v['PG'], s32(v['MASK']), v['Q8']) == (m, rw['MF'], rw['GAIN'], rw['PG'], rw['MASK'], q8) \
            and abs(v['TINC'] / want_t - 1) < 2e-4 and v['ROW'] == S['MODT'] + G.ROWB * (m - 1)
        want = biquads(model_raster(SMP, v, len(got)), rw['ST'])
        err = max(abs(a_ / 2 ** 31 - b_) for a_, b_ in zip(s32l(got), want))
        chk('%s Note %d: Takt %.0f Hz (%s), Q8 %d, Werte der Zeile %s; Modell max. %.1e'
            % (nm, note, v['TINC'] * 48000 / 2 ** 32, 'mit der Tonhoehe' if rw['MF'] & 1 else 'fest', v['Q8'], vok, err),
            vok and err < 2e-6)
for m, nm in MODS:
    rw = row_of(m)
    for vn, par, rv in (('Loop', {11: 0x1000, 12: 0x0400, 15: 0x100}, False), ('Reverse + Loop', {11: 0x3000, 12: 0x0300, 15: 0x100, 16: 0x100}, True),
                        ('Reverse', {16: 0x100}, True)):
        par = {**par, 14: MW[m], 18: 0x7F00}
        e, outs, caught = vloop(IMG, [6, 0, 0, 0, 0, 0], 30, smp=SMP, par={0: par}, notes={0: 67})
        got = [x for c_ in caught for x in c_]; v = VOX(e)
        want = biquads(model_raster(SMP, v, len(got), loop=bool(par.get(15)), rev=rv), rw['ST'])
        err = max(abs(a_ / 2 ** 31 - b_) for a_, b_ in zip(s32l(got), want))
        chk('%s %s (Note 67): Modell max. %.1e' % (nm, vn, err), err < 2e-6)
# Vollaussteuerung: Rechteck +-32767 (Ueberschwinger des Filters) -> Saettigung statt Ueberlauf
SQ = [32767 if (i // 40) % 2 else -32768 for i in range(N)]
for m, nm in MODS:
    e, outs, caught = vloop(IMG, [6, 0, 0, 0, 0, 0], 20, smp=SQ, par={0: {14: MW[m], 18: 0x7F00}})
    got = s32l([x for c_ in caught for x in c_]); v = VOX(e)
    want = biquads(model_raster(SQ, v, len(got)), row_of(m)['ST'])
    err = max(abs(a_ / 2 ** 31 - b_) for a_, b_ in zip(got, want))
    flips = sum(1 for a_, b_ in zip(got, got[1:]) if abs(a_ - b_) > 1.5 * 2 ** 31)
    chk('%s Rechteck voll: Spitze %.4f, Saettigung %d Samples, kein Ueberlauf (Spruenge %d); Modell max. %.1e'
        % (nm, max(abs(x) for x in got) / 2 ** 31, sum(1 for x in got if abs(x) >= 2 ** 31 - 1), flips, err), flips == 0 and err < 2e-6)
# Filter-Entwurf: Betrag der Kette (aus den Q31-Koeffizienten der Zeile)
def mag(stages, f):
    zz = np.exp(-2j * np.pi * f / 48000); h = 1
    for b0, a1, a2 in stages: h *= b0 * (1 + zz) ** 2 / (1 + a1 * zz + a2 * zz * zz)
    return 20 * np.log10(abs(h))
import numpy as np
fr = {nm: [round(float(mag(row_of(m)['ST'], f)), 1) for f in (100, 1000, 5000, 11000, 12000, 16000, 20000)] for m, nm in ((1, 'SP'), (2, 'LM'))}
chk('Rekonstruktions-Filter (dB bei 0.1 / 1 / 5 / 11 / 12 / 16 / 20 kHz): %s' % fr,
    abs(fr['SP'][0]) < 0.01 and abs(fr['SP'][4] + 3.0) < 0.1 and fr['SP'][6] < -24 and abs(fr['LM'][0]) < 0.01
    and abs(fr['LM'][3] + 3.0) < 0.1 and fr['LM'][6] < -12)
# Spiegeltoene des Takts (smp3-Pruefung, jetzt mit den Takten der Modelle): Sinus 50 + 150 Hz, ohne Bits / mu-law,
# staerkste Komponente abseits der echten Linien k * R +- f
NS = 48000
SIN = [int(round(8000 * math.sin(2 * math.pi * 50 * i / 48000) + 2000 * math.sin(2 * math.pi * 150 * i / 48000 + 1))) for i in range(NS + 64)]
def spur_db(y, R):
    y = np.array(y[2000:-2000]); win = np.blackman(len(y)); X = np.abs(np.fft.rfft(y * win)); f = np.fft.rfftfreq(len(y), 1 / 48000)
    legit = [abs(k * R + sg * f0) for k in range(4) for f0 in range(50, 500, 50) for sg in (1, -1)]
    msk = (f > 500) & (f < 20000)
    for l in legit: msk &= np.abs(f - l) > 30
    return 20 * np.log10(X[msk].max() / X.max())
res = []
for m, nm in MODS:
    rw = row_of(m)
    q8 = (65536 << 8) // rw['R16']
    tinc = (65536 << 24) // q8 if not rw['MF'] & 1 else rw['R16'] << 16
    v = dict(ST=0, SPAN=NS, TINC=tinc, KINV=0xFFFFFFFF // (tinc >> 16), INCI=1, INCF=0, GAIN=256, MASK=0xFFFFFFFF, PG=32767,
             MF=rw['MF'] & ~(1 << G.MF_MULAW), Q8=q8)
    y = biquads(model_raster(SIN, v, NS), rw['ST'])
    res.append((nm, round(tinc * 48000 / 2 ** 32), round(float(spur_db(y, tinc * 48000 / 2 ** 32)), 1)))
chk('Spiegeltoene (Modell, Takt Hz, dB): %s' % res, all(x[2] < -68 for x in res))
# ---------------- SWEEP-Filter (smp7): Mitte aus (bitgleich), links Tiefpass, rechts Hochpass; Gleitkomma-Modell (Zavalishin)
def svf(xs, a1, a2, a3, hp, ic1=0.0, ic2=0.0, fade=None):
    """fade = {Index: (Blende 1 ein / 2 aus, Index im Block)}: Blende zwischen trocken und gefiltert (smp8)"""
    out = []
    for n, x in enumerate(xs):
        d = x; x /= 2; v3 = x - ic2; v1 = a1 * ic1 + a2 * v3; v2 = ic2 + a2 * ic1 + a3 * v3
        ic1, ic2 = 2 * v1 - ic1, 2 * v2 - ic2
        y = (x - math.sqrt(2) * v1 - v2) if hp else v2
        if fade and n in fade:
            k, i = fade[n]; w = (i + 1) if k == 1 else (31 - i)
            y = d / 2 + (y - d / 2) * w / 32
        out.append(max(-1.0, min(1.0 - 2 ** -31, 2 * y)))
    return out
FADE_IN = {i: (1, i) for i in range(32)}
e, outs, caught = vloop(IMG, [6, 0, 0, 0, 0, 0], 8, smp=SMP)
ref = s32l([x for c in caught for x in c])
for w, nm in ((0x4000, 'Mitte'), (0x3F81, 'knapp unter der Mitte (gerundet Mitte)')):
    e, outs, caught = vloop(IMG, [6, 0, 0, 0, 0, 0], 8, smp=SMP, par={0: {13: w}})
    chk('Filter %s: aus, Block bitgleich' % nm, s32l([x for c in caught for x in c]) == ref)
fr = []
for w, hp in ((0x2000, 0), (0x0000, 0), (0x3F00, 0), (0x4100, 1), (0x6000, 1), (0x7F00, 1)):
    e, outs, caught = vloop(IMG, [6, 0, 0, 0, 0, 0], 8, smp=SMP, par={0: {13: w}})
    got = s32l([x for c in caught for x in c]); v = VOX(e)
    a1, a2, a3 = (s32(v[k]) / 2 ** 31 for k in ('FA1', 'FA2', 'FA3'))
    want = svf([x / 2 ** 31 for x in ref], a1, a2, a3, hp, fade=FADE_IN)
    err = max(abs(a_ / 2 ** 31 - b_) for a_, b_ in zip(got, want))
    i = v['FI'] & 0xffff
    f = 20 * 800 ** (i / (G.NFG - 1))
    chk('Filter %#06x: %s %.0f Hz (Stufe %d, Seite %d), erster Block eingeblendet, Modell max. %.1e' % (w, 'Hochpass' if hp else 'Tiefpass', f, i, v['FI'] >> 16, err),
        err < 2e-6 and v['FI'] >> 16 == (1 if hp else 2))
# Betrag: 5 kHz durch den Tiefpass bei ~220 Hz leise, 80 Hz durch den Hochpass bei ~1.1 kHz leise; Durchlass ~0 dB
def rms(xs): return math.sqrt(sum(x * x for x in xs) / len(xs))
for w, fsig, nm in ((0x1A00, 5000, 'Tiefpass'), (0x6600, 80, 'Hochpass'), (0x1A00, 60, 'Tiefpass (Durchlass)'), (0x6600, 8000, 'Hochpass (Durchlass)')):
    sig = [int(16000 * math.sin(2 * math.pi * fsig * i / 48000)) for i in range(6000)]
    e, outs, caught = vloop(IMG, [6, 0, 0, 0, 0, 0], 40, smp=sig, par={0: {13: w}})
    y = [x / 2 ** 31 for c in caught[10:] for x in c]
    g = 20 * math.log10(rms(y) / (16000 / 32768 / math.sqrt(2)))
    fr.append((nm, fsig, round(g, 1)))
chk('Filter-Betrag (Signal, dB): %s' % fr, fr[0][2] < -40 and fr[1][2] < -40 and fr[2][2] > -1.5 and fr[3][2] > -1.5)
e, outs, caught = vloop(IMG, [6, 0, 0, 0, 0, 0], 4, smp=SQ, par={0: {13: 0x7F00}})
gl = s32l([x for c in caught for x in c])
chk('Filter Hochpass, Rechteck voll: kein Ueberlauf (Spruenge)', sum(1 for a_, b_ in zip(gl, gl[1:]) if abs(a_ - b_) > 1.5 * 2 ** 31) == 0)
# smp8: Uebergaenge ohne Knacken (Pip: "knackt leise, wenn man ueber 0 dreht"). Knopf blockweise ueber die Mitte, hin und
# zurueck, auch mit Sprung von links nach rechts; Signal 150 Hz + 6 kHz. Groesster Schritt von Sample zu Sample gegen
# denselben Lauf ohne Filter; dazu das alte Verhalten (Zustand leer, hart umgeschaltet) als Vergleich im Modell.
CLK = [int(9000 * math.sin(2 * math.pi * 150 * i / 48000) + 5000 * math.sin(2 * math.pi * 6000 * i / 48000)) for i in range(48000)]
SWP = [0x4300, 0x4200, 0x4100, 0x4000, 0x3F00, 0x3E00, 0x3D00, 0x3E00, 0x3F00, 0x4000, 0x4100, 0x4000, 0x4000, 0x3F00,
       0x4100, 0x3F00, 0x4000, 0x7000, 0x1000, 0x4000]
def maxstep(xs): return max(abs(a_ - 2 * b_ + c_) for a_, b_, c_ in zip(xs, xs[1:], xs[2:])) / 2 ** 31   # 2. Differenz: Knacken
for m, nm in ((0, 'Clean'), (1, 'SP'), (2, 'LM')):
    pb = {4 + 3 * k: {0: {13: w}} for k, w in enumerate(SWP)}
    base = {0: {13: 0x4000, 14: m << 8, 18: 0x7F00}}
    e, outs, caught = vloop(IMG, [6, 0, 0, 0, 0, 0], 4 + 3 * len(SWP) + 2, smp=CLK, par=base, per_block=pb)
    y = s32l([x for c in caught for x in c])
    e, outs, caught = vloop(IMG, [6, 0, 0, 0, 0, 0], 4 + 3 * len(SWP) + 2, smp=CLK, par=base)
    y0 = s32l([x for c in caught for x in c])
    a_, b_ = maxstep(y[100:]), maxstep(y0[100:])
    chk('%s: Knopf ueber die Mitte (%d Wechsel): groesste 2. Differenz %.4f, ohne Filter %.4f' % (nm, len(SWP), a_, b_), a_ < 1.15 * b_)
# alte Umschaltung im Modell (Clean, Tiefpass 16 kHz aus leerem Zustand): so sah das Knacken aus
ref1 = [x / 32768 for x in CLK[:600]]
v61 = [math.tan(math.pi * 16000 / 48000)]; g_ = v61[0]; a1_ = 1 / (1 + g_ * (g_ + math.sqrt(2)))
old = ref1[:80] + svf(ref1[80:], a1_, g_ * a1_, g_ * g_ * a1_, 0)
chk('zum Vergleich, alte Umschaltung (Tiefpass aus leerem Zustand): 2. Differenz %.4f statt %.4f' % (maxstep([x * 2 ** 31 for x in old]),
    maxstep([x * 2 ** 31 for x in ref1])), maxstep([x * 2 ** 31 for x in old]) > 1.5 * maxstep([x * 2 ** 31 for x in ref1]))
# smp8: Modelle filtern am Anfang der Kette (Wandler-Takt), danach Pegel / Clip / Bits / Halten / Rekonstruktion.
# SFTK im Emulator mitschreiben: Eingang = Wert am Takt (Modell), Ausgang = Gleitkomma-SVF; den Ausgang ins Modell
# der Kette gegeben -> Block bitgleich. Stufe = Knopf + Verschiebung um den Takt (log2(48 kHz / Takt) * 6.33).
def shift_x(tinc): return math.log2(2 ** 32 / tinc) / math.log2(800 ** (1 / 61))
def shift_ref(tinc): return round(shift_x(tinc))
for m, nm in MODS:
    for w, hp, note in ((0x2000, 0, 60), (0x6000, 1, 60), (0x2000, 0, 72)):
        rec = []
        def tap_in(u, a, z, _): rec.append([s16(u.reg_read(mk.UC_M68K_REG_D0) & 0xffff), None])
        def tap_out(u, a, z, _): rec[-1][1] = s16(u.reg_read(mk.UC_M68K_REG_D0) & 0xffff)
        e, outs, caught = vloop(IMG, [6, 0, 0, 0, 0, 0], 12, smp=SMP, par={0: {13: w, 14: MW[m], 18: 0x7F00}}, notes={0: note},
                                hooks=[(S['SFTK'], tap_in), (S['SFTKR'], tap_out)])
        got = [x for c_ in caught for x in c_]; v = VOX(e)
        raw = []; it = iter([b_ for a_, b_ in rec])
        def pre(n, x, raw):                       # Block 0: Filter noch aus (SFLT entscheidet nach dem Block)
            if n < 32: return x
            raw.append(x); return next(it)
        want = biquads(model_raster(SMP, v, len(got), pre=pre, raw=raw), row_of(m)['ST'])
        err = max(abs(a_ / 2 ** 31 - b_) for a_, b_ in zip(s32l(got), want))
        a1, a2, a3 = (s32(v[k]) / 2 ** 31 for k in ('FA1', 'FA2', 'FA3'))
        fy = svf([x / 32768 for x in raw], a1, a2, a3, hp)
        ferr = max(abs(fy[i] - rec[i][1] / 32768) for i in range(len(rec) // 2, len(rec)))   # nach der Blende
        base_st = 30 if not hp else 31
        st_ok = abs((v['FI'] & 0xffff) - min(G.NFG - 1, base_st + shift_x(v['TINC']))) < 0.55   # log2 genaehert
        chk('%s Note %d %s: Filter am Takt (%d Takte), Eingang = Wert des Wandlers %s, Stufe %d (Knopf %d + Takt %.2f), '
            'Filter max. %.1e, Kette danach max. %.1e'
            % (nm, note, 'Hochpass' if hp else 'Tiefpass', len(rec), raw == [a_ for a_, b_ in rec], v['FI'] & 0xffff, base_st,
               shift_x(v['TINC']), ferr, err),
            raw == [a_ for a_, b_ in rec] and st_ok and ferr < 1e-3 and err < 2e-6)
# CONTOUR -> Modell (gerundet, begrenzt); Clean = SCLN, Biquads leer
mm = []
TOPW = (G.NMOD - 1) << 8
for w in (0, 0x7F, 0x80, 0x100, 0x17F, 0x180, TOPW, 0x7F00):
    e, outs, caught = vloop(IMG, [6, 0, 0, 0, 0, 0], 2, smp=SMP, par={0: {14: w}})
    mm.append(e.r32(0x42308828 + G.V['VIN']))
chk('CONTOUR 0 / 0x7f / 0x80 / 0x100 / 0x17f / 0x180 / %#x / 0x7f00 -> Modell %s' % (TOPW, mm), mm == [0, 0, 1, 1, 1, 2, G.NMOD - 1, G.NMOD - 1])
e, outs, caught = vloop(IMG, [6, 0, 0, 0, 0, 0], 4, smp=SMP, par={0: {14: 0x100}})
h1 = [e.r32(0x42308828 + G.V['H0'] + 4 * i) for i in range(12)]
e.u.mem_write(PAR + 14 + 2 * 14, struct.pack('>H', 0)); e.mac.macsr = 0xA0; e.call(0x400A7D4A, OUT, PAR, 0, 0, count=2000000)
h0 = [e.r32(0x42308828 + G.V['H0'] + 4 * i) for i in range(12)]
chk('SP -> Clean im Spielen: Biquads leer (vorher %d Zustaende != 0)' % sum(1 for x in h1 if x), any(h1) and not any(h0))
e, outs, caught = vloop(IMG, [6, 0, 0, 0, 0, 0], 40, smp=SMP[:300], par={0: {14: 0x100}})
tail = [x for c in caught[12:] for x in c]
chk('SP, Sample 300 Frames: danach Stille, Spielen-Bit aus, Biquads leer',
    all(x == 0 for x in tail) and not e.r32(0x42308828 + G.V['FLAGS']) & 2 and not any(e.r32(0x42308828 + G.V['H0'] + 4 * i) for i in range(12)))
e, outs, caught = vloop(IMG, [6, 0, 0, 0, 0, 0], 40, smp=SMP[:200])
tail = [x for c in caught[10:] for x in c]
chk('Clean, Sample 200 Frames: danach Stille, Spielen-Bit aus', all(x == 0 for x in tail) and not e.r32(0x42308828 + G.V['FLAGS']) & 2)
e, outs, caught = vloop(IMG, [6, 0, 0, 0, 0, 0], 3, smp=SMP)
chk('Gate der Sampl-Spur aus (+0x24c = 0), Decay aus der Tabelle der Firmware',
    e.r32(0x42308828 + 0x24C) == 0 and e.r32(0x42308828 + 0x250) == e.r32(G.DECLUT + 4 * 127))
e, outs, caught = vloop(IMG, [6, 0, 0, 0, 0, 0], 3, smp=None)
chk('Sample nicht geladen: Stille, kein Absturz', all(x == 0 for c in caught for x in c) and len(caught) == 2)
# Kosten: 6 Spuren Sampl, je Modell, Noten 60 / 84 (LM: Takt mit der Tonhoehe)
for w, note in [(0, 60), (0, 72)] + [(i << 8, n) for i in range(1, G.NMOD) for n in (60, 84, 72)]:      # Note 72: mit Filter
    e = boot(IMG, emac=True)
    e.u.mem_write(POOL, struct.pack('>%dh' % N, *SMP) + bytes(32)); e.u.mem_write(S['TAB'], struct.pack('>4I', SID, POOL, N, 65536))
    for t in range(6):
        p = PAR + 14 + 66 * t
        for k, v in {9: 6 << 8, 10: 0x4000, 12: 0x7F00, 13: 0x4000 if note != 72 else 0x2000, 14: w, 17: 0x4000, 18: 0x7F00}.items():
            e.u.mem_write(p + 2 * k, struct.pack('>H', v))
        e.w32(PMOD + 4 * t, note << 16); e.w32(G.TGT0 + 66 * t + 2 * G.K_ID, SID)
    kit_audio(e, [6] * 6, [SID] * 6)
    for t in (G.AMPENV, G.VCA) + G.UPD_ORIG + G.RND_ORIG:
        e.u.mem_write(t, b'\x4e\x75')
    e.mac.macsr = 0xA0; e.call(0x400A7D4A, OUT, PAR, 0x3F, 0, count=2000000)
    e.mac.macsr = 0xA0; e.call(0x400A7D4A, OUT, PAR, 0, 0, count=2000000)
    n = [0]; h = e.u.hook_add(UC_HOOK_CODE, lambda u, a, z, _: n.__setitem__(0, n[0] + 1), begin=0x40140000, end=0x40195FFF)
    e.mac.macsr = 0xA0; e.call(0x400A7D4A, OUT, PAR, 0, 0, count=2000000); e.u.hook_del(h)
    lim = ((1200 if note == 60 else 2600) if w == 0 else 3600 if w == 0x100 else 4600) + (2300 if note == 72 and w else 0)   # Takt mit der Tonhoehe: 2 Oktaven hoch Takt jedes Sample; Note 72 mit Filter (smp8: Blende, am Wandler); smp13: Biquad ohne << (+ 2 mac je Stufe)
    chk('Kosten %s Note %d: %d Befehle pro Block fuer 6 Sampl-Spuren (ohne Huellkurve / VCA), < %d pro Spur'
        % (G.MODELS[w >> 8]['name'], note, n[0], lim), n[0] < 6 * lim)

# ---------------- 3 Laden (Dateisystem gestubbt: Index, Datei-Infos, Oeffnen, Lesen, Schliessen)
class FS:
    def __init__(s, e, files):
        s.e, s.files, s.open = e, files, {}
        s.closed = 0
        u = e.u
        def ret(u, v):
            sp = u.reg_read(mk.UC_M68K_REG_A7); u.reg_write(mk.UC_M68K_REG_D0, v & 0xffffffff)
            u.reg_write(mk.UC_M68K_REG_PC, e.r32(sp)); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
        def arg(u, i): return e.r32(u.reg_read(mk.UC_M68K_REG_A7) + 4 + 4 * i)
        ids = s.ids = sorted(files)
        s.locked = []
        def find(u, a, z, _):
            s.locked.append(e.r32(G.FS_LOCKO) == TASK)
            h = arg(u, 0); ret(u, s.ids.index(h) if h in s.files else -1)
        def stat(u, a, z, _):
            ino, out = arg(u, 0), arg(u, 1)
            if 1000 <= ino < 1000 + len(s.ids):
                h = s.ids[ino - 1000]; e.u.mem_write(out, struct.pack('>4I', ino, h, len(s.files[h]), 0)); ret(u, 0)
            else: ret(u, -1)
        def opn(u, a, z, _):
            hdl, fh = arg(u, 0), arg(u, 1); ino = e.r32(hdl)
            e.u.mem_write(fh, struct.pack('>4I', ino, 0, 0, 1)); ret(u, 1)
        def rd(u, a, z, _):
            buf, n, fh = arg(u, 0), arg(u, 1), arg(u, 2)
            ino, p = e.r32(fh), e.r32(fh + 4); data = s.files[s.ids[ino - 1000]][p:p + n]
            e.u.mem_write(buf, data); e.w32(fh + 4, p + len(data)); ret(u, len(data))
        def cls(u, a, z, _): s.closed += 1; ret(u, 0)
        for t, f in ((G.FS_FIND, find), (G.FS_STAT, stat), (G.FS_OPEN, opn), (G.FS_READ, rd), (G.FS_CLOSE, cls)):
            u.hook_add(UC_HOOK_CODE, f, begin=t, end=t)
        s.index()
        e.w32(G.FS_MOUNT, 1)
    def index(s):
        s.ids = sorted(s.files)
        for i, h in enumerate(s.ids): s.e.w32(G.FS_IDX + 8 * i, 1000 + i)


def smpfile(frames, stereo=0, rate=48000, extra=0):
    hdr = bytearray(64); hdr[1] = stereo
    struct.pack_into('>II', hdr, 4, 2 * len(frames), rate)
    return bytes(hdr) + struct.pack('>%dh' % len(frames), *frames) + bytes(extra)


def tick(e, n=1):
    for _ in range(n):
        e.call(S['STICK'], 0x4F04B000, count=5000000)
def tab(e): return [tuple(r32s(e, S['TAB'] + 16 * i, 4)) for i in range(G.NTAB)]


e = boot(IMG)
e.u.hook_add(UC_HOOK_CODE, lambda u, a, z, _: (u.reg_write(mk.UC_M68K_REG_PC, e.r32(u.reg_read(mk.UC_M68K_REG_A7))),
             u.reg_write(mk.UC_M68K_REG_A7, u.reg_read(mk.UC_M68K_REG_A7) + 4)), begin=G.VCRENDER, end=G.VCRENDER)
mono = [((i * 37) % 4000) - 2000 for i in range(70000)]
st_l = [((i * 13) % 3000) - 1500 for i in range(5000)]; st_r = [((i * 7) % 2000) - 1000 for i in range(5000)]
inter = [x for pair in zip(st_l, st_r) for x in pair]
files = {0x1001: smpfile(mono), 0x2003: smpfile(inter, stereo=1, rate=44100), 0x3005: b'\0' * 30 + b'junk' * 10,
         0x4007: smpfile(mono[:100], rate=1000)}
fs = FS(e, files)
KIT = 0x4F04D000
e.w32(G.KITP, KIT); e.u.mem_write(KIT, bytes(28 + 600))
for t, (m, sid) in enumerate(((6, 0x1001), (0, 0), (6, 0x2003), (6, 0x3005), (6, 0x4007), (6, 0x1001))):
    e.u.mem_write(KIT + 28 + 100 * t + 38, bytes([m])); e.w32(KIT + 28 + 100 * t + G.O_ID, sid)
tick(e, 6)
tb = tab(e)
chk('Kit: erstes Sample (70000 Frames) in 6 Bildern zu 64 KB geladen: %s' % [hex(x) for x in tb[0]],
    tb[0][0] == 0x1001 and tb[0][2] == 70000 and tb[0][3] == 65536 and
    list(struct.unpack('>70000h', bytes(e.u.mem_read(tb[0][1], 140000)))) == mono and bytes(e.u.mem_read(tb[0][1] + 140000, 32)) == bytes(32))
tick(e, 12)
tb = tab(e)
ids = [x[0] for x in tb if x[0]]
st = [x for x in tb if x[0] == 0x2003]
chk('Stereo 44.1 kHz -> Mono (L + R) / 2, Rate %s; Datei ohne gueltigen Kopf und Rate 1000 Hz nicht geladen (Fehl-Ring %s)'
    % (st and hex(st[0][3]), [hex(x) for x in r32s(e, S['LFAIL'], G.NFAIL)]),
    ids == [0x1001, 0x2003] and st[0][2] == 5000 and st[0][3] == 44100 * 65536 // 48000 and
    list(struct.unpack('>5000h', bytes(e.u.mem_read(st[0][1], 10000)))) == [(a_ + b_) >> 1 for a_, b_ in zip(st_l, st_r)]
    and set(r32s(e, S['LFAIL'], G.NFAIL)) >= {0x3005, 0x4007})
chk('Dateien geschlossen (%d), Lader frei' % fs.closed, fs.closed >= 4 and e.r32(S['LST']) == 0)
def ov_model(fr):
    n = len(fr); out = []; col = 0; bnd = n >> 7; mn, mx, f = 32767, -32768, 0
    for x in fr:
        mn, mx, f = min(mn, x), max(mx, x), f + 1
        while f >= bnd and col < 128:
            out.append((mn >> 8, mx >> 8)); mn = mx = x; col += 1; bnd = ((col + 1) * n) >> 7
    return out
def ov_read(e, ptr, frames):
    a_ = (ptr + 2 * frames + 47) & ~15
    raw = bytes(e.u.mem_read(a_, 256)); return a_, [(struct.unpack('b', raw[2 * i:2 * i + 1])[0], struct.unpack('b', raw[2 * i + 1:2 * i + 2])[0]) for i in range(128)]
tb = tab(e)
ent = {x[0]: x for x in tb if x[0]}
o1, ov1 = ov_read(e, ent[0x1001][1], 70000); o2, ov2 = ov_read(e, ent[0x2003][1], 5000)
chk('Uebersicht (128 Spalten min / max) hinter dem Sample = Modell (Mono 70000 Frames in 3 Stuecken, Stereo 5000 Frames);'
    ' das naechste Sample beginnt dahinter',
    ov1 == ov_model(mono) and ov2 == ov_model([(a_ + b_) >> 1 for a_, b_ in zip(st_l, st_r)]) and ent[0x2003][1] == o1 + 256)
files[0x5009] = smpfile(mono[:1000]); fs.index()
e.w32(S['LREQ'], 0x5009); tick(e, 2)
chk('Browser-Wahl (LREQ) zuerst geladen', any(x[0] == 0x5009 for x in tab(e)))
chk('Index-Suche (0x4007dc30) immer unter der Sperre des Dateisystems (%d Suchen), danach frei' % len(fs.locked),
    fs.locked and all(fs.locked) and e.r32(G.FS_LOCKO) == 0)
# Schutz: zweiter Lauf (BUSY) und 'diese Task ist schon im Dateisystem' -> kein Zugriff, nur die Firmware
files[0x600B] = smpfile(mono[:500]); fs.index()
n0 = len(fs.locked)
e.w8(S['BUSY'], 0x80); e.w32(S['LREQ'], 0x600B); tick(e, 2)
g1 = len(fs.locked) == n0 and e.r8(S['BUSY']) == 0x80 and e.r32(S['LREQ']) == 0x600B
e.w8(S['BUSY'], 0); e.w32(G.FS_LOCKO, TASK); tick(e, 2)
g2 = len(fs.locked) == n0 and e.r8(S['BUSY']) == 0 and e.r32(S['LREQ']) == 0x600B
e.w32(G.FS_LOCKO, 0); tick(e, 2)
chk('Lader laeuft nicht doppelt (zweite Task) und nicht innerhalb des Dateisystems; danach normal %s' % [g1, g2],
    g1 and g2 and any(x[0] == 0x600B for x in tab(e)) and e.r8(S['BUSY']) == 0)
files[0x700D] = smpfile(mono[:800]); fs.index()
e.w32(S['OVR'] + 12, 0x700D); tick(e, 3)
chk('Sample eines Locks (OVR) wird geladen (KSO)', any(x[0] == 0x700D for x in tab(e)))
e.w32(S['OVR'] + 12, 0)
e.w32(KIT + 28 + 100 * 1 + G.O_ID, 0x2222); e.u.mem_write(KIT + 28 + 100 * 1 + 38, bytes([6])); n0 = len(fs.locked); tick(e, 3)
chk('gerade Kennung (keine Datei, z. B. Rest im Sound) wird nicht gesucht', len(fs.locked) == n0)

# Platz freigeben (smp5 / smp28): Tabelle voll -> ein Platz, den keine Spur, kein Lock (OVR oder im laufenden Pattern) und
# keine Stimme benutzt; das neue Sample kommt in die erste passende Luecke (LFIT)
def locks(spec):                                   # {(Spur, Step): Lock-Index}; Rest -1 (Layout mit 0x400548ce geprueft)
    for t in range(6): e.u.mem_write(PATB + G.T_STRIDE * t + G.T_LOCK, b'\xff' * 64)
    for (t, st), idx in spec.items(): e.u.mem_write(PATB + G.T_STRIDE * t + G.T_LOCK + st, struct.pack('b', idx))
def pool(n, sid, mach=6, valid=True):
    a = KIT + G.K_POOL + 100 * n; e.u.mem_write(a, bytes(100)); e.u.mem_write(a + 4, b'L' if valid else b'\0')
    e.u.mem_write(a + 38, bytes([mach])); e.w32(a + G.O_ID, sid)
def lend(ptr, fr): return ((ptr + 2 * fr + 47) & ~15) + 256
def kit(ids):
    for t, sid in enumerate(ids): e.w32(KIT + 28 + 100 * t + G.O_ID, sid); e.u.mem_write(KIT + 28 + 100 * t + 38, bytes([6 if sid else 0]))
base = G.POOL0
locks({})
ev_ids = [0x10001 + 2 * i for i in range(G.NTAB)]
e.u.mem_write(S['TAB'], b''.join(struct.pack('>4I', h, base + 0x10000 * i, 1000, 65536) for i, h in enumerate(ev_ids)))
kit([ev_ids[0], 0, 0, 0, 0, 0])                                                      # Spur 0 benutzt Platz 0
e.w32(S['OVR'] + 8, ev_ids[1])                                                       # Lock auf Spur 2: Platz 1
e.w32(0x42308828 + 0x31C * 4 + G.V['PTR'], base + 0x20000)                           # Stimme 4 spielt Platz 2
pool(5, ev_ids[3]); locks({(0, 10): 5})                                              # Lock im Pattern (Spur 0, Step 10): Platz 3
files[0x800F] = smpfile(mono[:600]); fs.index()
e.w32(S['LREQ'], 0x800F); tick(e, 3)
tb = tab(e); ids_now = [x[0] for x in tb]
new = [x for x in tb if x[0] == 0x800F]
chk('Tabelle voll: Platz 4 freigegeben (0..3 benutzt: Spur, Lock, Stimme, Lock im Pattern), neues Sample geladen, Rest unberuehrt %s'
    % [hex(x) for x in ids_now[:6]],
    ids_now[:4] == ev_ids[:4] and ids_now[4] == 0x800F and ids_now[5:] == ev_ids[5:] and new
    and list(struct.unpack('>600h', bytes(e.u.mem_read(new[0][1], 1200)))) == mono[:600])
chk('  neues Sample in der ersten passenden Luecke (hinter Platz 3, der freigegebene Speicher wird wieder benutzt)',
    bool(new) and new[0][1] == lend(base + 0x30000, 1000))
# smp28 (Pip: mehr als 3 Sample-Locks spinnen): Tabelle voller fremder Samples, 5 Locks auf einer Grit-Spur -> alle Locks
# werden vorgeladen (ohne dass ein Trig spielt), ohne einander hinauszuwerfen; eine weitere Browser-Wahl wirft nur Fremdes hinaus
for t in range(6): e.w32(S['OVR'] + 4 * t, 0); e.w32(0x42308828 + 0x31C * t + G.V['PTR'], 0)
junk = [0x50001 + 2 * i for i in range(G.NTAB)]
e.u.mem_write(S['TAB'], b''.join(struct.pack('>4I', h, base + 0x10000 * i, 1000, 65536) for i, h in enumerate(junk)))
LIDS = [0xB001 + 2 * i for i in range(5)]
for i, sid in enumerate(LIDS):
    files[sid] = smpfile([(i + 1) * 100 + (k % 7) for k in range(700 + 50 * i)]); pool(10 + i, sid)
pool(20, 0xB101, mach=3); pool(21, 0xB103, valid=False); pool(22, 0xB105); files[0xB105] = smpfile(mono[:300])
fs.index()
kit([0x1001, 0x7777, 0, 0, 0, 0]); e.u.mem_write(KIT + 28 + 100 + 38, bytes([2]))   # Spur 1: keine Grit-Spur
locks({(0, 0): 10, (0, 4): 11, (0, 8): 12, (0, 12): 13, (0, 63): 14, (0, 20): 20, (0, 24): 21, (1, 3): 22})
n0 = len(fs.locked); tick(e, 20)
tb = tab(e); have = {x[0] for x in tb}
chk('5 Locks einer Grit-Spur vorgeladen (Sample der Spur dazu), ohne Trig; Lock auf eine andere Maschine, leerer Lock-Platz und'
    ' Lock auf einer Nicht-Grit-Spur nicht %s' % [hex(x) for x in LIDS if x not in have],
    set(LIDS) <= have and 0x1001 in have and not ({0xB101, 0xB103, 0xB105} & have) and e.r32(S['LST']) == 0)
ok_data = all(list(struct.unpack('>%dh' % x[2], bytes(e.u.mem_read(x[1], 2 * x[2])))) == [(LIDS.index(x[0]) + 1) * 100 + (k % 7) for k in range(x[2])]
              for x in tb if x[0] in LIDS)
rng = sorted((x[1], lend(x[1], x[2])) for x in tb if x[0])
chk('  Daten der Locks richtig, kein Sample ueberlappt ein anderes (%d belegt)' % len(rng),
    ok_data and all(a_[1] <= b_[0] for a_, b_ in zip(rng, rng[1:])) and rng[0][0] >= base)
n_ev = sum(1 for h in junk if h not in have)
for k in range(4):                                                                   # wie YES: Sample der Spur 2..5
    files[0xC001 + 2 * k] = smpfile(mono[:400]); fs.index(); e.w32(S['LREQ'], 0xC001 + 2 * k); tick(e, 3)
    e.w32(KIT + 28 + 100 * (2 + k) + G.O_ID, 0xC001 + 2 * k); e.u.mem_write(KIT + 28 + 100 * (2 + k) + 38, bytes([6]))
tb = tab(e); have = {x[0] for x in tb}
chk('  weitere Browser-Wahlen (Spuren 2..5): Locks und Spuren bleiben, nur Fremdes wird ersetzt (%d + %d fremde frei)' % (n_ev, sum(1 for h in junk if h not in have) - n_ev),
    set(LIDS) <= have and 0x1001 in have and {0xC001 + 2 * k for k in range(4)} <= have and sum(1 for h in junk if h not in have) - n_ev == 4)
# alles benutzt: Spuren (6), OVR (6), Stimmen (4), Locks des Patterns (16) -> nichts frei, Fehl-Ring
e.u.mem_write(S['TAB'], b''.join(struct.pack('>4I', 0x30001 + 2 * i, base + 0x10000 * i, 1000, 65536) for i in range(G.NTAB)))
kit([0x30001 + 2 * t for t in range(6)])
for t in range(6): e.w32(S['OVR'] + 4 * t, 0x30001 + 2 * (t + 6))
for t in range(4): e.w32(0x42308828 + 0x31C * t + G.V['PTR'], base + 0x10000 * (t + 12))
for n in range(16): pool(n, 0x30001 + 2 * (16 + n))
locks({(n % 6, n): n for n in range(16)})
files[0x900F] = smpfile(mono[:600]); fs.index()
e.w32(S['LREQ'], 0x900F); tick(e, 3)
chk('alles benutzt (Spuren, OVR, Stimmen, Locks des Patterns): nichts freigegeben, Datei in den Fehl-Ring, Lader frei',
    [x[0] for x in tab(e)] == [0x30001 + 2 * i for i in range(G.NTAB)] and 0x900F in r32s(e, S['LFAIL'], G.NFAIL) and e.r32(S['LST']) == 0)
for t in range(6): e.w32(S['OVR'] + 4 * t, 0); e.w32(0x42308828 + 0x31C * t + G.V['PTR'], 0)
# LFIT: erste Luecke; bis ans Ende des Speichers; zu gross -> 0
def lfit(need, ents):
    e.u.mem_write(S['TAB'], bytes(16 * G.NTAB))
    for i, (p_, fr) in enumerate(ents): e.u.mem_write(S['TAB'] + 16 * i, struct.pack('>4I', 0x1001 + 2 * i, p_, fr, 65536))
    e.w32(S['LNEED'], need); return e.call(S['LFIT'], count=200000)[0]
big = (G.POOL_END - base) // 4
r1 = lfit(0x20000, [(base + 0x100000, 100), (base, 1000)])
r2 = lfit(0x100000, [(base + 0x100000, 100), (base, 1000)])
r3 = lfit(G.POOL_END - lend(base, big), [(base, big)])
r4 = lfit(G.POOL_END - lend(base, big) + 16, [(base, big)])
r5 = lfit(0x1000, [])
chk('LFIT: erste Luecke %s, sonst hinter dem letzten %s, genau bis zum Ende %s, zu gross -> 0 %s, leer -> Anfang %s'
    % (hex(r1), hex(r2), hex(r3), hex(r4), hex(r5)),
    r1 == lend(base, 1000) and r2 == lend(base + 0x100000, 100) and r3 == lend(base, big) and r4 == 0 and r5 == base)
e.u.mem_write(S['TAB'], bytes(16 * G.NTAB)); locks({})

# ---------------- 4 Browser (0x400a6602 -> SPARSE): Sound der aktiven Spur, Datei ohne Preset-Groesse
def browse(img, machine, size, path=b'/Samples/Drums/AMEN BREAK 120.wav', inside=False):
    e = boot(img); calls = []
    if inside: e.w32(G.FS_LOCKO, TASK)
    KIT = 0x4F04D000; e.w32(G.KITP, KIT); e.u.mem_write(KIT, bytes(28 + 600))
    snd = bytes(range(100)); e.u.mem_write(KIT + 28 + 100 * 2, snd); e.u.mem_write(KIT + 28 + 200 + 38, bytes([machine]))
    e.w32(G.ACT_TRACK, 2)
    e.u.mem_write(0x4F04C000, path + b'\0')
    def pth(u, a, z, _):
        sp = u.reg_read(mk.UC_M68K_REG_A7); calls.append(('PATH', e.r32(sp + 4))); u.reg_write(mk.UC_M68K_REG_D0, 0x4F04C000)
        u.reg_write(mk.UC_M68K_REG_PC, e.r32(sp)); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
    def prs(u, a, z, _):
        sp = u.reg_read(mk.UC_M68K_REG_A7); calls.append(('PARSE', u.reg_read(mk.UC_M68K_REG_A0), e.r32(sp + 4)))
        u.reg_write(mk.UC_M68K_REG_PC, e.r32(sp)); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
    e.u.hook_add(UC_HOOK_CODE, pth, begin=G.FS_PATH, end=G.FS_PATH)
    e.u.hook_add(UC_HOOK_CODE, prs, begin=G.PARSE, end=G.PARSE)
    H, RES = 0x4F04C800, 0x4F04C900
    e.u.mem_write(H, struct.pack('>4I', 77, 0xABCDEF01, size, 5)); e.u.mem_write(RES, bytes(8))
    d0, good = e.call(S['SPARSE'], H, regs={mk.UC_M68K_REG_A0: RES}, count=200000)
    return e, calls, RES, good, d0
e, calls, RES, good, d0 = browse(IMG, 6, 200000)
p, ctl = e.r32(RES), e.r32(RES + 4)
s = bytes(e.u.mem_read(p, 100)) if p else b''
chk('Sampl-Spur, Sample: Ergebnis = neuer Sound + Kontrollblock (Vtable, Zaehler 1 / 1, Zeiger), Register ok, d0 = &Ergebnis',
    good and d0 == RES and p and ctl and e.r32(ctl) == G.SPVT and r32s(e, ctl + 4, 3) == [1, 1, p])
want = bytearray(range(100)); want[38] = 6; struct.pack_into('>I', want, G.O_ID, 0xABCDEF01)
want[4:20] = b'AMEN BREAK 120.' + b'\0'
chk('  Sound = Sound der Spur, Kennung in k 25/26, Name = Dateiname (15 Zeichen): %r' % s[4:20], s == bytes(want))
chk('  Pfad der Datei 77 gefragt, Lade-Wunsch gesetzt', calls == [('PATH', 77)] and e.r32(S['LREQ']) == 0xABCDEF01)
for nm, mach, size in (('Preset (100 B) auf Sampl', 6, 100), ('Sample auf KICK-Spur', 0, 200000)):
    e, calls, RES, good, d0 = browse(IMG, mach, size)
    chk('%s: Firmware-Leser mit denselben Argumenten (a0 = &Ergebnis, Handle)' % nm,
        len(calls) == 1 and calls[0] == ('PARSE', RES, 0x4F04C800) and good)
e, calls, RES, good, d0 = browse(IMG, 6, 200000, inside=True)
p = e.r32(RES); s_ = bytes(e.u.mem_read(p, 100)) if p else b''
chk('Browser schon im Dateisystem: Sample trotzdem gewaehlt, ohne Pfad-Abfrage (Name der Spur bleibt)',
    good and p and not calls and s_[4:20] == bytes(range(4, 20)) and struct.unpack('>I', s_[G.O_ID:G.O_ID + 4])[0] == 0xABCDEF01)
e, calls, RES, good, d0 = browse(IMG, 6, 40)
chk('zu kleine Datei (40 B, kein Preset): leeres Ergebnis', e.r32(RES) == 0 and e.r32(RES + 4) == 0 and not calls)

# ---------------- 5 Sound speichern / laden (Core-Slot): Kennung im Satz +76
e = Emu(IMG)
SND, REC1, SND2 = 0x4F044000, 0x4F045000, 0x4F046000
snd = bytearray(random.Random(5).getrandbits(8) for _ in range(256))
rr = random.Random(6)
for k in range(23): snd[20 + 2 * k:22 + 2 * k] = struct.pack('>H', rr.randrange(0, 0x7F01))
snd[28] = 30; snd[88:92] = struct.pack('>I', 31)          # LFO -> Env, Velocity -> Decay (gueltige Ziele)
struct.pack_into('>I', snd, G.O_ID, 0x7777AAA1)
for nm, fn in (('v2', G.core.SV2_HOOK), ('v1', G.core.SV1_HOOK)):
    e.u.mem_write(SND, bytes(snd)); e.u.mem_write(REC1, bytes(256)); _, ok1 = e.call(fn, REC1, SND, count=200000)
    rec = bytes(e.u.mem_read(REC1, 128))
    e.u.mem_write(SND2, bytes(256)); _, ok2 = e.call(G.core.LD_HOOK, SND2, REC1, count=200000)
    back = e.r32(SND2 + G.O_ID)
    chk('Speichern %s + Laden: Kennung %#x (Satz +76 = %#x)' % (nm, back, struct.unpack('>I', rec[76:80])[0]),
        ok1 and ok2 and back == 0x7777AAA1 and rec[76:80] == struct.pack('>I', 0x7777AAA1))
# Stock-Satz (Firmware schreibt +76..79 = 0 und liest sie nicht): Kennung 0 = kein Sample; Stock laedt k 25/26 nie
es = Emu(STOCK)
es.u.mem_write(SND, bytes(snd)); es.u.mem_write(REC1, b'\xEE' * 256); es.call(G.core.SV2_HOOK, REC1, SND, count=200000)
srec = bytes(es.u.mem_read(REC1, 128))
e.u.mem_write(REC1, srec); e.u.mem_write(SND2, b'\xEE' * 256); e.call(G.core.LD_HOOK, SND2, REC1, count=200000)
chk('Stock-Satz: +76..79 = 0 (%s) -> Kennung 0 (kein Sample)' % srec[76:80].hex(),
    srec[76:80] == bytes(4) and e.r32(SND2 + G.O_ID) == 0)
# ---------------- 6 Maschinenwechsel mit dem echten Code: MACHINES-Rad 0x400a2712 -> 0x4001488a -> Setzen 0x4001477e
#                  -> Defaults 0x40014072 (Maschinen-Satz 0x4004df5c, Texte, Deskriptoren, Defaults in den Sound)
TRK, TVT, TSND, TCODE, THIS = 0x4F04E000, 0x4F04E100, 0x4F04E400, 0x4F04E800, 0x4F04EC00
def track_emu(img, machine):
    e = boot(img)
    e.w32(TRK, TVT)
    e.u.mem_write(TCODE, struct.pack('>HIH', 0x203C, TSND, 0x4E75) + struct.pack('>HH', 0x7000, 0x4E75))
    for k in range(16): e.w32(TVT + 4 * k, TCODE + (0 if k == 10 else 8))          # vt +0x28 -> Sound, sonst 0
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
        except Exception as x:
            good = False
        ok &= good; out.append(mach(e))
    return e, out, ok
e6, seq6, ok6 = wheel_seq(IMG, [1, 1, 1, 1, -1, 1])
e5, seq5, ok5 = wheel_seq(REF, [1, 1, 1, 1, -1, 1])
chk('MACHINES-Rad (echter Code, TONE +1 x4, -1, +1): %s, ohne sampler %s; Register / Stapel erhalten' % (seq6, seq5),
    seq6 == [5, 6, 6, 6, 5, 6] and seq5 == [5, 5, 5, 5, 4, 5] and ok6 and ok5)
s6 = bytes(e6.u.mem_read(TSND, 100))
w = lambda b, k: struct.unpack('>H', b[20 + 2 * k:22 + 2 * k])[0]
dec24 = struct.unpack('>I', IMG[G.DESC0 + G.DSTRIDE * 24 + 16 - BASE:][:4])[0] & 0xffff
chk('  Defaults von Sampl in den Sound: Start %#x, Length %#x, Filter %#x, Modell %#x, Decay %#x (Deskriptor 24: %#x)'
    % (w(s6, 11), w(s6, 12), w(s6, 13), w(s6, 14), w(s6, 18), dec24),
    (w(s6, 11), w(s6, 12), w(s6, 13), w(s6, 14), w(s6, 18)) == (0, 0x7F00, 0x4000, 0, dec24))
# jeder Wechsel 0..5 -> 0..5 schreibt denselben Sound wie ohne sampler; 0..5 -> 6 und 6 -> 0..5 ohne Fehler
bad = []
for a_ in range(7):
    for b_ in range(7):
        res = []
        for img in (IMG, REF):
            e = track_emu(img, a_)
            try:
                _, good = e.call(0x4001477E, TRK, b_, 0, 0, count=2000000)
            except Exception:
                good = False
            res.append((good, bytes(e.u.mem_read(TSND, 100))))
        (g1, s1), (g0, s0) = res
        if not g1 or (a_ < 6 and b_ < 6 and (s1 != s0 or not g0)) or (b_ == 6 and s1[38] != 6) or (a_ == 6 and b_ < 6 and s1[38] != b_):
            bad.append((a_, b_))
chk('Setzen 0x4001477e (echte Defaults) fuer alle Wechsel 0..6 -> 0..6: 0..5 wie ohne sampler, Sampl hin und zurueck %s' % bad[:6], not bad)
# ---------------- 7 Wellenform beim Drehen von Start / Length (KDRAW, echte Zeichenfunktionen und Schriften der Firmware)
VIEW, UIA, BMP, DATA, KSTR = 0x4F023000, 0x4F020800, 0x4F020400, 0x4F021000, 0x4F03F800
KIT = 0x4F04D000
def kd_emu(img):
    e = boot(img)
    e.u.mem_write(BMP, struct.pack('>IIIII', 0, 128, 64, 2, DATA))
    e.call(0x400E7D50)                                # Schriften wie beim Start
    e.u.mem_write(UIA, bytes(0x200)); e.u.mem_write(VIEW, bytes(0x300))
    e.u.hook_add(UC_HOOK_CODE, lambda u, a, z, _: (u.reg_write(mk.UC_M68K_REG_D0, UIA),
                 u.reg_write(mk.UC_M68K_REG_PC, e.r32(u.reg_read(mk.UC_M68K_REG_A7))),
                 u.reg_write(mk.UC_M68K_REG_A7, u.reg_read(mk.UC_M68K_REG_A7) + 4)), begin=G.UIGET, end=G.UIGET)
    e.orig = []
    def org(u, a, z, _):
        sp = u.reg_read(mk.UC_M68K_REG_A7); e.orig.append((e.r32(sp + 4), e.r32(sp + 8)))
        u.reg_write(mk.UC_M68K_REG_PC, e.r32(sp)); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
    e.u.hook_add(UC_HOOK_CODE, org, begin=G.KDRAW_ORIG, end=G.KDRAW_ORIG)
    return e
def screen(e):
    raw = bytes(e.u.mem_read(DATA, 1024)); px = set()
    for x in range(128):
        for wd in range(2):
            v = struct.unpack('>I', raw[(x * 2 + wd) * 4:(x * 2 + wd) * 4 + 4])[0]
            for bit in range(32):
                if v >> (31 - bit) & 1: px.add((x, wd * 32 + bit))
    return px
def kd_setup(e, frames, ovv, c, s, name, desc=10, popup=10, held=0, mach=6, sid=SID, track=2, loaded=True):
    e.w32(G.KITP, KIT); e.u.mem_write(KIT, bytes(28 + 600)); e.w32(G.ACT_TRACK, track)
    snd = KIT + 28 + 100 * track
    e.u.mem_write(snd + 4, name.encode()[:16].ljust(16, b'\0')); e.u.mem_write(snd + 38, bytes([mach]))
    e.u.mem_write(snd + 42, struct.pack('>HH', c << 8, s << 8)); e.w32(snd + G.O_ID, sid)
    e.u.mem_write(S['TAB'], bytes(16 * G.NTAB))
    if loaded: e.u.mem_write(S['TAB'] + 16, struct.pack('>4I', SID, POOL, frames, 65536))
    a_ = (POOL + 2 * frames + 47) & ~15
    e.u.mem_write(a_, b''.join(struct.pack('bb', lo, hi) for lo, hi in ovv))
    e.w32(VIEW + 0x230, desc); e.w32(UIA + 0x58, popup); e.w8(UIA + 0x164, held)
    e.u.mem_write(DATA, b'\x5a' * 1024)
def kd_native(e, ovv, c, s, name, desc):
    """dieselben Firmware-Aufrufe aus Python (Vorlage)"""
    call = lambda f, *a: e.call(f, *[x & 0xffffffff for x in a], count=400000)
    e.u.mem_write(DATA, b'\x5a' * 1024)
    call(G.FILL_F, BMP, 0, 0, 127, 63, 0)
    xs, xe = c, s
    for x in range(128):
        if (x < xs or x > xe) and x & 1: continue
        call(G.FILL_F, BMP, x, 26 + ((ovv[x][0] * 26) >> 7), x, 26 + ((ovv[x][1] * 26) >> 7), 1)
    call(G.FILL_F, BMP, xs, 0, xs, 52, -1)
    if xe != xs: call(G.FILL_F, BMP, xe, 0, xe, 52, -1)
    e.u.mem_write(KSTR, G.KDLAB[desc - 10].encode() + b'\0'); call(G.TXT_F, BMP, G.F_NAME, 0, 55, 0, G.FMT_S, KSTR)
    call(G.TXT_F, BMP, G.F_NAME, 128, 55, 4, G.FMT_D, c if desc == 10 else s)
    return screen(e)
# Uebersicht einer Kick (abklingender Sinus) ueber das Modell des Laders
KICK = [int(30000 * math.exp(-i / 6000) * math.sin(2 * math.pi * 55 * i / 48000 * (1 + 3 * math.exp(-i / 1500)))) for i in range(24000)]
OVK = ov_model(KICK)
ek = kd_emu(IMG)
for c, s, desc, nm in ((0, 127, 10, 'Kick 909'), (20, 60, 10, 'AMEN BREAK 120.wav'), (20, 60, 11, 'AMEN BREAK 120.wav'), (100, 0, 11, 'x'),
                       (90, 127, 11, 'Snare long name here')):
    kd_setup(ek, len(KICK), OVK, c, s, nm, desc=desc, popup=desc)
    ek.orig.clear(); _, good = ek.call(S['KDRAW'], VIEW, BMP, count=2000000); got = screen(ek)
    want = kd_native(ek, OVK, c, s, nm, desc)
    wave = {p for p in got if p[1] <= 52}
    chk('Wellenform %s Start %d Length %d: wie die Firmware-Aufrufe (%d Pixel), Linien bei %d / %d, Text oben, Register ok'
        % (G.KDLAB[desc - 10], c, s, len(got), c, s),
        good and not ek.orig and got == want and any(p[1] >= 55 for p in got) and not any(53 <= p[1] <= 54 for p in got) and wave)
    if c == 20 and desc == 10: PREV = [(got, 'Start 20')]
    if c == 20 and desc == 11: PREV.append((got, 'Length 60'))
    if c == 90: PREV.append((got, 'Start 90 Length 127'))
# sonst die Firmware (gleiche Argumente): anderer Parameter, kein Popup, Trig gehalten, andere Maschine, Sample nicht geladen
for nm, kw in (('Deskriptor 12', dict(desc=12)), ('Deskriptor 13 (Modell)', dict(desc=13)), ('kein Popup', dict(popup=0)),
               ('Trig gehalten (p-lock)', dict(held=1)), ('KICK-Spur', dict(mach=0)), ('Sample nicht geladen', dict(loaded=False)),
               ('kein Sample', dict(sid=0)), ('Spur 7?', dict(track=7))):
    kd_setup(ek, len(KICK), OVK, 20, 60, 'n', **kw)
    ek.orig.clear(); _, good = ek.call(S['KDRAW'], VIEW, BMP, count=2000000)
    chk('%s: Zeichnen der Firmware mit denselben Argumenten, Bild unberuehrt' % nm,
        good and ek.orig == [(VIEW, BMP)] and bytes(ek.u.mem_read(DATA, 1024)) == b'\x5a' * 1024)
chk('Vtable 0x4010053c -> KDRAW (Firmware: 0x4001e40a)', ek.r32(G.VT_KDRAW) == S['KDRAW'] and struct.unpack('>I', STOCK[G.VT_KDRAW - BASE:][:4])[0] == G.KDRAW_ORIG)
try:
    from PIL import Image
    sc = 4; out = Image.new('RGB', (128 * sc + 16, (64 * sc + 16) * len(PREV) + 16), (40, 40, 40))
    for i, (px, _) in enumerate(PREV):
        im = Image.new('RGB', (128, 64), (20, 20, 30))
        for (x, y) in px: im.putpixel((x, 63 - y), (230, 230, 240))
        out.paste(im.resize((128 * sc, 64 * sc), Image.NEAREST), (8, 8 + i * (64 * sc + 16)))
    out.save('wave_preview.png')
except ImportError:
    pass
# ---------------- 8 Sample-Lock (smp5): SLK in der Uebernahme eines Trigs (Haken 0x400590ce), Stimme mit OVR, Laden
EVT8, LOCK8 = 0x4F049800, 0x4F049A00
def slk(e, t, a5, ev2c):
    e.w32(EVT8 + 0x2c, ev2c); e.w32(EVT8 + 0x30, 0)
    d0, good = e.call(S['SLK'], regs={mk.UC_M68K_REG_D2: t, mk.UC_M68K_REG_A1: KITV, mk.UC_M68K_REG_A2: EVT8,
                                      mk.UC_M68K_REG_A5: a5}, count=5000)
    return e.u.reg_read(mk.UC_M68K_REG_A5), d0, e.r32(S['OVR'] + 4 * t), good and e.u.reg_read(mk.UC_M68K_REG_D2) == t
e8 = boot(IMG)
chk('Haken 0x400590ce = jsr SLK + nop', IMG[G.SL_HOOK - BASE:G.SL_HOOK - BASE + 8] == C.jsr(S['SLK']) + b'\x4e\x71')
kit_audio(e8, [6, 6, 0, 6, 6, 6], [SID, SID, 0, SID, SID, SID])
ks = lambda t: KITV + 28 + 100 * t
def lock(m, sid):
    e8.u.mem_write(LOCK8, bytes(100)); e8.u.mem_write(LOCK8 + 38, bytes([m])); e8.w32(LOCK8 + G.O_ID, sid)
res = []
e8.w32(S['OVR'] + 4, 0x7777); res.append(('ohne Lock', slk(e8, 1, ks(1), 0), (ks(1), 1 + 0x93, 0)))
lock(6, SID2); res.append(('Lock Sampl', slk(e8, 1, LOCK8, LOCK8), (ks(1), 1 + 0x93, SID2)))
lock(6, SID2); res.append(('danach ohne Lock', slk(e8, 1, ks(1), 0), (ks(1), 1 + 0x93, 0)))
lock(2, SID2); res.append(('Lock eines METAL-Presets', slk(e8, 3, LOCK8, LOCK8), (LOCK8, 3 + 0x93, 0)))
lock(6, SID2); res.append(('Lock auf einer KICK-Spur', slk(e8, 2, LOCK8, LOCK8), (LOCK8, 2 + 0x93, 0)))
lock(6, SID2); res.append(('anderer Sound (kein Lock)', slk(e8, 4, LOCK8, 0), (LOCK8, 4 + 0x93, 0)))
lock(6, 0); res.append(('Lock ohne Sample', slk(e8, 5, LOCK8, LOCK8), (LOCK8, 5 + 0x93, 0)))
for nm, (a5, d0, ov, good), want in res:
    chk('SLK %s: Sound %s, d0 = Spur + 0x93, OVR %#x, Register ok' % (nm, 'der Spur' if a5 != LOCK8 else 'des Locks', ov),
        (a5, d0, ov) == want and good)
SMP2 = [int(9000 * math.sin(2 * math.pi * i / 23.0)) + (i % 300) * 20 for i in range(2000)]
e, outs, caught = vloop(IMG, [6, 0, 0, 0, 0, 0], 10, smp=SMP, smp2=SMP2, ovr={0: SID2}, par={0: {11: 0x2000, 12: 0x4000}})
got = [x for c in caught for x in c]
st2 = len(SMP2) * 0x20 // 127; sp2 = max(1, len(SMP2) * 0x40 // 127 - st2)
chk('Stimme mit Lock (OVR): zweites Sample, Start / Length der Spur (nicht des Locks)', got == model_clean(SMP2, st2, sp2, 65536, 0, 0, len(got)))
e, outs, caught = vloop(IMG, [6, 0, 0, 0, 0, 0], 10, smp=SMP, smp2=SMP2)
got = [x for c in caught for x in c]
chk('Stimme ohne Lock: Kennung aus dem Sound der Spur im Kit der Klangerzeugung', got == model_clean(SMP, 0, N, 65536, 0, 0, len(got)))
# ---------------- 9 Browser-Vorschau (smp7): KCUR, wenn der Cursor im Preset-Browser wandert (Vtable 0x401183ec +0x4c)
BRW, LST9, LVT9, UI9, PTH9 = 0x4F03A000, 0x4F03A400, 0x4F03A500, 0x4F03A600, 0x4F03A800
e9 = boot(IMG); calls9 = []
ENT = {3: (1003, 0x3001, 200000), 5: (1005, 0x5001, 90000), 6: (1006, 0x6001, 4096), 7: (1007, 0x7001, 100),
       8: (1008, 0x8001, 50000), 9: (1009, 0x9001, 60000), 10: (1010, 0xA001, 70000), 11: (1011, 0xB002, 70000),
       12: (1012, 0xC001, 70000)}
DIRS = {6}
def ret9(u, v=None):
    sp = u.reg_read(mk.UC_M68K_REG_A7)
    if v is not None: u.reg_write(mk.UC_M68K_REG_D0, v & 0xffffffff)
    u.reg_write(mk.UC_M68K_REG_PC, e9.r32(sp)); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
def cur9(u, a, z, _):
    sp = u.reg_read(mk.UC_M68K_REG_A7); calls9.append(('cur', e9.r32(sp + 4), e9.r32(sp + 8))); ret9(u)
def isfile9(u, a, z, _):
    sp = u.reg_read(mk.UC_M68K_REG_A7); ret9(u, 0 if e9.r32(sp + 8) in DIRS else 1)
def entry9(u, a, z, _):
    sp = u.reg_read(mk.UC_M68K_REG_A7); out = u.reg_read(mk.UC_M68K_REG_A0); i = e9.r32(sp + 8)
    ino, hid, size = ENT.get(i, (0xFFFFFFFF, 0, 0)); e9.u.mem_write(out, struct.pack('>4I', ino, hid, size, 0))
    calls9.append(('entry', e9.r32(sp + 4), i)); ret9(u, out)
def path9(u, a, z, _):
    sp = u.reg_read(mk.UC_M68K_REG_A7); ino = e9.r32(sp + 4)
    e9.u.mem_write(PTH9, b'/Samples/Drums/File %d.wav\0' % ino); ret9(u, PTH9)
for addr, fn in ((G.BR_CUR, cur9), (0x4F03A5F0, isfile9), (G.FL_ENTRY, entry9), (G.FS_PATH, path9),
                 (G.UIGET, lambda u, a, z, _: ret9(u, UI9))):
    e9.u.hook_add(UC_HOOK_CODE, fn, begin=addr, end=addr)
e9.u.mem_write(LVT9, bytes(0x40)); e9.w32(LVT9 + 0x20, 0x4F03A5F0); e9.w32(LST9, LVT9); e9.u.mem_write(UI9, bytes(0x200))
e9.u.mem_write(BRW, bytes(0x300)); e9.w32(BRW + 0x278, LST9); e9.w32(BRW + 0x280, LST9)
KIT9 = 0x4F04D000; e9.w32(G.KITP, KIT9); e9.u.mem_write(KIT9, bytes(28 + 600)); e9.w32(G.ACT_TRACK, 2)
snd9 = KIT9 + 28 + 200
e9.u.mem_write(snd9 + 4, b'OLD NAME\0'.ljust(16, b'\0')); e9.u.mem_write(snd9 + 38, bytes([6])); e9.w32(snd9 + G.O_ID, SID)
def step9(cursor):
    # wie die Listenlogik der Firmware (0x4007264e / 0x40072aa8): erst +0x10 = Cursor, dann vt+0x4c(Liste, +0x10);
    # +0x24 ist ein anderes Feld (smp7 las es faelschlich, Pip: Vorhoeren ging nicht) - hier absichtlich falsch belegt
    e9.w32(BRW + 0x10, cursor); e9.w32(BRW + 0x24, 5 if cursor != 5 else 12); calls9.clear(); e9.w32(S['LREQ'], 0)
    _, good = e9.call(S['KCUR'], BRW, cursor, count=200000)
    return e9.r32(snd9 + G.O_ID), e9.cstr(snd9 + 4), e9.r32(S['LREQ']), good and ('cur', BRW, cursor) in calls9
def ck9(nm, r, sid, name, req):
    chk('Cursor %s: Kennung %#x, Name %r, Lade-Wunsch %#x, Firmware (Vorhoeren) gerufen, Register ok' % (nm, r[0], r[1], r[2]),
        r[:3] == (sid, name, req) and r[3])
ck9('auf Sample 5', step9(5), 0x5001, 'File 1005.wav', 0x5001)
ck9('auf einen Ordner', step9(6), 0x5001, 'File 1005.wav', 0)
ck9('auf ein Preset (100 B)', step9(7), 0x5001, 'File 1005.wav', 0)
e9.w8(UI9 + 0x164, 1); ck9('mit gehaltenem Trig (Lock erst mit YES)', step9(8), 0x5001, 'File 1005.wav', 0); e9.w8(UI9 + 0x164, 0)
e9.u.mem_write(snd9 + 38, bytes([0])); ck9('auf einer KICK-Spur', step9(9), 0x5001, 'File 1005.wav', 0); e9.u.mem_write(snd9 + 38, bytes([6]))
e9.w32(BRW + 0x278, LST9 + 0x40); ck9('mit anderer Liste aktiv', step9(10), 0x5001, 'File 1005.wav', 0); e9.w32(BRW + 0x278, LST9)
ck9('auf gerade Kennung (keine Datei)', step9(11), 0x5001, 'File 1005.wav', 0)
ck9('ausserhalb der Liste', step9(40), 0x5001, 'File 1005.wav', 0)
ck9('auf Sample 12', step9(12), 0xC001, 'File 1012.wav', 0xC001)
e9.w32(G.FS_LOCKO, TASK); ck9('im Dateisystem: Kennung ja, Name bleibt', step9(9), 0x9001, 'File 1012.wav', 0x9001); e9.w32(G.FS_LOCKO, 0)
def _fw_calls_4c():
    # statisch: beide Aufrufer von vt+0x4c in der Listenlogik schieben +0x10 als Cursor (move.l $10(a2),-(sp) bzw. $18(sp))
    import hashlib
    h = lambda a, n: hashlib.sha256(STOCK[a - BASE:][:n]).hexdigest()
    return (h(0x4007264E, 10) == '8cdd43b5de29784a55070a7b4fa500d14a6fd2547e6d8a310681b23d81aedab0'
            and h(0x40072AAA, 6) == '788d13c7a150b92bd86c2eb4c449fa97ae63595b837288a77a7dd7e6bd77a645')
chk('Firmware ruft vt+0x4c mit Liste +0x10 als Cursor (0x4007264e, 0x40072aaa)', _fw_calls_4c())
chk('smp15: Vtable des Preset-Browsers +0x4c (Cursor bewegt) bleibt bei der Firmware 0x400a64be (Sample erst mit YES)',
    e9.r32(G.VT_CUR) == G.BR_CUR == struct.unpack('>I', STOCK[G.VT_CUR - BASE:][:4])[0])
chk('alle Aufrufe erhalten d2-d7 / a2-a6 und den Stapel %s' % sorted(set(BADCALL))[:8], not BADCALL)
# smp12 (Pip: "Start verschiebt Start + Length als Block"): SHAPE = Ende; Start aendert das Ende nicht
sp_ = []
for st_ in (0, 20, 40, 60, 100):
    e, outs, caught = vloop(IMG, [6, 0, 0, 0, 0, 0], 2, smp=SMP, par={0: {11: st_ << 8, 12: 80 << 8}})
    v_ = 0x42308828
    sp_.append((e.r32(v_ + G.V['ST']), e.r32(v_ + G.V['SPAN'])))
E80 = N * 80 // 127
chk('Ende 80 bei Start 0 / 20 / 40 / 60 / 100: Ende bleibt %s, Laenge = Ende - Start; Start hinter dem Ende: 1 Frame'
    % [a_ + b_ for a_, b_ in sp_[:4]], [a_ + b_ for a_, b_ in sp_[:4]] == [E80] * 4 and sp_[4][1] == 1)
# ---------------- smp41: DCK (Pip: Knacken beim Retrigger langer Samples / Vlvt-Akkorde): Uebergang beim Trig glaetten
ed = boot(IMG)
VD = 0x42308828 + 0x31C * 3                                  # Stimme der Spur 4
BUFD = 0x4F025000
def dck(block, trig):
    ed.u.mem_write(BUFD, struct.pack('>32i', *block)); ed.w32(VD + 0x38, 1 if trig else 0)
    d0, good = ed.call(S['DCK'], regs={mk.UC_M68K_REG_A0: BUFD, mk.UC_M68K_REG_A2: VD}, count=20000)
    return list(struct.unpack('>32i', bytes(ed.u.mem_read(BUFD, 128)))), good
ed.u.mem_write(G.DCKS_A, bytes(96))
old = [int(0.6 * 2 ** 31) - 1000 * i for i in range(32)]
o1, g1 = dck(old, False)                                     # alter Ton, kein Trig: unveraendert, LAST gemerkt
new = [-int(0.5 * 2 ** 31) + 2000 * i for i in range(32)]
o2, g2 = dck(new, True)                                      # Trig: Sprung von +0.6 auf -0.5
o3, g3 = dck(new, False); o4, g4 = dck(new, False); o5, g5 = dck(new, False)
seq = o2 + o3 + o4
jump = abs(seq[0] - old[-1]) / 2 ** 31
maxstep = max(abs(a - b) for a, b in zip(seq, seq[1:])) / 2 ** 31
chk('DCK: ohne Trig unveraendert; Trig: erster Wert = letzter des alten Tons (Sprung %.4f statt %.2f), dann linear in %d Samples '
    'auf den neuen (groesster Schritt %.4f), danach unveraendert; Register / Stapel ok'
    % (jump, abs(new[0] - old[-1]) / 2 ** 31, G.NDK, maxstep),
    o1 == old and jump < 0.001 and maxstep < 1.2 / G.NDK + 0.01 and o5 == new and all(abs(a - b) <= 8 for a, b in zip(o4[G.NDK - 64:], new[G.NDK - 64:]))
    and g1 and g2 and g3 and g4 and g5)
# Saettigung: Versatz + Signal ueber Vollaussteuerung
dck([0x7FFFFFFF] * 32, False); o6, _ = dck([0x7F000000] * 32, True)
dck([-0x80000000] * 32, False); o7, _ = dck([0x7F000000] * 32, True)
chk('DCK: gesaettigt, kein Ueberlauf (%#x / %#x)' % (o6[0] & 0xffffffff, o7[0] & 0xffffffff), all(x > 0x7E000000 for x in o6) and o7[0] < -0x7E000000 and o7[31] < o7[0] + 0x7F000000)
chk('jsr DCK im Image (Grit AMPT, mit strings auch Vlvt): %d' % IMG.count(b'\x4e\xb9' + struct.pack('>I', S['DCK'])), IMG.count(b'\x4e\xb9' + struct.pack('>I', S['DCK'])) >= 1)
done()
