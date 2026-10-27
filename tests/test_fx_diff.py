# Reverb FX und Delay FX (v2) gegen v1 (auf der Hardware getestet), Block fuer Block bitgleich:
# gleiche Eingaben, v1 mit seinen Einstellungsbytes, v2 mit den Pattern-Bytes. Dazu Weichen, Namen, Muell, Schreib-DMA,
# Delay-Zeit mit und ohne 'delay-notes', Gesten ueber den echten Encoder-Haken (v1-Kette gegen v2-Verteiler).
import random, struct
from rig import *

REVERB, STOCKD, WDMA = 0x400579C4, 0x40057488, 0x400573FA
IN, OUT, PAR = 0x8000B990, 0x8000BB90, 0x4F020000
V1, V2 = v1_image(), v2_image()
R1, R2 = int(V1SYM['70-mod-delays']['R'], 16), V2SYM['reverb-fx']['R']
MD1, MD2 = int(V1SYM['70-mod-delays']['md'], 16), V2SYM['delay-fx']['MD']
DESC = lambda k: 0x4010DCE0 + 0x38 * k
FN39, FN40 = 0x40A71754 + 3900 + 0x20, 0x40A71754 + 4000 + 0x20


def mkemu(img):
    e = Emu(img); e.calls = []
    def rev(u, a, z, _):                 # Reverb der Firmware: deterministischer Ersatz (out = in/2 + Parameter), Aufruf mitschreiben
        sp = u.reg_read(mk.UC_M68K_REG_A7); ret, out, inp, par = struct.unpack('>IIII', bytes(u.mem_read(sp, 16)))
        p = struct.unpack('>HH', bytes(u.mem_read(par, 4)))
        e.calls.append(('REV', p))
        d = bytes(u.mem_read(inp, 256))
        vals = [struct.unpack('>i', d[i:i + 4])[0] for i in range(0, 256, 4)]
        u.mem_write(out, b''.join(struct.pack('>i', (v >> 1) + p[0] - p[1]) for v in vals))
        u.reg_write(mk.UC_M68K_REG_PC, ret); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
    def stockd(u, a, z, _):
        e.calls.append(('STOCK',)); u.emu_stop()
    e.u.hook_add(UC_HOOK_CODE, rev, begin=REVERB, end=REVERB)
    e.u.hook_add(UC_HOOK_CODE, stockd, begin=STOCKD, end=STOCKD)
    e.w32(FN39, 0x40045A68); e.w32(FN40, 0x4004E00E)
    return e


def block(e, entry, frames, p0, p1):
    e.u.mem_write(IN, b''.join(struct.pack('>ii', l, r) for l, r in frames)); e.u.mem_write(PAR, struct.pack('>HH', p0, p1))
    sp = STACK - 0x40; e.u.mem_write(sp, struct.pack('>IIII', RET, OUT, IN, PAR)); e.u.reg_write(mk.UC_M68K_REG_A7, sp)
    for i, r in enumerate(KEEP): e.u.reg_write(r, 0xC0DE0000 + i)
    e.calls = []
    e.u.emu_start(entry, RET, count=2000000)
    stopped = e.calls[-1:] == [('STOCK',)]
    good = stopped or (all(e.u.reg_read(r) == 0xC0DE0000 + i for i, r in enumerate(KEEP)) and e.u.reg_read(mk.UC_M68K_REG_A7) == sp + 4)
    raw = bytes(e.u.mem_read(OUT, 256))
    return [struct.unpack('>ii', raw[i:i + 8]) for i in range(0, 256, 8)], list(e.calls), good


def names(e, ks): return [(e.cstr(e.r32(DESC(k) + 0x2C)), e.cstr(e.r32(DESC(k) + 0x34))) for k in ks]


# ================= Reverb-Platz
a, b = mkemu(V1), mkemu(V2)
random.seed(11); same = regs = True; nm_same = True; seen = set()
mode = 1
for bl in range(1200):
    if bl % 100 == 0:
        mode = [1, 2, 3, 4, 0, 3, 1, 4, 2, 0, 4, 1][bl // 100]
        a.w8(0x404E9B5D, mode); b.w8(b.hdr(C.P_RFX), mode)
    S = [0, 30, 64, 127][(bl // 37) % 4]; D = [0, 50, 127][(bl // 53) % 3]
    fr = [(random.randint(-2**30, 2**30), random.randint(-2**30, 2**30)) if bl % 13 < 9 else (0, 0) for _ in range(32)]
    if bl % 211 == 7: fr = [(2**31 - 1, 2**31 - 1) if i % 2 else (-2**31, -2**31) for i in range(32)]
    o1, c1, g1 = block(a, R1, fr, S << 8, D << 8); o2, c2, g2 = block(b, R2, fr, S << 8, D << 8)
    same &= (o1 == o2 and c1 == c2); regs &= g1 and g2; seen.add(mode)
    if bl % 100 == 1:
        f1 = (a.r32(FN39), a.r32(FN40)); f2 = (b.r32(FN39), b.r32(FN40))
        fsame = f1 == f2 if mode == 0 else (f2[0] == f2[1] and bytes(a.u.mem_read(f1[0], 26)) == bytes(b.u.mem_read(f2[0], 26)))
        nm_same &= names(a, (27, 39, 40)) == names(b, (27, 39, 40)) and fsame
chk('Reverb-Platz: 1200 Bloecke bitgleich mit v1 (Reverb, Chorus I/II, Phaser, RAZR, Wechsel, Vollaussteuerung) %s' % sorted(seen), same)
chk('Reverb-Platz: Register/Stack ok', regs)
chk('Reverb-Platz: Parameternamen und Anzeigefunktionen wie v1 in allen Modi (F0 an neuer Adresse, gleicher Code)', nm_same)
for m, nm in ((1, 'Cho1 Send'), (3, 'Phas Send'), (4, 'Razr Mix')):
    b.w8(b.hdr(C.P_RFX), m); block(b, R2, [(0, 0)] * 32, 0, 0)
    chk('  Modus %d: Name %s' % (m, names(b, (27,))[0][0]), names(b, (27,))[0][0] == nm)
for junk in (5, 9, 200):
    b.w8(b.hdr(C.P_RFX), junk); _, c, g = block(b, R2, [(1, 1)] * 32, 0, 0)
    chk('Muell %d im Pattern-Byte -> Reverb der Firmware, RMODE 0' % junk, c and c[0][0] == 'REV' and g and b.r8(0x4233C3FC) == 0)
b.w32(C.CUR_PAT, 0); _, c, _ = block(b, R2, [(1, 1)] * 32, 0, 0)
chk('kein Pattern (CUR_PAT = 0) -> Reverb der Firmware', c and c[0][0] == 'REV')
b.w32(C.CUR_PAT, PATB)

# ================= Delay-Platz
MAP = {0: 1, 1: 0, 2: 3, 3: 2}                      # v2-Typ -> v1-Byte
a, b = mkemu(V1), mkemu(V2)
DN = {0: names(b, (26, 37, 38)), 1: [('Digi Send', 'DIGS'), ('Digi Time', 'TIME'), ('Digi Fdbk', 'FDBK')],
      2: [('VIBDEL Send', 'VIBD'), ('VIBDEL Time', 'TIME'), ('VIBDEL Fdbk', 'FDBK')], 3: [('CHODEL Send', 'CHOD'), ('CHODEL Time', 'TIME'), ('CHODEL Fdbk', 'FDBK')]}
random.seed(7); same = regs = True; seen = set(); nm_same = True
for bl in range(1500):
    if bl % 125 == 0:
        t = [2, 3, 1, 0, 3, 2, 1, 3, 0, 2, 1, 2][bl // 125]; S = random.choice([0, 1, 40, 64, 127])
        a.w8(0x404E9B5C, MAP[t]); a.w8(0x404E9B5B, S); b.w8(b.hdr(C.P_DFX), t); b.w8(b.hdr(C.P_DSPD), S ^ 64)
    Tm = [8192, 2048, 512, 20 << 8, 41 << 8][(bl // 300) % 5]; F = [10400, 20000, 32512][(bl // 200) % 3]
    fr = [(random.randint(-2**30, 2**30), random.randint(-2**30, 2**30)) if bl % 97 < 4 else (0, 0) for _ in range(32)]
    o1, c1, g1 = block(a, MD1, fr, Tm, F); o2, c2, g2 = block(b, MD2, fr, Tm, F)
    if t == 0: same &= c1 == c2 == [('STOCK',)]
    else: same &= o1 == o2 and c1 == c2
    regs &= g1 and g2; seen.add(t)
    if bl % 125 == 1:                   # v1 stellte die Delay-Namen nur im Reverb-Haken um; v2 im eigenen Haken
        nm_same &= names(b, (26, 37, 38)) == DN[t]
chk('Delay-Platz: 1500 Bloecke bitgleich mit v1 (Original, Digital, VIBDEL, CHODEL, Speed, Zeiten inkl. Triolen 4T/2T) %s' % sorted(seen), same)
chk('Delay-Platz: Register/Stack ok', regs)
chk('Delay-Platz: Parameternamen je Typ (Original, Digi, VIBDEL, CHODEL)', nm_same and DN[0][0][0] == 'Delay Send')
for junk in (4, 9, 255):
    b.w8(b.hdr(C.P_DFX), junk); _, c, _ = block(b, MD2, [(0, 0)] * 32, 8192, 0)
    chk('Muell %d im Typ-Byte -> Delay der Firmware' % junk, c == [('STOCK',)])
b.w8(b.hdr(C.P_DFX), 2)
for raw, exp in ((64, 0), (0, 64), (127 ^ 64, 127), (200, 64)):
    b.w8(b.hdr(C.P_DSPD), raw); block(b, MD2, [(0, 0)] * 32, 8192, 0)
    chk('Speed-Byte %d -> Speed %d (SMIR)' % (raw, exp), b.r8(0x4233C3FE) == exp)
# Schreib-DMA
W2 = V2SYM['delay-fx']['W2']
for t, shifted in ((0, False), (1, True), (2, True), (3, True), (9, False)):
    b.w8(b.hdr(C.P_DFX), t); block(b, MD2, [(0, 0)] * 32, 8192, 0)
    b.w32(0x8000B988, 0x1234); h = []
    hh = b.u.hook_add(UC_HOOK_CODE, lambda u, a_, z, _: (h.append(1), u.emu_stop()), begin=WDMA, end=WDMA)
    b.u.mem_write(STACK - 0x80, struct.pack('>I', RET)); b.u.reg_write(mk.UC_M68K_REG_A7, STACK - 0x80); b.u.emu_start(W2, RET, count=100)
    b.u.hook_del(hh)
    chk('Schreib-DMA Typ %d: %s' % (t, 'obere Haelfte' if shifted else 'normal'), h == [1] and b.r32(0x8000B988) == (0x41234 if shifted else 0x1234))

# Delay-Zeit ohne 'delay-notes': wie die Firmware (addi #$100), Triolen nicht verschoben
V2n = v2_image([i for i in V2_IDS if i != 'delay-notes'])
c = mkemu(V2n); a = mkemu(V1); same_nt = True; tri_diff = False
for Tm in (8192, 2048, 512, 20 << 8, 41 << 8, 84 << 8):
    for x in (a, c):
        x.w8(0x404E9B5C, 0); x.w8(x.hdr(C.P_DFX), 1)
        x.u.mem_write(0x4233C140, bytes(20))
    r1 = block(a, MD1, [(1 << 28, 1 << 28)] * 32, Tm, 20000); r2 = block(c, V2SYM['delay-fx']['MD'], [(1 << 28, 1 << 28)] * 32, Tm, 20000)
    t1, t2 = a.r32(0x4233C140 + 4), c.r32(0x4233C140 + 4)
    if (Tm >> 8) in (20, 41, 84): tri_diff |= t1 != t2
    else: same_nt &= t1 == t2
chk('ohne delay-notes: gerade Werte gleich, Triolen-Werte nicht korrigiert (TC erkennt das zur Laufzeit)', same_nt and tri_diff)
TC = V2SYM['delay-fx']['TC']
for img_, exp in ((V2, 'jsr'), (V2n, 'addi')):
    x = Emu(img_); d0, g = x.call(TC, regs={mk.UC_M68K_REG_D0: 0x1400, mk.UC_M68K_REG_D1: 0xBB80, mk.UC_M68K_REG_A0: 0x40149310})
    want = 0x1500 + (85 if exp == 'jsr' else 0)
    chk('TC %s: d0 0x1400 -> %#x, d1/a0 bleiben' % (exp, d0), d0 == want and x.u.reg_read(mk.UC_M68K_REG_D1) == 0xBB80 and x.u.reg_read(mk.UC_M68K_REG_A0) == 0x40149310 and g)

# ================= Gesten: TRACK + Reverb Size / Delay Time, SETTINGS + DELAY SEND (v1-Kette gegen v2-Verteiler)
a, b = mkemu(V1), mkemu(V2)
for x in (a, b):
    x.w32(C.TIMER, 1000); x.u.mem_write(C.ACC, bytes(12)); x.u.mem_write(0x404E9B10, b'COKI')
a.w8(0x404E9B5D, 0); a.w8(0x404E9B5C, 1); b.w8(b.hdr(C.P_RFX), 0); b.w8(b.hdr(C.P_DFX), 0)
seq1, seq2, ok_ = [], [], True
for enc, d in [(14, 1)] * 20 + [(14, -1)] * 9 + [(15, 1)] * 14 + [(15, -1)] * 5:
    r1 = a.enc(enc, d, {2}); r2 = b.enc(enc, d, {2})
    ok_ &= r1['passed'] == r2['passed'] == 0 and r2['regs'] and r2['sp']
    seq1.append((a.r8(0x404E9B5D), {1: 0, 0: 1, 3: 2, 2: 3}[a.r8(0x404E9B5C)])); seq2.append((b.r8(b.hdr(C.P_RFX)), b.r8(b.hdr(C.P_DFX))))
chk('TRACK + Reverb Size / Delay Time: gleiche Schrittfolge wie v1 %s' % seq2[3::4], seq1 == seq2)
chk('  Ereignis mit Drehung 0 weiter (Firmware-Popup), Register/Stack ok', ok_)
chk('  Namen sofort umgestellt (wie v1)', names(a, (27, 39, 40, 26, 37, 38)) == names(b, (27, 39, 40, 26, 37, 38)))
for enc, held in ((14, ()), (15, ()), (14, (1,)), (13, (2,)), (16, (2,))):
    r = b.enc(enc, 1, held)
    exp = 0 if (held == (1,) and False) else 1
    chk('  Encoder %d mit %s: durchgereicht' % (enc, held or 'nichts'), r['passed'] == 1 and not r['skipped'] and r['sp'])
# SETTINGS + DELAY SEND
for t in (2, 3, 0):
    b.w8(b.hdr(C.P_DFX), t); a.w8(0x404E9B5C, MAP[t])
    a.w8(0x404E9B5B, 120); b.w8(b.hdr(C.P_DSPD), 120 ^ 64)
    s1, s2 = [], []
    for d in (3, 5, -2, 10, -127, -1, 4):
        r1 = a.enc(8, d, {13}); r2 = b.enc(8, d, {13})
        s1.append(a.r8(0x404E9B5B)); s2.append(b.r8(b.hdr(C.P_DSPD)) ^ 64)
        ok2 = r2['skipped'] and r2['sp'] and r2['regs'] and r2['consumed'] == [13]
    lab = b.cstr(b.r32(C.VARS + C.V_L1)); lab2 = b.cstr(b.r32(C.VARS + C.V_L2))
    chk('SETTINGS + DELAY SEND (Typ %d): Speed wie v1 %s, verschluckt, consume(13), Popup %s / %s = %d' % (t, s2, lab, lab2, b.r32(C.VARS + C.V_VAL)),
        s1 == s2 and ok2 and lab == {2: 'VIBDEL', 3: 'CHODEL', 0: 'Delay'}[t] and lab2 == 'Speed' and b.r32(C.VARS + C.V_VAL) == s2[-1]
        and b.r32(C.VARS + C.V_KIND) == 1)
r = b.enc(8, 1, ()); chk('DELAY SEND ohne SETTINGS: durchgereicht', r['passed'] == 1)
r = b.enc(8, 1, (2,)); chk('TRACK + DELAY SEND (CONTROL ALL): durchgereicht', r['passed'] == 1)
done()
