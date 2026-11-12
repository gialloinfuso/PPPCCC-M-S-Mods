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
    from cfasm import asm, done as adone
    a = A(MASK)
    asm(a, f'''
            lea     -44(sp),sp
            movem.l d2-d7/a2-a6,(sp)
            movea.l 56(sp),a0                ; params
            mvz.w   (a0),d0
            lsr.l   #8,d0                    ; S
            mvz.w   2(a0),d1
            lsr.l   #8,d1                    ; D
            moveq   #0,d7
            move.b  {MODE:#x},d7
            subq.l  #1,d7
            cmpi.l  #{MAXIDX},d7
            bls     mok
            moveq   #0,d7
    mok:    lsl.l   #4,d7
            lea     {M_TAB:#x},a0
            adda.l  d7,a0                    ; Modus-Tabelle
            move.l  4(a0),d4                 ; INCS
            muls.l  d0,d4
            add.l   (a0),d4                  ; + INC0
            move.l  8(a0),d6                 ; DSC
            muls.l  d6,d1                    ; D*DSC
            lea     {STATE:#x},a2
            move.l  12(a0),d6                ; BASE (Q16)
            move.l  d6,{BOFF}(a2)
            lsl.l   #{DSHIFT},d1             ; Depth-Ziel
            move.l  d1,{DT}(a2)
            move.l  {DC}(a2),d1              ; Depth aktuell
    ; Drift: rnd = rnd*A + C ; drift += rnd>>27 ; drift -= drift>>10 ; inc += 4*drift
            move.l  {RND}(a2),d0
            move.l  #{LCG_A},d6
            muls.l  d6,d0
            addi.l  #{LCG_C},d0
            move.l  d0,{RND}(a2)
            moveq   #27,d7
            asr.l   d7,d0                    ; +-16
            move.l  {DRIFT}(a2),d7
            move.l  d7,d6
            asr.l   #8,d6
            asr.l   #2,d6                    ; drift>>10
            sub.l   d6,d7
            add.l   d0,d7
            move.l  d7,{DRIFT}(a2)
            add.l   d7,d7
            add.l   d7,d7
            add.l   d7,d4                    ; inc += 4*drift
            move.l  (a2),d2                  ; w
            move.l  4(a2),d3                 ; Phase
            lea     16(a2),a3                ; Ring
            movea.l {YL}(a2),a5
            movea.l {YR}(a2),a6
            movea.l 52(sp),a0                ; in
            movea.l 48(sp),a1                ; out
            moveq   #32,d5
            jmp     {M_LOOP:#x}              ; Schleife
    ''')
    return adone(a)

def build_loop(tl):
    """tl: Labels von build_tap (tap, filt, sat, o4)"""
    from cfasm import asm, done as adone
    if EXTRA_OUT:
        out = f'''
    ; Ausgabe je Modus (O4: d6*4 gesaettigt -> (a1)+)
            moveq   #0,d0
            move.b  {MODE:#x},d0
            cmpi.l  #3,d0
            beq     dim
            cmpi.l  #4,d0
            beq     spl
            move.l  a5,d6                    ; Chorus: L = yL
            bra     outr
    dim:    move.l  a6,d7                    ; Dimension: L = yL - yR/2, R = yR - yL/2
            asr.l   #1,d7
            move.l  a5,d6
            sub.l   d7,d6
            jsr     {tl['o4']:#x}
            move.l  a5,d7
            asr.l   #1,d7
            move.l  a6,d6
            sub.l   d7,d6
            bra     out2
    spl:    move.l  0(a3,d2.l*4),d6          ; Split: L = trocken (Mono-Eingang), R = yR
    outr:   jsr     {tl['o4']:#x}
            move.l  a6,d6
    out2:   jsr     {tl['o4']:#x}'''
    else:
        out = f'''
            move.l  a5,d6
            jsr     {tl['o4']:#x}
            move.l  a6,d6
            jsr     {tl['o4']:#x}'''
    a = A(M_LOOP)
    asm(a, f'''
    loop:   move.l  (a0)+,d6
            asr.l   #2,d6                    ; L/4
            move.l  (a0)+,d7
            asr.l   #2,d7                    ; R/4
            add.l   d7,d6                    ; x (+-2^30)
            jsr     {tl['sat']:#x}           ; Saettigung x - x^3/6
            move.l  d6,0(a3,d2.l*4)
    ; LFO (wie v3): Dreieck -> (3t - t^3)/2
            add.l   d4,d3
            move.l  d3,d6
            bpl     pos
            not.l   d6
    pos:    subi.l  #0x40000000,d6
            asr.l   #7,d6
            asr.l   #8,d6
            move.l  d6,d7
            muls.l  d7,d7
            asr.l   #7,d7
            asr.l   #8,d7
            muls.l  d6,d7
            asr.l   #7,d7
            asr.l   #8,d7
            move.l  d6,d0
            add.l   d6,d6
            add.l   d0,d6
            sub.l   d7,d6
            asr.l   #1,d6                    ; 3t - t^3, /2
            move.l  {DT}(a2),d0              ; Depth glaetten (je Sample, ~2.7 ms)
            sub.l   d1,d0
            asr.l   #7,d0
            add.l   d0,d1
            move.l  d1,d7
            asr.l   #4,d7
            muls.l  d7,d6
            asr.l   #4,d6                    ; Swing
            movea.l d6,a4
    ; links
            move.l  d2,d7
            moveq   #16,d0
            lsl.l   d0,d7
            sub.l   d6,d7
            sub.l   {BOFF}(a2),d7
            jsr     {M_TAP:#x}               ; TAP (d6 = Abgriff)
            move.l  a5,d0                    ; yL
            jsr     {tl['filt']:#x}
            movea.l d0,a5
    ; rechts
            move.l  d2,d7
            moveq   #16,d0
            lsl.l   d0,d7
            move.l  a4,d6
            add.l   d6,d7
            sub.l   {BOFF}(a2),d7
            jsr     {M_TAP:#x}
            move.l  a6,d0                    ; yR
            jsr     {tl['filt']:#x}
            movea.l d0,a6{out}
            addq.l  #1,d2
            andi.l  #{RING_MASK:#x},d2
            subq.l  #1,d5
            bne     loop
            move.l  d2,(a2)
            move.l  d3,4(a2)
            move.l  a5,{YL}(a2)
            move.l  a6,{YR}(a2)
            move.l  d1,{DC}(a2)
            movem.l (sp),d2-d7/a2-a6
            lea     44(sp),sp
            rts
    ''')
    return adone(a)

def build_tap():
    from cfasm import asm, done as adone
    a = A(M_TAP)
    asm(a, f'''
    tap:    andi.l  #{(RING_MASK + 1 << 16) - 1:#x},d7   ; d7 = Leseposition Q16, d0 = 16 -> d6 = Abgriff (ungefiltert)
            move.l  d7,d6
            lsr.l   d0,d6                    ; Index
            lsr.l   #4,d7
            andi.l  #0xfff,d7                ; Bruch (12 Bit)
            move.l  0(a3,d6.l*4),d0          ; s0
            addq.l  #1,d6
            andi.l  #{RING_MASK:#x},d6
            move.l  0(a3,d6.l*4),d6          ; s1
            sub.l   d0,d6
            addi.l  #0x800,d6                ; runden
            asr.l   #8,d6
            asr.l   #4,d6
            muls.l  d7,d6
            add.l   d0,d6
            rts
    filt:   move.l  d0,d7                    ; d6 = x, d0 = y -> d0 = y neu
            asr.l   #1,d6
            asr.l   #1,d7
            sub.l   d7,d6                    ; d = (x-y)/2
            move.l  d6,d7
            asr.l   #2,d7
            add.l   d7,d6                    ; 0.625*(x-y)
            add.l   d6,d0                    ; y neu
            rts
    sat:    move.l  d6,d7                    ; d6 = x -> x - x^3/6 (normiert 2^30); d0, d7 frei
            asr.l   #7,d7
            asr.l   #8,d7                    ; t
            move.l  d7,d0
            muls.l  d7,d0                    ; t^2
            asr.l   #7,d0
            asr.l   #8,d0
            muls.l  d7,d0                    ; t^3
            asr.l   #7,d0
            asr.l   #8,d0
            move.l  #5461,d7
            muls.l  d7,d0                    ; t^3/6 (Q30)
            asr.l   #7,d0
            asr.l   #8,d0                    ; Q15
            moveq   #15,d7
            lsl.l   d7,d0
            sub.l   d0,d6
            rts
    o4:     add.l   d6,d6                    ; d6 -> 4*d6 gesaettigt nach (a1)+
            sats.l  d6
            add.l   d6,d6
            sats.l  d6
            move.l  d6,(a1)+
            rts
    ''')
    return adone(a), a.lab

def build():
    from gen_chorusfx import check_cf
    s = build_setup(); tap, lab = build_tap()
    lp = build_loop(lab)
    for c, b in ((s, MASK), (lp, M_LOOP), (tap, M_TAP)):
        assert len(c) <= 280, (hex(b), len(c)); check_cf(c, b)
    return s, lp, tap

def table():
    import struct
    return b''.join(struct.pack('>4I', i0, isc, dsc, base << 16) for i0, isc, dsc, base in MODES)
if __name__ == "__main__":
    s, lp, t = build(); print(len(s), len(lp), len(t))
