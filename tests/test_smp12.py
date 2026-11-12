# smp12 (Pip 03.11.2026), Core: T1..T6 waehlen die Spur nur mit TRACK (TSEL), FUNC + DECAY = Amp Attack (Knopf-Suche LKW /
# LKP, Deskriptor 6, k 23, Sound-Slot, Rampe hinter dem VCA ATKV / ATKP, Objekt der Klangerzeugung RPH);
# Sampler: FUNC + SAMPLE START verschiebt Start und Ende gemeinsam (BSH, Encoder-Slot 'sampler').
import struct
from rig import *
import g2_core as CO
import g2_sampler as G

IMG = v2_image()
CS, SS = V2SYM['core'], V2SYM['sampler']

# ---------------- Haken
chk('Haken: 0x4001d36a jsr TSEL, 0x4005981e jsr RPH, 0x4001e814 jmp LKW, 0x400a9430 jmp ATKV',
    IMG[CO.TSEL_AT - BASE:][:6] == C.jsr(CS['TSEL']) and IMG[CO.RP_AT - BASE:][:6] == C.jsr(CS['RPH'])
    and IMG[CO.LOOKUP - BASE:][:6] == C.jmp(CS['LKW']) and IMG[CO.VCA_FN - BASE:][:6] == C.jmp(CS['ATKV']))

# ---------------- 1 TSEL
e = Emu(IMG); UI = 0x4F046000; sel = []
e.u.mem_write(UI, bytes(0x200))
def stub(addr, fn):
    def h(u, a, z, _):
        sp = u.reg_read(mk.UC_M68K_REG_A7); r = fn(e.r32(sp + 4))
        if r is not None: u.reg_write(mk.UC_M68K_REG_D0, r)
        u.reg_write(mk.UC_M68K_REG_PC, e.r32(sp)); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
    e.u.hook_add(UC_HOOK_CODE, h, begin=addr, end=addr)
stub(CO.UIGET, lambda x: UI)
stub(CO.TSEL_FN, lambda t: sel.append(t))
res = []
for held, pm in (((), 0), ((2,), 0), ((), 1), ((1,), 0), ((2, 1), 0)):
    e.held = set(held); e.w8(UI + CO.UI_PMODE, pm); sel.clear()
    _, good = e.call(CS['TSEL'], 3)
    res.append((held, pm, list(sel), good))
chk('TSEL: T allein -> keine Auswahl; TRACK + T -> Auswahl; Pattern-Auswahlmodus -> Auswahl (wie Firmware) %s' % res,
    [r[2] for r in res] == [[], [3], [3], [], [3]] and all(r[3] for r in res))

# ---------------- 2 Knopf-Suche: FUNC + DECAY = Attack, sonst unveraendert; lfo-amount (RETRIG + LFO SPEED) weiter
def knobs(img):
    e = Emu(img)
    e.u.mem_map(0x42300000, 0x30000); e.u.mem_map(0x43800000, 0x800000); e.u.mem_map(0x422F0000, 0x10000)
    e.w32(0x422FEF30, 0x4F04F800)
    e.call(0x4000045C, count=2000000); e.call(0x400DE244, count=20000000); e.call(0x4005A274, count=5000000)
    for t, v in ((0x4001E318, None), (0x4006B736, 0), (0x400CF9A8, 0x4F046000)):
        e.u.hook_add(UC_HOOK_CODE, lambda u, a, z, _, v=v: (u.reg_write(mk.UC_M68K_REG_D0, e.mach if v is None else v),
                     u.reg_write(mk.UC_M68K_REG_PC, e.r32(u.reg_read(mk.UC_M68K_REG_A7))),
                     u.reg_write(mk.UC_M68K_REG_A7, u.reg_read(mk.UC_M68K_REG_A7) + 4)), begin=t, end=t)
    VW, VEC = 0x4F047000, 0x4F047800
    e.u.mem_write(VEC, struct.pack('>6I', *range(1, 7))); e.w32(VW + 0x68, VEC)
    out = {}
    for m in range(7):
        e.mach = m
        for held in ((), (4,)):
            e.held = set(held)
            for kn in range(2, 16):
                for f in (0, 1):
                    d0, good = e.call(0x4001E814, VW, kn, f, -1, count=200000); out[(m, held, kn, f)] = d0 if good else 'X'
    return e, out
e0, k0 = knobs(v2_image([i for i in V2_IDS if i not in ('sampler', 'strings', 'mono')]))   # Referenz-Lage: ohne Sampler gibt es Maschine 6 nicht
e1, k1 = knobs(IMG)
diff = [(k, k0[k], k1[k]) for k in k1 if k[0] < 6 and not (k[2] == 3 and k[3] == 1) and k0[k] != k1[k]]
atk = [k1[(m, (), 3, 1)] for m in range(7)]
lfo = [k1[(m, (4,), 10, 0)] for m in range(7)]
chk('FUNC + DECAY -> Deskriptor 6 (Attack) auf allen 7 Maschinen %s; alles andere wie vorher %s; RETRIG + LFO SPEED -> 5 %s'
    % (atk, diff[:3], lfo), atk == [CO.D_ATK] * 7 and not diff and lfo == [5] * 7)
row = struct.unpack('>14I', bytes(e1.u.mem_read(C.DESC(CO.D_ATK), 56)))
chk('Deskriptor 6: Maschine 7, k 23, 0..127, Standard 0, Name %r / %r, Gruppe Amp, UI-Objekt Formatierer Zahl'
    % (e1.cstr(row[11]), e1.cstr(row[13])), row[:5] == (7, 23, 0, 0x7F00, 0) and e1.cstr(row[11]) == 'Attack'
    and e1.cstr(row[13]) == 'ATK' and e1.cstr(row[12]) == 'Amp' and e1.r32(CO.REC + 100 * CO.D_ATK + 0x20) == CO.FMT_INT)

# ---------------- 3 Sound-Slot: Satz +86 <-> Sound k 23
e = Emu(IMG); RECB, SND = 0x4F040000, 0x4F040100
h = e.r32(CS['SSLOTS'] + 4 * C.SSLOT['core-attack'])
e.u.mem_write(RECB, bytes(100)); e.u.mem_write(SND, bytes(100))
e.u.mem_write(SND + 20 + 2 * 23, struct.pack('>H', 0x5A00))
e.call(h, regs={mk.UC_M68K_REG_A0: RECB, mk.UC_M68K_REG_A1: SND, mk.UC_M68K_REG_D1: 1})
sv = e.r8(RECB + 86)
e.u.mem_write(SND + 20 + 2 * 23, struct.pack('>H', 0)); e.call(h, regs={mk.UC_M68K_REG_A0: RECB, mk.UC_M68K_REG_A1: SND, mk.UC_M68K_REG_D1: 0})
ld = struct.unpack('>H', bytes(e.u.mem_read(SND + 66, 2)))[0]
e.u.mem_write(RECB + 86, b'\0'); e.call(h, regs={mk.UC_M68K_REG_A0: RECB, mk.UC_M68K_REG_A1: SND, mk.UC_M68K_REG_D1: 0})
ld0 = struct.unpack('>H', bytes(e.u.mem_read(SND + 66, 2)))[0]
chk('Sound-Slot Attack: speichern 0x5a00 -> Satz +86 = %#x, laden -> %#x; alter Satz (0) -> Attack 0' % (sv, ld),
    h == CS['ATH'] and sv == 0x5A and ld == 0x5A00 and ld0 == 0)

# ---------------- 4 Rampe hinter dem VCA (Firmware-VCA einmal im Original-, einmal im v2-Image)
OBJ, BUF = 0x4F041000, 0x4F042000
def vca(img, track, atk, trig, x, blocks=1, obj=True, own=False):
    e = Emu(img); e.u.mem_map(0x42300000, 0x30000)
    if own: e.w8(CS['OWN'] + track, 1)                 # smp24: CHORD / Vlvt mit eigener Huellkurve je Ton
    v = 0x42308828 + 0x31C * track
    e.u.mem_write(v, bytes(0x31C))
    e.w32(v + 0x230, 0x40000000); e.w32(v + 0x234, 0x40000000); e.w32(v + 0x38, 1 if trig else 0)
    e.u.mem_write(OBJ, bytes(14 + 66 * 6)); e.u.mem_write(OBJ + 14 + 66 * track + 46, struct.pack('>H', atk << 8))
    if obj and img is IMG: e.w32(CS['PARP'], OBJ)
    def body(u, a, z, _):                            # Rumpf des VCA (EMAC der Firmware) nachgebildet: Puffer * 0.75
        sp = u.reg_read(mk.UC_M68K_REG_A7); buf = e.r32(sp + 20)
        vals = struct.unpack('>32i', bytes(u.mem_read(buf, 128)))
        u.mem_write(buf, struct.pack('>32i', *[(v_ * 3) >> 2 for v_ in vals]))
        u.reg_write(mk.UC_M68K_REG_PC, e.r32(sp + 16)); u.reg_write(mk.UC_M68K_REG_A7, sp + 20)
    e.u.hook_add(UC_HOOK_CODE, body, begin=CO.VCA_CONT, end=CO.VCA_CONT)
    out = []; ok = True
    for b in range(blocks):
        e.u.mem_write(BUF, struct.pack('>32i', *x))
        _, good = e.call(0x400A9430, BUF, v, count=200000); ok &= good
        out.append(list(struct.unpack('>32i', bytes(e.u.mem_read(BUF, 128)))))
        e.w32(v + 0x38, 0)
    return out, ok
import sys
sys.path.insert(0, str(ROOT / 'Modded-Cycles' / 'tools' / 'emu'))
X = [int(0.6 * 2 ** 31 * (1 if i % 7 < 4 else -1)) for i in range(32)]
ref, ok0 = vca(STOCK, 2, 0, True, X, 3)
a0, ok1 = vca(IMG, 2, 0, True, X, 3)
chk('Attack 0: Ausgang des VCA unveraendert (3 Bloecke), Register / Stack ok', a0 == ref and ok0 and ok1)
for atk in (1, 20, 64, 127):
    got, ok2 = vca(IMG, 4, atk, True, X, 4)
    rf, _ = vca(STOCK, 4, 0, True, X, 4)
    N = max(1, atk * atk * 96000 // 16129); step = 0x1000000 // N
    want = []; g = 0
    for b in range(4):
        if g >= 0x1000000: want.append(rf[b]); continue      # Rampe fertig: Block unberuehrt
        blk = []
        for i in range(32):                                  # sonst der ganze Block mit Verstaerkung (Q15)
            y = rf[b][i] >> 15; blk.append(y * (g >> 9))
            g = min(0x1000000, g + step)
        want.append(blk)
    chk('Attack %d: Rampe %d Samples (%.0f ms) ab dem Trig, Ausgang wie Modell, Register ok' % (atk, N, N / 48), got == want and ok2)
got, okk = vca(IMG, 3, 64, True, X, 3, own=True)
chk('smp24: OWN der Spur gesetzt (CHORD / Vlvt): keine Rampe, Ausgang wie Stock', got == vca(STOCK, 3, 0, True, X, 3)[0] and okk)
got, _ = vca(IMG, 4, 64, False, X, 1)
chk('Ohne neuen Trig und ohne Rampe (Zustand leer, Verstaerkung 0, kein Trig -> Rampe laeuft weiter von 0)', got != vca(STOCK, 4, 0, False, X, 1)[0])
got, _ = vca(IMG, 2, 64, True, X, 1)
chk('ohne Objekt der Klangerzeugung (PARP = 0): keine Rampe', vca(IMG, 2, 64, True, X, 1, obj=False)[0] == vca(STOCK, 2, 0, True, X, 1)[0])
# RPH merkt sich das Objekt
e = Emu(IMG); seen = []
e.u.hook_add(UC_HOOK_CODE, lambda u, a, z, _: (seen.append(e.r32(u.reg_read(mk.UC_M68K_REG_A7) + 8)), u.reg_write(mk.UC_M68K_REG_PC, e.r32(u.reg_read(mk.UC_M68K_REG_A7))),
             u.reg_write(mk.UC_M68K_REG_A7, u.reg_read(mk.UC_M68K_REG_A7) + 4)), begin=CO.RENDERFN, end=CO.RENDERFN)
_, good = e.call(CS['RPH'], 0x80001858, 0x4F041234, 7, 8)
chk('RPH: PARP = Objekt (%#x), dann die Firmware mit denselben Argumenten' % e.r32(CS['PARP']), e.r32(CS['PARP']) == 0x4F041234 and seen == [0x4F041234] and good)

# ---------------- 5 FUNC + SAMPLE START: Fenster verschieben
def bsh(start, end, delta, mach=6, held=(1,), trig=0, enc=4):
    e = Emu(IMG); UI = 0x4F046000; calls = []
    e.u.mem_write(UI, bytes(0x200)); e.w8(UI + 0x164, trig)
    stub2 = lambda addr, n, tag: e.u.hook_add(UC_HOOK_CODE, lambda u, a, z, _: (calls.append((tag,) + tuple(e.r32(u.reg_read(mk.UC_M68K_REG_A7) + 4 + 4 * i) for i in range(n))),
                     u.reg_write(mk.UC_M68K_REG_PC, e.r32(u.reg_read(mk.UC_M68K_REG_A7))), u.reg_write(mk.UC_M68K_REG_A7, u.reg_read(mk.UC_M68K_REG_A7) + 4)), begin=addr, end=addr)
    stub2(0x4006F698, 5, 'mk'); stub2(0x40006158, 2, 'post'); stub2(0x400CF76A, 1, 'free')
    e.u.hook_add(UC_HOOK_CODE, lambda u, a, z, _: (u.reg_write(mk.UC_M68K_REG_D0, UI), u.reg_write(mk.UC_M68K_REG_PC, e.r32(u.reg_read(mk.UC_M68K_REG_A7))),
                 u.reg_write(mk.UC_M68K_REG_A7, u.reg_read(mk.UC_M68K_REG_A7) + 4)), begin=G.UIGET, end=G.UIGET)
    KIT = 0x4F04D000; e.w32(G.KITP, KIT); e.u.mem_write(KIT, bytes(700)); e.w32(G.ACT_TRACK, 1)
    snd = KIT + 28 + 100
    e.u.mem_write(snd + 38, bytes([mach])); e.u.mem_write(snd + 42, bytes([start, 0, end, 0]))
    e.held = set(held)
    EV = 0x4F0F0000; e.u.mem_write(EV, struct.pack('>IIiI', 0, enc, 0, 0x777)); e.u.mem_write(EV + 8, bytes([delta & 0xff]))
    d0, good = e.call(SS['BSH'], 0xD2D2D2D2, 0xA3A3A3A3, 0x12345678, 0xD5D5D5D5, 1,
                      regs={mk.UC_M68K_REG_A2: EV, mk.UC_M68K_REG_D4: 0xD4D4D4D4})
    nd = struct.unpack('b', bytes(e.u.mem_read(EV + 8, 1)))[0]
    return d0, nd, calls, good
r = bsh(20, 60, 10)
chk('FUNC + Start +10 (Start 20, Ende 60): Ereignis fuer Ende gebaut wie die Firmware (Puffer d2, Knopf 5, +10, d5, FUNC), gesendet (d4), '
    'aufgeraeumt; Start-Ereignis laeuft weiter (d0 = 0) %s' % (r[2],),
    r[0] == 0 and r[1] == 10 and r[2] == [('mk', 0xD2D2D2D2, 5, 10, 0xD5D5D5D5, 1), ('post', 0xD4D4D4D4, 0xD2D2D2D2), ('free', 0xD2D2D2D2)] and r[3])
lim = [bsh(20, 60, 100)[1], bsh(20, 60, -50)[1], bsh(60, 20, -50)[1], bsh(0, 127, 5)[1], bsh(20, 60, 0)[1]]
chk('Begrenzung, Breite bleibt: +100 -> %d (Ende 127), -50 -> %d (Start 0), Ende vor Start -50 -> %d, voll +5 -> %d, 0 -> %d' % tuple(lim),
    lim == [67, -20, -20, 0, 0])
no = [bsh(20, 60, 10, mach=2), bsh(20, 60, 10, held=()), bsh(20, 60, 10, trig=1), bsh(20, 60, 10, enc=5)]
chk('nicht behandelt (d0 = 0, keine Aufrufe, Drehung bleibt): KICK-Spur, ohne FUNC, Trig gehalten, anderer Knopf',
    all(x[0] == 0 and x[1] == 10 and not x[2] and x[3] for x in no))
slot = struct.unpack('>I', IMG[CS['SLOTS'] - BASE + 4 * C.SLOT['sampler']:][:4])[0]
chk('Encoder-Slot sampler (8) = BSH, 10 Slots', slot == SS['BSH'] and C.NSLOT == 10)
done()
