# mono (v2, Patch 18, smp18): 9. Maschine 'Monom' (smp18 'Mono'). Echter Firmware-Code im Emulator wie test_strings, Vergleich mit dem Image
# ohne mono; Stimme bitgleich gegen das Ganzzahl-Modell mono_model.
# Aufruf: test_mono.py [--wav pfad]
import math, struct, sys, wave
from rig import *
import g2_mono as G
import g2_strings as ST
import g2_sampler as SM
import mono_model as MM
import mono_tables as MT
import cfemac
sys.path.insert(0, str(ROOT / 'Modded-Cycles' / 'tools' / 'emu'))
import emac as MEMAC
import numpy as np

IMG = v2_image()
REF = v2_image([i for i in V2_IDS if i != 'mono'])
S, SS, S7 = V2SYM['mono'], V2SYM['strings'], V2SYM['sampler']
SM.build(); ST.build(); G.build()
OPS = cfemac.ops()
WAV = sys.argv[sys.argv.index('--wav') + 1] if '--wav' in sys.argv else None
TASK = 0x4F04F800
R2D = {66: 80, 67: 81, 68: 82, 69: 83}


def boot(img, emac=False):
    e = Emu(img)
    e.u.mem_map(0x42300000, 0x30000); e.u.mem_map(0x43800000, 0x800000); e.u.mem_map(0x422F0000, 0x10000)
    e.w32(SM.RUNNING, TASK)
    if emac:
        m = MEMAC.EMAC(e.u); m.install(OPS); e.mac = m
    e.call(0x4000045C, count=2000000); e.call(0x400DE244, count=20000000); e.call(0x4005A274, count=5000000)
    for t in range(6): e.w32(0x42308828 + 0x31C * t + 0x318, 0x8000BD98 + 0x30 * t)
    return e


def r32s(e, a, n): return list(struct.unpack('>%dI' % n, bytes(e.u.mem_read(a, 4 * n))))


# ---------------- 1 Anmeldung
e1, e0 = boot(IMG), boot(REF)
rows0, rows1 = r32s(e0, SS['ROWS8'], 64), r32s(e1, S['ROWS9'], 72)
chk('Zeilen 0..7 wie ohne mono, Zeile 8 = Decay 65 (TONE), -, eigene 80..83: %s' % rows1[64:],
    rows1[:64] == rows0 and rows1[64:] == [65, 0, 80, 81, 82, 83, 0, 0] and all(e1.r32(v) == S['ROWS9'] for v in SM.ROW_REFS))
D = [struct.unpack('>14I', bytes(e1.u.mem_read(C.DTD(k), 0x38))) for k in range(80, 86)]
chk('Deskriptoren 80..85: Feld / Slot / Bereich / Default wie geplant, Namen %s' % [e1.cstr(x[11]) for x in D],
    [x[:5] for x in D] == [(f, sl, 0, top, df) for _, _, f, sl, top, df, _, _ in G.KNOBS]
    and [e1.cstr(x[11]) for x in D] == [x[0] for x in G.KNOBS] and [e1.cstr(x[13]) for x in D] == [x[1] for x in G.KNOBS]
    and bytes(e1.u.mem_read(C.DONOR + 4, 6)) == bytes(x[7] for x in G.KNOBS) and bytes(e1.u.mem_read(C.MACHMAP + 4, 6)) == bytes([8] * 4 + [0xFF] * 2))
bad = []
for slot in range(34):
    for m in range(9):
        a_ = e1.call(0x4005A692, slot, m)[0]
        want = e0.call(0x4005A692, slot, m)[0] if (m in (5, 7) and slot in (24, 27)) else {24: 84, 27: 85}.get(slot, e0.call(0x4005A692, slot, m)[0] if m < 8 else {11: 80, 12: 81, 13: 82, 14: 83, 18: 65}.get(slot, e0.call(0x4005A692, slot, 4)[0] if not 11 <= slot <= 14 else 0))
        if a_ != want: bad.append((slot, m, a_, want))
chk('Parameter-Suche (Slot 0..33, Maschine 0..8): 0..7 wie ohne mono, Mono = 80..83, Decay 65; k 24 / 27 = Glide / Noise (allgemein; CHORD / Vlvt: Strum) %s' % bad[:4], not bad)
recs0 = [r32s(e0, e0.call(0x4004DF5C, n)[0], 19) for n in range(9)]
recs1 = [r32s(e1, e1.call(0x4004DF5C, n)[0], 19) for n in range(10)]
r10 = recs1[9]
chk('Maschinen-Saetze 0..8 wie ohne mono; 9 = eigener (R10) aus dem von TONE, 66..69 -> 80..83: %s' % r10[2:8],
    recs1[:9] == recs0 and e1.call(0x4004DF5C, 9)[0] == S['R10'] and r10[2:] == [R2D.get(x, x) for x in recs0[5][2:]]
    and e1.r32(G.OBJ0 + 32) == S['WFMT'] and e1.r32(G.OBJ0 + 44) == 0)
of = [e1.call(0x4004DF76, m)[0] for m in range(10)]; of0 = [e0.call(0x4004DF76, m)[0] for m in range(10)]
chk('Satz der Maschine: 0..7 wie ohne mono, 8 = R10', of[:8] == of0[:8] and of[8] == S['R10'] and of[9] == of0[9])
BUF = 0x4F04B800
fm = []
for v in (0, 0x100, 0x380, 0x700, 0x7F00, 0xFFFFFF00):
    e1.u.mem_write(BUF, bytes(32)); e1.call(S['WFMT'], 0x4F04B700, v, BUF, count=200000); fm.append(e1.cstr(BUF))
chk('Formatierer der Wellen (sprintf der Firmware): %s' % fm, fm == ['SAW', 'SQR', 'TRI', 'RING', 'RING', 'SAW'])
def knobs(e, m):
    VW = 0x4F047000; VEC = 0x4F047800
    e.u.mem_write(VEC, struct.pack('>6I', *range(1, 7))); e.w32(VW + 0x68, VEC)
    return [e.call(0x4001E814, VW, kn, f, -1, count=200000)[0] for kn in range(2, 16) for f in (0, 1)]
for e in (e0, e1):
    for t, v in ((0x4001E318, None), (0x4006B736, 0), (0x400CF9A8, 0x4F046000)):
        e.u.hook_add(UC_HOOK_CODE, lambda u, a, z, _, e=e, v=v: (u.reg_write(mk.UC_M68K_REG_D0, e.mach if v is None else v),
                     u.reg_write(mk.UC_M68K_REG_PC, e.r32(u.reg_read(mk.UC_M68K_REG_A7))),
                     u.reg_write(mk.UC_M68K_REG_A7, u.reg_read(mk.UC_M68K_REG_A7) + 4)), begin=t, end=t)
kk = {}
for m in range(9):
    e0.mach = e1.mach = m
    kk[m] = (knobs(e0, m), knobs(e1, m))
chk('Knoepfe der Maschinen 0..7 wie ohne mono (auch mit FUNC)', all(kk[m][0] == kk[m][1] for m in range(8)))
k8 = kk[8][1]; t4 = kk[4][0]
want = [R2D.get(x, x) for x in t4]; want[(2 - 2) * 2 + 1] = 84; want[(7 - 2) * 2 + 1] = 85
chk('Knoepfe Mono: wie TONE mit 80..83, FUNC + PITCH = 84 (Glide), FUNC + CONTOUR = 85 (Noise): %s' % k8[:12], k8 == want)
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
c8, d8_, r8_ = images(IMG, 8); c4, d4_, _ = images(REF, 4)
ev = Emu(IMG); bm = [ev.r32(S['MBM'] + 4 * i) for i in range(6)]
chk('MACHINES-Bilder: 0..7 wie ohne mono; Monom = grosses Bild von TONE + eigenes Icon (MBM), Stapel wie die Firmware, d3 bleibt 8',
    all(images(IMG, m) == images(REF, m) for m in range(8)) and c8[0] == c4[0] and c8[1] == c4[1][:1] + (S['MBM'],) + c4[1][2:]
    and len(c8) == 2 and d8_ == d4_ and r8_ == 8 and bm == [C.BITMAP_VT, 34, 34, 2, S['MICON'], SM.ICON_MASK]
    and bytes(ev.u.mem_read(S['MICON'], 272)) == C.icon(G.ICON_FILE)[2])
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
mk9 = marks(IMG, 8)
chk('MACHINES: 9 Positionen ab x = 73, Abstand 6 (letzte bei %d), die 9. gefuellt' % mk9[-1][0],
    [x for x, _ in mk9] == [73 - 4 + 6 * i for i in range(9)] and [f for _, f in mk9] == [False] * 8 + [True])
nm = [e1.cstr(e1.r32(S['NAMES9'] + 4 * i)) for i in range(9)]
chk('Namen: %s' % nm, nm == ['Kick', 'Snare', 'Metal', 'Perc', 'Tone', 'Chord', 'Grit', 'Vlvt', 'Monom'] and e1.r32(SM.NAMES_REF) == S['NAMES9'])
chk('Grenzen 8, Algorithm bis 8, Tabelle Maschine -> Klangerzeugung (9 Eintraege), update / render 9',
    e1.r32(SM.ALG_MAX) == 0x800 and all(IMG[va - BASE + 1] == REF[va - BASE + 1] + 1 for va in G.B8)
    and e1.r32(G.MAP_REF) == S['MAP9'] and bytes(e1.u.mem_read(S['MAP9'], 9)) == bytes(range(9))
    and r32s(e1, S['UPD9'], 9)[:8] == r32s(e0, SS['UPD8'], 8) and r32s(e1, S['UPD9'], 9)[8] == S['MUPD']
    and r32s(e1, S['RND9'], 9)[:8] == r32s(e0, SS['RND8'], 8) and r32s(e1, S['RND9'], 9)[8] == S['MRND'])
OBJ, TRKO, VT, FN, SND = 0x4F04C000, 0x4F04C100, 0x4F04C200, 0x4F04C400, 0x4F04C500
def appl(e, m):
    e.w32(OBJ + 4, TRKO); e.w32(TRKO, VT); e.w32(VT + 0x28, FN)
    e.u.mem_write(FN, struct.pack('>HIH', 0x203C, SND, 0x4E75)); e.u.mem_write(SND + 38, bytes([m]))
    return [(e.call(0x4000AA9A, OBJ, k)[0] != 0) for k in range(96)]
bad = []
for m in range(9):
    a1, a0 = appl(e1, m), appl(e0, m)
    for k in range(96):
        want = (a0[k] if k < 80 or k >= 86 else False) or (m == 8 and 80 <= k <= 83) or k in (84, 85)
        if a1[k] != want: bad.append((m, k))
chk('Anwendbarkeit: 0..79 / 86.. wie ohne mono, 80..83 nur auf Mono, 84 / 85 allgemein (wie Attack) %s' % bad[:5], not bad)
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
def wheel_seq(img, steps, start=6):
    e = track_emu(img, start); out = []; ok = True
    for st in steps:
        try: _, good = e.call(0x400A2712, THIS, st, 0, 0, count=2000000)
        except Exception: good = False
        ok &= good; out.append(e.r8(TSND + 38))
    return out, ok
s9, ok9 = wheel_seq(IMG, [1, 1, 1, -1, 1, -1, -1]); s8, ok8 = wheel_seq(REF, [1, 1, 1, -1, 1, -1, -1])
chk('MACHINES-Rad (Grit +1 x3, -1, +1, -1 x2): %s, ohne mono %s' % (s9, s8), s9 == [7, 8, 8, 7, 8, 7, 6] and s8 == [7, 7, 7, 6, 7, 6, 5] and ok9 and ok8)
w = lambda b, k: struct.unpack('>H', b[20 + 2 * k:22 + 2 * k])[0]
e = track_emu(IMG, 4); e.call(0x4001477E, TRK, 8, 0, 0, count=2000000); sd = bytes(e.u.mem_read(TSND, 100))
chk('  Defaults von Mono (Welle, Timbre, Sub, Drive) = %s' % [hex(w(sd, k)) for k in (11, 12, 13, 14)],
    sd[38] == 8 and [w(sd, k) for k in (11, 12, 13, 14)] == [x[5] for x in G.KNOBS[:4]])
bad = []
for a_ in range(9):
    for b_ in range(9):
        res = []
        for img in (IMG, REF):
            e = track_emu(img, a_ if img is IMG or a_ < 8 else 4)
            try: _, good = e.call(0x4001477E, TRK, b_, 0, 0, count=2000000)
            except Exception: good = False
            res.append((good, bytes(e.u.mem_read(TSND, 100))))
        (g1, s1), (g0, s0) = res
        if not g1 or (a_ < 8 and b_ < 8 and (s1 != s0 or not g0)) or s1[38] != b_: bad.append((a_, b_))
chk('Setzen 0x4001477e fuer alle Wechsel 0..8 -> 0..8: 0..7 wie ohne mono, Mono hin und zurueck %s' % bad[:6], not bad)
# smp23: Glide / Noise (k 24 / 27) speichert der Core (Sound-Slot 3, Satz +80 / +81; test_strum), Sound-Slot 4 ist frei
chk('Sound-Slot 4 (frueher mono) frei, Slot 3 = ATH des Cores', 'mono' not in C.SSLOT and e1.r32(V2SYM['core']['SSLOTS'] + 4 * C.SSLOT['core-attack']) == V2SYM['core']['ATH'])

# ---------------- 2 Stimme gegen das Modell
PAR, OUT, PMOD = 0x4F04A000, 0x80001858, 0x80001830
DEF = {10: 0x4000, 11: 0, 12: 0x4000, 13: 0, 14: 0x1800, 15: 0, 16: 0, 17: 0x4000, 18: 0x4000, 24: 0, 27: 0}


def vloop(blocks, par=None, notes=None, trig_at=(1,), per_block=None, count_ins=False):
    e = boot(IMG, emac=True)
    caught = {t: [] for t in range(6)}
    for t_ in (SM.AMPENV, SM.VCA):
        e.u.mem_write(t_, b'\x4e\x75')
        def cb(u, a, z, _, t_=t_):
            sp = u.reg_read(mk.UC_M68K_REG_A7)
            if t_ == SM.VCA:
                tr = (e.r32(sp + 8) - 0x42308828) // 0x31C
                caught[tr].append(list(struct.unpack('>32i', bytes(e.u.mem_read(e.r32(sp + 4), 128)))))
        e.u.hook_add(UC_HOOK_CODE, cb, begin=t_, end=t_)
    for f in SM.UPD_ORIG + SM.RND_ORIG: e.u.mem_write(f, b'\x4e\x75')
    for t in range(6):
        vals = dict(DEF); vals[9] = 8 << 8; vals.update((par or {}).get(t, {}))
        for k, v in vals.items(): e.u.mem_write(PAR + 14 + 66 * t + 2 * k, struct.pack('>H', v & 0xffff))
        e.w32(PMOD + 4 * t, (notes or {}).get(t, 48 << 16))
    n_ins = [0]
    if count_ins:
        e.u.hook_add(UC_HOOK_CODE, lambda u, a, z, _: n_ins.__setitem__(0, n_ins[0] + 1), begin=G.ORG, end=G.ORG + G.ROOM)
    cnt = []
    for b in range(blocks):
        e.u.mem_write(OUT, bytes(6 * 128))
        for t, kv in ((per_block or {}).get(b) or {}).items():
            for k, v in kv.items():
                if k == 'note': e.w32(PMOD + 4 * t, v)
                else: e.u.mem_write(PAR + 14 + 66 * t + 2 * k, struct.pack('>H', v & 0xffff))
        e.mac.macsr = 0xA0
        n0 = n_ins[0]
        _, good = e.call(0x400A7D4A, OUT, PAR, 0x3F if ((b in trig_at and b >= 2) or b == 0) else 0, 0, count=4000000)
        cnt.append(n_ins[0] - n0); assert good
    return e, caught, cnt


def model_run(blocks, par=None, notes=None, trig_at=(1,), per_block=None, track=0):
    v = MM.Voice(track)
    pr = dict(DEF); pr.update((par or {}).get(track, {}))
    note = (notes or {}).get(track, 48 << 16); out = []
    for b in range(blocks):
        for k, x in ((per_block or {}).get(b) or {}).get(track, {}).items():
            if k == 'note': note = x
            else: pr[k] = x
        if b == 0: continue
        # Die Stimmen-Schleife legt den Trig-Wunsch eines Blocks erst im naechsten Block an die Stimme (+0x38): Block 0 (Wechsel
        # der Maschine) -> Trig in Block 1, Wunsch in b >= 2 -> Trig in b + 1 (der Pruefstand setzt in Block 1 keinen Wunsch)
        v.update(pr, note, b == 1 or (b - 1 >= 2 and (b - 1) in trig_at)); out.append(v.render())
    return out


def cmp(nm, blocks, **kw):
    e, caught, _ = vloop(blocks, **kw)
    ok_, err = True, 0
    for t in (0, 3):
        ref = model_run(blocks, track=t, **kw); got = caught[t]
        if len(got) != blocks - 1 or len(ref) != blocks - 1: ok_ = False; continue
        err = max(err, max(abs(a - b) for x, y in zip(got, ref) for a, b in zip(x, y)))
    pk = max(abs(a) for x in caught[0] for a in x) / 2 ** 31
    chk('%s: %d Bloecke, Spur 1 / 4 gegen das Modell (Abweichung %d LSB), Spitze %.3f' % (nm, blocks, err, pk), ok_ and err == 0)
    return caught


for wv in range(8):
    cmp('Welle %s, SHAPE 64 / 127 / 0, Sub, Drive' % MT.WAVES[wv], 40,
        par={t: {11: wv << 8, 12: (0x4000, 0x7F00, 0)[t % 3], 13: 0x4000 * (t % 2), 14: 0x2000 + 0x1800 * t} for t in range(6)},
        notes={t: (36 + 7 * t) << 16 for t in range(6)}, trig_at=(1, 20))
cmp('Glide 60 und 127, Notenwechsel, Noise 64 / 127', 70, par={t: {24: (60 << 8) if t < 3 else 0x7F00, 27: 0x4000 if t % 2 else 0x7F00} for t in range(6)},
    per_block={20: {t: {'note': 60 << 16} for t in range(6)}, 45: {t: {'note': 36 << 16} for t in range(6)}}, trig_at=(1, 20, 45))
cmp('Welle umschalten im Spiel (alle 8), PITCH / FINE', 90, per_block={10 * i: {t: {11: i << 8, 10: 0x4000 + 0x100 * i, 17: 0x4000 - 0x400 * i} for t in range(6)} for i in range(8)})
cmp('Extreme: Note 108 SYNC 127, Note 12 SUB 127, Drive 127', 30, par={t: {11: 0x500, 12: 0x7F00, 13: 0x7F00, 14: 0x7F00} for t in range(6)},
    notes={t: (108 if t < 3 else 12) << 16 for t in range(6)})
# Unperfektheit: zwei Anschlaege desselben Tons sind nicht gleich (Zufall), Drift bewegt die Tonhoehe langsam
v = MM.Voice(0); p = dict(DEF)
v.update(p, 48 << 16, True); r1 = v.rnd; v.update(p, 48 << 16, True); r2 = v.rnd
cents = [(r * 100 / 65536) for r in (r1, r2)]
d = []
for b in range(4000):
    v.update(p, 48 << 16, False); d.append(v.drift('o1') * 100 / 65536)
chk('Zufall je Anschlag %s Cent (+-%.1f), Drift Osc 1 zwischen %.2f und %.2f Cent' % (['%.2f' % c for c in cents], MT.RNDC, min(d), max(d)),
    r1 != r2 and all(abs(c) <= MT.RNDC for c in cents) and max(d) - min(d) > 1.5 and max(abs(x) for x in d) <= 2.6)
# Bandbegrenzung: SAW offen, Note 96: Spiegelungen weit unter dem Grundton (Modell, bitgleich zum Code)
v = MM.Voice(0); p = dict(DEF); p[12] = 0; p[14] = 0
y = []
for b in range(400): v.update(p, 96 << 16, b == 0); y += v.render()
y = np.array(y[3200:], float); f0 = 440 * 2 ** ((96 - 69) / 12)
sp_ = np.abs(np.fft.rfft(y * np.hanning(len(y)))); fr = np.fft.rfftfreq(len(y), 1 / 48000)
harm = np.array([abs(f - round(f / f0) * f0) < 40 for f in fr])
al = 20 * math.log10(sp_[np.argmin(abs(fr - f0))] / sp_[(~harm) & (fr > 300) & (fr < 16000)].max())
chk('SAW Note 96 (%.0f Hz): Nicht-Harmonische bis 16 kHz %.0f dB unter dem Grundton (Rauschteppich und Drift eingeschlossen)' % (f0, al), al > 40)
# andere Maschinen unberuehrt
def dispatch(img):
    e = boot(img, emac=True); tr = []
    fs = list(SM.UPD_ORIG + SM.RND_ORIG) + [S7['SUPD'], S7['SRND'], SS['SUPD8'], SS['SRND8']]
    for f in fs:
        e.u.mem_write(f, b'\x4e\x75')
        def cb(u, a, z, _, f=f):
            sp = u.reg_read(mk.UC_M68K_REG_A7); tr.append((f,) + tuple(e.r32(sp + 4 + 4 * i) for i in range(3)))
        e.u.hook_add(UC_HOOK_CODE, cb, begin=f, end=f)
    for b in range(9):
        for t in range(6): e.u.mem_write(PAR + 14 + 66 * t + 18, struct.pack('>H', ((t + b // 3) % 8) << 8))
        e.mac.macsr = 0xA0; e.call(0x400A7D4A, OUT, PAR, 0x3F if b % 3 == 0 else 0, 0, count=2000000)
    return tr
t1, t0 = dispatch(IMG), dispatch(REF)
chk('Stimmen-Schleife, Maschinen 0..7 (auch Wechsel): %d Aufrufe wie ohne mono' % len(t1), t1 == t0 and len(t1) == 9 * 12)
# smp44: GATE (Byte 32 = k 16) wie bei TONE: echte Huellkurve der Firmware (AMPENV, Stufen 0 Attack, 2 Halten, 1 Decay); Spuren
# ohne / mit GATE im Wechsel; Loslassen (4. Argument der Stimmen-Schleife) bei Block 40; Spur 5: Decay 127
def gate_run(img):
    e = boot(img, emac=True)
    for f in [SM.VCA] + list(SM.UPD_ORIG + SM.RND_ORIG): e.u.mem_write(f, b'\x4e\x75')
    for t in range(6):
        vals = dict(DEF); vals[9] = 8 << 8; vals[16] = (t & 1) << 8; vals[18] = 0x7F00 if t == 5 else 0x1400
        for k, v in vals.items(): e.u.mem_write(PAR + 14 + 66 * t + 2 * k, struct.pack('>H', v & 0xffff))
        e.w32(PMOD + 4 * t, 48 << 16)
    st, ev = [], []
    for b in range(90):
        e.mac.macsr = 0xA0
        _, good = e.call(0x400A7D4A, OUT, PAR, 0x3F if b in (0, 2) else 0, 0x3F if b == 40 else 0, count=4000000); assert good
        st.append([e.r32(0x42308828 + 0x31C * t + 0x23C) for t in range(6)])
        ev.append([e.r32(0x42308828 + 0x31C * t + 0x230) for t in range(6)])
    return st, ev
st, ev = gate_run(IMG)
col = lambda x, t: [r[t] for r in x]
chk('smp44 GATE: Stufen der Firmware-Huellkurve ohne GATE %s, mit GATE %s ... (Halten bis zum Loslassen)' % (''.join(map(str, col(st, 0)[:8])),
    ''.join(map(str, col(st, 1)[:8]))), col(st, 0) == col(st, 2) == col(st, 4) and col(st, 1) == col(st, 3) == col(st, 5)
    and set(col(st, 0)[3:]) == {1} and set(col(st, 1)[3:40]) == {2} and set(col(st, 1)[42:]) == {1})
h = [b for b in range(90) if st[b][1] == 2]
chk('smp44 GATE: Monom haelt voll (Stufe 2) von Block %d bis %d, danach Decay; ohne GATE ab Block %d Decay; Pegel bei 39 mit / ohne GATE: %.3f / %.3f'
    % (h[0], h[-1], col(st, 0).index(1), ev[39][1] / 2 ** 31, ev[39][0] / 2 ** 31),
    h and h[-1] <= 41 and h[-1] >= 39 and all(ev[b][1] == 0x80000000 for b in h) and ev[60][1] < ev[41][1] and ev[39][0] < ev[39][1] // 4
    and col(ev, 0) == col(ev, 2))
for wv in (0, 2, 5, 7):
    _, _, cnt = vloop(6, par={t: {11: wv << 8, 13: 0x4000, 27: 0x2000} for t in range(6)}, count_ins=True)
    per = max(cnt[2:]) / 6
    chk('Kosten %s mit Sub und Noise: %d Befehle je Spur und Block (ohne Huellkurve / VCA)' % (MT.WAVES[wv], per), per < 4500)
done()
