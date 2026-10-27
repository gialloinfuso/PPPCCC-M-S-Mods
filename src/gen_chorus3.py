#!/usr/bin/env python3
"""Chorus v9: 4 Modi (MODE-Byte 1..4: Chorus I, Chorus II, Dimension, Split) auf Basis von Chorus v8.
Modus-Tabelle je 16 B: [INC0, INCS, DSC, BASE_Q16]; BASE liegt im Zustand (BOFF), Ausgabe je Modus am Schleifenende.

Chorus v7 (Reverb-Platz): waermer + Fix fuer leises LFO-Geraeusch im Ausklang.
Aenderungen gegenueber v3:
  * Interpolation: ((s1-s0 + 2048) >> 12) * frac12 statt ((s1-s0) >> 15) * frac15. Die alte Form rundete kleine Differenzen
    immer ab -> pegelunabhaengiger Fehler (~-96 dBFS) mit Gleichanteil, der mit dem LFO wandert ('Extrasound' im Ausklang).
  * Sanfte Saettigung am Mono-Eingang: y = x - x^3/6 (normiert auf 2^30).
  * Tiefpass (1 Pol, ~7.5 kHz) auf beiden Wet-Abgriffen: y += 0.625*(x - y).
  * Grundverzoegerung 12 ms (576 Samples) statt 20 ms; Depth-Skala 6 statt 10 (bei 127: 4..20 ms).
  * LFO-Drift: langsamer Zufallslauf auf dem Phasenzuwachs (LCG je Block, Leck 1/1024).
Aufteilung: Setup bei MASK (0x40166760), Schleife bei M_LOOP, Abgriff/Filter bei M_TAP."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from gen_solo import A, BASE
MASK = 0x40166760
M_LOOP = 0x401601FC
M_TAP = 0x4015F50C
STATE = 0x4A338100            # +0 w, +4 Phase, +8 Magic, +16 Ring (2048 Longs), +0x2010 yL, +0x2014 yR, +0x2018 rnd, +0x201c drift
YL, YR, RND, DRIFT, DT, DC, BOFF = 0x2010, 0x2014, 0x2018, 0x201C, 0x2020, 0x2024, 0x2028   # DT/DC: Depth Ziel/aktuell (Q8)
RING_MASK = 0x7FF
BASE_Q16 = 576 << 16
INC0, INCS, DSC = 8948, 1761, 6
LCG_A, LCG_C = 1664525, 1013904223
NE, EQ, PL, LS, BRA = 0x6, 0x7, 0xA, 0x3, 0x0
MODE = 0x404E9B5D
M_TAB = 0x4014AB5C            # Modus-Tabelle (+ Namen, siehe gen_v9)
MODES = [(8948, 1761, 6, 576), (14000, 2800, 8, 672), (6000, 1000, 3, 480), (8948, 1761, 6, 576)]
DSHIFT = 8        # Depth-Ziel = D*DSC << DSHIFT (8: DSC ganze Einheiten; 5: Achtel)
MAXIDX = 3        # hoechster Tabellenindex (Modus-1)
EXTRA_OUT = True  # Dimension-/Split-Ausgabe (Modus 3/4)

def build_setup():
    a = A(MASK); w, l = a.w, a.l32
    w(0x4FEF, 0xFFD4)                       # lea -44(a7),a7
    w(0x48D7, 0x7CFC)                       # movem.l d2-d7/a2-a6,(a7)
    w(0x206F, 0x0038)                       # movea.l 56(a7),a0     params
    w(0x71D0, 0xE088)                       # mvz.w (a0),d0 ; lsr.l #8,d0     S
    w(0x73E8, 0x0002, 0xE089)               # mvz.w 2(a0),d1 ; lsr.l #8,d1    D
    w(0x7E00)                               # moveq #0,d7
    w(0x1E39); l(MODE)                      # move.b MODE,d7
    w(0x5387)                               # subq.l #1,d7
    w(0x0C87); l(MAXIDX)                    # cmpi.l #MAXIDX,d7
    a.bcc(LS, 'mok')
    w(0x7E00)                               # moveq #0,d7
    a.label('mok')
    w(0xE98F)                               # lsl.l #4,d7
    w(0x41F9); l(M_TAB)                     # lea M_TAB,a0
    w(0xD1C7)                               # adda.l d7,a0
    w(0x2828, 0x0004)                       # move.l 4(a0),d4       INCS
    w(0x4C00, 0x4800)                       # muls.l d0,d4
    w(0xD890)                               # add.l (a0),d4         + INC0
    w(0x2C28, 0x0008)                       # move.l 8(a0),d6       DSC
    w(0x4C06, 0x1800)                       # muls.l d6,d1          D*DSC
    w(0x45F9); l(STATE)                     # lea STATE,a2
    w(0x2C28, 0x000C)                       # move.l 12(a0),d6      BASE (Q16)
    w(0x2546, BOFF)                         # move.l d6,BOFF(a2)
    w(0xE189 if DSHIFT == 8 else 0xE189 | (DSHIFT << 9))   # lsl.l #DSHIFT,d1   Depth-Ziel
    w(0x2541, DT)                           # move.l d1,DT(a2)
    w(0x222A, DC)                           # move.l DC(a2),d1      Depth aktuell
    # Drift: rnd = rnd*A + C ; drift += rnd>>27 ; drift -= drift>>10 ; inc += 4*drift
    w(0x202A, RND)                          # move.l RND(a2),d0
    w(0x2C3C); l(LCG_A)                     # move.l #A,d6
    w(0x4C06, 0x0800)                       # muls.l d6,d0
    w(0x0680); l(LCG_C)                     # addi.l #C,d0
    w(0x2540, RND)                          # move.l d0,RND(a2)
    w(0x7E1B)                               # moveq #27,d7
    w(0xEEA0)                               # asr.l d7,d0           +-16
    w(0x2E2A, DRIFT)                        # move.l DRIFT(a2),d7
    w(0x2C07)                               # move.l d7,d6
    w(0xE086, 0xE486)                       # asr.l #8,d6 ; asr.l #2,d6   drift>>10
    w(0x9E86)                               # sub.l d6,d7
    w(0xDE80)                               # add.l d0,d7
    w(0x2547, DRIFT)                        # move.l d7,DRIFT(a2)
    w(0xDE87, 0xDE87)                       # add.l d7,d7 ; add.l d7,d7
    w(0xD887)                               # add.l d7,d4           inc += 4*drift
    w(0x2412)                               # move.l (a2),d2        w
    w(0x262A, 0x0004)                       # move.l 4(a2),d3       Phase
    w(0x47EA, 0x0010)                       # lea 16(a2),a3         Ring
    w(0x2A6A, YL)                           # movea.l YL(a2),a5
    w(0x2C6A, YR)                           # movea.l YR(a2),a6
    w(0x206F, 0x0034)                       # movea.l 52(a7),a0     in
    w(0x226F, 0x0030)                       # movea.l 48(a7),a1     out
    w(0x7A20)                               # moveq #32,d5
    w(0x4EF9); l(M_LOOP)                    # jmp Schleife
    return a.done()

def build_loop():
    a = A(M_LOOP); w, l = a.w, a.l32
    a.label('loop')
    w(0x2C18, 0xE486)                       # move.l (a0)+,d6 ; asr.l #2,d6     L/4
    w(0x2E18, 0xE487)                       # move.l (a0)+,d7 ; asr.l #2,d7     R/4
    w(0xDC87)                               # add.l d7,d6           x (+-2^30)
    # Saettigung: t = x>>15 ; c = ((t*t>>15)*t>>15)*5461>>15 ; x -= c<<15
    w(0x4EB9); l(0)                         # jsr SAT
    fs = len(a.b) - 4
    w(0x2786, 0x2C00)                       # move.l d6,0(a3,d2.l*4)
    # LFO (wie v3): Dreieck -> (3t - t^3)/2
    w(0xD684)                               # add.l d4,d3
    w(0x2C03)                               # move.l d3,d6
    a.bcc(PL, 'pos')
    w(0x4686)                               # not.l d6
    a.label('pos')
    w(0x0486); l(0x40000000)                # subi.l #$40000000,d6
    w(0xEE86, 0xE086)                       # asr #15
    w(0x2E06)                               # move.l d6,d7
    w(0x4C07, 0x7800)                       # muls.l d7,d7
    w(0xEE87, 0xE087)
    w(0x4C06, 0x7800)                       # muls.l d6,d7
    w(0xEE87, 0xE087)
    w(0x2006, 0xDC86, 0xDC80, 0x9C87, 0xE286)   # 3t - t^3, /2
    w(0x202A, DT)                           # move.l DT(a2),d0      Depth glaetten (je Sample, ~2.7 ms)
    w(0x9081, 0xEE80, 0xD280)               # sub.l d1,d0 ; asr.l #7,d0 ; add.l d0,d1
    w(0x2E01, 0xE887)                       # move.l d1,d7 ; asr.l #4,d7
    w(0x4C07, 0x6800, 0xE886)               # muls.l d7,d6 ; asr.l #4,d6   Swing
    w(0x2846)                               # movea.l d6,a4
    # links
    w(0x2E02, 0x7010, 0xE1AF, 0x9E86)       # move.l d2,d7 ; moveq #16,d0 ; lsl.l d0,d7 ; sub.l d6,d7
    w(0x9EAA, BOFF)                         # sub.l BOFF(a2),d7
    w(0x4EB9); l(M_TAP)                     # jsr TAP  (d6 = Abgriff)
    w(0x200D)                               # move.l a5,d0          yL
    w(0x4EB9); l(0)                         # jsr FILT (Platzhalter)
    fixL = len(a.b) - 4
    w(0x2A40)                               # movea.l d0,a5
    # rechts
    w(0x2E02, 0x7010, 0xE1AF)               # move.l d2,d7 ; moveq #16,d0 ; lsl.l d0,d7
    w(0x2C0C, 0xDE86)                       # move.l a4,d6 ; add.l d6,d7
    w(0x9EAA, BOFF)                         # sub.l BOFF(a2),d7
    w(0x4EB9); l(M_TAP)
    w(0x200E)                               # move.l a6,d0          yR
    w(0x4EB9); l(0)
    fixR = len(a.b) - 4
    w(0x2C40)                               # movea.l d0,a6
    if EXTRA_OUT:
        # Ausgabe je Modus (O4: d6*4 gesaettigt -> (a1)+)
        w(0x7000)                               # moveq #0,d0
        w(0x1039); l(MODE)                      # move.b MODE,d0
        w(0x0C80); l(3)                         # cmpi.l #3,d0
        a.bcc(EQ, 'dim')
        w(0x0C80); l(4)                         # cmpi.l #4,d0
        a.bcc(EQ, 'spl')
        w(0x2C0D)                               # move.l a5,d6          Chorus: L = yL
        a.bcc(BRA, 'outr')
        a.label('dim')                          # Dimension: L = yL - yR/2, R = yR - yL/2
        w(0x2E0E, 0xE287)                       # move.l a6,d7 ; asr.l #1,d7
        w(0x2C0D, 0x9C87)                       # move.l a5,d6 ; sub.l d7,d6
        w(0x4EB9); l(0)                         # jsr O4
        fx1 = len(a.b) - 4
        w(0x2E0D, 0xE287)                       # move.l a5,d7 ; asr.l #1,d7
        w(0x2C0E, 0x9C87)                       # move.l a6,d6 ; sub.l d7,d6
        a.bcc(BRA, 'out2')
        a.label('spl')                          # Split: L = trocken (Mono-Eingang), R = yR
        w(0x2C33, 0x2C00)                       # move.l 0(a3,d2.l*4),d6
        a.label('outr')
        w(0x4EB9); l(0)                         # jsr O4
        fx2 = len(a.b) - 4
        w(0x2C0E)                               # move.l a6,d6
        a.label('out2')
        w(0x4EB9); l(0)                         # jsr O4
        fx3 = len(a.b) - 4
    else:
        w(0x2C0D)                           # move.l a5,d6
        w(0x4EB9); l(0); fx1 = len(a.b) - 4 # jsr O4
        w(0x2C0E)                           # move.l a6,d6
        w(0x4EB9); l(0); fx2 = len(a.b) - 4
        fx3 = fx2
    w(0x5282)                               # addq.l #1,d2
    w(0x0282); l(RING_MASK)
    w(0x5385)                               # subq.l #1,d5
    a.bcc(NE, 'loop')
    w(0x2482)                               # move.l d2,(a2)
    w(0x2543, 0x0004)                       # move.l d3,4(a2)
    w(0x254D, YL)                           # move.l a5,YL(a2)
    w(0x254E, YR)                           # move.l a6,YR(a2)
    w(0x2541, DC)                           # move.l d1,DC(a2)
    w(0x4CD7, 0x7CFC)                       # movem.l (a7),d2-d7/a2-a6
    w(0x4FEF, 0x002C)                       # lea 44(a7),a7
    w(0x4E75)
    return a, fixL, fixR, (fx1, fx2, fx3), fs

def build_tap():
    a = A(M_TAP); w, l = a.w, a.l32
    a.label('tap')                          # d7 = Leseposition Q16, d0 = 16 -> d6 = Abgriff (ungefiltert)
    w(0x0287); l((RING_MASK + 1 << 16) - 1) # andi.l #mask,d7
    w(0x2C07)                               # move.l d7,d6
    w(0xE0AE)                               # lsr.l d0,d6           Index
    w(0xE88F)                               # lsr.l #4,d7
    w(0x0287); l(0xFFF)                     # andi.l #$fff,d7       Bruch (12 Bit)
    w(0x2033, 0x6C00)                       # move.l 0(a3,d6.l*4),d0   s0
    w(0x5286)                               # addq.l #1,d6
    w(0x0286); l(RING_MASK)
    w(0x2C33, 0x6C00)                       # move.l 0(a3,d6.l*4),d6   s1
    w(0x9C80)                               # sub.l d0,d6
    w(0x0686); l(0x800)                     # addi.l #$800,d6       runden
    w(0xE086, 0xE886)                       # asr.l #8,d6 ; asr.l #4,d6
    w(0x4C07, 0x6800)                       # muls.l d7,d6
    w(0xDC80)                               # add.l d0,d6
    w(0x4E75)                               # rts
    a.label('filt')                         # d6 = x, d0 = y -> d0 = y neu
    w(0x2E00)                               # move.l d0,d7
    w(0xE286, 0xE287)                       # asr.l #1,d6 ; asr.l #1,d7
    w(0x9C87)                               # sub.l d7,d6           d = (x-y)/2
    w(0x2E06, 0xE487)                       # move.l d6,d7 ; asr.l #2,d7
    w(0xDC87)                               # add.l d7,d6           0.625*(x-y)
    w(0xD086)                               # add.l d6,d0           y neu
    w(0x4E75)
    a.label('sat')                          # d6 = x -> x - x^3/6 (normiert 2^30); d0, d7 frei
    w(0x2E06, 0xEE87, 0xE087)               # move.l d6,d7 ; asr.l #7,d7 ; asr.l #8,d7   t
    w(0x2007)                               # move.l d7,d0
    w(0x4C07, 0x0800)                       # muls.l d7,d0          t^2
    w(0xEE80, 0xE080)                       # asr.l #7,d0 ; asr.l #8,d0
    w(0x4C07, 0x0800)                       # muls.l d7,d0          t^3
    w(0xEE80, 0xE080)                       # asr #15
    w(0x2E3C); l(5461)                      # move.l #5461,d7
    w(0x4C07, 0x0800)                       # muls.l d7,d0          t^3/6 (Q30)
    w(0xEE80, 0xE080)                       # asr #15 -> Q15
    w(0x7E0F, 0xEFA8)                       # moveq #15,d7 ; lsl.l d7,d0
    w(0x9C80)                               # sub.l d0,d6
    w(0x4E75)
    a.label('o4')                           # d6 -> 4*d6 gesaettigt nach (a1)+
    w(0xDC86, 0x4C86)                       # add.l d6,d6 ; sats.l d6
    w(0xDC86, 0x4C86)                       # add.l d6,d6 ; sats.l d6
    w(0x22C6)                               # move.l d6,(a1)+
    w(0x4E75)
    return a.done(), a.lab

def build():
    import struct
    from gen_chorusfx import check_cf
    s = build_setup(); tap, lab = build_tap()
    a, fl, fr, fo, fs = build_loop()
    a.b[fs:fs+4] = struct.pack('>I', lab['sat'])
    a.b[fl:fl+4] = struct.pack('>I', lab['filt']); a.b[fr:fr+4] = struct.pack('>I', lab['filt'])
    for f in fo: a.b[f:f+4] = struct.pack('>I', lab['o4'])
    lp = a.done()
    for c, b in ((s, MASK), (lp, M_LOOP), (tap, M_TAP)):
        assert len(c) <= 280, (hex(b), len(c)); check_cf(c, b)
    return s, lp, tap

def table():
    import struct
    return b''.join(struct.pack('>4I', i0, isc, dsc, base << 16) for i0, isc, dsc, base in MODES)
if __name__ == "__main__":
    s, lp, t = build(); print(len(s), len(lp), len(t))
