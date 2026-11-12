# Hall / Room / Plate (smp9, Reverb-Platz Modi 5..7, v2/g2_reverbs.py + v2/rv_algos.py):
# 1. Start: echte BSS-Loeschung 0x400004b2 mit Haken -> Nutzlast liegt bitgleich bei 0x43000000, BSS leer, Ruecksprung.
# 2. Klang: Block fuer Block gegen das Gleitkomma-Modell (rv_algos.render), alle drei, verschiedene Size / Tone.
# 3. Loeschen bei Moduswechsel (still, Stuecke zu 4 KB), Rueckkehr ueber andere Modi beginnt leer (SMODE = -1 aus R).
# 4. Weiche R: Pattern-Byte 52 = 5 / 6 / 7 -> RVB; Namen der Parameter; Register / Stack; Vollaussteuerung; Kosten.
import math, random, struct, sys
from rig import *
import cfemac
import g2_reverbfx as GR
import g2_reverbs as RV
import rv_algos as RA
sys.path.insert(0, str(ROOT / 'Modded-Cycles' / 'tools' / 'emu'))
import emac as MEMAC
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN

IMG = v2_image()
parts, LAB, BLOB, SIZES = GR.build(STOCK)               # auch fuer das EMAC-Protokoll der Nutzlast
OPS = cfemac.ops()
SYM = V2SYM['reverb-fx']
chk('Nutzlast im Image: Platz reverb-fx der Nutzlast des Cores hinter dem MAIN OS (%d von %d B), gleich der erzeugten' % (len(BLOB), C.PAYSZ),
    IMG[C.IMG_END - BASE:C.IMG_END - BASE + len(BLOB)] == BLOB and len(STOCK) == C.IMG_END - BASE and len(IMG) == len(STOCK) + C.PAYSZ
    and C.PAY_SLOT['reverb-fx'] == (0, 0x7000) and RV.PAY == C.PAY)

# ---------------- 1 Start
u = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN); u.ctl_set_cpu_model(mk.UC_CPU_M68K_CFV4E)
u.mem_map(0x40000000, 0x2400000); u.mem_map(0x43000000, 0x200000); u.mem_map(RET, 0x1000); u.mem_map(STACK - 0x10000, 0x20000)
u.mem_write(BASE, IMG); u.mem_write(0x43000000, b'\x5a' * 0x8000)
u.mem_write(0x423380A0, b'\x77' * 0x20)
sp = STACK - 0x100; u.mem_write(sp, struct.pack('>I', RET)); u.reg_write(mk.UC_M68K_REG_A7, sp)
for i, r in enumerate(KEEP): u.reg_write(r, 0xC0DE0000 + i)
u.emu_start(0x400004B2, RET, count=40000000)
got = bytes(u.mem_read(RV.PAY, len(BLOB)))
bss = bytes(u.mem_read(0x4019B590, 0x10000)) + bytes(u.mem_read(0x423380A0, 0x10))
chk('Start: Nutzlast bei %#x bitgleich, BSS ab 0x4019b590 leer (auch die Nutzlast im Image), hinter dem BSS unberuehrt, '
    'Ruecksprung mit Stack und Registern' % RV.PAY,
    got == BLOB and not any(bss) and bytes(u.mem_read(0x423380B0, 0x10)) == b'\x77' * 0x10
    and u.reg_read(mk.UC_M68K_REG_A7) == sp + 4 and all(u.reg_read(r) == 0xC0DE0000 + i for i, r in enumerate(KEEP)))
del u

# ---------------- Pruefstand
IN, OUT, PAR = 0x8000B990, 0x8000BB90, 0x4F020000
RMODE = GR.RMODE


def mkemu():
    e = Emu(IMG)
    assert bytes(e.u.mem_read(RV.PAY, len(BLOB))) == BLOB     # rig.Emu legt die Nutzlast ab
    e.u.mem_write(RV.ST, b'\xa5' * 0x400)               # RAM nach dem Einschalten: Muell
    m = MEMAC.EMAC(e.u); m.install(OPS); e.mac = m
    return e


def block(e, entry, frames, size, tone):
    e.u.mem_write(IN, b''.join(struct.pack('>ii', l, r) for l, r in frames)); e.u.mem_write(PAR, struct.pack('>HH', size << 8, tone << 8))
    sp = STACK - 0x40; e.u.mem_write(sp, struct.pack('>IIII', RET, OUT, IN, PAR)); e.u.reg_write(mk.UC_M68K_REG_A7, sp)
    for i, r in enumerate(KEEP): e.u.reg_write(r, 0xC0DE0000 + i)
    e.mac.macsr = 0
    n = [0]
    h = e.u.hook_add(UC_HOOK_CODE, lambda u_, a, z, _: n.__setitem__(0, n[0] + 1), begin=0x43000000, end=0x430FFFFF)
    e.u.emu_start(entry, RET, count=3000000); e.u.hook_del(h)
    good = all(e.u.reg_read(r) == 0xC0DE0000 + i for i, r in enumerate(KEEP)) and e.u.reg_read(mk.UC_M68K_REG_A7) == sp + 4
    raw = bytes(e.u.mem_read(OUT, 256))
    return [struct.unpack('>ii', raw[i:i + 8]) for i in range(0, 256, 8)], good, n[0]


def nclear(mode): return -(-SIZES[mode] // RV.CHUNK)


random.seed(5)
FS = 48000
def burst(n):
    x = []
    for i in range(n):
        v = 0.0
        if i < 3000: v += random.uniform(-0.5, 0.5) * math.exp(-i / 700)
        if 9000 <= i < 30000: v += 0.3 * math.sin(2 * math.pi * 330 * i / FS) * math.exp(-(i - 9000) / 6000)
        x.append(v)
    return x


# ---------------- 2 Klang gegen das Modell (+ 3 Loeschen am Anfang)
costs = {}
for mode, algo in RV.MODES.items():
    for size, tone, nbl in ((70, 90, 300), (127, 127, 120), (0, 0, 80)):
        e = mkemu(); e.w8(RMODE, mode)
        nc = nclear(mode); sil = True; regs = True
        for b in range(nc):
            o, g, _ = block(e, LAB['RVB'], [(0x1234567, -0x1234567)] * 32, size, tone)
            sil &= all(v == (0, 0) for v in o); regs &= g
        x = burst(32 * nbl)
        q = [int(round(v * 2 ** 31)) for v in x]
        L, R = [], []; cs = []
        for b in range(nbl):
            o, g, n = block(e, LAB['RVB'], [(q[32 * b + i], q[32 * b + i]) for i in range(32)], size, tone)
            L += [a_ for a_, b_ in o]; R += [b_ for a_, b_ in o]; regs &= g; cs.append(n)
        ml, mr = RA.render(algo, [v / 2 ** 31 * 2 ** 31 / 2 ** 31 for v in q], size, tone)
        err = max(max(abs(a_ / 2 ** 31 - b_) for a_, b_ in zip(L, ml)), max(abs(a_ / 2 ** 31 - b_) for a_, b_ in zip(R, mr)))
        pk = max(max(abs(v) for v in ml), max(abs(v) for v in mr))
        costs[(mode, size)] = max(cs)
        chk('%s Size %d Tone %d: %d Bloecke Loeschen still, dann %d Bloecke wie das Modell (max. Fehler %.1e bei Spitze %.3f), '
            'Register / Stack ok' % (RA.ALGOS[algo]()['name'], size, tone, nc, nbl, err, pk), sil and regs and err < 2e-4 * max(1, pk / 0.5))
# ---------------- 3 Moduswechsel / Rueckkehr
e = mkemu(); e.w8(RMODE, 5)
for b in range(nclear(5)): block(e, LAB['RVB'], [(0, 0)] * 32, 64, 64)
for b in range(120): o, g, _ = block(e, LAB['RVB'], [((1 << 29) * (1 if (b * 32 + i) % 50 < 25 else -1),) * 2 for i in range(32)], 64, 64)
chk('Hall laeuft (Ausgang nicht still)', any(v != (0, 0) for v in o))
e.w8(RMODE, 7)
o, g, _ = block(e, LAB['RVB'], [(1 << 29, 1 << 29)] * 32, 64, 64)
chk('Wechsel Hall -> Plate: SMODE = 7, Loeschen beginnt (still, %#x B geloescht)' % e.r32(RV.ST + 4),
    e.r32(RV.ST) == 7 and e.r32(RV.ST + 4) == RV.CHUNK and all(v == (0, 0) for v in o) and g)
# R: Modus 0 setzt SMODE = -1
def rblock(e, mode, frames):
    e.w8(e.hdr(C.P_RFX), mode); return block(e, SYM['R'], frames, 64, 64)
e = mkemu(); e.w8(e.hdr(C.P_RFX), 6)
calls = []
e.u.hook_add(UC_HOOK_CODE, lambda u_, a, z, _: calls.append('RVB'), begin=LAB['RVB'], end=LAB['RVB'])
def rev(u_, a, z, _):
    sp_ = u_.reg_read(mk.UC_M68K_REG_A7); calls.append('REV')
    u_.reg_write(mk.UC_M68K_REG_PC, struct.unpack('>I', bytes(u_.mem_read(sp_, 4)))[0]); u_.reg_write(mk.UC_M68K_REG_A7, sp_ + 4)
e.u.hook_add(UC_HOOK_CODE, rev, begin=GR.REVERB, end=GR.REVERB)
e.w32(0x40A71754 + 3900 + 0x20, 0x40045A68); e.w32(0x40A71754 + 4000 + 0x20, 0x4004E00E)
seq = []
for mode in (6, 6, 0, 6, 5, 7, 8, 200):
    calls.clear(); o, g, _ = rblock(e, mode, [(0, 0)] * 32)
    seq.append((mode, tuple(calls), e.r32(RV.ST) & 0xffffffff, g))
chk('Weiche R: 6 -> RVB, 0 -> Reverb der Firmware und SMODE -1, wieder 6 -> leer beginnen, 5 / 7 -> RVB, Muell -> Firmware: %s'
    % [(m, c, hex(s_)) for m, c, s_, g in seq],
    [c for m, c, s_, g in seq] == [('RVB',), ('RVB',), ('REV',), ('RVB',), ('RVB',), ('RVB',), ('REV',), ('REV',)]
    and seq[2][2] == 0xffffffff and seq[3][2] == 6 and seq[4][2] == 5 and seq[5][2] == 7 and seq[6][2] == 0xffffffff
    and all(g for *_, g in seq))
DESC = C.DTD                                   # smp18: Kopie der Tabelle in der Nutzlast des Cores (zur Laufzeit gelesen)
nm = []
for mode in (5, 6, 7, 4, 0):
    rblock(e, mode, [(0, 0)] * 32)
    nm.append(tuple(e.cstr(e.r32(DESC(k) + 0x2C)) for k in (27, 39, 40)))
chk('Namen: %s' % nm, nm[:3] == [('Hall Send', 'Hall Decay', 'Hall Tone'), ('Room Send', 'Room Decay', 'Room Tone'),
                                  ('Plate Send', 'Plate Decay', 'Plate Tone')] and nm[3][0] == 'Razr Mix')
# ---------------- 4 Vollaussteuerung: Rechteck / Rauschen voll, dann Stille: kein Ueberlauf, klingt ab (Size 64 und 127)
for mode, algo in RV.MODES.items():
    for size, nsil, need in ((64, 1500, 6.0), (127, 1500, 0.5)):
        e = mkemu(); e.w8(RMODE, mode)
        for b in range(nclear(mode)): block(e, LAB['RVB'], [(0, 0)] * 32, size, 100)
        ys = []; ok = True
        for b in range(300 + nsil):
            fr = [((2 ** 31 - 1) if (i // 8) % 2 else -2 ** 31,) * 2 for i in range(32)] if b < 200 else \
                 [(random.randint(-2 ** 31, 2 ** 31 - 1), random.randint(-2 ** 31, 2 ** 31 - 1)) for _ in range(32)] if b < 300 else [(0, 0)] * 32
            o, g, _ = block(e, LAB['RVB'], fr, size, 100); ok &= g; ys += [a_ for a_, b_ in o]
        flips = sum(1 for a_, b_ in zip(ys, ys[1:]) if abs(a_ - b_) > 1.5 * 2 ** 31)
        rms = lambda v: math.sqrt(sum(x * x for x in v) / len(v)) / 2 ** 31
        r0, r1 = rms(ys[32 * 300:32 * 400]), rms(ys[-32 * 100:])
        drop = 20 * math.log10(r0 / max(r1, 1e-12))
        chk('%s voll, Size %d: kein Ueberlauf (Spruenge %d), Spitze %.2f, nach %.1f s Stille %.1f dB leiser, Register ok'
            % (algo, size, flips, max(abs(v) for v in ys) / 2 ** 31, nsil * 32 / 48000, drop), flips == 0 and ok and drop > need)
# ---------------- 5 smp10: Daempfung je Leitung (Kuhschwanz) - Koeffizienten im Code gleich dem Modell; Nachhall je Band
bad = []
for mode, algo in RV.MODES.items():
    A = RA.ALGOS[algo]()
    e = mkemu(); e.w8(RMODE, mode)
    for b in range(nclear(mode)): block(e, LAB['RVB'], [(0, 0)] * 32, 64, 64)
    for size, tone in ((0, 0), (64, 64), (127, 0), (127, 127), (30, 100)):
        block(e, LAB['RVB'], [(0, 0)] * 32, size, tone)
        for k in RA.lp_lengths(A):
            if e.r32(RV.ST + RV.V['LPA'] + 4 * k) != RA.shelf_g_int(algo, A, k, size, tone): bad.append((algo, size, tone, k))
        if e.r32(RV.ST + RV.V['TONEA']) != RV.u32(RV.q31(RA.tone_lp(algo, tone))): bad.append((algo, size, tone, 'lp'))
chk('Kuhschwaenze: g je Leitung und Tiefpass wie das Modell (3 Reverbs x 5 Stellungen) %s' % bad[:3], not bad)
import numpy as np
from scipy.signal import butter, sosfilt
def band_rt(algo, size, tone, fc, dur):
    x = [0.0] * int(48000 * dur); x[0] = 1.0
    l, r = RA.render(algo, x, size, tone); l = np.array(l)
    y = sosfilt(butter(3, [fc / 1.41, fc * 1.41], 'bandpass', fs=48000, output='sos'), l)
    en = np.cumsum((y ** 2)[::-1])[::-1]; db = 10 * np.log10(en / en[0] + 1e-30)
    return (np.argmax(db < -25) - np.argmax(db < -5)) / 48000 * 3
res = {}
for algo, size in (('hall', 64), ('room', 100), ('plate', 64)):
    T = RA.rt60(algo, size)
    res[algo] = (round(T, 2), round(band_rt(algo, size, 0, 250, T + 0.6), 2), round(band_rt(algo, size, 127, 250, T + 0.6), 2),
                 round(band_rt(algo, size, 0, 4000, T + 0.6), 2), round(band_rt(algo, size, 127, 4000, T + 0.6), 2))
chk('Nachhall (Modell): Size-Zeit / 250 Hz Tone 0 / 127 / 4 kHz Tone 0 / 127: %s' % res,
    all(abs(v[1] / v[0] - 1) < 0.2 and abs(v[2] / v[0] - 1) < 0.2 and v[4] > (1.6 if k == 'plate' else 2.5) * v[3]
        for k, v in res.items()))   # Plate: die Allpaesse im Tank klingen ungedaempft ~1 s nach (Dattorro)
for (mode, size), n in sorted(costs.items()):
    chk('Kosten %s Size %d: %d Befehle pro Block (32 Frames)' % (RV.MODES[mode], size, n), n < 10000)
done()
