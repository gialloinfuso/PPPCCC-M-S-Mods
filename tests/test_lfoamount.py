# lfo-amount (v2, Patch 14): Parameter LFO Amount (k 32, Deskriptor 5) hinter der Depth.
# 1. Echter Haken 0x400597c6 (AMT) mit gestubbtem LFO 0x40091ab2: der LFO sieht Depth' = Mitte + (Depth - Mitte) * Amount/127,
#    danach ist Depth wieder wie vorher; Amount 127 = bitgenau; Amount vom LFO moduliert wirkt im naechsten Block;
#    Argumente, Register, Stack.
# 2. Knopf-Suche 0x4001e814 (Rumpf gestubbt): nur Knopf 10 (LFO SPEED) + RETRIG -> 5, UI-Objekt 5 bekommt den Formatierer.
# 3. Sound speichern / laden (echte Funktionen, Core-Slots): Amount, LFO- und Velocity-Ziel k 32; alter Sound -> 127.
# 4. p-locks (Core): k 32 -> Index 33 -> k 32. Deskriptor 5.
# Aufruf: test_lfoamount.py [--alone]   (--alone: nur Core + lfo-amount)
import random, struct, sys
from rig import *
import g2_lfoamount as G

ALONE = '--alone' in sys.argv
IMG = v2_image(['core', 'lfo-amount'], latch=False) if ALONE else v2_image()
S = V2SYM['lfo-amount']
OBJ, TEMPO, MASK = 0x4F040000, 0x12345, 0x3F
DEP = lambda t: OBJ + 14 + 66 * t + 2 * G.K_DEP
AMT = lambda t: OBJ + 14 + 66 * t + 2 * G.K_AMT
chk('Haken 0x400597c6 = jsr AMT', IMG[G.LFO_HOOK - BASE:][:6] == C.jsr(S['AMT']))
chk('Haken 0x4001e814 = jmp W', IMG[G.LOOKUP - BASE:][:6] == C.jmp(S['W']))

e = Emu(IMG); seen = []; lfo_add = {}
def lfo(u, a, z, _):
    sp = u.reg_read(mk.UC_M68K_REG_A7)
    seen.append(((e.r32(sp + 4), e.r32(sp + 8), e.r32(sp + 12)),
                 [struct.unpack('>h', bytes(e.u.mem_read(DEP(t), 2)))[0] for t in range(6)]))
    for t, v in lfo_add.items():                         # wie der LFO: Modulation auf das Zielwort (hier Amount)
        e.u.mem_write(AMT(t), struct.pack('>h', v))
    u.reg_write(mk.UC_M68K_REG_PC, e.r32(sp)); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
e.u.hook_add(UC_HOOK_CODE, lfo, begin=G.LFO_FN, end=G.LFO_FN)


def blk(deps, amts):
    for t in range(6):
        e.u.mem_write(DEP(t), struct.pack('>h', deps[t])); e.u.mem_write(AMT(t), struct.pack('>h', amts[t]))
    seen.clear()
    _, good = e.call(S['AMT'], OBJ, TEMPO, MASK)
    back = [struct.unpack('>h', bytes(e.u.mem_read(DEP(t), 2)))[0] for t in range(6)]
    return good and len(seen) == 1 and seen[0][0] == (OBJ, TEMPO, MASK) and back == list(deps), seen[0][1] if seen else None


def want(d, a): return d if a >= 0x7F00 else 0x4000 + int((d - 0x4000) * a / 0x7F00)


deps = [0x7F00, 0x0000, 0x4000, 0x6000, 0x2100, 0x7F00]
ok1, got = blk(deps, [0x7F00] * 6)
chk('Amount 127 (auch erster Block, Speicher leer): LFO sieht Depth unveraendert, Args/Register ok', ok1 and got == deps)
amts = [0x7F00, 0x3F80, 0x0000, 0x7E00, 0x1000, 0x6000]
blk(deps, amts)                                          # Amount wird nach dem LFO gemerkt ...
ok1, got = blk(deps, amts)                               # ... und wirkt ab dem naechsten Block
w_ = [want(d, a) for d, a in zip(deps, amts)]
chk('Amount 127 / 63.5 / 0 / 126 / 16 / 96: Depth beim LFO %s (erwartet %s), danach zurueck' % (got, w_), ok1 and got == w_)
lfo_add = {3: 0x0000}                                    # LFO moduliert Amount von Track 3 auf 0
blk(deps, amts); lfo_add = {}
ok1, got = blk(deps, amts)
chk('LFO auf Amount: Wirkung im naechsten Block (Track 3 Depth Mitte, dann wieder normal)', got[3] == 0x4000)
ok1, got = blk(deps, amts)
chk('  ein Block spaeter wieder Amount 126', got[3] == want(deps[3], amts[3]))
bad = []
rnd = random.Random(5)
for n in range(200):
    d = [rnd.randrange(0, 0x7F01) for _ in range(6)]; a_ = [rnd.randrange(0, 0x7F01) for _ in range(6)]
    blk(d, a_); okk, got = blk(d, a_)
    if not okk or got != [want(x, y) for x, y in zip(d, a_)]: bad.append((d, a_, got))
chk('200 Zufallswerte: Depth\' = Mitte + (Depth - Mitte) * Amount / 0x7f00 (auf 0 gerundet) %s' % bad[:1], not bad)

# ---------------- 2 Knopf-Suche
VIEW = 0x4F042000
def emu_lk(img):
    e2 = Emu(img)
    def body(u, a, z, _):
        sp = u.reg_read(mk.UC_M68K_REG_A7)
        u.reg_write(mk.UC_M68K_REG_D0, 50 + e2.r32(sp + 0x3C)); u.reg_write(mk.UC_M68K_REG_PC, 0x4001E934)
    e2.u.hook_add(UC_HOOK_CODE, body, begin=0x4001E81E, end=0x4001E81E)
    return e2
bad = []
e2 = emu_lk(IMG)
for held in ((), (G.KEY_RETRIG,), (C.KEY_FUNC,), (G.KEY_RETRIG, C.KEY_FUNC), (8,)):
    e2.held = set(held)
    for k in range(16):
        for f in (0, 1):
            d0, good = e2.call(G.LOOKUP, VIEW, k, f, -1)
            wnt = 5 if (k == 10 and G.KEY_RETRIG in held) else 50 + k
            if d0 != wnt or not good: bad.append((held, k, f, d0, good))
chk('Knopf-Suche: nur LFO SPEED (10) + RETRIG -> Deskriptor 5, sonst Firmware %s' % bad[:2], not bad)
chk('UI-Objekt 5: Formatierer INT, keine Sonderzeichnung', e2.r32(G.REC + 500 + 0x20) == G.FMT_INT and e2.r32(G.REC + 500 + 0x2C) == 0)
if not ALONE:
    import g2_trackfilter as TF
    T = V2SYM['track-filter']; res = []
    for mode in (0, TF.MAGIC):
        e2.w32(TF.MODE, mode)
        for held in ((), (G.KEY_RETRIG,)):
            e2.held = set(held); res.append([e2.call(T['KNOB'], VIEW, k, 0, -1)[0] for k in (2, 3, 10, 11)])
    chk('mit track-filter (Filter-Modus aus / an): %s' % res, res == [[52, 53, 60, 61], [52, 53, 5, 61], [1, 4, 60, 61], [1, 4, 5, 61]])

# ---------------- 3 Sound speichern / laden
e3 = Emu(IMG)
SND, REC1, SND2 = 0x4F044000, 0x4F045000, 0x4F046000
snd = bytearray(rnd.getrandbits(8) for _ in range(256))
for k in range(33): snd[20 + 2 * k:22 + 2 * k] = struct.pack('>H', rnd.randrange(0, 0x7F01))
snd[0x58:0x5C] = struct.pack('>I', 32); snd[28] = 32    # Velocity- und LFO-Ziel = Amount
res = []
for amt in (0x0000, 0x2A00, 0x7F00, 0x7E00):
    snd[20 + 64:22 + 64] = struct.pack('>H', amt)
    for fn in (G.core.SV2_HOOK, G.core.SV1_HOOK):
        e3.u.mem_write(SND, bytes(snd)); e3.u.mem_write(REC1, bytes(256))
        _, o1 = e3.call(fn, REC1, SND, count=200000)
        e3.u.mem_write(SND2, bytes(256)); _, o2 = e3.call(G.core.LD_HOOK, SND2, REC1, count=200000)
        b = bytes(e3.u.mem_read(SND2, 128))
        res.append(o1 and o2 and struct.unpack('>H', b[84:86])[0] == amt and b[28] == 32 and struct.unpack('>I', b[88:92])[0] == 32)
chk('Speichern (v2, v1) + Laden: Amount 0 / 42 / 127 / 126, LFO-Ziel und Velocity-Ziel = Amount zurueck', all(res))
es = Emu(STOCK)
es.u.mem_write(SND, bytes(snd)); es.u.mem_write(REC1, bytes(256)); es.call(G.core.SV2_HOOK, REC1, SND, count=200000)
e3.u.mem_write(REC1, bytes(es.u.mem_read(REC1, 100))); e3.u.mem_write(SND2, bytes(256)); e3.call(G.core.LD_HOOK, SND2, REC1, count=200000)
chk('alter Sound (Stock gespeichert): Amount 127', struct.unpack('>H', bytes(e3.u.mem_read(SND2 + 84, 2)))[0] == 0x7F00)

# ---------------- 4 p-locks, Deskriptor
FN = 0x4005AA1A
pt = struct.unpack('>33I', bytes(e3.u.mem_read(V2SYM['core']['PTAB'], 132)))
chk('p-lock: k 32 -> Index %d -> k %d' % (pt[32], e3.call(FN, 1, pt[32])[0]), pt[32] == 33 and e3.call(FN, 1, 33)[0] == 32)
r = struct.unpack('>14I', IMG[C.DESC(5) - BASE:][:0x38])
chk('Deskriptor 5: Gruppe 7, k 32, 0..0x7f00, Default 127, LFO/Velocity-Ziel, "%s" / "%s" / "%s"' %
    (e3.cstr(r[11]), e3.cstr(r[12]), e3.cstr(r[13])),
    r[:5] == (7, 32, 0, 0x7F00, 0x7F00) and r[9] == 0x600 and e3.cstr(r[11]) == 'LFO Amount' and e3.cstr(r[12]) == 'LFO')
# ---------------- 5 neuer Sound (Firmware-Init 0x40061866 nach dem Aufbau der Parameter-Tabellen 0x4005a274): Defaults
e5 = Emu(IMG); e5.call(0x4005A274, count=5000000); okn = True
for mach in range(6):
    e5.u.mem_write(SND, bytes(256)); e5.call(0x40061866, SND, 0, mach, count=2000000)
    okn &= struct.unpack('>H', bytes(e5.u.mem_read(SND + 20 + 2 * G.K_AMT, 2)))[0] == 0x7F00
chk('neuer Sound (alle 6 Maschinen): Amount 127', okn)
done()
