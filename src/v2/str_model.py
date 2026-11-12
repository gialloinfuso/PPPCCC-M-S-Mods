"""Ganzzahl-Modell der Maschine 'Strng' (g2_strings): dieselben Schritte wie der Code, EMAC fraktional mit 8 Schutzbits
(mac: Akku += a * b >> 23, movclr: >> 8 gesaettigt). Fuer die Tests (bitgenau bis auf Rundung mehrerer Produkte)."""
import math, struct
import g2_strings as G
import g2_sampler as SM
import common as C

M = 0xFFFFFFFF


def s32(x):
    x &= M
    return x - (1 << 32) if x & 0x80000000 else x


def sat(v):
    return max(-0x80000000, min(0x7FFFFFFF, v))


class Acc:
    def __init__(s): s.v = 0
    def load(s, r): s.v = s32(r) << 8
    def mac(s, a, b): s.v += (s32(a) * s32(b)) >> 23
    def msac(s, a, b): s.v -= (s32(a) * s32(b)) >> 23
    def clr(s):
        r = sat(s.v >> 8); s.v = 0; return r


def tabs():
    t = G.tables()
    u = lambda nm: list(struct.unpack('>%dI' % (len(t[nm]) // 4), t[nm]))
    return {k: u(k) for k in t}


class Voice:
    def __init__(s, stock, track=0):
        s.T = tabs(); s.stock = stock; s.track = track
        s.blk = 0xFFFF
        s.osc = []
        for j in range(4):
            p = (j * 0x5D000000) & M
            s.osc.append(dict(P=p ^ 0x80000000, INC=0, KINV=0, PREV=0, PEND=0, G=0, DG=0, TG=0))
            s.osc.append(dict(P=((2 * p) & M) ^ 0x80000000, INC=0, KINV=0, PREV=0, PEND=0, G=0, DG=0, TG=0))
        s.hplp = s.ic1 = s.ic2 = 0
        s.fa = (0, 0, 0)
        s.W = 0; s.ph1 = s.ph2 = 0
        d0 = G.KW['D0Q']; s.dc = [d0, d0, d0]; s.di = [0, 0, 0]; s.dt = [0, 0, 0]
        s.wg = s.dry = 0; s.ens = 0
        s.ring = [0] * G.NRING
        s.nn = 0
        s.perm = [0, 0, 0, 0]              # T_PERM (Zustand leer)
        s.env = [0] * 4; s.stg = [0] * 4   # smp24: Huellkurve / Stufe je Ton

    def r32(s, va): return struct.unpack('>I', s.stock[va - G.BASE:va - G.BASE + 4])[0]

    # ---------------- update
    def update(s, par, pmod, trig, tempo=14400, perm=None):
        """par: dict k -> Wort (Slots 10..18, Strum 24 / 27). perm: Raenge fuer RND (sonst aus dem Pattern)"""
        if trig:
            s.blk = 0
            s.stg = [0] * 4
            p = (par.get(C.K_SPAT, 0) >> 8) & 0xFF
            if p > len(C.STRUM_PATS) - 1: p = 0
            if p == C.STRUM_RND:
                assert perm is not None, 'RND: Raenge angeben'
                s.perm = list(perm)
            else:
                s.perm = list(C.STRUM_RANKS[p])
        elif s.blk < 0xFFFF: s.blk += 1
        inc0 = s.pitch(par, pmod)
        dec = (par[18] >> 8) & 0xFF
        dec = dec - 256 if dec > 127 else dec
        s.m = s.r32(SM.DECLUT + 4 * dec)                       # Faktor der Firmware (SUPD8 -> Stimme +0x250)
        s.atk = (par.get(C.K_EXT0, 0) >> 8) & 0xFF
        s.chord(par, inc0, C.strum_step8((par.get(C.K_STIME, 0) >> 8) & 0xFF, tempo))
        s.filt(par)
        s.ensu(par)

    def pitch(s, par, pmod):
        d0 = ((s32(par[10]) & 0xFFFF) - 0x4000) << 8
        d0 += (((par[17]) & 0xFFFF) - 0x4000) << 3
        d0 += pmod
        d0 = max(G.NLO << 16, min(G.NHI << 16, d0))
        octv, rem = divmod(d0, 12 << 16)
        semi, frac = rem >> 16, rem & 0xFFFF
        p12 = s.T['P12']
        r = p12[semi] + ((((p12[semi + 1] - p12[semi]) * frac) & M) >> 16)
        x = (G.KW['INC0'] << octv) & M
        return s.mul16(x, r)

    @staticmethod
    def mul16(x, r):
        hi = ((x >> 16) * r) & M
        lo = ((((x & 0xFFFF) * r) & M) >> 16)
        return (hi + lo) & M

    def chord(s, par, inc0, sp):
        sh = (par[12] >> 8) & 0xFF
        sh = min(sh, G.NCHORD - 1)
        if sh <= 2:
            rat = s.T['UNIT'][4 * sh:4 * sh + 4]; n = 1 << sh
        else:
            rat = [s.r32(G.CH_TAB + 16 * sh + 4 * i) for i in range(4)]; n = 4
        s.nn = n
        rat = [r >> 10 for r in rat]
        c = (par[11] >> 8) & 0xFF
        g8, g4 = s.T['COLT'][2 * c], s.T['COLT'][2 * c + 1]
        gn = s.T['GNT'][n]
        a = Acc(); a.mac(g8, gn); g8 = a.clr() & M; a.mac(g4, gn); g4 = a.clr() & M
        for j in range(4):
            o8, o4 = s.osc[2 * j], s.osc[2 * j + 1]
            if j >= n:
                o8['TG'] = 0; o4['TG'] = 0; s.env[j] = 0; s.stg[j] = 0
            else:
                inc = s.mul16(inc0, rat[j])
                inc = min(inc, G.INCMAX)
                o8['INC'] = inc; o8['KINV'] = M // (inc >> 16)
                inc4 = (2 * inc) & M
                o4['INC'] = inc4; o4['KINV'] = M // (inc4 >> 16)
                r = s.ramp(j, n, sp)
                a.mac(g8, r); o8['TG'] = a.clr() & M
                a.mac(g4, r); o4['TG'] = a.clr() & M
            for o in (o8, o4):
                o['DG'] = (s32(o['TG']) - s32(o['G'])) >> 5 & M

    def ramp(s, j, n, sp):
        """smp24: Huellkurve von Ton j (Attack k 23, Decay mit dem Faktor der Firmware), Einsatz = (Rang x sp) >> 3"""
        rank = sum(1 for i in range(n) if s.perm[i] < s.perm[j])
        on = ((rank * sp) & M) >> 3
        d = s.blk - on
        if d < 0:
            e = s.env[j] - (s.env[j] >> 2); s.env[j] = e if e >= C.STRUM_FADE_MIN else 0   # smp39: ausblenden statt 0
            s.stg[j] = 0; return s.env[j]
        if s.stg[j]:
            f = (-s.m) & M; e = s.env[j]
            eh, el, fh, fl = e >> 16, e & 0xFFFF, f >> 16, f & 0xFFFF
            e = ((((eh * fl + el * fh) & M) >> 15) + 2 * eh * fh) & M
            s.env[j] = e
            return min(e, 0x7FFFFFFF)
        full = False
        if s.atk == 0:
            if on == 0 or d >= 2: full = True
            else: s.env[j] = 0x20000000 if d == 0 else 0x40000000
        else:
            dd = s.atk * s.atk * 96000 // 16129
            if dd < 32: full = True
            else:
                x = s.env[j] + (((1 << 31) // dd) << 5 & M)
                if x >= 1 << 31: full = True
                else: s.env[j] = x
        if full:
            s.env[j] = 1 << 31; s.stg[j] = 2; return 0x7FFFFFFF
        return s.env[j]

    def filt(s, par):
        sw = (par[13] >> 8) & 0xFF
        s.fa = tuple(s.T['SVFT'][3 * sw:3 * sw + 3])

    def sinq(s, ph):
        i = ph >> 24
        fr = ((ph << 8) & M) >> 1
        s0, s1 = s.T['SINT'][i], s.T['SINT'][i + 1]
        a = Acc(); a.load(s0); a.mac(fr, (s32(s1) - s32(s0)) & M)
        return a.clr() & M

    def ensu(s, par):
        c = (par[14] >> 8) & 0xFF
        wg, dry, am1, am2 = s.T['ENST'][4 * c:4 * c + 4]
        was = s.ens
        s.wg, s.dry, s.ens = wg, dry, wg
        if not (was | wg): return
        s.ph1 = (s.ph1 + G.KW['DPH1']) & M
        s.ph2 = (s.ph2 + G.KW['DPH2']) & M
        p1, p2 = s.ph1, s.ph2
        for i in range(3):
            x1 = s.sinq(p1); x2 = s.sinq(p2)
            a = Acc(); a.load(G.KW['D0Q']); a.mac(am1, x1); a.mac(am2, x2)
            t = a.clr()
            s.dt[i] = t & M
            s.di[i] = ((t - s32(s.dc[i])) >> 5) & M
            p1 = (p1 + 0x55555555) & M; p2 = (p2 + 0x55555555) & M

    # ---------------- render
    def render(s):
        buf = [0] * 32
        for o in s.osc: s.osc_block(o, buf)
        s.lpf(buf)
        if s.ens: s.ensb(buf)
        else:
            for i in range(32):
                a = Acc()
                for _ in range(4): a.mac(0x7FFFFFFF, buf[i])
                buf[i] = a.clr()
        return buf

    def osc_block(s, o, buf):
        g, dg = o['G'], o['DG']
        if g == 0 and dg == 0:
            q = (o['P'] + (o['INC'] << 5)) & M
            o['P'] = q; o['PREV'] = q; o['PEND'] = 0
            return
        q, inc, kinv, prev, pend = o['P'], o['INC'], o['KINV'], o['PREV'], o['PEND']
        def out(i, val, g):
            a = Acc(); a.mac(g, val); buf[i] = s32(buf[i] + a.clr())
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

    def lpf(s, buf):
        lp, k = s.hplp, G.KW['HPK']
        ic1, ic2 = s.ic1, s.ic2
        a1, a2, a3 = s.fa
        for i in range(32):
            x = s32(buf[i]) >> 1
            hp = s32(x - s32(lp))
            a = Acc(); a.load(lp); a.mac(k, hp); lp = a.clr()
            v3 = s32(hp - s32(ic2))
            a.mac(a1, ic1); a.mac(a2, v3); v1 = a.clr()
            b = Acc(); b.load(ic2); b.mac(a2, ic1); b.mac(a3, v3); v2 = b.clr()
            ic1 = s32(2 * v1 - s32(ic1)); ic2 = s32(2 * v2 - s32(ic2))
            buf[i] = v2
        s.hplp, s.ic1, s.ic2 = lp & M, ic1 & M, ic2 & M

    def ensb(s, buf):
        W = s.W; dc = list(s.dc); wg, dry = s.wg, s.dry
        for i in range(32):
            x = s32(buf[i])
            a2 = Acc()
            for _ in range(4): a2.mac(dry, x)
            s.ring[W >> 22] = x >> 1
            tot = 0; a1 = Acc()
            for t in range(3):
                pos = (W - dc[t]) & M
                idx = pos >> 22
                fr = ((pos << 10) & M) >> 1
                s0 = s.ring[idx]
                tot = s32(tot + s0)
                s1 = s.ring[(idx + 1) & (G.NRING - 1)]
                a1.mac(fr, (s1 - s0) & M)
            tot = s32(tot + a1.clr())
            for _ in range(4): a2.mac(wg, tot)
            buf[i] = a2.clr()
            W = (W + (1 << 22)) & M
            for t in range(3): dc[t] = (dc[t] + s.di[t]) & M
        s.W = W
        s.dc = list(s.dt)
