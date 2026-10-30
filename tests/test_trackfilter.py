# track-filter (v2, Patch 13): 12-dB-Tiefpass pro Track, Huellkurve, Filter-Modus (CLICK doppelt), Parameter k 28..31.
# EMAC exakt nachgebildet (Modded-Cycles tools/emu/emac.py, MIT) mit den Befehlen aus unserem eigenen Assembler (cfemac.LOG).
# 1. DSP ueber den echten Haken 0x40059852 (POST; Volume+Dist gestubbt): Cutoff 127 = bitgenau, Vergleich mit einem
#    Gleitkomma-Modell (gleiche Gleichungen, exakte Koeffizienten), Frequenzgang (Q, -24 dB/Oktave), Huellkurve,
#    Stabilitaet bei hoher Resonanz und Vollaussteuerung, Ausklingen und Ruhe, Register / MACSR / Akkus, Kosten.
# 2. Knopf-Zuordnung (Vtable-Slot 124), Doppel-Tippen (KEYH, echtes OVS des Cores), Laden / Speichern (echte Funktionen),
#    p-lock-Umrechnung (echte 0x4005aa1a), PTAB, Deskriptoren.
# Aufruf: test_trackfilter.py [--alone]   (--alone: nur Core + track-filter)
import math, random, struct, sys, pathlib
from rig import *
import g2_trackfilter as G
import cfemac
sys.path.insert(0, str(ROOT / 'Modded-Cycles' / 'tools' / 'emu'))
import emac as MEMAC

ALONE = '--alone' in sys.argv
IMG = v2_image(['core', 'track-filter'], latch=False) if ALONE else v2_image()
S = V2SYM['track-filter']
G.build()                                                 # fuellt cfemac.LOG (Adressen = Patch)
OPS = cfemac.ops()
TRK, PAR, CTX = 0x80001858, 0x4F040000, 0x4F041000
TS = G.TS


def emu():
    e = Emu(IMG)
    m = MEMAC.EMAC(e.u); m.install(OPS); e.mac = m
    e.u.hook_add(UC_HOOK_CODE, lambda u, a, z, _: (u.reg_write(mk.UC_M68K_REG_PC, e.r32(u.reg_read(mk.UC_M68K_REG_A7))),
                                                   u.reg_write(mk.UC_M68K_REG_A7, u.reg_read(mk.UC_M68K_REG_A7) + 4)),
                 begin=G.VOLDIST, end=G.VOLDIST)
    return e


def q31(x): return max(min(int(round(x * 2 ** 31)), 0x7FFFFFFF), -0x80000000)


def setp(e, t, cut=G.TOP, res=0, env=0x4000, dec=0x4000):
    for k, v in ((G.K_CUT, cut), (G.K_RES, res), (G.K_ENV, env), (G.K_DEC, dec)):
        e.u.mem_write(PAR + 14 + 66 * t + 2 * k, struct.pack('>h', v))


def block(e, xs, trig=0, count=False):
    """xs: 6 Listen mit 32 Samples (float) -> 6 Listen Ausgang (float), Erfolg"""
    for t in range(6):
        e.u.mem_write(TRK + 128 * t, struct.pack('>32i', *[q31(x) for x in xs[t]]))
    e.w32(CTX + 16, trig)
    n = [0]
    if count:
        h = e.u.hook_add(UC_HOOK_CODE, lambda u, a, z, _: n.__setitem__(0, n[0] + 1), begin=0x40140000, end=0x40190000)
    e.mac.macsr = 0x1234 & 0xff
    d0, good = e.call(S['POST'], TRK, PAR, regs={mk.UC_M68K_REG_A3: CTX}, count=400000)
    if count: e.u.hook_del(h)
    out = [[v / 2 ** 31 for v in struct.unpack('>32i', bytes(e.u.mem_read(TRK + 128 * t, 128)))] for t in range(6)]
    good = good and e.mac.macsr == 0x34 and e.mac.acc == [0, 0, 0, 0]
    return out, good, n[0]


# ---------------- Gleitkomma-Modell (gleiche Kennlinien wie die Tabellen, exakte Rechnung)
def lerp(tab, w):
    w = max(0, min(w, G.TOP)); j, f = w >> 9, (w & 511) / 512
    return (tab[j] + (tab[j + 1] - tab[j]) * f) / 2 ** 31


GT, KT, DT, NT = G.tables()


class Model:
    def __init__(s): s.s1 = s.s2 = s.env = 0.0; s.on = False; s.n = 0
    def block(s, xs, trig, cut, res, env, dec):
        if trig: s.env = 1.0
        elif s.env:
            s.env *= lerp(DT, dec)
            if s.env < 0x10000 / 2 ** 31: s.env = 0.0
        no = s.n
        if cut >= G.TOP and (not s.env or env >= 0x4000):
            if s.n == 0: s.on = False; return list(xs)
            c = G.TOP; s.n -= 1                              # ausblenden
        else:
            c = cut + (int(math.floor(2 * (env - 0x4000) * s.env)) if s.env else 0)
            c = min(max(c, 0), G.TOP); s.n = min(s.n + 1, G.NFADE)
        g = 4 * lerp(GT, c); k = 2 * max(lerp(KT, res), lerp(NT, c))
        a1 = 1 / (1 + g * (g + k)); c1, c2, a3 = 2 * a1 - 1, 2 * g * a1, g * g * a1; ee = 1 - 2 * a3
        if not s.on: s.s1, s.s2, s.on = 0.0, xs[0] / 2, True
        out = []
        for x in xs:
            u = x / 2 * (1 - x * x / 4)
            n1 = c1 * s.s1 + c2 * u - c2 * s.s2
            n2 = ee * s.s2 + c2 * s.s1 + 2 * a3 * u
            n1, n2 = max(-1, min(n1, 1)), max(-1, min(n2, 1))
            n1 = n1 * (1 - n1 * n1 / 4)
            out.append(max(-1, min(s.s2 + n2, 1))); s.s1, s.s2 = n1, n2
        if no == s.n == G.NFADE: return out
        return [(no / 8 + i * (s.n - no) / 256) * y + (1 - no / 8 - i * (s.n - no) / 256) * x for i, (x, y) in enumerate(zip(xs, out))]


def sine(f, amp, n0, n=32): return [amp * math.sin(2 * math.pi * f * (n0 + i) / 48000) for i in range(n)]


# ---------------- 1a Bypass
e = emu()
for t in range(6): setp(e, t)
rnd = random.Random(1)
xs = [[rnd.uniform(-0.9, 0.9) for _ in range(32)] for _ in range(6)]
out, good, _ = block(e, xs, trig=0x3F)
chk('Cutoff 127: alle 6 Spuren bitgenau (auch mit Trig)', all(struct.pack('>32i', *[q31(x) for x in xs[t]]) ==
                                                              bytes(e.u.mem_read(TRK + 128 * t, 128)) for t in range(6)))
chk('Register, Stack, MACSR, Akkus wie vorher', good)
setp(e, 1, env=0x6000)                                    # Env positiv: bleibt offen
out, good, _ = block(e, xs, trig=0x3F)
chk('Cutoff 127 + Env positiv: bitgenau', struct.pack('>32i', *[q31(x) for x in xs[1]]) == bytes(e.u.mem_read(TRK + 128, 128)))

# ---------------- 1b Vergleich mit dem Modell (verschiedene Einstellungen, Rauschen + Sinus, Trigs)
cases = [(0x3000, 0, 0x4000, 0x4000), (0x5000, 0x6000, 0x4000, 0x4000), (0x1800, 0x7F00, 0x4000, 0x4000),
         (0x2000, 0x3000, 0x7F00, 0x2000), (0x7000, 0x5000, 0x0000, 0x5000), (0x0000, 0x7F00, 0x7F00, 0x7F00)]
e = emu(); models = [Model() for _ in range(6)]
for t, c in enumerate(cases): setp(e, t, *c)
err = [0.0] * 6; okb = True
for b in range(120):
    xs = [[0.6 * rnd.uniform(-1, 1) * (1 if (b // 30) % 2 == 0 else 0.1) + sine(110 * (t + 1), 0.3, 32 * b)[i] for i in range(32)]
          for t in range(6)]
    trig = 0x3F if b % 25 == 0 else 0
    out, good, _ = block(e, xs, trig)
    okb &= good
    for t in range(6):
        ref = models[t].block(xs[t], trig >> t & 1, *cases[t])
        err[t] = max(err[t], max(abs(a - r) for a, r in zip(out[t], ref)))
chk('Modell: max. Abweichung %s (< 3e-4; Extremfall Cutoff 0 + volle Resonanz + Env < 5e-3)' % ', '.join('%.1e' % x for x in err),
    max(err[:5]) < 3e-4 and err[5] < 5e-3)
chk('Register / MACSR / Akkus in allen Bloecken', okb)


# ---------------- 1b2 Huellkurve ueber 127 hinaus: Filter bleibt an (v2: Ab- und Wiedereinschalten = Klicken)
e = emu(); mdl = Model()
for t in range(6): setp(e, t)
setp(e, 0, 0x6000, 0x4000, 0x7F00, 0x3000)
onf = []; jump = 0.0; prev = None; errc = 0.0
for b in range(60):
    xs = [sine(220, 0.5, 32 * b)] + [[0.0] * 32] * 5
    out, good, _ = block(e, xs, trig=1 if b in (0, 30) else 0)
    ref = mdl.block(xs[0], 1 if b in (0, 30) else 0, 0x6000, 0x4000, 0x7F00, 0x3000)
    errc = max(errc, max(abs(a_ - r_) for a_, r_ in zip(out[0], ref)))
    onf.append(e.r32(G.M_ST + 12))
    for v in out[0]:
        if prev is not None: jump = max(jump, abs(v - prev))
        prev = v
chk('Cutoff 96 + Env +63: Filter bleibt an %s, keine Spruenge (max. Schritt %.3f, Sinus 220 Hz: %.3f), Modell %.1e'
    % (set(onf), jump, 0.5 * 2 * math.pi * 220 / 48000 * 1.1, errc), set(onf) == {1} and jump < 0.5 * 2 * math.pi * 220 / 48000 * 1.5
    and errc < 3e-4)

# ---------------- 1b3 Cutoff 127 <-> 126 (an / aus) mit lautem Signal: ueberblendet, kein Sprung
e = emu(); mdl = Model()
for t in range(6): setp(e, t)
jump = 0.0; prev = None; errx = 0.0; nseen = set()
for b in range(120):
    cut = 0x7E00 if (b // 15) % 2 else G.TOP
    setp(e, 0, cut, 0x7F00)
    xs = [sine(3000, 0.95, 32 * b)] + [[0.0] * 32] * 5
    out, good, _ = block(e, xs)
    ref = mdl.block(xs[0], 0, cut, 0x7F00, 0x4000, 0x4000)
    errx = max(errx, max(abs(a_ - r_) for a_, r_ in zip(out[0], ref)))
    nseen.add(e.r32(G.M_ST + G.T_N))
    for i, v in enumerate(out[0]):
        if prev is not None: jump = max(jump, abs(v - prev))
        prev = v
dmax = 0.95 * 2 * math.pi * 3000 / 48000
chk('Cutoff 127 <-> 126, Reso 127, Sinus 3 kHz 0.95: groesster Schritt %.3f (Sinus selbst %.3f), Modell %.1e, n %s'
    % (jump, dmax, errx, sorted(nseen)), jump < dmax * 1.3 and errx < 3e-4 and nseen == set(range(9)))
setp(e, 0, G.TOP, 0x7F00)
for b in range(9): block(e, [sine(3000, 0.95, 32 * b)] + [[0.0] * 32] * 5)
xs = [sine(3000, 0.95, 32 * 9)] + [[0.0] * 32] * 5; block(e, xs)
chk('nach dem Ausblenden (8 Bloecke) wieder bitgenau, Zustand vergessen', bytes(e.u.mem_read(TRK, 128)) ==
    struct.pack('>32i', *[q31(x) for x in xs[0]]) and e.r32(G.M_ST + 12) == 0 and e.r32(G.M_ST + G.T_N) == 0)

# ---------------- 1c Frequenzgang (kleiner Pegel: Saettigung vernachlaessigbar)
def gain(cut, res, f, amp=0.05, nb=60):
    e = emu()
    for t in range(6): setp(e, t)
    setp(e, 0, cut, res)
    pk = 0.0
    for b in range(nb):
        xs = [sine(f, amp, 32 * b)] + [[0.0] * 32] * 5
        out, _, _ = block(e, xs)
        if b >= nb // 2: pk = max(pk, max(abs(v) for v in out[0]))
    return 20 * math.log10(pk / amp)


cw = 0x4000
fc = G.cutoff_hz(cw)
g_lo, g_c, g_hi = gain(cw, 0, fc / 8), gain(cw, 0, fc), gain(cw, 0, fc * 4)
chk('Cutoff 64 = %.0f Hz, Reso 0 (Q 0.5): unten %.1f dB, bei fc %.1f dB (-6), 4 fc %.1f dB (~ -24)' % (fc, g_lo, g_c, g_hi),
    abs(g_lo) < 0.3 and abs(g_c + 6.0) < 0.6 and -27 < g_hi < -21)
for cw2, rq in ((0x4000, 0x5A00), (0x4000, 0x7F00), (0x7000, 0x7F00), (0x7800, 0x7F00), (0x0400, 0x7F00)):
    f2 = G.cutoff_hz(cw2); q = min(G.q_of(rq), G.q_cap(f2))
    g_q = gain(cw2, rq, f2, amp=0.01, nb=max(60, int(2 * 48000 / f2 / 32)))
    chk('Cutoff %d (%.0f Hz), Reso %d: Q %.2f, bei fc %.1f dB (erwartet %.1f)' % (cw2 >> 8, f2, rq >> 8, q, g_q, 20 * math.log10(q)),
        abs(g_q - 20 * math.log10(q)) < 0.8)
# Resonanz wird mit dem Pegel weich begrenzt (keine harte Uebersteuerung)
gl = [gain(0x4000, 0x7F00, fc, amp=a_) for a_ in (0.01, 0.2, 0.5)]
chk('volle Resonanz bei 0.01 / 0.2 / 0.5: %.1f / %.1f / %.1f dB (wird mit dem Pegel kleiner, Ausgang < 1)' % tuple(gl),
    gl[0] > gl[1] > gl[2] and 0.5 * 10 ** (gl[2] / 20) < 0.99)

# ---------------- 1d Huellkurve (nur Spur 0)
e = emu()
for t in range(6): setp(e, t)
setp(e, 0, 0x2000, 0, 0x7F00, 0x3000)
st = S.get('state', None)
envs = []
for b in range(40):
    block(e, [[0.1] * 32] + [[0.0] * 32] * 5, trig=1 if b == 0 else 0)
    envs.append(e.r32(G.M_ST + 8))
m = lerp(DT, 0x3000)
chk('Huellkurve: Trig = 1, dann pro Block * %.4f (tau %.0f ms)' % (m, 1000 * G.tau_of(0x3000)),
    envs[0] == 0x7FFFFFFF and all(abs(envs[i + 1] / 2 ** 31 - envs[i] / 2 ** 31 * m) < 1e-6 for i in range(30) if envs[i + 1]))
chk('Huellkurve laeuft auf 0 aus', Model() and envs[-1] < envs[10])

# ---------------- 1e Stabilitaet: volle Resonanz, tiefer Cutoff, Rechteck mit Vollaussteuerung, dann Stille
e = emu()
for t in range(6): setp(e, t, 0x1000 + 0x1200 * t, 0x7F00)
mx = 0.0; fin = True
for b in range(200):
    xs = [[(1.0 if ((32 * b + i) // 50) % 2 else -1.0) * 0.999 for i in range(32)] for _ in range(6)]
    out, good, _ = block(e, xs)
    mx = max(mx, max(max(abs(v) for v in o) for o in out))
for b in range(1500):
    out, good, _ = block(e, [[0.0] * 32] * 6)
tail = max(max(abs(v) for v in o) for o in out)
chk('Volle Resonanz + Vollaussteuerung: begrenzt (max %.3f), klingt aus (Rest nach 1 s %.1e)' % (mx, tail), mx <= 1.0 and tail < 1e-3)
e = emu()
for t in range(6): setp(e, t, 0x1000 + 0x1200 * t, 0x4000)
for b in range(50): block(e, [sine(300, 0.9, 32 * b)] * 6)
for b in range(600): out, good, _ = block(e, [[0.0] * 32] * 6)
tail = max(max(abs(v) for v in o) for o in out)
states = [struct.unpack('>4i', bytes(e.u.mem_read(G.M_ST + TS * t, 16))) for t in range(6)]
chk('Ruhe: Zustand geloescht, Block bleibt 0', all(s[0] == 0 and s[1] == 0 for s in states) and tail == 0)

# ---------------- 1f Kosten: alle 6 Spuren aktiv
e = emu()
for t in range(6): setp(e, t, 0x3000, 0x4000, 0x6000, 0x4000)
_, _, nf = block(e, [[0.3] * 32] * 6, trig=0x3F, count=True)       # Einblenden
for b in range(10): block(e, [sine(200, 0.4, 32 * b)] * 6)
_, _, n = block(e, [sine(200, 0.4, 32)] * 6, count=True)
print('     Kosten beim Ueberblenden (alle 6 Spuren gleichzeitig): %d Befehle' % nf)
e2 = emu()
for t in range(6): setp(e2, t)
_, _, n0 = block(e2, [sine(200, 0.4, 32)] * 6, count=True)
print('     Kosten: %d Befehle pro Block (6 Spuren an), %d (alle aus); Block = ~166000 Takte' % (n, n0))
chk('Kosten < 7000 Befehle pro Block', n < 7000)

# ---------------- 2a Knopf-Zuordnung
e = emu()
e.u.hook_add(UC_HOOK_CODE, lambda u, a, z, _: (u.reg_write(mk.UC_M68K_REG_D0, 77),
                                               u.reg_write(mk.UC_M68K_REG_PC, e.r32(u.reg_read(mk.UC_M68K_REG_A7))),
                                               u.reg_write(mk.UC_M68K_REG_A7, u.reg_read(mk.UC_M68K_REG_A7) + 4)),
             begin=G.KNOB_ORIG, end=G.KNOB_ORIG)
chk('Vtable-Slot 124 -> KNOB', e.r32(G.KNOB_SLOT) == S['KNOB'])
off = [e.call(S['KNOB'], 0x4F042000, k, 0, -1)[0] for k in range(16)]
e.w32(G.MODE, G.MAGIC)
on = [e.call(S['KNOB'], 0x4F042000, k, f, -1)[0] for k in range(16) for f in (0, 1)]
chk('Modus aus: immer die Firmware-Suche', off == [77] * 16)
chk('Modus an: PITCH 1 Cutoff, DECAY 4 Decay, COLOR 2 Reso, SHAPE 3 Env; Rest Firmware',
    on[4:12] == [1, 1, 4, 4, 2, 2, 3, 3] and all(v == 77 for i, v in enumerate(on) if not 4 <= i < 12))
chk('UI-Objekte 1..4: Formatierer INT, INT, OFF, INT; keine Sonderzeichnung',
    [e.r32(G.REC + 100 * i + 0x20) for i in range(1, 5)] == [G.FMT_INT, G.FMT_INT, G.FMT_OFF, G.FMT_INT] and
    all(e.r32(G.REC + 100 * i + 0x2C) == 0 for i in range(1, 5)))
_, good = e.call(S['KNOB'], 0x4F042000, 3, 0, -1)
chk('KNOB: Register + Stack', good)

# ---------------- 2b Filter-Modus: RETRIG + GATE an, RETRIG aus
e = emu(); acts = []
e.u.hook_add(UC_HOOK_CODE, lambda u, a, z, _: (acts.append((e.r32(u.reg_read(mk.UC_M68K_REG_A7) + 4),
                                                            e.r32(u.reg_read(mk.UC_M68K_REG_A7) + 8))),
                                               u.reg_write(mk.UC_M68K_REG_PC, e.r32(u.reg_read(mk.UC_M68K_REG_A7))),
                                               u.reg_write(mk.UC_M68K_REG_A7, u.reg_read(mk.UC_M68K_REG_A7) + 4)),
             begin=G.CLICK_ACT, end=G.CLICK_ACT)
chk('Haken 0x4001ca9c = jsr KEYH ; 3 nop', IMG[G.KEY_HOOK - BASE:][:12] == C.jsr(S['KEYH']) + b'\x4e\x71' * 3)
chk('Haken 0x4001c4ba = jmp RT ; nop', IMG[G.RT_HOOK - BASE:][:8] == C.jmp(S['RT']) + b'\x4e\x71')
VIEW, EV = 0x4F043000, 0x4F043100
t0 = [100]
def popup(): return e.cstr(e.r32(C.VARS + C.V_VAL)) if e.r32(C.VARS + C.V_VAL) else ''
def gate(held=()):
    e.held = set(held); e.w32(C.VARS + C.V_VAL, 0); n = len(acts)
    _, good = e.call(S['KEYH'], regs={mk.UC_M68K_REG_A2: VIEW})
    return good, e.r32(G.MODE) == G.MAGIC, len(acts) - n, popup()
def retrig(bits):
    """echter Fall RETRIG im Hauptbildschirm ab 0x4001c4ba (d3 = Ereignis), Halt in 0x4001c4c2 (nach den verschobenen
    Befehlen: Ereignis gepusht, FUNC-Abfrage der Firmware gelaufen)"""
    e.w32(EV + 0x10, bits); e.w32(C.VARS + C.V_VAL, 0)
    sp = STACK - 0x300; e.u.reg_write(mk.UC_M68K_REG_A7, sp); e.u.reg_write(mk.UC_M68K_REG_D3, EV)
    for i, r in enumerate(KEEP): 
        if r != mk.UC_M68K_REG_D3: e.u.reg_write(r, 0xC0DE0000 + i)
    e.u.emu_start(G.RT_HOOK, 0x4001C4C2, count=20000)
    good = (e.u.reg_read(mk.UC_M68K_REG_PC) == 0x4001C4C2 and e.u.reg_read(mk.UC_M68K_REG_A7) == sp - 4 and e.r32(sp - 4) == EV
            and all(e.u.reg_read(r) == 0xC0DE0000 + i for i, r in enumerate(KEEP) if r != mk.UC_M68K_REG_D3)
            and e.u.reg_read(mk.UC_M68K_REG_D0) & 0xff == (bits >> 1) & 1)
    return good, e.r32(G.MODE) == G.MAGIC, popup()
r = gate()
chk('GATE allein: macht was GATE immer macht (this, 0x2d), kein Modus', r[0] and not r[1] and r[2] == 1 and acts[-1] == (VIEW, 0x2D))
q1 = retrig(1); q2 = retrig(0)
chk('RETRIG antippen (Modus aus): nichts, Firmware-Weg unveraendert', q1[0] and q2[0] and not q2[1] and q2[2] == '')
retrig(1); r = gate((G.KEY_RETRIG,)); q = retrig(0)
chk('RETRIG halten + GATE: Modus an, Popup FILTER ON, GATE nicht umgeschaltet; Loslassen: bleibt an',
    r[0] and r[1] and r[2] == 0 and r[3] == 'ON' and e.cstr(e.r32(C.VARS + C.V_L1)) == 'FILTER' and q[0] and q[1])
r = gate()
chk('GATE allein im Modus: GATE wie immer, Modus bleibt', r[1] and r[2] == 1)
q = retrig(1 | 2); q2 = retrig(0 | 2)
chk('FUNC + RETRIG: Modus bleibt', q[0] and q2[0] and q2[1])
q = retrig(1); q2 = retrig(1 | 8); q3 = retrig(0)
chk('RETRIG antippen im Modus (mit Wiederholung): beim Loslassen aus, Popup FILTER OFF', q[0] and q[1] and q2[1] and q3[0] and not q3[1]
    and q3[2] == 'OFF')
retrig(1); gate((G.KEY_RETRIG,)); retrig(0)                      # wieder an
q = retrig(1)
res = e.enc(10, 1, held={G.KEY_RETRIG})
q2 = retrig(0)
chk('RETRIG halten + Knopf drehen (LFO SPEED): Drehung geht an die Firmware, Loslassen: Modus bleibt an',
    res['passed'] == 1 and res['regs'] and res['sp'] and q2[0] and q2[1])
q = retrig(1); res = e.enc(10, 1, held=set()); q2 = retrig(0)
chk('Knopf ohne gehaltenes RETRIG zaehlt nicht: Antippen beendet', not q2[1])
retrig(1); gate((G.KEY_RETRIG,)); retrig(0)
q = retrig(1); r = gate((G.KEY_RETRIG,)); q2 = retrig(0)
chk('RETRIG + GATE im Modus: bleibt an', r[1] and q2[1])
# ---------------- 2c Speichern / Laden (echte Funktionen)
e = emu()
SND, REC1, SND2 = 0x4F044000, 0x4F045000, 0x4F046000
def run_save(fn, snd, rec):
    _, good = e.call(fn, rec, snd, count=200000); return good
snd = bytearray(rnd.getrandbits(8) for _ in range(256))
for k in range(23): snd[20 + 2 * k:22 + 2 * k] = struct.pack('>H', rnd.randrange(0, 0x7F01))
for k, v in ((28, 0x2300), (29, 0x5600), (30, 0x1200), (31, 0x6A00)): snd[20 + 2 * k:22 + 2 * k] = struct.pack('>H', v)
snd[28] = 30; snd[88:92] = struct.pack('>I', 31)          # LFO -> Env, Velocity -> Decay
res = {}
for nm, fn in (('v2', G.SV2_HOOK), ('v1', G.SV1_HOOK)):
    e.u.mem_write(SND, bytes(snd)); e.u.mem_write(REC1, bytes(256))
    ok1 = run_save(fn, SND, REC1)
    rec = bytes(e.u.mem_read(REC1, 128))
    e.u.mem_write(SND2, bytes(256))
    _, ok2 = e.call(G.LD_HOOK, SND2, REC1, count=200000)
    back = bytes(e.u.mem_read(SND2, 128))
    res[nm] = (ok1, ok2, rec, back)
    w = lambda b, k: struct.unpack('>H', b[20 + 2 * k:22 + 2 * k])[0]
    chk('Speichern %s + Laden: k28..31 = %s' % (nm, [hex(w(back, k)) for k in range(28, 32)]),
        ok1 and ok2 and [w(back, k) for k in range(28, 32)] == [0x2300, 0x5600, 0x1200, 0x6A00])
    chk('  LFO-Ziel %d, Velocity-Ziel %d zurueck; k0 = 0' % (back[28], struct.unpack('>I', back[88:92])[0]),
        back[28] == 30 and struct.unpack('>I', back[88:92])[0] == 31 and w(back, 0) == 0)
# Gleiches mit der Stock-Firmware: Satz ohne unsere Plaetze identisch
es = Emu(STOCK)
es.u.mem_write(SND, bytes(snd)); es.u.mem_write(REC1, bytes(256)); es.call(G.SV2_HOOK, REC1, SND, count=200000)
srec = bytes(es.u.mem_read(REC1, 128))
mine = res['v2'][2]
diff = [i for i in range(128) if srec[i] != mine[i]]
chk('Satz wie Stock bis auf +64/65, +82/83, +88..91 (+84 lfo-amount) (Unterschiede an %s)' % diff,
    set(diff) <= {64, 65, 82, 83, 88, 89, 90, 91} | ({84} if not ALONE else set()))
# alter Satz (Plaetze 0): Filter offen, Env / Decay Mitte
e.u.mem_write(REC1, srec); e.u.mem_write(SND2, bytes(256)); e.call(G.LD_HOOK, SND2, REC1, count=200000)
back = bytes(e.u.mem_read(SND2, 128))
chk('alter Sound (Stock gespeichert): Cutoff 127, Reso 0, Env Mitte, Decay 64',
    [struct.unpack('>H', back[20 + 2 * k:22 + 2 * k])[0] for k in range(28, 32)] == [0x7F00, 0, 0x4000, 0x4000])
es.u.mem_write(SND2, bytes(256)); es.call(G.LD_HOOK, SND2, REC1, count=200000)
sback = bytes(es.u.mem_read(SND2, 128))
chk('  sonst wie Stock geladen', all(sback[i] == back[i] for i in range(128) if not 76 <= i < (84 if ALONE else 86) and i not in (20, 21)))

# ---------------- 2d p-locks: Index -> k (echte 0x4005aa1a), k -> Index (PTAB)
e = emu(); es = Emu(STOCK)
FN = 0x4005AA1A
bad = []
for t in list(range(6)) + [6, 7]:
    for i in range(0, 40):
        a_, _ = e.call(FN, t, i); b_, _ = es.call(FN, t, i)
        want = b_ if (t > 5 or i <= 23) else (i - 1 if i <= 33 else 0)
        if a_ != want: bad.append((t, i, a_, want))
chk('Index -> k (Core): 0..23 wie Stock, 24..33 -> 23..32, sonst 0; andere Tracks wie Stock %s' % bad[:3], not bad)
PT = V2SYM['core']['PTAB']
pt = struct.unpack('>33I', bytes(e.u.mem_read(PT, 132)))
chk('PTAB (Core): 0..22 wie Firmware-Tabelle, 23..32 -> 24..33',
    list(pt[:23]) == list(struct.unpack('>23I', STOCK[G.PTAB_ORIG - BASE:][:92])) and list(pt[23:]) == list(range(24, 34)))
chk('beide Verweise auf PTAB', all(e.r32(v) == PT for v in G.PTAB_REFS))
chk('Hin und zurueck: k 23..32 -> Index -> k', all(e.call(FN, 2, pt[k])[0] == k for k in range(23, 33)))

# ---------------- 2e Deskriptoren
rows = [struct.unpack('>14I', IMG[C.DESC(i) - BASE:][:0x38]) for i in range(1, 5)]
names = [(e.cstr(r[11]), e.cstr(r[12]), e.cstr(r[13])) for r in rows]
print('     ', names)
chk('Deskriptoren 1..4: Gruppe 7, k 28..31, 0..0x7f00, LFO/Velocity, Amp',
    all(r[0] == 7 and r[1] == 28 + i and r[3] == 0x7F00 and r[9] == 0x600 and r[12] == G.AMP for i, r in enumerate(rows)))
chk('Defaults: Cutoff 127, Reso 0, Env Mitte, Decay 64', [r[4] for r in rows] == [0x7F00, 0, 0x4000, 0x4000])
e5 = Emu(IMG); e5.call(0x4005A274, count=5000000); okn = True
for mach in range(6):
    e5.u.mem_write(0x4F044000, bytes(256)); e5.call(0x40061866, 0x4F044000, 0, mach, count=2000000)
    okn &= [struct.unpack('>H', bytes(e5.u.mem_read(0x4F044000 + 20 + 2 * k, 2)))[0] for k in range(28, 32)] == [0x7F00, 0, 0x4000, 0x4000]
chk('neuer Sound (Firmware-Init, alle 6 Maschinen): Cutoff 127, Reso 0, Env Mitte, Decay 64', okn)
done()
