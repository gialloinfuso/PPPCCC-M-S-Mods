#!/usr/bin/env python3
"""Mod 'track-filter' (v2, Patch 13): 12-dB-Tiefpass pro Track mit leichter Saettigung, Filter-Huellkurve (Decay) und
Filter-Modus fuer die Knoepfe. Braucht nur den Core (Popup OVS).

Bedienung (Pip 27.10.2026):
  RETRIG halten + GATE = Filter-Modus an (Popup 'FILTER ON'); RETRIG kurz antippen = aus ('FILTER OFF'). RETRIG halten und
    dabei einen Knopf drehen (z. B. RETRIG + LFO SPEED = LFO Amount) beendet den Modus nicht (Pip 28.10.2026;
    vorher CLICK doppelt: das schaltete GATE zweimal um). GATE allein macht weiter, was es immer macht.
  Im Filter-Modus: PITCH = Cutoff, DECAY = Env Decay, COLOR = Resonanz, SHAPE = Env-Tiefe (bipolar, Mitte = OFF).
  Cutoff 127 = Filter aus (die Spur bleibt bitgenau, wenn die Huellkurve den Cutoff nicht nach unten zieht). Ist der Filter
  an, bleibt er an, auch wenn Cutoff + Huellkurve ueber 127 gehen (dann ~20 kHz).
Parameter: vier echte Parameter aller Maschinen (Deskriptoren 1..4, freie 'Error'-Plaetze, k = 28..31): p-lockbar, LFO- und
  Velocity-Ziel, CC 74 (Cutoff) und 71 (Resonanz); mit dem Sound gespeichert. Die Firmware glaettet die Werte und rechnet LFO,
  p-locks und Velocity ein; der Filter liest die geglaetteten Worte einmal pro Block (32 Samples).
DSP (eigener Code): Zustandsraum-Form des trapezfoermigen SVF (Zavalishin, 'The Art of VA Filter Design'), Tiefpass:
  u = x/2 (1 - x^2/4)   (leichte Saettigung, intern halbe Aussteuerung)
  s1' = c1 s1 + c2 u - c2 s2 ;  s2' = e s2 + c2 s1 + 2 a3 u ;  y = s2 + s2'
  g = tan(pi fc/48000), k = 1/Q, a1 = 1/(1 + g(g + k)), c1 = 2 a1 - 1, c2 = 2 g a1, a3 = g^2 a1, e = 1 - 2 a3.
  a1 per Division (divu.l, 16 Bit) und einem Newton-Schritt. Huellkurve: 1 bei jedem Trig der Spur, dann exponentiell.
Firmware 1.13 (Schnittstellen nach Modded-Cycles notes/47, MIT; der Code hier ist eigener Code):
  0x40059852 jsr Volume+Dist (0x40056f58, Args TRK-Puffer 0x80001858, geglaettete Parameter) -> jsr POST (erst Volume+Dist).
    a3 = Kontext der Audiofunktion, +16 = Tracks mit Trig in diesem Block. Geglaettete Worte: Param + 14 + 66 t + 2 k.
  0x401005a8 Vtable ParameterPageView Slot 124 (Knopf -> Deskriptor, 0x4001e814) -> KNOB.
  0x4001ca9c GATE (Taste 7, FUNC + GATE = Click-Menue) im Hauptbildschirm: pea 0x2d (Deskriptor 45 Gate) ; push this ;
    jsr 0x4001ac4a ; addq -> jsr KEYH + nops. 0x4001c4ba RETRIG (Taste 4) im Hauptbildschirm -> jmp RT (Prolog nachgespielt).
  Sound speichern / laden und p-locks fuer k 28..31: ueber den Core (Sound-Slot FH; Satz-Plaetze +88, +90, +64/65 wie
    Modded-Cycles: Cutoff XOR 0x7f00, Resonanz, Env XOR 64, Decay XOR 64; LFO-/Velocity-Ziel und p-locks macht der Core).
Aufruf: g2_trackfilter.py [out.json]
"""
import math, struct, sys
from common import *                 # noqa: F401,F403
import common as C
import g2_core as core
import cfemac as E

# ---- Masken
M_DSP, M_KER, M_GT, M_KT, M_DT, M_UI, M_SL, M_PT, M_ST, M_CO, M_NT, M_RT, M_PO, M_LED = (0x40172608, 0x40179730, 0x4014AB5C, 0x401601FC, 0x401625BC,
                                                         0x40163FB8, 0x4016616C, 0x40166760, 0x40173848,
                                                         0x401780A8, 0x401784E8, 0x40165FEC, 0x40172A68, 0x4014B5B4)
SIZE = {M_DSP: 376, M_KER: 376, M_GT: 280, M_KT: 280, M_DT: 280, M_UI: 280, M_SL: 280, M_PT: 280, M_ST: 272, M_CO: 272, M_NT: 272, M_RT: 192, M_PO: 192, M_LED: 108}
LED_HOOK, LED_CK = 0x40021E0E, (6, 'b780ebb6e174efbef17219af7ed884491db4dba1955db01fdbf030508c122c84')
LED_VEC, LED_SET, LED_LAYER, LED_ON = 0x404A8BAC, 0x40005F86, 0x404A8CB8, 2
NLED = 4                             # Knopf-LEDs 0..3 (Knopf - 2): PITCH, DECAY, COLOR, SHAPE
# ---- Zustand (Maske M_ST, im Image genullt): 6 x 32 B pro Track, dann Modus
TS = 40                              # +0 s1, +4 s2, +8 Huellkurve, +12 an, +16 c1, +20 c2, +24 e, +28 a3, +32 n, +36 n alt
T_N, T_NO, NFADE = 32, 36, 8         # Ueberblendung an/aus in 8 Bloecken (5.3 ms)
MODE, RH = M_ST + 6 * TS, M_ST + 6 * TS + 4    # RH: RETRIG im Modus gedrueckt, Loslassen beendet ihn (wenn sonst nichts)
KEY_RETRIG = 4                       # RETRIG (Tastencode; die Firmware fragt HELD(4) in der Trig-Ansicht ab, LED 0x1b)
MAGIC = 0x464C5431                   # 'FLT1'
# ---- Firmware
POST_HOOK, VOLDIST = 0x40059852, 0x40056F58
KNOB_SLOT, KNOB_ORIG = 0x401005A8, 0x4001E814
RT_HOOK, RT_CK = 0x4001C4BA, (8, '3ce931d7357a496e83843a4e65042d557eab086f9393fd43ae72ba28e3fad05f')
K_PRESS, K_FUNC, K_REL = 0x400724A0, 0x40072490, 0x40072470   # Ereignis: gedrueckt (keine Wiederholung) / FUNC / losgelassen
KEY_HOOK, KEY_CK, CLICK_ACT = 0x4001CA9C, (12, 'd664b310882ba76ffa861068dfa6ff742e8f472bfa8d685491a1b55936289230'), 0x4001AC4A
from g2_core import LD_HOOK, SV2_HOOK, SV1_HOOK, PTAB_REFS, PTAB_ORIG   # noqa: E402 (Tests; Sound/p-locks: Core)
REC = 0x40A71754                     # UI-Objekte der Deskriptoren (100 B): +0x20 Formatierer, +0x2c Sonderzeichnung
FMT_INT, FMT_OFF = 0x400456C8, 0x40045BD6
AMP = 0x40129882                     # Gruppenname "Amp"
ENC_PITCH, ENC_DECAY, ENC_COLOR = 2, 3, 4
# ---- Parameter: k, Offset im Track-Block (2 k), Deskriptor
K_CUT, K_RES, K_ENV, K_DEC = 28, 29, 30, 31
O_CUT, O_RES, O_ENV, O_DEC = 2 * K_CUT, 2 * K_RES, 2 * K_ENV, 2 * K_DEC
TOP = 0x7F00
# Knopf (PITCH, DECAY, COLOR, SHAPE) -> Deskriptor (1 Cutoff, 2 Reso, 3 Env, 4 Decay)
KMAP = (1, 4, 2, 3)
DESCS = [  # (k, Default, CC-Feld, NRPN, Sortierschluessel, Langname, Kurzname, Formatierer)
    (K_CUT, TOP, 0x004AFFFF, 0x94, 72, "Filter Cutoff", "CUT", FMT_INT),
    (K_RES, 0, 0x0047FFFF, 0x95, 73, "Filter Reso", "RESO", FMT_INT),
    (K_ENV, 0x4000, 0xFFFFFFFF, 0xFFFFFFFF, 74, "Filter Env", "FENV", FMT_OFF),
    (K_DEC, 0x4000, 0xFFFFFFFF, 0xFFFFFFFF, 75, "Filter Decay", "FDEC", FMT_INT),
]
FS, BLOCK_HZ = 48000.0, 1500.0


# ---------------- Kennlinien (Tabellen: 65 Werte, Index = Wort / 512, linear interpoliert)
def cutoff_hz(w):
    return 20.0 * 1000.0 ** (min(w, TOP) / TOP)


Q_MAX = 5.0


def q_of(w):
    """Resonanz 0..127 -> Q 0.5..5 (v1: bis 20, Pip 27.10.: zu krass, Fiepen)"""
    return 0.5 * (Q_MAX / 0.5) ** (w / TOP)


def q_cap(fc):
    """hoechstes Q je Cutoff: 5 von 80 Hz bis 2 kHz, darueber weicher (kein Fiepen), darunter kein Bass-Droehnen"""
    if fc >= 2000: return max(Q_MAX * (2000 / fc) ** 0.7, 0.7)
    if fc >= 80: return Q_MAX
    return 1.0 + (Q_MAX - 1.0) * max(fc - 20, 0) / 60


def tau_of(w):
    return 0.005 * 1000.0 ** (w / TOP)


def q31(x):
    return max(min(int(round(x * 2 ** 31)), 0x7FFFFFFF), -0x80000000)


def tables():
    gt = [q31(math.tan(math.pi * cutoff_hz(512 * j) / FS) / 4) for j in range(65)]
    kt = [q31(1 / (2 * q_of(512 * j))) for j in range(65)]
    dt = [q31(math.exp(-1 / (BLOCK_HZ * tau_of(512 * j)))) for j in range(65)]
    nt = [q31(1 / (2 * q_cap(cutoff_hz(512 * j)))) for j in range(65)]
    return gt, kt, dt, nt


def build_dsp(lab):
    """POST (Haken) und TRACK. lab: Adressen aus build_ker (KERNEL, COEF, INTERP), Tabellen."""
    a = A(M_PO); w, l = a.w, a.l32
    a.label('POST')
    w(0x2F2F, 0x0008, 0x2F2F, 0x0008, 0x4EB9); l(VOLDIST); w(0x508F)     # Volume + Dist wie bisher
    w(0x4FEF, 0xFFC8, 0x48D7, 0x7CFC)                                     # lea -56(sp),sp ; movem.l d2-d7/a2-a6,(sp)
    E.macsr_to(a, 'd0'); w(0x2F40, 0x002C)                                # MACSR sichern (44(sp))
    E.to_macsr(a, 0xA0)                                                   # fraktional, gesaettigt
    for n in range(4):
        E.movclr(a, n, 'd0')                                              # Akkus leer (wie die Firmware sie erwartet)
    w(0x202B, 0x0010, 0x2F40, 0x0030)                                     # Trig-Bits (a3+16) -> 48(sp)
    w(0x2A6F, 0x0040, 0x4BED, 0x000E)                                     # a5 = Param + 14 (Track 0)
    w(0x2C6F, 0x003C, 0x49F9); l(M_ST)                                    # a6 = TRK ; a4 = Zustand
    w(0x7006, 0x2F40, 0x0034)                                             # 6 Tracks -> 52(sp)
    a.label('tl')
    w(0x202F, 0x0030, 0x7201, 0xC081, 0x4EB9); l(M_DSP)               # d0 = Trig-Bit ; jsr TRACK (Adresse unten)
    w(0x202F, 0x0030, 0xE288, 0x2F40, 0x0030)                             # Trig-Bits >> 1
    w(0x49EC, TS, 0x4BED, 0x0042, 0x4DEE, 0x0080)                         # naechster Track: Zustand, Parameter, Puffer
    w(0x53AF, 0x0034); a.bcc(NE, 'tl')
    for n in range(4):
        E.movclr(a, n, 'd0')                                              # Akkus leer zurueck
    w(0x202F, 0x002C); E.to_macsr(a, 'd0')
    w(0x4CD7, 0x7CFC, 0x4FEF, 0x0038, 0x4E75)
    post = a.done(); E.check(post, M_PO); lpost = dict(a.lab)
    # ---------------- TRACK (d0 Trig, a4 Zustand, a5 Parameter, a6 Puffer); zerstoert d0-d7, a0-a3
    a = A(M_DSP); w, l = a.w, a.l32
    a.label('TRACK')
    w(0x282C, 0x0008)                                                     # d4 = Huellkurve
    w(0x4A80); a.bcc(EQ, 'nt')
    w(0x283C); l(0x7FFFFFFF); a.bcc(BRA, 'eok')                           # Trig: 1
    a.label('nt')
    w(0x4A84); a.bcc(EQ, 'eok')
    w(0x716D, O_DEC, 0x41F9); l(lab['DT']); w(0x4EB9); l(lab['INTERP'])   # d0 = Faktor pro Block
    E.mac(a, 'd0', 'd4', 0); E.movclr(a, 0, 'd4')
    w(0x0C84); l(0x10000); a.bcc(CC, 'eok')
    w(0x7800)                                                             # zu klein: aus
    a.label('eok')
    w(0x2944, 0x0008)
    w(0x7B6D, O_CUT)                                                      # d5 = Cutoff (mvs.w)
    # Aus (Spur bitgenau) nur, wenn der Knopf ganz offen ist und die Huellkurve ihn nicht nach unten zieht. Sonst bleibt der
    # Filter an, auch wenn die Huellkurve ueber 127 hinaus will (v2 schaltete dann ab und beim Zurueckkommen neu an: Klicken).
    w(0x0C85); l(TOP); a.bcc(LT, 'act')
    w(0x4A84); a.bcc(EQ, 'byp')
    w(0x716D, O_ENV, 0x0C80); l(0x4000); a.bcc(GE, 'byp')
    a.label('act')
    w(0x4A84); a.bcc(EQ, 'cl')
    w(0x716D, O_ENV, 0x0480); l(0x4000); w(0xD080)                        # d0 = 2 (Env - Mitte)
    E.mac(a, 'd0', 'd4', 0); E.movclr(a, 0, 'd0'); w(0xDA80)              # Cutoff + Tiefe * Huellkurve
    a.label('cl')
    w(0x4A85); a.bcc(PL, 'c0')
    w(0x7A00)
    a.label('c0')
    w(0x0C85); l(TOP); a.bcc(LE, 'up')
    w(0x2A3C); l(TOP)                                                     # begrenzen: Filter bleibt an (~20 kHz)
    a.label('up')                                                         # Filter an: Ueberblendung hoch (n -> n+1, bis 8)
    w(0x202C, T_N, 0x2940, T_NO, 0x7200 | NFADE, 0xB081); a.bcc(GE, 'on')
    w(0x5280, 0x2940, T_N); a.bcc(BRA, 'on')
    a.label('byp')                                                        # ganz offen
    w(0x202C, T_N); a.bcc(NE, 'fo')
    w(0x42AC, 0x000C, 0x4E75)                                             # ausgeblendet: Spur unveraendert, Zustand vergessen
    a.label('fo')                                                         # noch eingeblendet: weiter filtern, ausblenden
    w(0x2940, T_NO, 0x5380, 0x2940, T_N, 0x2A3C); l(TOP)
    a.label('on')
    w(0x2005, 0x41F9); l(lab['GT']); w(0x4EB9); l(lab['INTERP']); w(0x2C00)   # d6 = G = g/4
    w(0x716D, O_RES, 0x41F9); l(lab['KT']); w(0x4EB9); l(lab['INTERP']); w(0x2E00)   # d7 = K = k/2
    w(0x2005, 0x41F9); l(lab['NT']); w(0x4EB9); l(lab['INTERP'])          # d0 = kleinstes K bei diesem Cutoff
    w(0xBE80); a.bcc(GE, 'kk'); w(0x2E00)                                 # K = max(K, Kmin)
    a.label('kk')
    w(0x4EB9); l(lab['COEF'])
    # ---------------- Kopf des Kernels (Start, stiller Block), dann KERNEL
    w(0x204E, 0x43EE, 0x0080)
    w(0x4AAC, 0x000C); a.bcc(NE, 'run')
    w(0x2010, 0xE280, 0x2940, 0x0004, 0x4294, 0x7001, 0x2940, 0x000C)     # Start: s1 = 0, s2 = x0/2
    w(0x4EF9); l(lab['KERNEL'])
    a.label('run')
    w(0x2448, 0x7000, 0x7207)
    a.label('zl')
    w(0x809A, 0x809A, 0x809A, 0x809A, 0x5381); a.bcc(PL, 'zl')
    w(0x4A80); a.bcc(NE, 'kg')
    w(0x2014); a.bcc(PL, 'p1'); w(0x4480)                                 # Block still: Zustand klein -> nichts tun
    a.label('p1')
    w(0x222C, 0x0004); a.bcc(PL, 'p2'); w(0x4481)
    a.label('p2')
    w(0x8081, 0x0C80); l(0x1000); a.bcc(CC, 'kg')
    w(0x4294, 0x42AC, 0x0004, 0x4E75)
    a.label('kg')
    w(0x4EF9); l(lab['KERNEL'])
    code = a.done()
    E.check(code, M_DSP)
    return post, code, dict(a.lab, **lpost)


def build_ker():
    a = A(M_KER); w, l = a.w, a.l32

    def regs():                                                           # d1 s1, d2 s2, d3 c1, d4 c2, d5 e, a2 a3, d7 1
        w(0x4CD4, 0x0006, 0x4CEC, 0x0038, 0x0010, 0x246C, 0x001C, 0x2E3C); l(0x7FFFFFFF)

    def body():                                                           # ein Sample; Ergebnis in acc2
        w(0x2010)                                                         # x
        E.mac(a, 'd0', 'd0', 3); E.movclr(a, 3, 'd6')                     # x^2
        w(0xE486, 0x0A86); l(0x7FFFFFFF); w(0xE280)                       # 1 - x^2/4 ; x/2
        E.mac(a, 'd0', 'd6', 3); E.movclr(a, 3, 'd0')                     # u
        E.to_acc(a, 'd2', 2)                                              # y = s2 ...
        E.mac(a, 'd3', 'd1', 0); E.mac(a, 'd4', 'd0', 0); E.msac(a, 'd4', 'd2', 0)              # s1'
        E.mac(a, 'd5', 'd2', 1); E.mac(a, 'd4', 'd1', 1); E.mac(a, 'a2', 'd0', 1, shift=1)      # s2'
        E.movclr(a, 0, 'd1'); E.movclr(a, 1, 'd2')
        E.mac(a, 'd1', 'd1', 3); E.movclr(a, 3, 'd6')                     # Resonanz weich begrenzen:
        w(0xE486, 0x0A86); l(0x7FFFFFFF)                                  # s1 (1 - s1^2/4)
        E.mac(a, 'd1', 'd6', 3); E.movclr(a, 3, 'd1')
        E.mac(a, 'd2', 'd7', 2)                                           # ... + s2'

    # ---------------- KERNEL (a4 Zustand mit Koeffizienten, a6 Puffer): 32 Samples
    a.label('KERNEL')
    a.label('go')
    w(0x202C, T_N, 0xD0AC, T_NO, 0x0C80); l(2 * NFADE); a.bcc(EQ, 'full')
    # Ueberblendung (n_alt -> n_neu): Ausgang = (1 - F) x + F y, F linear ueber den Block von n_alt/8 nach n_neu/8
    w(0x202C, T_NO, 0x721C, 0xE3A8, 0x4A80); a.bcc(PL, 'f0'); w(0x5380)  # F = n_alt << 28 (8 -> 0x7fffffff)
    a.label('f0')
    w(0x222C, T_N, 0x92AC, T_NO, 0x7C17, 0xEDA1)                          # Schritt pro Sample = (n_neu - n_alt) << 23
    w(0x2F0C, 0x2F01)                                                     # a4 und Schritt auf den Stack
    regs()
    w(0x2640, 0x2C07, 0x9C80, 0x2846)                                     # a3 = F, a4 = 1 - F
    a.label('lpf')
    body()
    E.movclr(a, 2, 'd0')                                                  # y
    E.mac(a, 'a3', 'd0', 2); w(0x2C10); E.mac(a, 'a4', 'd6', 2); E.movclr(a, 2, 'd0')   # F y + (1 - F) x
    w(0x20C0, 0xD7D7, 0x99D7, 0xB1C9); a.bcc(NE, 'lpf')
    w(0x286F, 0x0004, 0x508F, 0x48D4, 0x0006, 0x4E75)
    a.label('full')
    regs()
    a.label('lp')
    body()
    E.movclr(a, 2, 'd0')
    w(0x20C0, 0xB1C9); a.bcc(NE, 'lp')
    w(0x48D4, 0x0006, 0x4E75)
    code = a.done()
    E.check(code, M_KER)
    return code, a.lab


def build_co():
    a = A(M_CO); w, l = a.w, a.l32
    # ---------------- COEF (d6 G = g/4, d7 K = k/2, a4 Zustand) -> c1, c2, e, a3
    a.label('COEF')
    w(0x2006, 0xE880)                                                     # d0 = G/16
    E.to_acc(a, 0x01000000, 0)
    E.mac(a, 'd0', 'd6', 0, shift=1); E.mac(a, 'd0', 'd7', 0); E.movclr(a, 0, 'd1')   # d1 = D/128 = 2^-7 + G^2/8 + GK/16
    w(0x2401, 0x760D, 0xE6AA, 0x263C); l(0x7FFFFFFF); w(0x4C42, 0x3003)   # d3 = 0x7fffffff / (d1 >> 13)
    w(0x740B, 0xE5AB)                                                     # H0 = d3 << 11 ~ 1/D
    E.mac(a, 'd1', 'd3', 0); E.movclr(a, 0, 'd2')                         # D H0 / 128
    w(0x203C); l(0x01000000); w(0x9082, 0xEF80)                           # d0 = 1 - D H0
    E.to_acc(a, 'd3', 0); E.mac(a, 'd3', 'd0', 0); E.movclr(a, 0, 'd3')   # a1 = H0 (2 - D H0)
    w(0x2003, 0xD080, 0x0840, 0x001F, 0x2940, 0x0010)                     # c1 = 2 a1 - 1
    E.mac(a, 'd6', 'd3', 0); E.movclr(a, 0, 'd0'); w(0xE780, 0x2940, 0x0014)          # c2 = 8 G a1
    E.mac(a, 'd6', 'd0', 0, shift=1); E.movclr(a, 0, 'd1')                # a3 = 2 G c2
    w(0x4A81); a.bcc(NE, 'a3')
    w(0x7201)
    a.label('a3')
    w(0x2941, 0x001C, 0xD281, 0x203C); l(0x80000000); w(0x9081, 0x2940, 0x0018, 0x4E75)   # e = 1 - 2 a3
    # ---------------- INTERP (a0 Tabelle, d0 Wort) -> d0 ; zerstoert d1-d3
    a.label('INTERP')
    w(0x4A80); a.bcc(PL, 'i1'); w(0x7000)
    a.label('i1')
    w(0x0C80); l(TOP); a.bcc(LE, 'i2'); w(0x203C); l(TOP)
    a.label('i2')
    w(0x2200, 0x7409, 0xE4A1)                                             # j = w >> 9
    w(0x2400, 0x0282); l(0x1FF); w(0x7616, 0xE7AA)                        # f = (w & 511) << 22
    w(0x2630, 0x1C00, 0x2230, 0x1C04, 0x9283)                             # T[j], T[j+1] - T[j]
    E.mac(a, 'd1', 'd2', 0); E.movclr(a, 0, 'd0'); w(0xD083, 0x4E75)
    code = a.done()
    E.check(code, M_CO)
    return code, a.lab


def build_ui(cs, strs):
    a = A(M_UI); w, l = a.w, a.l32
    # ---------------- KNOB: Vtable-Slot 124 (Ansicht, Knopf, FUNC, -1) -> d0 Deskriptor
    a.label('KNOB')
    a.bcc(BSR, 'OBJS')
    w(0x2F2F, 0x0010, 0x2F2F, 0x0010, 0x2F2F, 0x0010, 0x2F2F, 0x0010, 0x4EB9); l(KNOB_ORIG); w(0x4FEF, 0x0010)
    w(0x2239); l(MODE); w(0x0C81); l(MAGIC); a.bcc(NE, 'ko')
    w(0x222F, 0x0008, 0x5581, 0x0C81); l(3); a.bcc(HI, 'ko')              # PITCH..SHAPE
    w(0x41F9); l(0); fix_map = len(a.b) - 4
    w(0x71B0, 0x1800)                                                     # mvz.b (a0,d1.l),d0
    a.label('ko')
    w(0x4E75)
    # ---------------- OBJS: Formatierer der vier UI-Objekte, keine Sonderzeichnung
    a.label('OBJS')
    w(0x41F9); l(REC + 100); w(0x43F9); l(0); fix_fm = len(a.b) - 4
    w(0x7204)
    a.label('ob')
    w(0x2019, 0x2140, 0x0020, 0x42A8, 0x002C, 0x41E8, 0x0064, 0x5381); a.bcc(NE, 'ob')
    w(0x4E75)
    # ---------------- KEYH: GATE (Taste 7, Druecken ohne FUNC; a2 = Ansicht). RETRIG gehalten -> Filter-Modus an.
    a.label('KEYH')
    w(0x4878, KEY_RETRIG, 0x4EB9); l(C.HELD); w(0x588F, 0x4A80); a.bcc(EQ, 'norm')
    w(0x42B9); l(RH)                                                      # RETRIG wurde benutzt: Loslassen beendet nichts
    w(0x2039); l(MODE); w(0x0C80); l(MAGIC); a.bcc(EQ, 'kx')              # schon an
    w(0x223C); l(MAGIC); w(0x23C1); l(MODE)
    w(0x223C); l(0); fix_son = len(a.b) - 4
    w(0x41F9); l(0); fix_sf = len(a.b) - 4
    w(0x93C9, 0x7000 | C.OV_TEXT, 0x4EF9); l(cs['OVS'])
    a.label('kx')
    w(0x4E75)
    a.label('norm')
    w(0x4878, 0x002D, 0x2F0A, 0x4EB9); l(CLICK_ACT); w(0x508F, 0x4E75)   # was GATE immer tut
    code = bytearray(a.done())
    while len(code) % 4: code += b'\0'
    fm = M_UI + len(code); code += struct.pack('>4I', *[d[7] for d in DESCS])
    mp = M_UI + len(code); code += bytes(KMAP)
    for at, v in ((fix_map, mp), (fix_fm, fm), (fix_son, strs['S_ON']), (fix_sf, strs['S_FLT'])):
        code[at:at + 4] = struct.pack('>I', v)
    E.check(bytes(code[:fm - M_UI]), M_UI)
    return bytes(code), dict(a.lab, FMTS=fm, KMAP=mp)


def build_rt(cs, strs):
    """RT: RETRIG im Hauptbildschirm (Haken 0x4001c4ba, d3 = Ereignis, jedes Ereignis der Taste): im Modus kurz antippen
    (Druecken + Loslassen ohne Knopfdrehung und ohne GATE dazwischen) beendet den Filter-Modus."""
    a = A(M_RT); w, l = a.w, a.l32
    a.label('RT')
    w(0x2F03, 0x4EB9); l(K_FUNC); w(0x588F, 0x4A00); a.bcc(NE, 'cont')   # FUNC + RETRIG: Firmware
    w(0x2F03, 0x4EB9); l(K_PRESS); w(0x588F, 0x4A00); a.bcc(EQ, 'rel')
    w(0x7200, 0x2039); l(MODE); w(0x0C80); l(MAGIC); a.bcc(NE, 'st')      # Druecken: im Modus RH = 1, sonst 0
    w(0x7201)
    a.label('st')
    w(0x23C1); l(RH); a.bcc(BRA, 'cont')
    a.label('rel')
    w(0x2F03, 0x4EB9); l(K_REL); w(0x588F, 0x4A00); a.bcc(EQ, 'cont')
    w(0x4AB9); l(RH); a.bcc(EQ, 'cont')                                   # Loslassen nach blossem Antippen: Modus aus
    w(0x42B9); l(RH)
    w(0x2039); l(MODE); w(0x0C80); l(MAGIC); a.bcc(NE, 'cont')
    w(0x42B9); l(MODE)
    w(0x223C); l(strs['S_OFF']); w(0x41F9); l(strs['S_FLT']); w(0x93C9, 0x7000 | C.OV_TEXT, 0x4EB9); l(cs['OVS'])
    a.label('cont')
    a.orig(RT_HOOK, 8)                                                    # verschobene Originalbefehle
    w(0x4EF9); l(RT_HOOK + 8)
    # ---------------- ENC: Encoder-Slot des Cores: Knopf gedreht, waehrend RETRIG gehalten -> Loslassen beendet nichts
    a.label('ENC')
    w(0x4878, KEY_RETRIG, 0x4EB9); l(C.HELD); w(0x588F, 0x4A80); a.bcc(EQ, 'ez')
    w(0x42B9); l(RH)
    a.label('ez')
    w(0x7000, 0x4E75)
    code = a.done()
    check_cf(code, M_RT)
    return code, a.lab


def build_led():
    """FLED: Knopf-LEDs im Hauptbildschirm. PatternGridView (Frame 0x40021d22) setzt die 12 Knopf-LEDs (Vektor 0x404a8bac) nur
    bei gehaltenem Trig (p-locks); sonst schaltet das Frame-Ende jede nicht beanspruchte LED aus. Im Filter-Modus beansprucht
    FLED zu Beginn des Frames (vor der Auswahlmodus-Abfrage) PITCH, DECAY, COLOR, SHAPE = an (0x40005f86, Ebene 0x404a8cb8,
    erster Anspruch gilt). Ansichten, die vorher dran sind, behalten ihre LEDs; ohne Filter-Modus alles wie bisher.
    Haken: 0x40021e0e jsr (Vektor-Freigabe, Argument liegt auf dem Stapel) -> jmp FLED; d2 = LED-Steuerung der Firmware."""
    a = A(M_LED); w, l = a.w, a.l32
    a.label('FLED')
    w(0x2039); l(MODE); w(0x0C80); l(MAGIC); a.bcc(NE, 'lo')
    w(0x4FEF, 0xFFF8, 0x48D7, 0x0808)                                     # d3/a3 sichern
    w(0x2679); l(LED_VEC)                                                 # a3 = Knopf-LEDs
    w(0x7600 | NLED)                                                      # d3 = Anzahl
    a.label('ll')
    w(0x4879); l(LED_LAYER); w(0x4878, LED_ON)                           # Ebene, Zustand an
    w(0x2F1B, 0x2F02)                                                     # LED (a3)+, Steuerung d2
    w(0x4EB9); l(LED_SET); w(0x4FEF, 0x0010)
    w(0x5383); a.bcc(NE, 'll')                                            # subq #1,d3
    w(0x4CD7, 0x0808, 0x4FEF, 0x0008)
    a.label('lo')
    a.orig(LED_HOOK, 6)                                                   # verschobener Befehl (Vektor freigeben)
    w(0x4EF9); l(LED_HOOK + 6)
    code = a.done()
    E.check(code, M_LED)
    return code, a.lab


def build_sl():
    """FH: Sound-Slot des Cores (a0 Satz, a1 Sound, d1 = 0 Laden / 1 Speichern). Satz +88 Cutoff XOR 0x7f00, +90 Resonanz,
    +64 Env XOR 64, +65 Decay XOR 64 (Null = Default: alte Sounds laden mit offenem Filter)."""
    a = A(M_SL); w, l = a.w, a.l32
    a.label('FH')
    w(0x4A81); a.bcc(NE, 'sv')
    w(0x3228, 0x0058, 0x0A81); l(TOP); w(0x3341, 0x004C)                  # Cutoff
    w(0x3228, 0x005A, 0x3341, 0x004E)                                     # Resonanz
    w(0x73A8, 0x0040, 0x0A81); l(0x40); w(0xE189, 0x3341, 0x0050)         # Env
    w(0x73A8, 0x0041, 0x0A81); l(0x40); w(0xE189, 0x3341, 0x0052)         # Decay
    w(0x4E75)
    a.label('sv')
    w(0x3229, 0x004C, 0x0A81); l(TOP); w(0x3141, 0x0058)
    w(0x3229, 0x004E, 0x3141, 0x005A)
    w(0x73A9, 0x0050, 0x0A81); l(0x40); w(0xE189)
    w(0x71A9, 0x0052, 0x0A80); l(0x40); w(0x8280, 0x3141, 0x0040)
    w(0x4E75)
    code = a.done()
    E.check(code, M_SL)
    return code, a.lab


def build_pt():
    """Namen der Deskriptoren, Popup-Texte"""
    code = bytearray()
    names = {}
    for i, d in enumerate(DESCS):
        for j, s in ((5, d[5]), (6, d[6])):
            names[(i, j)] = M_PT + len(code); code += s.encode() + b'\0'
    for name, s in (('S_FLT', 'FILTER'), ('S_ON', 'ON'), ('S_OFF', 'OFF')):
        names[name] = M_PT + len(code); code += s.encode() + b'\0'
    return bytes(code), {}, names


def desc_rows(names):
    rows = b''
    for i, (k, dflt, cc, nrpn, key, _, _, _) in enumerate(DESCS):
        rows += struct.pack('>14I', 7, k, 0, TOP, dflt, 0, cc, nrpn, 0, 0x600, key, names[(i, 5)], AMP, names[(i, 6)])
    return rows


def build():
    cs = core.sym()
    gt, kt, dt, nt = tables()
    ker, lk = build_ker()
    co, lo = build_co()
    lab = dict(lk, GT=M_GT, KT=M_KT, DT=M_DT, NT=M_NT, **lo)
    po, dsp, ld = build_dsp(lab); lab.update(ld)
    pt, lp, names = build_pt(); lab.update(lp)
    ui, lu = build_ui(cs, names); lab.update(lu)
    sl, ls = build_sl(); lab.update(ls)
    rt, lr = build_rt(cs, names); lab.update(lr)
    ld_, ll = build_led(); lab.update(ll)
    parts = {M_PO: po, M_DSP: dsp, M_KER: ker, M_GT: struct.pack('>65i', *gt), M_KT: struct.pack('>65i', *kt),
             M_DT: struct.pack('>65i', *dt), M_NT: struct.pack('>65i', *nt), M_CO: co, M_UI: ui, M_RT: rt, M_LED: ld_, M_SL: sl, M_PT: pt, M_ST: bytes(6 * TS + 12)}
    return parts, lab, names


def tweak(img):
    base = apply(img, core.tweak(img))
    parts, lab, names = build()
    W = Writes(base)
    for va, b in parts.items():
        W.mask(va, b, SIZE[va])
    W.hook(POST_HOOK, jsr(VOLDIST), jsr(lab['POST']))
    W.hook(KNOB_SLOT, struct.pack('>I', KNOB_ORIG), struct.pack('>I', lab['KNOB']))
    W.hook(KEY_HOOK, KEY_CK, jsr(lab['KEYH']) + bytes.fromhex('4e71') * 3)
    W.hook(RT_HOOK, RT_CK, jmp(lab['RT']) + bytes.fromhex('4e71'))
    core.slot_write(W, 'track-filter', lab['ENC'])
    W.hook(LED_HOOK, LED_CK, jmp(lab['FLED']))
    core.sslot_write(W, 'track-filter', lab['FH'])
    lo = C.DESC(1)
    for i in range(4):
        assert struct.unpack_from('>i', base, lo - BASE + 0x38 * i)[0] == -1, f"Deskriptor {i + 1} nicht frei"
    W.put(lo, desc_rows(names))
    hooks = [POST_HOOK, KNOB_SLOT, KEY_HOOK, RT_HOOK, LED_HOOK]
    return patch('track-filter', 13, 'Track filter',
                 ["12 dB low-pass filter per track with light saturation, cutoff, resonance, envelope depth and decay.",
                  "RETRIG + GATE = filter mode on: PITCH = cutoff, DECAY = env decay, COLOR = resonance, SHAPE = env depth;"
                  " tap RETRIG = off (holding RETRIG while turning a knob keeps the mode).",
                  "Four real parameters (p-locks, LFO, velocity, CC 74 / 71), saved with the sound. Cutoff 127 = off.",
                  "Erzeugt von v2/g2_trackfilter.py."], W,
                 requires=['core'], hooks=[f"{x:#x}" for x in hooks],
                 memory=[{"va": f"{M_ST:#x}", "size": 6 * TS + 12, "ram": True, "use": "filter state + mode"}],
                 symbols={k: f"{lab[k]:#x}" for k in ('POST', 'TRACK', 'KERNEL', 'COEF', 'INTERP', 'KNOB', 'OBJS', 'KEYH', 'RT', 'FLED',
                                                       'FH', 'GT', 'KT', 'DT')},
                 params={"state": f"{M_ST:#x}", "ts": TS, "mode": f"{MODE:#x}", "rh": f"{RH:#x}", "key_retrig": KEY_RETRIG, "magic": f"{MAGIC:#x}", "k": [K_CUT, K_RES, K_ENV, K_DEC],
                         "kmap": list(KMAP)})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    parts, lab, _ = build()
    print({f"{va:#x}": len(b) for va, b in parts.items()}, {k: hex(v) for k, v in lab.items() if k.isupper()})
