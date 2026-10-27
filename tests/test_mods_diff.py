# Strum, Grooves/Humanize, Lastanzeige (v2) gegen v1: Klang-Pfade bitgleich (v1-Einstellungsbytes gegen v2-Pattern-Bytes),
# Gesten ueber den echten Encoder-Haken (v1-Kette gegen v2-Verteiler), Popup-Inhalt.
import random, struct
from rig import *

V1, V2 = v1_image(), v2_image()
VOICE0, VSTEP = 0x42308828, 0x31C
def mkemu(img):
    e = Emu(img); e.u.mem_map(0x42300000, 0x30000); return e

# ================= Strum (ST am Ende des CHORD-Updates)
ST1, ST2 = int(V1SYM['71-strum']['ST'], 16), V2SYM['strum']['ST']
G0 = 0x4233C378; CNT = 0x4233C360
SAVED = [0xD2000002, 0xD3000003, 0xD4000004, 0xD5000005, 0x0, 0xA3000003, 0xA4000004]
def run_st(e, st, voice, trig, gains):
    u = e.u
    u.mem_write(voice + 0x38, struct.pack('>I', 1 if trig else 0)); u.mem_write(voice + 0x0C, struct.pack('>3i', *gains))
    sp = 0x4F008000; sv = SAVED[:]; sv[4] = voice
    u.mem_write(sp, b'\xEE' * 8 + struct.pack('>7I', *sv) + struct.pack('>I', RET))
    u.reg_write(mk.UC_M68K_REG_A7, sp); u.reg_write(mk.UC_M68K_REG_A2, voice)
    u.reg_write(mk.UC_M68K_REG_D6, 0xD6D6D6D6); u.reg_write(mk.UC_M68K_REG_D7, 0xD7D7D7D7)
    u.emu_start(st, RET, count=5000)
    regs = [u.reg_read(r) for r in (mk.UC_M68K_REG_D2, mk.UC_M68K_REG_D3, mk.UC_M68K_REG_D4, mk.UC_M68K_REG_D5, mk.UC_M68K_REG_A2, mk.UC_M68K_REG_A3, mk.UC_M68K_REG_A4)]
    good = regs == sv and u.reg_read(mk.UC_M68K_REG_A7) == sp + 40 and u.reg_read(mk.UC_M68K_REG_D6) == 0xD6D6D6D6 and u.reg_read(mk.UC_M68K_REG_D7) == 0xD7D7D7D7
    return list(struct.unpack('>3i', bytes(u.mem_read(voice + 0x0C, 12)))), e.r32(G0), good
a, b = mkemu(V1), mkemu(V2)
for x in (a, b): x.u.mem_write(CNT, b'\x55' * 24)
random.seed(2); same = regs = True
for bl in range(2500):
    if bl % 250 == 0:
        S = random.choice([0, 1, 4, 32, 63, 80, 0xB0, 0xC0, 0xFF, 0xE0, 81, 100, 0xAF, 0x90]); a.w8(0x404E9B64, S); b.w8(b.hdr(C.P_STRUM), S)
    for i in range(6):
        trig = random.random() < 0.03; gains = [random.randint(0, 2**31 - 1) for _ in range(3)]
        r1 = run_st(a, ST1, VOICE0 + i * VSTEP, trig, gains); r2 = run_st(b, ST2, VOICE0 + i * VSTEP, trig, gains)
        same &= r1[:2] == r2[:2]; regs &= r1[2] and r2[2]
chk('Strum: 2500 Bloecke x 6 Stimmen bitgleich mit v1 (beide Richtungen, Grundton, Muell)', same)
chk('Strum: Epilog, Register, Stack ok', regs)
b.w8(b.hdr(C.P_STRUM), 0xC0); b.w32(C.CUR_PAT, 0)
g, g0, _ = run_st(b, ST2, VOICE0, True, [5, 6, 7])
chk('Strum ohne Pattern (CUR_PAT = 0): Pegel unveraendert, Grundton voll', g == [5, 6, 7] and g0 == 0x20000000)
b.w32(C.CUR_PAT, PATB)

# ================= Groove G (Ereignisbau 0x40054af8 -> 0x40054b0c)
HOOK, BACK = 0x40054AF8, 0x40054B0C
RND1, RND2 = int(V1SYM['73-groove']['RND'], 16), V2SYM['groove']['RND']
def run_g(e, swing, track, step, d5, vel, factor, trigbits):
    u = e.u; sp = 0x4F008000
    u.mem_write(sp, bytes(0x60)); u.mem_write(sp + 0x30, struct.pack('>i', vel)); u.mem_write(sp + 0x3A, bytes([factor & 0xff]))
    u.reg_write(mk.UC_M68K_REG_A7, sp)
    for r, v in ((mk.UC_M68K_REG_D0, swing), (mk.UC_M68K_REG_D1, trigbits), (mk.UC_M68K_REG_D3, step), (mk.UC_M68K_REG_D5, d5),
                 (mk.UC_M68K_REG_D6, track), (mk.UC_M68K_REG_A0, factor), (mk.UC_M68K_REG_A3, PATB), (mk.UC_M68K_REG_D2, 0xD2D2D2D2),
                 (mk.UC_M68K_REG_D4, 0xD4D4D4D4), (mk.UC_M68K_REG_A2, 0xA2A2A2A2), (mk.UC_M68K_REG_A4, 0xA4A4A4A4)):
        u.reg_write(r, v & 0xffffffff)
    u.emu_start(HOOK, BACK, count=3000)
    return (u.reg_read(mk.UC_M68K_REG_PC) == BACK, u.reg_read(mk.UC_M68K_REG_D5), struct.unpack('>i', bytes(u.mem_read(sp + 0x30, 4)))[0],
            u.reg_read(mk.UC_M68K_REG_A7) == sp, [u.reg_read(r) for r in (mk.UC_M68K_REG_D2, mk.UC_M68K_REG_D4, mk.UC_M68K_REG_D6,
                                                                       mk.UC_M68K_REG_A2, mk.UC_M68K_REG_A3, mk.UC_M68K_REG_A4)])
a, b = mkemu(V1), mkemu(V2)
a.w32(RND1, 0x7654321); b.w32(RND2, 0x7654321)
random.seed(4); same = reach = True; seen = set()
for n in range(6000):
    if n % 200 == 0:
        gm = random.choice([0, 1, 2, 3, 4, 5, 6, 7, 8, 200]); hum = [random.choice([0, 0, 13, 50, 100, 101, 255]) for _ in range(12)]
        a.w8(0x404E9B5E, gm); b.w8(b.hdr(C.P_GROOVE), gm)
        for x in (a, b): x.u.mem_write(x.hdr(C.P_HUM_T), bytes(hum))
        seen.add(gm)
    args = (random.randint(0, 30), random.randint(0, 6), random.randint(0, 63), random.randint(-3000, 3000), random.randint(1, 127),
            random.choice([1, 2, 4, 8]), random.choice([0, 0x10]))
    r1 = run_g(a, *args); r2 = run_g(b, *args)
    reach &= r1[0] and r2[0] and r1[3] and r2[3]
    same &= r1[1:3] == r2[1:3] and r1[4] == r2[4] and a.r32(RND1) == b.r32(RND2)
chk('Groove: 6000 Ereignisse bitgleich mit v1 (Zeit, Velocity, Zufall; Grooves 0..7 + Muell %s, Humanize inkl. Muell)' % sorted(seen), same)
chk('Groove: Rueckkehr nach 0x40054b0c, Stack/Register ok', reach)
b.w8(b.hdr(C.P_GROOVE), 3); b.u.mem_write(b.hdr(C.P_HUM_T), bytes(12))
r = run_g(b, 30, 2, 5, 100, 90, 2, 0x10); b.w8(b.hdr(C.P_GROOVE), 0); r0 = run_g(b, 30, 2, 5, 100, 90, 2, 0x10)
chk('Groove-Byte im Pattern wirkt (Reggae vs. Swing: %d vs. %d)' % (r[1], r0[1]), r[1] != r0[1])

# ================= Gesten: Groove, Humanize (Zeit/Velocity, Track/alle), Strum (v1-Kette gegen v2-Verteiler)
SEL = 0x40012412
def mkg(img):
    e = mkemu(img); e.track = 2
    def sel(u, a_, z, _):
        sp = u.reg_read(mk.UC_M68K_REG_A7); u.reg_write(mk.UC_M68K_REG_D0, e.track if a_ == SEL else 0x4F050000)
        u.reg_write(mk.UC_M68K_REG_PC, e.r32(sp)); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
    for t in (C.SEL_A, C.SEL_B, C.SEL_C): e.u.hook_add(UC_HOOK_CODE, sel, begin=t, end=t)
    e.w32(C.TIMER, 1000); e.u.mem_write(C.ACC, bytes(12)); e.u.mem_write(0x404E9B10, b'COKI')
    e.u.mem_write(e.hdr(40), bytes(24)); return e
a, b = mkg(V1), mkg(V2)
s1, s2, okk = [], [], True
for d in [1] * 40 + [-1] * 13 + [30, -30]:
    r1 = a.enc(12, d, {1}); r2 = b.enc(12, d, {1})
    s1.append(a.r8(0x404E9B5E)); s2.append(b.r8(b.hdr(C.P_GROOVE)))
    okk &= r2['skipped'] and r2['sp'] and r2['regs']
chk('FUNC + Swing: Groove-Folge wie v1 %s' % s2[3::4], s1 == s2 and okk)
names = ["Swing", "Boom Bap", "Disco", "Reggae", "Bongo", "Caixixi", "Highlife", "Kuduro"]
b.u.mem_write(C.ACC, bytes(12)); b.w8(b.hdr(C.P_GROOVE), 5)
for _ in range(4): b.enc(12, 1, {1})
chk('Popup Groove: Text "%s" / "%s"' % (b.cstr(b.r32(C.VARS + C.V_L1)), b.cstr(b.r32(C.VARS + C.V_VAL))),
    b.r32(C.VARS + C.V_KIND) == 2 and b.cstr(b.r32(C.VARS + C.V_L1)) == 'Groove' and b.cstr(b.r32(C.VARS + C.V_VAL)) == 'Highlife'
    and b.r32(C.VARS + C.V_L2) == 0)
for key, off, lab in ((13, C.P_HUM_T, 'Hum Time'), (5, C.P_HUM_V, 'Hum Vel')):
    for held, trk, lab2 in (({key}, 2, 'Track'), ({key, 2}, 4, 'All')):
        a.track = b.track = trk; seq1, seq2 = [], []
        for d in (5, 30, 70, -3, 1, -200 & 0xff if False else -120, 50):
            r1 = a.enc(12, d, held); r2 = b.enc(12, d, held)
            seq1.append(bytes(a.u.mem_read(a.hdr(40), 12))); seq2.append(bytes(b.u.mem_read(b.hdr(40), 12)))
        good = r2['skipped'] and r2['consumed'] == [key] and r2['sp'] and r2['regs']
        chk('%s + Swing (%s): Kopf-Bytes wie v1 %s, verschluckt, consume(%d), Popup %s / %s = %d' %
            ({13: 'SETTINGS', 5: 'MACHINE'}[key], lab2, list(seq2[-1][off - 40:off - 34]), key, b.cstr(b.r32(C.VARS + C.V_L1)),
             b.cstr(b.r32(C.VARS + C.V_L2)), b.r32(C.VARS + C.V_VAL)),
            seq1 == seq2 and good and b.cstr(b.r32(C.VARS + C.V_L1)) == lab and b.cstr(b.r32(C.VARS + C.V_L2)) == lab2
            and b.r32(C.VARS + C.V_VAL) == seq2[-1][off - 40 + trk])
for held in ((), (2,), (8,)):
    r = b.enc(12, 1, held); chk('Swing mit %s: durchgereicht' % (held or 'nichts'), r['passed'] == 1)
a.w8(0x404E9B64, 0); b.w8(b.hdr(C.P_STRUM), 0); t1, t2 = [], []
for d in (5, 30, 70, -3, -100, -100, 20):
    a.enc(5, d, {13}); r2 = b.enc(5, d, {13}); t1.append(a.r8(0x404E9B64)); t2.append(b.r8(b.hdr(C.P_STRUM)))
sv = struct.unpack('>i', struct.pack('>I', b.r32(C.VARS + C.V_VAL)))[0]
chk('SETTINGS + SHAPE: Strum-Folge wie v1 %s, Popup Strum = %d' % ([x - 256 if x > 127 else x for x in t2], sv),
    t1 == t2 and r2['skipped'] and r2['consumed'] == [13] and b.cstr(b.r32(C.VARS + C.V_L1)) == 'Strum' and sv == -60)
for held in ((), (2,), (1,)):
    r = b.enc(5, 1, held); chk('SHAPE mit %s: durchgereicht' % (held or 'nichts'), r['passed'] == 1)

# ================= Lastanzeige: PROBE gegen v1, Geste
AUDIO, PROBE1, PROBE2 = 0x4005979E, int(V1SYM['72-load-meter']['PROBE'], 16), V2SYM['load-meter']['PROBE']
def mkp(img):
    e = mkemu(img); e.dur = [0]
    def audio(u, a_, z, _):
        e.w32(C.TIMER, e.r32(C.TIMER) + e.dur[0]); sp = u.reg_read(mk.UC_M68K_REG_A7)
        u.reg_write(mk.UC_M68K_REG_D0, 0x1234); u.reg_write(mk.UC_M68K_REG_PC, e.r32(sp)); u.reg_write(mk.UC_M68K_REG_A7, sp + 4)
    e.u.hook_add(UC_HOOK_CODE, audio, begin=AUDIO, end=AUDIO); e.w32(C.TIMER, 5000); return e
a, b = mkp(V1), mkp(V2)
import g2_loadmeter as glm
good = True
for junk in (1, 0xFFFFFFFF, 0xDEADBEEF, 0x4C444F4D):         # RAM nach dem Einschalten: beliebiger Inhalt -> aus
    b.w32(0x4A33C3D0, junk); b.u.mem_write(C.VARS + C.V_KIND, bytes(4)); x, g = b.call(PROBE2)
    good &= x == 0x1234 and g and b.r32(C.VARS + C.V_KIND) == 0 and b.r32(0x4A33C3D0 + glm.N) in (0, b.r32(0x4A33C3D0 + glm.N))
chk('nach dem Einschalten (Zustand = Zufall, nicht LDON): aus, PROBE ruft nur die Audio-Funktion', good)
b.w32(0x4A33C3D0, 0); b.u.mem_write(0x4A33C3D0 + 12, bytes(12))
r1 = a.enc(9, 1, {13}); r2 = b.enc(9, 1, {13})
chk('SETTINGS + REVERB SEND rechts: an, verschluckt, consume(13), Popup Art 3 mit LDRAW', r2['skipped'] and r2['consumed'] == [13]
    and b.r32(C.VARS + C.V_KIND) == 3 and b.r32(C.VARS + C.V_L1) == V2SYM['load-meter']['LDRAW'] and b.r32(0x4A33C3D0) == glm.LM_ON)
random.seed(9); same = True
for n in range(2250):
    d = random.randint(40000, 95000); a.dur[0] = b.dur[0] = d
    x1, g1 = a.call(PROBE1); x2, g2 = b.call(PROBE2)
    same &= x1 == x2 == 0x1234 and g1 and g2
    if n % 750 == 749:
        t1 = bytes(a.u.mem_read(0x4A33C380 + 20, a.r32(0x4A33C380 + 28))); t2 = bytes(b.u.mem_read(0x4A33C3D0 + 28, b.r32(0x4A33C3D0 + 24)))
        import gen_overlay_113 as ov1, g2_loadmeter as glm
        same &= ''.join(ov1.ORDER[c] for c in t1) == ''.join(glm.ORDER[c] for c in t2) and b.r32(C.VARS + C.V_KIND) == 3
chk('PROBE: 2250 Bloecke, Text Spitze/Mittel wie v1 (%s), Ergebnis der Audio-Funktion durchgereicht, Register ok' %
    ''.join(glm.ORDER[c] for c in t2), same)
r2 = b.enc(9, -1, {13})
chk('links: aus, Popup weg', r2['skipped'] and b.r32(0x4A33C3D0) == 0 and b.r32(C.VARS + C.V_KIND) == 0)
x, g = b.call(PROBE2); chk('aus: PROBE ruft nur die Audio-Funktion', x == 0x1234 and g)
for held in ((), (2,)):
    r = b.enc(9, 1, held); chk('REVERB SEND mit %s: durchgereicht' % (held or 'nichts'), r['passed'] == 1)
done()
