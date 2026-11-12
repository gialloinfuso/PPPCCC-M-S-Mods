"""Ganzzahl-Modell der Maschine 'mono' (g2_mono): dieselben Schritte wie der Code (EMAC fraktional mit 8 Schutzbits wie
str_model). Fuer die Tests (bitgleich) und Hoerbeispiele."""
import struct
import mono_tables as MT
from str_model import Acc, s32, sat, M

INC0 = int(round(2 ** 32 * 440 * 2 ** (-69 / 12) / 48000))
P12 = [int(round(65536 * 2 ** (i / 12))) for i in range(13)]
OSCF = ('P', 'INC', 'KINV', 'PREV', 'PEND', 'G', 'DG', 'TG')
K = MT.C


def tabs():
    t = MT.tables()
    return {k: list(struct.unpack('>%dI' % (len(v) // 4), v)) for k, v in t.items()}


def mac1(a, b):
    x = Acc(); x.mac(a, b); return x.clr()


def mul16(x, r):
    hi = ((x >> 16) * r) & M
    lo = (((x & 0xFFFF) * r) & M) >> 16
    return (hi + lo) & M


def inc_of(n):
    n = max(0, min(127 << 16, s32(n)))
    octv, rem = divmod(n, 12 << 16)
    semi, frac = rem >> 16, rem & 0xFFFF
    r = P12[semi] + ((((P12[semi + 1] - P12[semi]) * frac) & M) >> 16)
    x = (INC0 << octv) & M
    v = mul16(x, r)
    return min(v, 0x7FFFFFFF)


def osc_block(o, buf):
    """wie str_model.Voice.osc_block (gleicher Code in g2_mono)"""
    g, dg = o['G'], o['DG']
    if g == 0 and dg == 0:
        q = (o['P'] + (o['INC'] << 5)) & M
        o['P'] = q; o['PREV'] = q; o['PEND'] = 0
        return
    q, inc, kinv, prev, pend = o['P'], o['INC'], o['KINV'], o['PREV'], o['PEND']
    def out(i, val, g):
        buf[i] = s32(buf[i] + mac1(g, val))
    i = 0
    if pend:
        q = (q + inc) & M
        out(i, (prev + pend) & M, g); pend = 0; prev = q; g = (g + dg) & M; i += 1
    while i < 32:
        q2 = s32(q) + s32(inc)
        wrap = q2 > 0x7FFFFFFF or q2 < -0x80000000
        q = q2 & M
        if not wrap:
            out(i, prev, g); prev = q; g = (g + dg) & M; i += 1
            continue
        p = q ^ 0x80000000
        u = ((((p >> 16) * kinv) & M) >> 16)
        v = min(0x10000 - u, 0xFFFF)
        v2 = ((v * v) & M) >> 1
        u2 = ((u * u) & M) >> 1
        out(i, (prev - u2) & M, g); prev = q; g = (g + dg) & M; i += 1
        if i == 32:
            pend = v2; break
        q = (q + inc) & M
        out(i, (prev + v2) & M, g); prev = q; g = (g + dg) & M; i += 1
    o['P'], o['PREV'], o['PEND'] = q, prev, pend
    o['G'] = o['TG']


class Voice:
    def __init__(s, track=0):
        s.T = tabs()
        s.o = {nm: dict.fromkeys(OSCF, 0) for nm in ('A1', 'A2', 'S1', 'S2', 'SL', 'R2')}
        s.o['A1']['P'] = 0x12345678; s.o['S1']['P'] = 0x5A000000; s.o['R2']['P'] = 0x03000000
        s.rng = (0x2545F491 + track * 0x9E3779B9) & M
        s.cur = 0; s.init = True; s.rnd = 0
        s.ph = dict.fromkeys(('o1a', 'o1b', 'o2a', 'o2b', 'suba', 'subb', 'pwm'), 0)
        s.lp = s.dcx = s.dcy = 0
        s.wave = 0; s.par = {}

    def rand(s):
        s.rng = (s.rng * 1664525 + 1013904223) & M
        return s.rng

    def sinq(s, ph):
        i = ph >> 24
        fr = ((ph << 8) & M) >> 1
        s0, s1 = s.T['SINT'][i], s.T['SINT'][i + 1]
        a = Acc(); a.load(s0); a.mac(fr, (s32(s1) - s32(s0)) & M)
        return a.clr() & M

    def drift(s, nm):
        a = Acc()
        a.mac(s.sinq(s.ph[nm + 'a']), K[f'D{nm}A']); a.mac(s.sinq(s.ph[nm + 'b']), K[f'D{nm}B'])
        return a.clr()

    # ---------------- update (Parameter-Worte k -> Wert)
    def update(s, par, pmod, trig):
        T = s.T
        if trig:
            r = s.rand() >> 16
            s.rnd = ((r * K['RNDK']) >> 16) - (K['RNDK'] >> 1)
        n = ((par[10] & 0xFFFF) - 0x4000 << 8) + (((par[17] & 0xFFFF) - 0x4000) << 3) + s32(pmod)
        tgt = max(12 << 16, min(108 << 16, n))
        g = (par.get(24, 0) >> 8) & 0xFF
        if s.init or g == 0:
            s.cur = tgt
        else:
            a = Acc(); a.load(s.cur); a.mac(T['GLT'][g], (tgt - s.cur) & M); s.cur = a.clr()
        s.init = False
        for nm in ('o1', 'o2', 'sub'):
            s.ph[nm + 'a'] = (s.ph[nm + 'a'] + K[f'R{nm}A']) & M
            s.ph[nm + 'b'] = (s.ph[nm + 'b'] + K[f'R{nm}B']) & M
        s.ph['pwm'] = (s.ph['pwm'] + K['DPWM']) & M
        base = s.cur + s.rnd
        d1, d2, ds = s.drift('o1'), s.drift('o2'), s.drift('sub')
        w = min(7, ((par[11] & 0xFFFF) + 0x80) >> 8)
        sh = (par[12] >> 8) & 0x7F
        s.wave, s.sh = w, sh
        inc1 = inc_of(base + d1)
        A1, A2, S1, S2, SL, R2 = (s.o[x] for x in ('A1', 'A2', 'S1', 'S2', 'SL', 'R2'))
        def setinc(o, inc):
            o['INC'] = inc; o['KINV'] = M // (inc >> 16)
        setinc(A1, inc1)
        A1['TG'] = K['G0'] if w not in (4, 5) else 0
        A2['TG'] = 0
        if w in (1, 2, 3):
            setinc(A2, inc1)
            if w == 1:
                off = (0x80000000 - sh * K['PWK']) & M; A2['TG'] = K['MG0']
            elif w == 2:
                off = ((0x80000000 - sh * K['PCK']) + mac1(s.sinq(s.ph['pwm']), K['PWMD'])) & M
                off = max(0x0CCCCCCD, min(0xF3333333, off))
                A2['TG'] = K['MG0']
            else:
                off = 0x80000000; A2['TG'] = (-(sh * K['SUBK'])) & M
            A2['P'] = (A1['P'] + off) & M
        elif w == 6:
            setinc(A2, inc_of(base + d2 + sh * 155)); A2['TG'] = K['G0']
        elif w == 5:
            setinc(SL, min(mul16(inc1, 65536 + 3612 * sh), 0x7FFFFFFF))
        elif w == 7:
            R2['INC'] = mul16(inc_of(base + d2), 32768 + 1806 * sh)
        setinc(S1, inc_of(base - (12 << 16) + ds)); setinc(S2, S1['INC'])
        S2['P'] = (S1['P'] + 0x80000000) & M
        sub = ((par[13] >> 8) & 0x7F) * K['SUBK']
        S1['TG'] = sub; S2['TG'] = (-s32(sub)) & M
        for o in (A1, A2, S1, S2):
            o['DG'] = ((s32(o['TG']) - s32(o['G'])) >> 5) & M
        s.lpc = T['SAWLP'][sh] if w == 0 else K['WARM']
        s.nl = K['NFL'] + ((par.get(27, 0) >> 8) & 0x7F) * K['NOK']
        c = (par[14] >> 8) & 0x7F
        s.dg8, s.mk = T['DRVT'][2 * c], T['DRVT'][2 * c + 1]
        s.g88 = 256 + 4 * sh

    # ---------------- render
    def render(s):
        T = s.T; w = s.wave
        buf = [0] * 32
        A1, A2, S1, S2, SL, R2 = (s.o[x] for x in ('A1', 'A2', 'S1', 'S2', 'SL', 'R2'))
        if w == 4:
            q, inc = A1['P'], A1['INC']
            for i in range(32):
                q = (q + inc) & M
                d = s32(q)
                if d < 0: d = ~d
                tri = s32((d << 1) - 0x7FFFFFFF)
                ph = ((((tri >> 11) * s.g88) & M) << 2) & M
                buf[i] = s32(buf[i] + mac1(K['G0'], s.sinq(ph)))
            A1['P'] = q
        elif w == 5:
            s.sync(buf)
        elif w == 7:
            tmp = [0] * 32
            osc_block(A1, tmp)
            q = R2['P']
            for i in range(32):
                q = (q + R2['INC']) & M
                buf[i] = s32(buf[i] + mac1(tmp[i], s.sinq(q)))
            R2['P'] = q
        else:
            osc_block(A1, buf)
        osc_block(A2, buf)
        osc_block(S1, buf); osc_block(S2, buf)
        return s.out(buf)

    def sync(s, buf):
        A1, SL = s.o['A1'], s.o['SL']
        q1, inc1, kinv1 = A1['P'], A1['INC'], A1['KINV']
        qs, incs, kinvs = SL['P'], SL['INC'], SL['KINV']
        prev, pend = SL['PREV'], SL['PEND']
        g2 = (2 * s32(K['G0'])) & M
        for i in range(32):
            t = s32(q1) + s32(inc1); mw = not -0x80000000 <= t <= 0x7FFFFFFF; q1 = t & M
            t = s32(qs) + s32(incs); sw = not -0x80000000 <= t <= 0x7FFFFFFF; qs = t & M
            val = s32(prev + pend); pn = 0
            if sw:
                u = ((((qs ^ 0x80000000) >> 16) * kinvs) & M) >> 16
                v = min(0x10000 - u, 0xFFFF)
                val = s32(val - (((u * u) & M) >> 2)); pn = s32(pn + (((v * v) & M) >> 2))
            if mw:
                u = ((((q1 ^ 0x80000000) >> 16) * kinv1) & M) >> 16
                us = ((incs >> 16) * u) & M
                vb = s32(qs - us)
                qn = (0x80000000 + us) & M
                dh = s32((s32(qn) >> 1) - (vb >> 1))
                v = min(0x10000 - u, 0xFFFF)
                u2 = ((u * u) & M) >> 1; v2 = ((v * v) & M) >> 1
                val = s32(val + mac1(dh, u2)); pn = s32(pn - mac1(dh, v2))
                qs = qn
            prev = s32(qs) >> 1; pend = pn
            buf[i] = s32(buf[i] + mac1(g2, val))
        A1['P'] = q1; SL['P'], SL['PREV'], SL['PEND'] = qs, prev & M, pend & M

    def out(s, buf):
        T = s.T; o = []
        lp, dcx, dcy = s32(s.lp), s32(s.dcx), s32(s.dcy)
        for i in range(32):
            xh = s32(buf[i]) >> 1
            xh = s32(xh + (mac1(s.nl, s.rand()) >> 1))
            a = Acc(); a.load(lp); a.mac(s.lpc, (xh - lp) & M); lp = a.clr()
            a.load(K['BIAS8']); a.mac(s.dg8, lp); a.mac(s.dg8, lp); z = a.clr()
            u = (z + 0x80000000) & M
            idx = u >> 24; fr = ((u << 8) & M) >> 1
            t0, t1 = T['TANH'][idx], T['TANH'][idx + 1]
            a.load(t0); a.mac(fr, (s32(t1) - s32(t0)) & M); t = a.clr()
            yh = s32((t >> 1) - (s32(K['TB']) >> 1))
            oh = mac1(s.mk, yh)
            a.load((oh - dcx) & M); a.mac(K['DCR'], dcy); y = a.clr()
            dcx, dcy = oh, y
            a.mac(0x7FFFFFFF, y); a.mac(0x7FFFFFFF, y); o.append(a.clr())
        s.lp, s.dcx, s.dcy = lp & M, dcx & M, dcy & M
        return o
