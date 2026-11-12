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
import collections, math, struct, sys
from common import *                 # noqa: F401,F403
import common as C
import g2_core as core
import cfemac as E
from cfasm import asm, done as adone

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
GP = M_ST + 6 * TS + 8               # smp24: GATE gedrueckt, Umschalten beim Loslassen (PLAY dazwischen -> nicht umschalten)
KEY_RETRIG = 4                       # RETRIG (Tastencode; die Firmware fragt HELD(4) in der Trig-Ansicht ab, LED 0x1b)
MAGIC = 0x464C5431                   # 'FLT1'
# ---- Firmware
POST_HOOK, VOLDIST = 0x40059852, 0x40056F58
KNOB_SLOT, KNOB_ORIG = 0x401005A8, 0x4001E814
RT_HOOK, RT_CK = 0x4001C4BA, (8, '3ce931d7357a496e83843a4e65042d557eab086f9393fd43ae72ba28e3fad05f')
K_PRESS, K_FUNC, K_REL = 0x400724A0, 0x40072490, 0x40072470   # Ereignis: gedrueckt (keine Wiederholung) / FUNC / losgelassen
# smp24 Filter-Reset (Pip 08.11.: GATE + PLAY, wie LFO + PLAY): GATE (7) schaltet erst beim Loslassen um (Haken GREL am Anfang des
#   GATE-Zweigs im Hauptbildschirm), PLAY (10) im Transport-Handler 0x4002439a (Haken PLH) bei gehaltenem GATE -> FRS.
KEY_GATE, KEY_PLAY = 7, 10
GREL_HOOK, GREL_CK, GREL_BACK, BIT4 = 0x4001C326, (8, 'dd2eb0ca5369c1127f3bc0a219b944ec307aae798df6163db26f93f1cf2e2190'), 0x4001C32E, 0x40072434
PLH_HOOK, PLH_CK = 0x400243D6, (6, 'ed188f2fa8550f90b33fee758d5276a0304b6f5e8289a98a3cac5478ec7f0485')   # moveq #10,d0 ; cmp.l d4,d0 ; beq.b
PL_PLAY, PL_NEXT, PL_DONE = 0x4002441A, 0x400243DC, 0x40024650      # PLAY-Zweig ; naechster Vergleich ; Ende (d0 = d4.b)
KIT_OF, SOBJ, SETP = 0x4000EB9C, 0x400097F0, 0x4000B274             # Kit(A()) ; Klang-Objekt(Kit, Spur) ; Parameter setzen
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
    a = A(M_PO)
    asm(a, f'''
    ; ---------------- POST: statt jsr Volume/Dist; danach je Track TRACK
    POST:   move.l  8(sp),-(sp)              ; Volume + Dist wie bisher
            move.l  8(sp),-(sp)
            jsr     {VOLDIST:#x}
            addq.l  #8,sp
            lea     -56(sp),sp
            movem.l d2-d7/a2-a6,(sp)
            move.l  macsr,d0
            move.l  d0,44(sp)                ; MACSR sichern (44(sp))
            move.l  #0xa0,macsr              ; fraktional, gesaettigt
            movclr  acc0,d0                  ; Akkus leer (wie die Firmware sie erwartet)
            movclr  acc1,d0
            movclr  acc2,d0
            movclr  acc3,d0
            move.l  16(a3),d0                ; Trig-Bits (a3+16) -> 48(sp)
            move.l  d0,48(sp)
            movea.l 64(sp),a5
            lea     14(a5),a5                ; a5 = Param + 14 (Track 0)
            movea.l 60(sp),a6                ; a6 = TRK ; a4 = Zustand
            lea     {M_ST:#x},a4
            moveq   #6,d0                    ; 6 Tracks -> 52(sp)
            move.l  d0,52(sp)
    tl:     move.l  48(sp),d0                ; d0 = Trig-Bit ; jsr TRACK (Adresse unten)
            moveq   #1,d1
            and.l   d1,d0
            jsr     {M_DSP:#x}
            move.l  48(sp),d0                ; Trig-Bits >> 1
            lsr.l   #1,d0
            move.l  d0,48(sp)
            lea     {TS}(a4),a4              ; naechster Track: Zustand, Parameter, Puffer
            lea     66(a5),a5
            lea     128(a6),a6
            subq.l  #1,52(sp)
            bne     tl
            movclr  acc0,d0                  ; Akkus leer zurueck
            movclr  acc1,d0
            movclr  acc2,d0
            movclr  acc3,d0
            move.l  44(sp),d0
            move.l  d0,macsr
            movem.l (sp),d2-d7/a2-a6
            lea     56(sp),sp
            rts
    ''')
    post = adone(a); E.check(post, M_PO); lpost = dict(a.lab)
    a = A(M_DSP)
    asm(a, f'''
    ; ---------------- TRACK (d0 Trig, a4 Zustand, a5 Parameter, a6 Puffer); zerstoert d0-d7, a0-a3
    TRACK:  move.l  8(a4),d4                 ; d4 = Huellkurve
            tst.l   d0
            beq     nt
            move.l  #0x7fffffff,d4           ; Trig: 1
            bra     eok
    nt:     tst.l   d4
            beq     eok
            mvs.w   {O_DEC}(a5),d0
            lea     {lab['DT']:#x},a0
            jsr     {lab['INTERP']:#x}       ; d0 = Faktor pro Block
            mac     d0,d4,acc0
            movclr  acc0,d4
            cmpi.l  #0x10000,d4
            bcc     eok
            moveq   #0,d4                    ; zu klein: aus
    eok:    move.l  d4,8(a4)
            mvs.w   {O_CUT}(a5),d5           ; d5 = Cutoff
    ; Aus (Spur bitgenau) nur, wenn der Knopf ganz offen ist und die Huellkurve ihn nicht nach unten zieht. Sonst bleibt der
    ; Filter an, auch wenn die Huellkurve ueber 127 hinaus will (v2 schaltete dann ab und beim Zurueckkommen neu an: Klicken).
            cmpi.l  #{TOP:#x},d5
            blt     act
            tst.l   d4
            beq     byp
            mvs.w   {O_ENV}(a5),d0
            cmpi.l  #0x4000,d0
            bge     byp
    act:    tst.l   d4
            beq     cl
            mvs.w   {O_ENV}(a5),d0           ; d0 = 2 (Env - Mitte)
            subi.l  #0x4000,d0
            add.l   d0,d0
            mac     d0,d4,acc0
            movclr  acc0,d0
            add.l   d0,d5                    ; Cutoff + Tiefe * Huellkurve
    cl:     tst.l   d5
            bpl     c0
            moveq   #0,d5
    c0:     cmpi.l  #{TOP:#x},d5
            ble     up
            move.l  #{TOP:#x},d5             ; begrenzen: Filter bleibt an (~20 kHz)
    ; Filter an: Ueberblendung hoch (n -> n+1, bis 8)
    up:     move.l  {T_N}(a4),d0
            move.l  d0,{T_NO}(a4)
            moveq   #{NFADE},d1
            cmp.l   d1,d0
            bge     on
            addq.l  #1,d0
            move.l  d0,{T_N}(a4)
            bra     on
    ; ganz offen
    byp:    move.l  {T_N}(a4),d0
            bne     fo
            clr.l   12(a4)                   ; ausgeblendet: Spur unveraendert, Zustand vergessen
            rts
    fo:     move.l  d0,{T_NO}(a4)            ; noch eingeblendet: weiter filtern, ausblenden
            subq.l  #1,d0
            move.l  d0,{T_N}(a4)
            move.l  #{TOP:#x},d5
    on:     move.l  d5,d0
            lea     {lab['GT']:#x},a0
            jsr     {lab['INTERP']:#x}
            move.l  d0,d6                    ; d6 = G = g/4
            mvs.w   {O_RES}(a5),d0
            lea     {lab['KT']:#x},a0
            jsr     {lab['INTERP']:#x}
            move.l  d0,d7                    ; d7 = K = k/2
            move.l  d5,d0
            lea     {lab['NT']:#x},a0
            jsr     {lab['INTERP']:#x}       ; d0 = kleinstes K bei diesem Cutoff
            cmp.l   d0,d7                    ; K = max(K, Kmin)
            bge     kk
            move.l  d0,d7
    kk:     jsr     {lab['COEF']:#x}
    ; ---------------- Kopf des Kernels (Start, stiller Block), dann KERNEL
            movea.l a6,a0
            lea     128(a6),a1
            tst.l   12(a4)
            bne     run
            move.l  (a0),d0                  ; Start: s1 = 0, s2 = x0/2
            asr.l   #1,d0
            move.l  d0,4(a4)
            clr.l   (a4)
            moveq   #1,d0
            move.l  d0,12(a4)
            jmp     {lab['KERNEL']:#x}
    run:    movea.l a0,a2
            moveq   #0,d0
            moveq   #7,d1
    zl:     or.l    (a2)+,d0
            or.l    (a2)+,d0
            or.l    (a2)+,d0
            or.l    (a2)+,d0
            subq.l  #1,d1
            bpl     zl
            tst.l   d0
            bne     kg
            move.l  (a4),d0                  ; Block still: Zustand klein -> nichts tun
            bpl     p1
            neg.l   d0
    p1:     move.l  4(a4),d1
            bpl     p2
            neg.l   d1
    p2:     or.l    d1,d0
            cmpi.l  #0x1000,d0
            bcc     kg
            clr.l   (a4)
            clr.l   4(a4)
            rts
    kg:     jmp     {lab['KERNEL']:#x}
    ''')
    code = adone(a)
    E.check(code, M_DSP)
    return post, code, dict(a.lab, **lpost)


# KERNEL: Register laden (d1 s1, d2 s2, d3 c1, d4 c2, d5 e, a2 a3, d7 1)
KER_REGS = '''
            movem.l (a4),d1-d2
            movem.l 16(a4),d3-d5
            movea.l 28(a4),a2
            move.l  #0x7fffffff,d7'''
# KERNEL: ein Sample (a0 Puffer); Ergebnis in acc2
KER_BODY = '''
            move.l  (a0),d0                  ; x
            mac     d0,d0,acc3
            movclr  acc3,d6                  ; x^2
            asr.l   #2,d6
            eori.l  #0x7fffffff,d6           ; 1 - x^2/4
            asr.l   #1,d0                    ; x/2
            mac     d0,d6,acc3
            movclr  acc3,d0                  ; u
            move.l  d2,acc2                  ; y = s2 ...
            mac     d3,d1,acc0
            mac     d4,d0,acc0
            msac    d4,d2,acc0               ; s1'
            mac     d5,d2,acc1
            mac     d4,d1,acc1
            mac     a2,d0,acc1
            mac     a2,d0,acc1               ; s2'
            movclr  acc0,d1
            movclr  acc1,d2
            mac     d1,d1,acc3               ; Resonanz weich begrenzen:
            movclr  acc3,d6
            asr.l   #2,d6
            eori.l  #0x7fffffff,d6           ; s1 (1 - s1^2/4)
            mac     d1,d6,acc3
            movclr  acc3,d1
            mac     d2,d7,acc2               ; ... + s2\''''


def build_ker():
    a = A(M_KER)
    asm(a, f'''
    ; ---------------- KERNEL (a4 Zustand mit Koeffizienten, a6 Puffer): 32 Samples
    KERNEL:
    go:     move.l  {T_N}(a4),d0
            add.l   {T_NO}(a4),d0
            cmpi.l  #{2 * NFADE},d0
            beq     full
    ; Ueberblendung (n_alt -> n_neu): Ausgang = (1 - F) x + F y, F linear ueber den Block von n_alt/8 nach n_neu/8
            move.l  {T_NO}(a4),d0            ; F = n_alt << 28 (8 -> 0x7fffffff)
            moveq   #28,d1
            lsl.l   d1,d0
            tst.l   d0
            bpl     f0
            subq.l  #1,d0
    f0:     move.l  {T_N}(a4),d1             ; Schritt pro Sample = (n_neu - n_alt) << 23
            sub.l   {T_NO}(a4),d1
            moveq   #23,d6
            asl.l   d6,d1
            move.l  a4,-(sp)                 ; a4 und Schritt auf den Stack
            move.l  d1,-(sp){KER_REGS}
            movea.l d0,a3                    ; a3 = F, a4 = 1 - F
            move.l  d7,d6
            sub.l   d0,d6
            movea.l d6,a4
    lpf:{KER_BODY}
            movclr  acc2,d0                  ; y
            mac     a3,d0,acc2
            move.l  (a0),d6
            mac     a4,d6,acc2
            movclr  acc2,d0                  ; F y + (1 - F) x
            move.l  d0,(a0)+
            adda.l  (sp),a3
            suba.l  (sp),a4
            cmpa.l  a1,a0
            bne     lpf
            movea.l 4(sp),a4
            addq.l  #8,sp
            movem.l d1-d2,(a4)
            rts
    full:{KER_REGS}
    lp:{KER_BODY}
            movclr  acc2,d0
            move.l  d0,(a0)+
            cmpa.l  a1,a0
            bne     lp
            movem.l d1-d2,(a4)
            rts
    ''')
    code = adone(a)
    E.check(code, M_KER)
    return code, a.lab


def build_co():
    a = A(M_CO)
    asm(a, f'''
    ; ---------------- COEF (d6 G = g/4, d7 K = k/2, a4 Zustand) -> c1, c2, e, a3
    COEF:   move.l  d6,d0
            asr.l   #4,d0                    ; d0 = G/16
            move.l  #0x1000000,acc0
            mac     d0,d6,acc0
            mac     d0,d6,acc0
            mac     d0,d7,acc0
            movclr  acc0,d1                  ; d1 = D/128 = 2^-7 + G^2/8 + GK/16
            move.l  d1,d2
            moveq   #13,d3
            lsr.l   d3,d2
            move.l  #0x7fffffff,d3
            divu.l  d2,d3                    ; d3 = 0x7fffffff / (d1 >> 13)
            moveq   #11,d2
            lsl.l   d2,d3                    ; H0 = d3 << 11 ~ 1/D
            mac     d1,d3,acc0
            movclr  acc0,d2                  ; D H0 / 128
            move.l  #0x1000000,d0
            sub.l   d2,d0
            asl.l   #7,d0                    ; d0 = 1 - D H0
            move.l  d3,acc0
            mac     d3,d0,acc0
            movclr  acc0,d3                  ; a1 = H0 (2 - D H0)
            move.l  d3,d0
            add.l   d0,d0
            bchg.l  #31,d0
            move.l  d0,16(a4)                ; c1 = 2 a1 - 1
            mac     d6,d3,acc0
            movclr  acc0,d0
            asl.l   #3,d0
            move.l  d0,20(a4)                ; c2 = 8 G a1
            mac     d6,d0,acc0
            mac     d6,d0,acc0
            movclr  acc0,d1                  ; a3 = 2 G c2
            tst.l   d1
            bne     a3
            moveq   #1,d1
    a3:     move.l  d1,28(a4)
            add.l   d1,d1
            move.l  #0x80000000,d0
            sub.l   d1,d0
            move.l  d0,24(a4)                ; e = 1 - 2 a3
            rts
    ; ---------------- INTERP (a0 Tabelle, d0 Wort) -> d0 ; zerstoert d1-d3
    INTERP: tst.l   d0
            bpl     i1
            moveq   #0,d0
    i1:     cmpi.l  #{TOP:#x},d0
            ble     i2
            move.l  #{TOP:#x},d0
    i2:     move.l  d0,d1
            moveq   #9,d2
            asr.l   d2,d1                    ; j = w >> 9
            move.l  d0,d2
            andi.l  #0x1ff,d2
            moveq   #22,d3
            lsl.l   d3,d2                    ; f = (w & 511) << 22
            move.l  0(a0,d1.l*4),d3          ; T[j], T[j+1] - T[j]
            move.l  4(a0,d1.l*4),d1
            sub.l   d3,d1
            mac     d1,d2,acc0
            movclr  acc0,d0
            add.l   d3,d0
            rts
    ''')
    code = adone(a)
    E.check(code, M_CO)
    return code, a.lab


def build_ui(cs, strs):
    text = f'''
    ; ---------------- KNOB: Vtable-Slot 124 (Ansicht, Knopf, FUNC, -1) -> d0 Deskriptor
    KNOB:   bsr     OBJS
            move.l  16(sp),-(sp)
            move.l  16(sp),-(sp)
            move.l  16(sp),-(sp)
            move.l  16(sp),-(sp)
            jsr     {KNOB_ORIG:#x}
            lea     16(sp),sp
            move.l  {MODE:#x},d1
            cmpi.l  #{MAGIC:#x},d1
            bne     ko
            move.l  8(sp),d1
            subq.l  #2,d1
            cmpi.l  #3,d1                    ; PITCH..SHAPE
            bhi     ko
            lea     KMAP,a0
            mvz.b   0(a0,d1.l),d0
    ko:     rts
    ; ---------------- OBJS: Formatierer der vier UI-Objekte, keine Sonderzeichnung
    OBJS:   lea     {REC + 100:#x},a0
            lea     FMTS,a1
            moveq   #4,d1
    ob:     move.l  (a1)+,d0
            move.l  d0,32(a0)
            clr.l   44(a0)
            lea     100(a0),a0
            subq.l  #1,d1
            bne     ob
            rts
    ; ---------------- KEYH: GATE (Taste 7, Druecken ohne FUNC; a2 = Ansicht). RETRIG gehalten -> Filter-Modus an.
    KEYH:   pea     {KEY_RETRIG}.w
            jsr     {C.HELD:#x}
            addq.l  #4,sp
            tst.l   d0
            beq     norm
            clr.l   {RH:#x}                  ; RETRIG wurde benutzt: Loslassen beendet nichts
            move.l  {MODE:#x},d0
            cmpi.l  #{MAGIC:#x},d0
            beq     kx                       ; schon an
            move.l  #{MAGIC:#x},d1
            move.l  d1,{MODE:#x}
            move.l  #{strs['S_ON']:#x},d1
            lea     {strs['S_FLT']:#x},a0
            suba.l  a1,a1
            moveq   #{C.OV_TEXT},d0
            jmp     {cs['OVS']:#x}
    kx:     rts
    norm:   moveq   #1,d0                    ; smp24: umschalten erst beim Loslassen (GREL)
            move.l  d0,{GP:#x}
            rts
'''
    def tail(end):                           # Formatierer der vier Deskriptoren, Knopf -> Deskriptor
        pad = -end % 4
        fm = end + pad
        return bytes(pad) + struct.pack('>4I', *[d[7] for d in DESCS]) + bytes(KMAP), {'FMTS': fm, 'KMAP': fm + 16}
    return asm2(M_UI, text, tail)


def build_rt(cs, strs):
    """RT: RETRIG im Hauptbildschirm (Haken 0x4001c4ba, d3 = Ereignis, jedes Ereignis der Taste): im Modus kurz antippen
    (Druecken + Loslassen ohne Knopfdrehung und ohne GATE dazwischen) beendet den Filter-Modus."""
    a = A(M_RT)
    asm(a, f'''
    RT:     move.l  d3,-(sp)
            jsr     {K_FUNC:#x}
            addq.l  #4,sp
            tst.b   d0
            bne     cont                     ; FUNC + RETRIG: Firmware
            move.l  d3,-(sp)
            jsr     {K_PRESS:#x}
            addq.l  #4,sp
            tst.b   d0
            beq     rel
            moveq   #0,d1                    ; Druecken: im Modus RH = 1, sonst 0
            move.l  {MODE:#x},d0
            cmpi.l  #{MAGIC:#x},d0
            bne     st
            moveq   #1,d1
    st:     move.l  d1,{RH:#x}
            bra     cont
    rel:    move.l  d3,-(sp)
            jsr     {K_REL:#x}
            addq.l  #4,sp
            tst.b   d0
            beq     cont
            tst.l   {RH:#x}                  ; Loslassen nach blossem Antippen: Modus aus
            beq     cont
            clr.l   {RH:#x}
            move.l  {MODE:#x},d0
            cmpi.l  #{MAGIC:#x},d0
            bne     cont
            clr.l   {MODE:#x}
            move.l  #{strs['S_OFF']:#x},d1
            lea     {strs['S_FLT']:#x},a0
            suba.l  a1,a1
            moveq   #{C.OV_TEXT},d0
            jsr     {cs['OVS']:#x}
    cont:   orig    {RT_HOOK:#x},8           ; verschobene Originalbefehle
            jmp     {RT_HOOK + 8:#x}
    ; ---------------- ENC: Encoder-Slot des Cores: Knopf gedreht, waehrend RETRIG gehalten -> Loslassen beendet nichts
    ENC:    pea     {KEY_RETRIG}.w
            jsr     {C.HELD:#x}
            addq.l  #4,sp
            tst.l   d0
            beq     ez
            clr.l   {RH:#x}
    ez:     moveq   #0,d0
            rts
    ''')
    code = adone(a)
    check_cf(code, M_RT)
    return code, a.lab


def build_led():
    """FLED: Knopf-LEDs im Hauptbildschirm. PatternGridView (Frame 0x40021d22) setzt die 12 Knopf-LEDs (Vektor 0x404a8bac) nur
    bei gehaltenem Trig (p-locks); sonst schaltet das Frame-Ende jede nicht beanspruchte LED aus. Im Filter-Modus beansprucht
    FLED zu Beginn des Frames (vor der Auswahlmodus-Abfrage) PITCH, DECAY, COLOR, SHAPE = an (0x40005f86, Ebene 0x404a8cb8,
    erster Anspruch gilt). Ansichten, die vorher dran sind, behalten ihre LEDs; ohne Filter-Modus alles wie bisher.
    Haken: 0x40021e0e jsr (Vektor-Freigabe, Argument liegt auf dem Stapel) -> jmp FLED; d2 = LED-Steuerung der Firmware."""
    a = A(M_LED)
    asm(a, f'''
    FLED:   move.l  {MODE:#x},d0
            cmpi.l  #{MAGIC:#x},d0
            bne     lo
            lea     -8(sp),sp
            movem.l d3/a3,(sp)               ; d3/a3 sichern
            movea.l {LED_VEC:#x},a3          ; a3 = Knopf-LEDs
            moveq   #{NLED},d3               ; d3 = Anzahl
    ll:     pea     {LED_LAYER:#x}           ; Ebene, Zustand an
            pea     {LED_ON}.w
            move.l  (a3)+,-(sp)              ; LED (a3)+, Steuerung d2
            move.l  d2,-(sp)
            jsr     {LED_SET:#x}
            lea     16(sp),sp
            subq.l  #1,d3
            bne     ll
            movem.l (sp),d3/a3
            lea     8(sp),sp
    lo:     orig    {LED_HOOK:#x},6          ; verschobener Befehl (Vektor freigeben)
            jmp     {LED_HOOK + 6:#x}
    ''')
    code = adone(a)
    E.check(code, M_LED)
    return code, a.lab


def build_sl():
    """FH: Sound-Slot des Cores (a0 Satz, a1 Sound, d1 = 0 Laden / 1 Speichern). Satz +88 Cutoff XOR 0x7f00, +90 Resonanz,
    +64 Env XOR 64, +65 Decay XOR 64 (Null = Default: alte Sounds laden mit offenem Filter)."""
    a = A(M_SL)
    asm(a, f'''
    FH:     tst.l   d1
            bne     sv
            move.w  88(a0),d1                ; Cutoff
            eori.l  #{TOP:#x},d1
            move.w  d1,{20 + O_CUT}(a1)
            move.w  90(a0),d1                ; Resonanz
            move.w  d1,{20 + O_RES}(a1)
            mvz.b   64(a0),d1                ; Env
            eori.l  #64,d1
            lsl.l   #8,d1
            move.w  d1,{20 + O_ENV}(a1)
            mvz.b   65(a0),d1                ; Decay
            eori.l  #64,d1
            lsl.l   #8,d1
            move.w  d1,{20 + O_DEC}(a1)
            rts
    sv:     move.w  {20 + O_CUT}(a1),d1
            eori.l  #{TOP:#x},d1
            move.w  d1,88(a0)
            move.w  {20 + O_RES}(a1),d1
            move.w  d1,90(a0)
            mvz.b   {20 + O_ENV}(a1),d1
            eori.l  #64,d1
            lsl.l   #8,d1
            mvz.b   {20 + O_DEC}(a1),d0
            eori.l  #64,d0
            or.l    d0,d1
            move.w  d1,64(a0)                ; Env << 8 | Decay
            rts
    ''')
    code = adone(a)
    E.check(code, M_SL)
    return code, a.lab


def build_pt():
    """Namen der Deskriptoren, Popup-Texte"""
    code = bytearray()
    names = {}
    for i, d in enumerate(DESCS):
        for j, s in ((5, d[5]), (6, d[6])):
            names[(i, j)] = M_PT + len(code); code += s.encode() + b'\0'
    for name, s in (('S_FLT', 'FILTER'), ('S_ON', 'ON'), ('S_OFF', 'OFF'), ('S_RST', 'RESET')):
        names[name] = M_PT + len(code); code += s.encode() + b'\0'
    return bytes(code), {}, names


def fr_text(cs, names):
    """smp24: GREL (GATE-Zweig, a2 Ansicht, d3 Ereignis), PLH (Transport-Handler, d2 Ereignis, d4 Taste), FRS (Filter der
    ausgewaehlten Spur auf die Standardwerte, nur der Sound; p-locks bleiben)."""
    return f"""
    ; GATE im Hauptbildschirm (jedes Ereignis der Taste): Loslassen ohne FUNC nach einem Druecken -> Gate umschalten wie bisher
    GREL:   tst.l   {GP:#x}
            beq     gr9
            move.l  d3,-(sp)
            jsr     {K_REL:#x}
            addq.l  #4,sp
            tst.b   d0
            beq     gr9
            clr.l   {GP:#x}
            move.l  d3,-(sp)
            jsr     {K_FUNC:#x}
            addq.l  #4,sp
            tst.b   d0
            bne     gr9
            pea     0x2d.w
            move.l  a2,-(sp)
            jsr     {CLICK_ACT:#x}
            addq.l  #8,sp
    gr9:    move.l  d3,-(sp)
            jsr     {BIT4:#x}
            jmp     {GREL_BACK:#x}
    ; Transport-Handler: PLAY bei gehaltenem GATE -> Filter-Reset (nur beim Druecken), jedes PLAY-Ereignis verbraucht
    PLH:    moveq   #{KEY_PLAY},d0
            cmp.l   d4,d0
            beq     ph1
            jmp     {PL_NEXT:#x}
    ph1:    pea     {KEY_GATE}.w
            jsr     {C.HELD:#x}
            addq.l  #4,sp
            tst.l   d0
            bne     ph2
            jmp     {PL_PLAY:#x}
    ph2:    clr.l   {GP:#x}
            move.l  d2,-(sp)
            jsr     {K_PRESS:#x}
            addq.l  #4,sp
            tst.b   d0
            beq     ph3
            jsr     FRS
    ph3:    moveq   #1,d4
            jmp     {PL_DONE:#x}
"""


def frs_text(cs, names):
    return f"""
    ; FRS: Filter der ausgewaehlten Spur -> Cutoff 127, Reso 0, Env Mitte, Decay 64 (Setter der Firmware wie Pan), Popup
    FRS:    lea     -12(sp),sp
            movem.l d2-d4,(sp)
            jsr     {C.SEL_A:#x}
            move.l  d0,-(sp)
            jsr     {KIT_OF:#x}
            move.l  d0,d2
            jsr     {C.SEL_A:#x}
            move.l  d0,(sp)
            jsr     {C.SEL_B:#x}
            move.l  d0,(sp)
            jsr     {C.SEL_C:#x}
            move.l  d0,d3
            move.l  d3,(sp)
            move.l  d2,-(sp)
            jsr     {SOBJ:#x}
            addq.l  #8,sp
            move.l  d0,d4
            moveq   #1,d2                    ; Deskriptor 1..4 (Cutoff, Reso, Env, Decay)
    fr1:    pea     1.w
            clr.l   -(sp)
            move.l  d3,-(sp)
            lea     FRV,a0
            mvz.w   -2(a0,d2.l*2),d0
            move.l  d0,-(sp)
            move.l  d2,-(sp)
            move.l  d4,-(sp)
            jsr     {SETP:#x}
            lea     24(sp),sp
            addq.l  #1,d2
            moveq   #5,d0
            cmp.l   d0,d2
            bne     fr1
            move.l  #{names['S_RST']:#x},d1
            lea     {names['S_FLT']:#x},a0
            suba.l  a1,a1
            moveq   #{C.OV_TEXT},d0
            jsr     {cs['OVS']:#x}
            movem.l (sp),d2-d4
            lea     12(sp),sp
            rts
    FRV:    dc.w    {', '.join(f'{d[1]:#x}' for d in DESCS)}
"""


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
    sl, ls = build_sl(); lab.update(ls)
    o1, o2 = M_PT + ((len(pt) + 3) & ~3), M_SL + ((len(sl) + 3) & ~3)
    lx = collections.defaultdict(int)
    for _ in range(3):
        a1 = A(o1); asm(a1, fr_text(cs, names), lx)
        a2 = A(o2); asm(a2, frs_text(cs, names), lx)
        lx = collections.defaultdict(int, {**a1.lab, **a2.lab})
    pt = pt + bytes(o1 - M_PT - len(pt)) + adone(a1, dict(lx))
    sl = sl + bytes(o2 - M_SL - len(sl)) + adone(a2, dict(lx)); lab.update(lx)
    ui, lu = build_ui(cs, names); lab.update(lu)
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
    W.hook(GREL_HOOK, GREL_CK, jmp(lab['GREL']) + bytes.fromhex('4e71'))
    W.hook(PLH_HOOK, PLH_CK, jmp(lab['PLH']))
    core.sslot_write(W, 'track-filter', lab['FH'])
    lo = C.DESC(1)
    for i in range(4):
        assert struct.unpack_from('>i', base, lo - BASE + 0x38 * i)[0] == -1, f"Deskriptor {i + 1} nicht frei"
    W.put(lo, desc_rows(names))
    hooks = [POST_HOOK, KNOB_SLOT, KEY_HOOK, RT_HOOK, LED_HOOK, GREL_HOOK, PLH_HOOK]
    return patch('track-filter', 13, 'Per Track LP Filter + Env Amt & Latched Filter Mode',
                 ["12 dB low-pass filter per track with light saturation, cutoff, resonance, envelope depth and decay.",
                  "RETRIG + GATE = filter mode on: PITCH = cutoff, DECAY = env decay, COLOR = resonance, SHAPE = env depth;"
                  " tap RETRIG = off (holding RETRIG while turning a knob keeps the mode).",
                  "Four real parameters (p-locks, LFO, velocity, CC 74 / 71), saved with the sound. Cutoff 127 = off.",
                  "Hold GATE + PLAY = filter reset of the selected track (cutoff 127, reso 0, env centre, decay 64; p-locks stay).",
                  "GATE now toggles on release (so GATE + PLAY does not toggle the gate).",
                  "Erzeugt von v2/g2_trackfilter.py."], W,
                 requires=['core'], hooks=[f"{x:#x}" for x in hooks],
                 memory=[{"va": f"{M_ST:#x}", "size": 6 * TS + 12, "ram": True, "use": "filter state + mode"}],
                 symbols={k: f"{lab[k]:#x}" for k in ('POST', 'TRACK', 'KERNEL', 'COEF', 'INTERP', 'KNOB', 'OBJS', 'KEYH', 'RT', 'FLED', 'GREL', 'PLH', 'FRS',
                                                       'FH', 'GT', 'KT', 'DT')},
                 params={"state": f"{M_ST:#x}", "ts": TS, "mode": f"{MODE:#x}", "rh": f"{RH:#x}", "key_retrig": KEY_RETRIG, "magic": f"{MAGIC:#x}", "k": [K_CUT, K_RES, K_ENV, K_DEC],
                         "kmap": list(KMAP)})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    parts, lab, _ = build()
    print({f"{va:#x}": len(b) for va, b in parts.items()}, {k: hex(v) for k, v in lab.items() if k.isupper()})
