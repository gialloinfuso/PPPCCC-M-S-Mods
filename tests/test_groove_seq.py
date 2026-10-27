# Grooves + Humanize (v2, Mod 'groove' + Core-Pattern-Speicher): echter Ereignisbau 0x400548ce (Modded-Cycles seqrig),
# Original gegen v2-Image; Tabellen-Grooves und Humanize gegen Python-Referenz; Groove aus dem Pattern-Kopf (Byte 55);
# Laden / neues Pattern (echte 0x4005b3b4 / 0x40061526) mit den Core-Haken (Bytes 40..63).
import json, struct, sys, pathlib
R = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R / 'uni/bindings/python')); sys.path.insert(0, str(R / 'Modded-Cycles/tools/emu')); sys.path.insert(0, str(R / 'solo'))
sys.path.insert(0, str(R / 'v2/tests'))
from unicorn import UC_HOOK_CODE
from unicorn import m68k_const as mk
import mcengine, seqrig
import rig
mcengine._emac_instrs = lambda img, ranges: {}
BASE = 0x40000400
stock = rig.STOCK
img = rig.v2_image(latch=False)
P_ = {'hsh': 7}
RND, HDR, HOFF = rig.V2SYM['groove']['RND'], 0x77B2, 40
GOFF = HDR + 55
ok = True
def chk(n, c):
    global ok; ok &= bool(c); print('ok  ' if c else 'FAIL', n)
def mkrig(im):
    e = mcengine.Engine(im, payload=(0x46700000, b"")); r = seqrig.Rig(e, keep=[(seqrig.BASE + seqrig.IMAGE_LEN, seqrig.BASE + len(im))])
    return e, r
P = seqrig.PAT
def ev(e, r, t, step, word, swing, patsw=-1, vel=100, micro=0, gm=0, hum=None, humv=None):
    e.call(0x40091d94, 0x42)
    r.uc.mem_write(P + GOFF, bytes([gm]))
    r.uc.mem_write(P + 722 * t + 718, struct.pack('b', swing)); r.uc.mem_write(P + 30666, struct.pack('b', patsw))
    r.uc.mem_write(P + 722 * t + 256 + step, struct.pack('b', micro))
    if hum is not None: r.uc.mem_write(P + HDR + HOFF, bytes(hum) + bytes(humv if humv is not None else [0] * 6))
    r.set_step(t, step, word=word, vel=vel); r.w32(seqrig.OFFP, 0)
    p = e.call(0x400548ce, t, P, seqrig.KIT, step, 0, seqrig.OFFP)
    return r.r32(seqrig.OFFP, True), r.r16(p + 0x16) >> 8
def s32(v): v &= 0xffffffff; return v - (1 << 32) if v & 0x80000000 else v
e0, r0 = mkrig(stock); e1, r1 = mkrig(img)
# ---- 1. Swing (Groove 0) ohne Humanize = Original
same = True
for t in (0, 3, 5):
    for step in range(0, 64, 5):
        for word in (0x81, 0x91):
            for sw in (0, 7, 30):
                for patsw in (-1, 25):
                    for micro in (0, -5):
                        same &= ev(e0, r0, t, step, word, sw, patsw, 90, micro) == ev(e1, r1, t, step, word, sw, patsw, 90, micro, 0, [0] * 6)
chk('Groove Swing, Humanize 0: identisch mit dem Original (Tracks, Steps, Swing, Pattern-Swing, Micro-Timing)', same)
# ---- 2. Tabellen-Grooves (1..3), Humanize 0
import gen_groove_113 as gg
import os; os.chdir(R)
for gm, f in enumerate(gg.GROOVES, 1):
    g = gg.table(f)[1]; good = True
    for st in range(64):
        for sw in (0, 15, 30):
            for v0 in (127, 100, 40, 1):
                for micro in (0, 4):
                    got = ev(e1, r1, 2, st, 0x91, sw, -1, v0, micro, gm, [0] * 6)
                    ou = (g['off'][st] * sw * 6 * 5) >> 6
                    k = (127 - g['vel'][st]) * sw; v = max(1, v0 - ((v0 * k * 165) >> 20))
                    good &= got == (ou * 1500 + micro * 225000, v)
    chk('%s (Groove %d, %d Steps): Zeit und Velocity wie Referenz (64 Steps, Swing 0/15/30)' % (g['name'], gm, g['steps']), good)
x = [ev(e1, r1, 0, st, 0x81, 30, -1, 100, 0, 8, [0] * 6) for st in range(4)]
chk('ungueltiger Groove 8: wie Swing 0 ohne Wirkung auf geraden Steps', all(b_ == 100 for a_, b_ in x))
# ---- 3. Humanize pro Track
def hum_ref(rnd, ht, hv, v0, base_t=0):
    st, sv = (ht * 77) >> P_['hsh'], (hv * 77) >> P_['hsh']
    if not st and not sv: return rnd, base_t, v0
    rnd = s32(rnd * 1664525 + 1013904223); S = 6 * 12 * st
    t = (((rnd >> 16) & 0x7fff) - 0x4000) * S >> 17; rr = (((rnd & 0xffffffff) >> 1) & 0x7fff) - 0x4000
    dv = (s32(rr * sv * v0 * 5) + 0x800000) >> 24
    return rnd, base_t + t * 1500, min(127, max(1, v0 + dv))
cl = lambda h: h if h <= 100 else 0
r1.w32(RND, 0x1234567); rnd = 0x1234567; good = True; spread = {}
for k in range(400):
    t = k % 6; st = (k * 7) % 64; ht = [0, 1, 4, 50, 100, 101, 0, 60][(k // 6) % 8]; hv = [0, 100, 30, 0, 100, 5, 77, 200][(k // 5) % 8]
    v0 = [100, 1, 127, 60][k % 4]
    a = [0] * 6; b_ = [0] * 6; a[t] = ht; b_[t] = hv
    got = ev(e1, r1, t, st, 0x81, 0, -1, v0, 0, 0, a, b_)
    rnd, et, evv = hum_ref(rnd, cl(ht), cl(hv), v0); good &= got == (et, evv)
    if (ht, hv) in ((100, 0), (0, 100)): spread.setdefault((ht, hv), []).append((got[0] / 5400000, got[1] - v0, v0))
chk('Humanize Zeit und Velocity getrennt (0/1/4/30/50/60/77/100, Muell 101/200) auf allen Tracks wie Referenz', good)
for key in spread:
    ts = [a_ for a_, _, _ in spread[key]]; dv = [d for _, d, v in spread[key] if v == 100]
    print('   Zeit %3d / Velocity %3d: Zeit %+.3f..%+.3f Step, Velocity (bei 100) %s' % (key[0], key[1], min(ts), max(ts), (min(dv), max(dv)) if dv else '-'))
chk('nur Zeit: Velocity unveraendert; nur Velocity: Zeit unveraendert',
    all(d == 0 for _, d, _ in spread.get((100, 0), [])) and all(t_ == 0 for t_, _, _ in spread.get((0, 100), [])))
got = ev(e1, r1, 1, 5, 0x81, 0, -1, 100, 0, 0, [0, 0, 80, 0, 0, 0], [0, 0, 80, 0, 0, 0])
chk('Humanize nur auf Track 3: Track 2 unveraendert', got == (0, 100))
# Groove + Humanize zusammen
g = gg.table('Boom Bap')[1]; r1.w32(RND, 0x7654321); rnd = 0x7654321; good = True
for st in range(32):
    got = ev(e1, r1, 4, st, 0x91, 30, -1, 100, 0, 1, [0, 0, 0, 0, 60, 0], [0, 0, 0, 0, 40, 0])
    ou = (g['off'][st] * 30 * 6 * 5) >> 6; k = (127 - g['vel'][st]) * 30; v1 = max(1, 100 - ((100 * k * 165) >> 20))
    rnd, et, evv = hum_ref(rnd, 60, 40, v1, ou * 1500); good &= got == (et, evv)
chk('Boom Bap (Swing 30) + Humanize Zeit 60 / Velocity 40 auf Track 5: Groove, dann Humanize', good)
# ---- 4. Laden / neues Pattern (echter Code)
u = e1.uc
A_, B_ = 0x4F300000, 0x4F301000
u.mem_write(A_, bytes(range(64))); u.mem_write(B_, b'\xEE' * 64)
d0 = e1.call(0x4005B3B4, B_, A_)
hb = bytes(u.mem_read(B_, 64)); u0 = e0.uc; u0.mem_write(A_, bytes(range(64))); u0.mem_write(B_, b'\xEE' * 64); e0.call(0x4005B3B4, B_, A_)
hs = bytes(u0.mem_read(B_, 64))
chk('Laden (Datei ohne Kennung): Bytes 40..51 aus der Datei, 52..59 = 0, Kennung, sonst wie Original, Rueckgabe 1',
    (d0 & 0xff) == 1 and hb[40:52] == bytes(range(40, 52)) and hb[52:60] == bytes(8) and hb[60:] == b'PCv2' and hb[:40] == hs[:40])
fa = bytearray(range(64)); fa[60:] = b'PCv2'; u.mem_write(A_, bytes(fa)); u.mem_write(B_, b'\xEE' * 64); e1.call(0x4005B3B4, B_, A_)
chk('Laden (Datei mit Kennung): Bytes 40..63 aus der Datei', bytes(u.mem_read(B_, 64))[40:] == bytes(fa[40:]))
u.mem_write(B_, b'\x33' * 64); u0.mem_write(B_, b'\x33' * 64); e1.call(0x40061526, B_, 0); e0.call(0x40061526, B_, 0)
hb = bytes(u.mem_read(B_, 64)); hs = bytes(u0.mem_read(B_, 64))
chk('Neues Pattern: Bytes 40..59 = 0, Kennung, sonst wie Original', hb[40:60] == bytes(20) and hb[60:] == b'PCv2' and hb[:40] == hs[:40])
print('GESAMT', 'ok' if ok else 'FEHLER')
sys.exit(0 if ok else 1)
