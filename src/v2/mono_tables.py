"""Klang-Konstanten und Tabellen der Maschine 'mono' (g2_mono, Modell mono_model). Eigene Werte, keine Firmware-Daten."""
import math, struct

FS = 48000
NB = 32
WAVES = ('SAW', 'SQR', 'PWM', 'S+P', 'TRI', 'SYNC', 'DTN', 'RING')
G0 = 0.28                     # Oszillator (Saege voll = G0); Sub bis G0, Rauschen bis NMAX: Summe < 1
NMAX, NFLOOR = 0.15, 0.0015
WARM_HZ = 9000.0              # fester 1-Pol-Tiefpass (alle Wellen ausser SAW: dort SHAPE 18 kHz .. 900 Hz)
SAW_HI, SAW_LO = 18000.0, 900.0
BIAS = 0.12                   # Unsymmetrie der Saettigung (gerade Obertoene)
DCR = 0.9987                  # DC-Sperre (~10 Hz)
# Unperfektheit: Drift (Cent) und Raten (Hz) je Oszillator (zwei Sinus), Zufall je Anschlag (Cent)
DRIFT = {'o1': (2.5, 0.13, 0.37), 'o2': (3.5, 0.11, 0.29), 'sub': (2.0, 0.17, 0.41)}
RNDC = 1.5
PWM_HZ, PWM_DEP = 0.7, 0.15


def q31(x):
    v = int(round(x * 2 ** 31)); v = max(-2 ** 31, min(2 ** 31 - 1, v))
    return v & 0xFFFFFFFF


def lp1(fc):
    return 1 - math.exp(-2 * math.pi * fc / FS)


def drive_gain(c):
    return 1.2 + 6.0 * (c / 127) ** 1.5


def glide_a(g):
    if g == 0: return 1.0
    tau = 0.004 * 350 ** (g / 127)                    # 4 ms .. 1.4 s
    return 1 - math.exp(-NB / FS / tau)


def tables():
    t = {}
    t['SINT'] = struct.pack('>257I', *[q31(0.999 * math.sin(2 * math.pi * i / 256)) for i in range(257)])
    t['TANH'] = struct.pack('>257I', *[q31(math.tanh((i - 128) / 16)) for i in range(257)])
    t['GLT'] = struct.pack('>128I', *[q31(glide_a(g)) for g in range(128)])
    t['SAWLP'] = struct.pack('>128I', *[q31(lp1(SAW_HI * (SAW_LO / SAW_HI) ** (s / 127))) for s in range(128)])
    t['DRVT'] = b''.join(struct.pack('>II', q31(drive_gain(c) / 8), q31(0.85 / math.tanh(drive_gain(c)))) for c in range(128))
    return t


C = dict(PWK=int(round(0.45 / 127 * 2 ** 32)), PCK=int(round(0.3 / 127 * 2 ** 32)), SUBK=int(round(G0 / 127 * 2 ** 31)),
         NOK=int(round((NMAX - NFLOOR) / 127 * 2 ** 31)), NFL=q31(NFLOOR),
         G0=q31(G0), MG0=q31(-G0), WARM=q31(lp1(WARM_HZ)), BIAS8=q31(BIAS / 8), TB=q31(math.tanh(BIAS)), DCR=q31(DCR),
         PWMD=q31(PWM_DEP * 2), DPWM=int(round(PWM_HZ * NB / FS * 2 ** 32)) & 0xFFFFFFFF)
for nm, (cent, f1, f2) in DRIFT.items():
    C[f'D{nm}A'] = int(round(cent / 100 * 0.6 * 65536)); C[f'D{nm}B'] = int(round(cent / 100 * 0.4 * 65536))
    C[f'R{nm}A'] = int(round(f1 * NB / FS * 2 ** 32)); C[f'R{nm}B'] = int(round(f2 * NB / FS * 2 ** 32))
C['RNDK'] = int(round(RNDC / 100 * 2 * 65536))         # Bereich +- RNDC Cent in 16.16 Halbtoenen
