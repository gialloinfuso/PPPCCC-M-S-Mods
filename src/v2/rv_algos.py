"""Hall / Room / Plate fuer den Reverb-Platz (smp9, Pip 02.11.2026: "drei Reverbs: Hall, Room, Plate").
Eigene Algorithmen im Stil der Dragonfly Reverbs (Michael Willis, GPL-3: kein Code uebernommen, nur die Bauart):
  Hall  = Vorverzoegerung, 4 Diffusions-Allpaesse, Rueckkopplungs-Netz aus 8 Leitungen (Hadamard), 2 Leitungen moduliert,
          Daempfung je Leitung (Tone), Abklingzeit 0.6 .. 12 s (Size).
  Room  = fruehe Reflexionen (12 Abgriffe, links / rechts verschieden) + Netz aus 8 kurzen Leitungen, 0.2 .. 3 s.
  Plate = Platte nach Dattorro (J. Dattorro, "Effect Design Part 1", JAES 1997): Bandbegrenzung, 4 Diffusoren,
          Acht-Schleife aus 2 Haelften (modulierter Allpass, Leitung, Daempfung, Allpass, Leitung), 7 Abgriffe je Seite.
Gemeinsam: Rechnung mit 24 kHz (2 Frames -> 1), Bloecke zu 16 Samples; jede Leitung >= 16, deshalb blockweise.
Ein Programm (Liste von Operationen) beschreibt jedes Reverb; daraus entstehen das Gleitkomma-Modell (Tests, Vorhoeren)
und der ColdFire-Code (g2_reverbs.py)."""
import math

FS, NB = 24000, 16
SC = FS / 29761.0                      # Dattorro-Laengen (29.761 kHz) -> 24 kHz


def L(x): return int(round(x * SC))


# Tabellen der Knoepfe (0..127)
def rt60(algo, s):
    lo, hi = {'hall': (0.6, 12.0), 'room': (0.2, 3.0), 'plate': (0.4, 8.0)}[algo]
    return lo * (hi / lo) ** (s / 127.0)


# smp10 (Pip: "Laengen kuerzer als angegeben, Tone wirkt wenig"): Daempfung als Kuhschwanz-Filter erster Ordnung je
# Leitung (Jot): y = lp + g (x - lp), lp = Tiefpass bei fc. Unter fc klingt alles mit RT (Size) ab, ueber fc mit RT * r;
# g je Leitung aus ihrer Laenge: g = exp(-3 ln10 L / (fs RT) (1 / r - 1)). Tone: dunkel = r 0.1, fc 1.2 kHz ..
# hell = r 1 (keine Daempfung). smp9 hatte einen festen Tiefpass je Durchlauf: lange Fahnen verloren die Hoehen nach
# wenigen Durchlaeufen, die Laenge war hoerbar kuerzer, und Tone aenderte vor allem den Anfang.
RMIN = {'hall': 0.10, 'room': 0.12, 'plate': 0.10}
FCR = {'hall': (1200.0, 7000.0), 'room': (1500.0, 8000.0), 'plate': (1200.0, 7000.0)}


def ratio(algo, t): return RMIN[algo] ** (1 - t / 127.0)


def tone_lp(algo, t):
    lo, hi = FCR[algo]; fc = lo * (hi / lo) ** (t / 127.0)
    return 1.0 - math.exp(-2 * math.pi * fc / FS)


def lp_lengths(A):
    """Zustand des Filters -> Weg, den es je Durchlauf daempft (Samples)"""
    if A['name'] == 'Plate': return {1: 2 * A['loops'][0], 2: 2 * A['loops'][1]}
    return dict(A['loops'])


# Ganzzahl-Rechnung wie im Code (Tabellen Q12, exp-Tabelle Q31 in Schritten von 1/32)
def xt(algo, s): return int(round(4096 / rt60(algo, s)))
def qt(algo, t): return int(round(4096 * (1 / ratio(algo, t) - 1)))
def aj(L): return int(round(4096 * 3 * math.log(10) * L / FS))
EB = [min(0x7FFFFFFF, int(round(math.exp(-min(i, 256) / 32) * 2 ** 31))) for i in range(258)]


def shelf_g_int(algo, A, k, s, t):
    P5 = ((xt(algo, s) * qt(algo, t)) >> 8) >> 5            # vorzeichenlos < 2^32
    c = (aj(lp_lengths(A)[k]) * P5) >> 7                    # Q16
    i = c >> 11; f = c & 2047
    if i >= 256: i, f = 256, 0
    return EB[i] + (((EB[i + 1] - EB[i]) >> 11) * f)


def shelf_g(algo, A, k, s, t): return shelf_g_int(algo, A, k, s, t) / 2 ** 31


# ---------------- Programme. Register 0..11 (je 16 Samples). Leitungen: Name -> Laenge (laengster Abgriff).
# Operationen:
#   ('IN', r)                        r = Eingang (mono, 24 kHz)
#   ('DLW', ln, r)                   r in Leitung schreiben
#   ('DLR', ln, r, d)                r = Leitung[t - d]               (d >= 16)
#   ('DLRM', ln, r, d, dep, lfo)     r = Leitung[t - d - m]           m = dep * Dreieck(lfo), linear interpoliert
#   ('AP', ln, r, g, d)              Allpass: v = x - g w, y = w + g v, w = Leitung[t - d], schreibt v
#   ('APM', ln, r, g, d, dep, lfo)   dasselbe mit moduliertem w
#   ('TAP', ln, d, r, g)             r += g Leitung[t - d]
#   ('LPF', r, k, 'tone' | a)        'tone': Kuhschwanz (Daempfung, Zustand k); sonst Tiefpass a
#   ('GAIN', r, j)                   r *= Abklingfaktor j (Tabelle je Size)
#   ('ADD', r, s, g)                 r += g s
#   ('MOV', r, s) / ('ZERO', r)
#   ('HAD', [r...], l, rr, c)        schnelle Hadamard (8), ohne Normierung; l += c y1, rr += c y2 (Zeilen 1 / 2 = HSL / HSR)
#   ('OUT', rl, rr, g)               Ausgang = g (rl, rr)
#   ('TLPF', r, l, rr, gl, gr, k)    l += gl r, rr += gr r, dann r = Kuhschwanz (Tone, Zustand k)  (Netz: lesen)
#   ('FWR', ln, r, j, c, s)          r = Abklingen_j * r + c * s, in die Leitung                  (Netz: schreiben)
#   ('GAINADD', r, s, j)             r += Abklingen_j * s
H8 = [887, 1031, 1213, 1381, 1543, 1747, 1913, 2111]
HSL = [1, -1, 1, -1, 1, -1, 1, -1]
HSR = [1, 1, -1, -1, 1, 1, -1, -1]
HIN = [1, -1, 1, 1, -1, 1, -1, -1]


def prog_hall():
    p = [('IN', 8), ('DLW', 'pre', 8), ('DLR', 'pre', 8, 288)]
    for i, (d, g) in enumerate(((113, 0.75), (89, 0.75), (307, 0.625), (223, 0.625))):
        p.append(('AP', 'hd%d' % i, 8, g, d))
    for j in range(8):
        if j in (0, 4):
            p.append(('DLRM', 'h%d' % j, j, H8[j], 9.0, j // 4))
        else:
            p.append(('DLR', 'h%d' % j, j, H8[j]))
    p += [('ZERO', 9), ('ZERO', 10)]
    for j in range(8):
        p.append(('LPF', j, j, 'tone'))
    p.append(('HAD', list(range(8)), 9, 10, 0.35))      # Ausgang = Zeilen 1 / 2 der Hadamard (Vorzeichen HSL / HSR)
    for j in range(8):
        p.append(('FWR', 'h%d' % j, j, j, 0.5 * HIN[j], 8))
    p.append(('OUT', 9, 10, 1.0))
    lines = {'pre': 288, 'hd0': 113, 'hd1': 89, 'hd2': 307, 'hd3': 223}
    lines.update({'h%d' % j: H8[j] + (10 if j in (0, 4) else 0) for j in range(8)})
    loops = {j: H8[j] for j in range(8)}
    return dict(prog=p, lines=lines, loops=loops, had=1 / math.sqrt(8), lfo=[0.31, 0.43], name='Hall')


R8 = [457, 547, 653, 769, 863, 977, 1109, 1229]
ERL = [(103, 0.78), (233, -0.61), (362, 0.52), (511, -0.43)]      # smp11: 4 je Seite (vorher 6; CPU)
ERR = [(142, 0.74), (271, -0.58), (430, 0.49), (593, -0.41)]


def prog_room():
    p = [('IN', 8), ('DLW', 'er', 8), ('ZERO', 9), ('ZERO', 10)]
    for d, g in ERL: p.append(('TAP', 'er', d, 9, g))
    for d, g in ERR: p.append(('TAP', 'er', d, 10, g))
    p += [('DLR', 'er', 11, 240)]                                 # spaete Reflexionen ab 10 ms
    for i, (d, g) in enumerate(((89, 0.7), (131, 0.7), (61, 0.6))):
        p.append(('AP', 'rd%d' % i, 11, g, d))
    for j in range(8):
        p.append(('DLRM', 'r%d' % j, j, R8[j], 5.0, j // 6) if j in (2, 6) else ('DLR', 'r%d' % j, j, R8[j]))
    for j in range(8):
        p.append(('LPF', j, j, 'tone'))
    p.append(('HAD', list(range(8)), 9, 10, 0.3))
    for j in range(8):
        p.append(('FWR', 'r%d' % j, j, j, 0.45 * HIN[j], 11))
    p.append(('OUT', 9, 10, 1.0))
    lines = {'er': 593, 'rd0': 89, 'rd1': 131, 'rd2': 61}
    lines.update({'r%d' % j: R8[j] + (6 if j in (2, 6) else 0) for j in range(8)})
    return dict(prog=p, lines=lines, loops={j: R8[j] for j in range(8)}, had=1 / math.sqrt(8), lfo=[0.57, 0.79], name='Room')


def prog_plate():
    d = dict(a1=L(672), d1=L(4453), a2=L(1800), d2=L(3720), a3=L(908), d3=L(4217), a4=L(2656), d4=L(3163))
    exc = 13.0
    p = [('IN', 8), ('LPF', 8, 0, 0.72)]
    for i, (n, g) in enumerate(((142, 0.75), (107, 0.75), (379, 0.625), (277, 0.625))):
        p.append(('AP', 'pd%d' % i, 8, g, L(n)))
    # linke Haelfte: Eingang + Abklingen * Ende der rechten
    p += [('DLR', 'd4', 1, d['d4']), ('MOV', 0, 8), ('GAINADD', 0, 1, 1),
          ('APM', 'a1', 0, -0.70, d['a1'], exc, 0), ('DLW', 'd1', 0), ('DLR', 'd1', 0, d['d1']),
          ('LPF', 0, 1, 'tone'), ('GAIN', 0, 0), ('AP', 'a2', 0, 0.5, d['a2']), ('DLW', 'd2', 0)]
    # rechte Haelfte
    p += [('DLR', 'd2', 3, d['d2']), ('MOV', 2, 8), ('GAINADD', 2, 3, 0),
          ('APM', 'a3', 2, -0.70, d['a3'], exc, 1), ('DLW', 'd3', 2), ('DLR', 'd3', 2, d['d3']),
          ('LPF', 2, 2, 'tone'), ('GAIN', 2, 1), ('AP', 'a4', 2, 0.5, d['a4']), ('DLW', 'd4', 2)]
    p += [('ZERO', 9), ('ZERO', 10)]
    tl = [('d1', 266, 1), ('d1', 2974, 1), ('a2', 1913, -1), ('d2', 1996, 1), ('d3', 1990, -1), ('a4', 187, -1), ('d4', 1066, -1)]
    tr = [('d3', 353, 1), ('d3', 3627, 1), ('a4', 1228, -1), ('d4', 2673, 1), ('d1', 2111, -1), ('a2', 335, -1), ('d2', 121, -1)]
    for ln, o, s in tl: p.append(('TAP', ln, L(o), 9, 0.6 * s))
    for ln, o, s in tr: p.append(('TAP', ln, L(o), 10, 0.6 * s))
    p.append(('OUT', 9, 10, 1.0))
    lines = {'pd%d' % i: L(n) for i, n in enumerate((142, 107, 379, 277))}
    lines.update(a1=d['a1'] + 15, d1=d['d1'], a2=d['a2'], d2=d['d2'], a3=d['a3'] + 15, d3=d['d3'], a4=d['a4'], d4=d['d4'])
    # Abklingen je Haelfte (Weg durch eine Haelfte)
    half = (d['a1'] + d['d1'] + d['a2'] + d['d2'] + d['a3'] + d['d3'] + d['a4'] + d['d4']) / 2
    return dict(prog=p, lines=lines, loops={0: half / 2, 1: half / 2}, had=1.0, lfo=[1.0, 0.77], name='Plate')   # zweimal je Haelfte


ALGOS = {'hall': prog_hall, 'room': prog_room, 'plate': prog_plate}


def decay_gain(algo, A, j, s):
    return 10 ** (-3.0 * A['loops'][j] / (FS * rt60(algo, s)))


# ---------------- Gleitkomma-Modell (Bloecke wie der Code)
class Model:
    def __init__(s, algo):
        s.algo = algo; s.A = ALGOS[algo](); s.t = 0
        s.ring = {k: [0.0] * (1 << max(5, (v + NB + 2).bit_length())) for k, v in s.A['lines'].items()}
        s.st = [0.0] * 12; s.ph = [0.0] * len(s.A['lfo']); s.R = [[0.0] * NB for _ in range(12)]

    def rd(s, ln, d):
        r = s.ring[ln]; m = len(r) - 1
        return [r[(s.t + i - d) & m] for i in range(NB)]

    def rdm(s, ln, d):                        # d gebrochen, linear
        r = s.ring[ln]; m = len(r) - 1; di = int(math.floor(d)); fr = d - di
        return [r[(s.t + i - di) & m] * (1 - fr) + r[(s.t + i - di - 1) & m] * fr for i in range(NB)]

    def wr(s, ln, x):
        r = s.ring[ln]; m = len(r) - 1
        for i in range(NB): r[(s.t + i) & m] = x[i]

    def tri(s, k):
        p = s.ph[k]; return 4 * p - 1 if p < 0.5 else 3 - 4 * p

    def block(s, x, size, tone):
        A, R = s.A, s.R
        g_ = {k: shelf_g(s.algo, A, k, size, tone) for k in lp_lengths(A)}; a_t = tone_lp(s.algo, tone)
        for op in A['prog']:
            o = op[0]
            if o == 'IN': R[op[1]] = list(x)
            elif o == 'DLW': s.wr(op[1], R[op[2]])
            elif o == 'DLR': R[op[2]] = s.rd(op[1], op[3])
            elif o == 'DLRM': R[op[2]] = s.rdm(op[1], op[3] + op[4] * s.tri(op[5]))
            elif o in ('AP', 'APM'):
                ln, r, g, d = op[1:5]
                w = s.rd(ln, d) if o == 'AP' else s.rdm(ln, d + op[5] * s.tri(op[6]))
                v = [R[r][i] - g * w[i] for i in range(NB)]
                R[r] = [w[i] + g * v[i] for i in range(NB)]; s.wr(ln, v)
            elif o == 'TAP':
                w = s.rd(op[1], op[2]); R[op[3]] = [R[op[3]][i] + op[4] * w[i] for i in range(NB)]
            elif o == 'LPF':
                y = s.st[op[2]]; out = []
                if op[3] == 'tone':
                    for v in R[op[1]]: y += a_t * (v - y); out.append(y + g_[op[2]] * (v - y))
                else:
                    for v in R[op[1]]: y += op[3] * (v - y); out.append(y)
                s.st[op[2]] = y; R[op[1]] = out
            elif o == 'GAIN':
                g = decay_gain(s.algo, A, op[2], size) * A['had']; R[op[1]] = [v * g for v in R[op[1]]]
            elif o == 'GAINADD':
                g = decay_gain(s.algo, A, op[3], size); R[op[1]] = [R[op[1]][i] + g * R[op[2]][i] for i in range(NB)]
            elif o == 'ADD': R[op[1]] = [R[op[1]][i] + op[3] * R[op[2]][i] for i in range(NB)]
            elif o == 'TLPF':
                r, l_, rr, gl, gr, k = op[1:]
                R[l_] = [R[l_][i] + gl * R[r][i] for i in range(NB)]; R[rr] = [R[rr][i] + gr * R[r][i] for i in range(NB)]
                y = s.st[k]; out = []
                for v in R[r]: y += a_t * (v - y); out.append(y + g_[k] * (v - y))
                s.st[k] = y; R[r] = out
            elif o == 'FWR':
                ln, r, j, c, src = op[1:]
                g = decay_gain(s.algo, A, j, size) * A['had']
                R[r] = [g * R[r][i] + c * R[src][i] for i in range(NB)]; s.wr(ln, R[r])
            elif o == 'MOV': R[op[1]] = list(R[op[2]])
            elif o == 'ZERO': R[op[1]] = [0.0] * NB
            elif o == 'HAD':
                rs = op[1]; n = len(rs); h = 1
                hl, hr, hc = op[2:5]
                while h < n:
                    for i in range(0, n, 2 * h):
                        for j in range(i, i + h):
                            a_, b_ = R[rs[j]], R[rs[j + h]]
                            R[rs[j]] = [a_[k] + b_[k] for k in range(NB)]; R[rs[j + h]] = [a_[k] - b_[k] for k in range(NB)]
                    h *= 2
                R[hl] = [R[hl][i] + hc * R[rs[1]][i] for i in range(NB)]
                R[hr] = [R[hr][i] + hc * R[rs[2]][i] for i in range(NB)]
            elif o == 'OUT': out = ([v * op[3] for v in R[op[1]]], [v * op[3] for v in R[op[2]]])
        s.t += NB
        for k, f in enumerate(A['lfo']):
            s.ph[k] = (s.ph[k] + f * NB / FS) % 1.0
        return out


def render(algo, x, size, tone):
    """x: Mono-Eingang mit 48 kHz -> (L, R) mit 48 kHz; Auf- / Abtastung wie der Code (Mittel / linear)."""
    m = Model(algo); L_, R_ = [], []; pl = pr = 0.0
    for b in range(0, len(x) - 2 * NB + 1, 2 * NB):
        xi = [(x[b + 2 * i] + x[b + 2 * i + 1]) / 2 for i in range(NB)]
        yl, yr = m.block(xi, size, tone)
        for i in range(NB):
            L_ += [(pl + yl[i]) / 2, yl[i]]; R_ += [(pr + yr[i]) / 2, yr[i]]; pl, pr = yl[i], yr[i]
    return L_, R_
