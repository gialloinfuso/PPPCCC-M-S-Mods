#!/usr/bin/env python3
"""Mod 'strum' (v2, smp23): Strum fuer CHORD und Vlvt, pro Spur im Sound. Braucht nur 'core'.
Bedienung (Pip 08.11.2026), nur auf CHORD- und Vlvt-Spuren (LKXT des Cores):
  FUNC + SHAPE = Strum-Abstand (k 24): smp36: 0 = OFF, 1..110 = ms (bis 250), 111..127 = Notenwerte von Patch 04 (/64 .. 1/1).
    Davor (smp33): 1..127 = die Werte 0..126 der Delay-Zeit der Firmware
    (.125 .. 1/16 .. 1/8 .. 128 Sechzehntel, im Tempo; Texte ueber deren Formatierer 0x40045720), der erste Ton auf dem Trig.
    Verlauf: smp23..32 ms + Notenwerte (1/64T..1/8T, dann 1/32T..1/8T); smp33 (Pip): 'genau wie die Delay-Noten, auch die
    Darstellung'. Popup in der schmalen grossen Schrift 0x40141b08 (Core PFONT, STYX Bit 7): die grosse Schrift 0x401429ec hat
    16 px je Zeichen um x 96, ein Zeichen ueber x 127 fehlt -> nur 3 Zeichen ('1/12' zeigte '1/1').
  FUNC + COLOR = Strum-Pattern (k 27): UP, DOWN, RND (jeder Trig eine neue Reihenfolge), 1324, 1423, 4132, 4231.
  Echte Parameter: p-locks, LFO-/Velocity-Ziel, gespeichert im Sound (Core, Sound-Slot 3: Satz +80 / +81).
  Auf Monom sind k 24 / 27 Glide / Noise; die Parameter-Suche 0x4005a6a6 (smp37: Core PSX bei 0x4005a6d0, vorher Haken PS hier; Tabelle der allgemeinen
  Parameter) liefert fuer k 24 / 27 auf CHORD (Maschine 5) / Vlvt (7) die Strum-Deskriptoren 86 / 87 bzw. 88 / 89.
  Ersetzt den globalen Strum (SETTINGS + SHAPE, Pattern-Kopf-Byte 56) - SETTINGS + SHAPE ist frei.
Deskriptoren 86..89 (Feld 0 = 5: kein Eintrag in Zeilen / Tabelle der Firmware, anwendbar nur auf der Maschine laut MACHMAP 5 / 7), Anzeige-Objekte
  1 / 2 (Spender, 'Error' der Firmware) mit eigenen Formatierern (FMTX des Cores): Abstand (OFF / Delay-Zeit), Pattern-Namen.
CHORD-Klang (wie v1 / smp22, Modded-Cycles notes/42 §3 und eigene Analyse): Haken ST am Ende des CHORD-Updates 0x400ab240 (a2
  Stimme, a3 Parameter): Zaehler je Stimme (Bloecke seit dem Trig), Rang je Operator (0..3) aus dem Pattern (RND: beim Trig
  gemischt), Einsatz = Rang x Abstand; Op 1..3: Pegel (Stimme +0x0c/+0x10/+0x14) vor dem Einsatz 0, dann 1/4, 1/2, voll; Op 0
  (Grundton) ueber G0 (Haken G0F im Render 0x400ab2d2) in 8 Stufen. Abstand in 1/8 Bloecken = 450000 * u / Tempo (u in
  1/768 ganzer Note, C.strum_units; Tempo 0x40149310 in 1/120 BPM, 1 Viertel = 10.8e6 / Tempo Bloecke zu 32 Samples).
Speicher: 0x40192734 (ST, G0F, PS), 0x4017a4d4 (PERM), 0x40163990 (Zaehler, Raenge, Zufall, Pattern), 0x401573cc (STEP8), 0x4018d4a8 (Formatierer, Texte).
  RAM G0 0x4233c378 (wie bisher).
Aufruf: g2_strum.py [out.json]
"""
import collections, struct, sys
from common import *                 # noqa: F401,F403
import common as C
import g2_core as core
import g2_dtab as DT
from cfasm import asm, done as adone

M_ST, M_FMT, M_ST2, M_ST3, M_SD = 0x40192734, 0x4018D4A8, 0x4017A4D4, 0x40189618, 0x40163990   # smp35: M_ST3 = frueher M_TAB des Samplers (272 B; 0x401573cc frei)
M_OP, M_OP2, M_ENV = 0x40166690, 0x401679D8, 0x40167B80               # smp24: Huellkurve je Ton
M_OPA, M_OP3 = 0x40168FB4, 0x40179C98     # smp37: M_PS 0x40168c4c frei (Parameter-Suche im Core)
SIZE = {M_ST: 376, M_FMT: 376, M_ST2: 124, M_ST3: 272, M_SD: 104, M_OP: 104, M_OP2: 104, M_ENV: 104, M_OPA: 104, M_OP3: 104}
G0, G0_FULL = 0x4233C378, 0x20000000
ST_HOOK = 0x400AB240
ST_ORIG = (6, '13187a38965400f61edba5135ed74da994ac2d300bd2c82157be68165467475b')   # movem.l 8(a7),d2-d5/a2-a4
R_HOOK = 0x400AB2D2
R_ORIG = (6, '37a77ef1bbd2879f9bea1730fa1954dbc1eeee9ce8c7474d97ef7f12d7a2614a')    # move.l #$20000000,d1
PS_HOOK, PS_CK, PS_RET, PS_TAB = 0x4005A6D0, (10, 'dbe8cd680b65aba085b6231e533d89fdee52f813a9a201f14f061aec7b770dfa'), 0x4005A6FC, 0x40A79394
VOICE0, VSTEP, NVOICE = 0x42308828, 0x31C, 6
TEMPO = C.TEMPO
FMT_D = 0x4012A9EA                    # '%d' der Firmware
M_CHORD, M_VLVT = 5, 7
KNOB_COLOR, KNOB_SHAPE = 4, 5
DBASE, DN = C.DESC_SLOT['strum']     # 86 CHORD Abstand, 87 CHORD Pattern, 88 Vlvt Abstand, 89 Vlvt Pattern
OBJ_TIME, OBJ_PAT = 1, 2
# Feld 0 der Deskriptoren = 5 ('Maschinen-Parameter'): Anwendbarkeit 0x4000aa9a fragt dann die Maschine ueber DMACH (MACHMAP 5 / 7),
# die Sound-Funktionen 0x4000b3e4 / 0x4000b65a (Feld <= 17, Maske 0x203ff) behandeln sie wie CHORD-Parameter. Die Zeilen-Bauer
# 0x4005a2f4 uebergehen sie: k 24 / 27 ist kein Maschinen-Slot (0x4005a25e) und Feld 5 - 6 / - 10 / - 13 liegt ausserhalb (0x4005a346 ff.).
FIELD = 5
PATS, P_RND, RANKS = C.STRUM_PATS, C.STRUM_RND, C.STRUM_RANKS
FADE_MIN = C.STRUM_FADE_MIN                # smp39: darunter aus


step8 = C.strum_step8


def st_text():
    return f'''
    ; ST: Ende des CHORD-Updates (a2 Stimme, a3 Parameter). d2-d5/a2-a4 holt der Epilog vom Stapel; d6/d7 NICHT anfassen.
    ST:     move.l  a2,d0
            subi.l  #{VOICE0:#x},d0
            bmi     full
            moveq   #0,d1
    vi:     cmpi.l  #{VSTEP},d0
            bcs     vf
            subi.l  #{VSTEP},d0
            addq.l  #1,d1
            moveq   #{NVOICE},d2
            cmp.l   d2,d1
            bcc     full
            bra     vi
    vf:     tst.l   d0
            bne     full
            moveq   #1,d0                    ; smp24: eigene Huellkurve je Ton -> Attack des Cores fuer diese Spur aus
            lea     {core.sym()['OWN']:#x},a0
            move.b  d0,0(a0,d1.l)
            lsl.l   #2,d1
            lea     CNT,a0
            adda.l  d1,a0                    ; a0 = Zaehler der Stimme, RNK + 4 i = Raenge, STG + 4 i = Stufen
            lea     RNK,a1
            adda.l  d1,a1
            tst.l   0x38(a2)                 ; Trig?
            beq     inc
            clr.l   (a0)
            lea     STG,a4
            adda.l  d1,a4
            clr.l   (a4)                     ; alle Toene: Stufe 0 (Attack)
            mvz.b   {2 * C.K_SPAT}(a3),d0    ; Pattern -> Raenge der Toene
            jsr     PERM
            bra     gate
    inc:    move.l  (a0),d0
            cmpi.l  #0xffff,d0
            bcc     gate
            addq.l  #1,d0
            move.l  d0,(a0)
    gate:   move.l  (a0),d4                  ; d4 = Bloecke seit dem Trig
            move.l  a1,d0
            subi.l  #RNK,d0
            movea.l d0,a4
            adda.l  #STG,a4
            lsl.l   #2,d0
            addi.l  #ENV,d0
            movea.l d0,a0                    ; a0 = ENV + 16 i
            mvz.b   {2 * C.K_STIME}(a3),d0   ; Abstand 0..127
            jsr     STEP8
            move.l  d0,d5                    ; d5 = Abstand in 1/8 Bloecken
            moveq   #0,d3                    ; Ton j = 0..3
    tl:     jsr     OPE                      ; d0 = Huellkurve des Tons (0..2^31)
            tst.l   d3
            bne     t1
            cmpi.l  #0x80000000,d0           ; Grundton (Op 0) ueber G0
            bcc     t0f
            lsr.l   #2,d0
            move.l  d0,{G0:#x}
            bra     tn
    t0f:    move.l  #{G0_FULL:#x},d0
            move.l  d0,{G0:#x}
            bra     tn
    t1:     cmpi.l  #0x80000000,d0           ; Op 1..3: Pegel (Stimme +0x0c / +0x10 / +0x14) * E
            bcc     tn
            clr.w   d0
            swap    d0                       ; E >> 16 (0..0x7fff)
            move.l  d3,d1
            lsl.l   #2,d1
            move.l  8(a2,d1.l),d2
            asr.l   #8,d2
            asr.l   #7,d2
            muls.l  d0,d2
            move.l  d2,8(a2,d1.l)
    tn:     addq.l  #1,d3
            moveq   #4,d0
            cmp.l   d0,d3
            bne     tl
            move.l  #0x80000000,d0           ; Huellkurve der Spur flach (die Toene haben ihre eigene)
            move.l  d0,0x250(a2)
            bra     out
    full:   move.l  #{G0_FULL:#x},d0
            move.l  d0,{G0:#x}
    out:    movem.l 8(sp),d2-d5/a2-a4
            lea     36(sp),sp
            rts
    ; G0F: im CHORD-Render statt move.l #$20000000,d1 (Pegel des Grundtons)
    G0F:    move.l  {G0:#x},d1
            rts
'''


def ps_text():
    return f'''
    ; PS: Parameter-Suche 0x4005a6a6, allgemeiner Parameter (a2 = k, d2 = Maschine; statt lea Tabelle,a0 ; move.l (a0,k*4),d0)
    PS:     move.l  a2,d0
            moveq   #{C.K_STIME},d1
            cmp.l   d1,d0
            beq     ps1
            moveq   #{C.K_SPAT},d1
            cmp.l   d1,d0
            bne     ps9
    ps1:    moveq   #{M_CHORD},d1
            cmp.l   d1,d2
            beq     psc
            moveq   #{M_VLVT},d1
            cmp.l   d1,d2
            bne     ps9
            moveq   #{DBASE + 2},d1
            bra     ps2
    psc:    moveq   #{DBASE},d1
    ps2:    moveq   #{C.K_STIME},d2
            cmp.l   d2,d0
            beq     ps3
            addq.l  #1,d1
    ps3:    move.l  d1,d0                    ; d2 holt die Firmware bei 0x4005a6fc vom Stapel
            jmp     {PS_RET:#x}
    ps9:    lea     {PS_TAB:#x},a0
            move.l  0(a0,a2.l*4),d0
            jmp     {PS_RET:#x}
'''


def ope_text():
    return f'''
    ; OPE: Huellkurve von Ton d3 (d4 Bloecke seit dem Trig, d5 Abstand 1/8 Bloecke, a0 ENV, a1 Raenge, a4 Stufen, a2 Stimme,
    ; a3 Parameter) -> d0 = E (0..2^31), gespeichert. Stufe 0 Attack (k 23, 0 = sofort), 1 Halten (GATE), 2 Decay (Faktor der
    ; Firmware aus 0x250 der Stimme). Benutzt d0-d2.
    OPE:    mvz.b   0(a1,d3.l),d0
            mulu.l  d5,d0
            lsr.l   #3,d0                    ; Einsatz (Block)
            move.l  d4,d1
            sub.l   d0,d1                    ; Bloecke seit dem Einsatz
            bmi     oz
            move.l  d0,d2                    ; Einsatz
            mvz.b   0(a4,d3.l),d0
            beq     oaj
            subq.l  #1,d0
            beq     oh
            move.l  0(a0,d3.l*4),d0          ; Decay
            jsr     EMULF
            move.l  d0,0(a0,d3.l*4)
            rts
    oh:     jsr     HELDQ
            bne     oe
            moveq   #2,d0
            move.b  d0,0(a4,d3.l)
    oe:     move.l  0(a0,d3.l*4),d0
            rts
    oz:     jmp     OZF
    oaj:    jmp     OATK
'''


def opea_text():
    return f'''
    ; OATK: Stufe 0 (Attack) von OPE (d1 Bloecke seit dem Einsatz, d2 Einsatz)
    OATK:   mvz.b   {2 * C.K_EXT0}(a3),d0    ; Attack 0..127
            bne     oat
            tst.l   d2                       ; Attack 0: erster Einsatz sofort voll, spaetere 1/4, 1/2, voll (kein Knacken)
            beq     ofl
            tst.l   d1
            bne     oa1
            move.l  #0x20000000,d0
            bra     ost
    oa1:    subq.l  #1,d1
            bne     ofl
            move.l  #0x40000000,d0
            bra     ost
    oat:    jsr     AINC                     ; d0 = Zuwachs je Block
            add.l   0(a0,d3.l*4),d0
            bcs     ofl
            bpl     ost                      ; < 2^31
    ofl:    move.l  #0x80000000,d0           ; voll -> Halten (GATE) oder Decay
            move.l  d0,0(a0,d3.l*4)
            jsr     HELDQ
            moveq   #2,d1
            sub.l   d0,d1                    ; 1 Halten, 2 Decay
            move.b  d1,0(a4,d3.l)
            move.l  #0x80000000,d0
            rts
    ost:    move.l  d0,0(a0,d3.l*4)
            rts
'''


def ope2_text():
    return f'''
    ; HELDQ: Z = 0 (ne), solange der Ton gehalten wird: GATE der Stimme (+0x24c) und noch nicht losgelassen (Stufe der Firmware
    ; +0x23c != 1; im Trig-Block gilt gehalten). Benutzt d0.
    HELDQ:  tst.l   0x24c(a2)
            beq     hq0
            tst.l   d4
            beq     hq1
            moveq   #1,d0
            cmp.l   0x23c(a2),d0
            beq     hq0
    hq1:    moveq   #1,d0
            rts
    hq0:    moveq   #0,d0
            rts
    ; EMULF: d0 = E * f / 2^31, f = -(Faktor der Firmware an +0x250) (0..2^31). Benutzt d1, d2.
    EMULF:  move.l  0x250(a2),d1
            neg.l   d1
            move.l  d3,-(sp)
            move.l  d0,d2
            clr.w   d2
            swap    d2                       ; Eh
            andi.l  #0xffff,d0               ; El
            move.l  d1,d3
            clr.w   d3
            swap    d3                       ; fh
            andi.l  #0xffff,d1               ; fl
            mulu.l  d2,d1
            mulu.l  d3,d0
            add.l   d1,d0
            lsr.l   #8,d0
            lsr.l   #7,d0
            mulu.l  d3,d2
            add.l   d2,d2
            add.l   d2,d0
            move.l  (sp)+,d3
            rts
'''


def ope3_text():
    return f'''
    ; OZF (smp39): Ton vor seinem Einsatz: Stufe 0, Pegel blendet aus (* 3/4 je Block, unter FADE_MIN 0) statt sofort 0
    ; (Pip: Knacken, wenn ein neuer Trig klingende Toene abschneidet). Benutzt d0 / d1.
    OZF:    moveq   #0,d0
            move.b  d0,0(a4,d3.l)
            move.l  0(a0,d3.l*4),d0
            move.l  d0,d1
            lsr.l   #2,d1
            sub.l   d1,d0
            cmpi.l  #{FADE_MIN:#x},d0
            bcc     oz1
            moveq   #0,d0
    oz1:    move.l  d0,0(a0,d3.l*4)
            rts
    ; AINC: d0 = Attack 1..127 -> Zuwachs je Block = 2^31 * 32 / (96000 (a / 127)^2) (wie der Attack des Cores). Benutzt d1.
    AINC:   mulu.l  d0,d0
            move.l  #96000,d1
            mulu.l  d1,d0
            move.l  #16129,d1
            divu.l  d1,d0
            moveq   #32,d1
            cmp.l   d1,d0
            bcs     ai9
            move.l  #0x80000000,d1
            divu.l  d0,d1
            lsl.l   #5,d1
            move.l  d1,d0
            rts
    ai9:    move.l  #0x80000000,d0
            rts
'''


def st2_text():
    return f'''
    ; PERM: d0 = Pattern -> Raenge (a1, 4 Bytes); RND: Fisher-Yates mit eigenem Zufall. Benutzt d0-d3, a4 (Epilog von ST).
    PERM:   moveq   #{len(PATS) - 1},d1
            cmp.l   d1,d0
            bls     pm1
            moveq   #0,d0
    pm1:    moveq   #{P_RND},d1
            cmp.l   d1,d0
            beq     pmr
            lea     RTAB,a4
            move.l  0(a4,d0.l*4),d0
            move.l  d0,(a1)
            rts
    pmr:    move.l  #0x00010203,d0
            move.l  d0,(a1)
            moveq   #3,d3                    ; j = 3..1
    pm2:    move.l  RNG,d0
            move.l  #1664525,d1
            muls.l  d1,d0
            addi.l  #1013904223,d0
            move.l  d0,RNG
            clr.w   d0
            swap    d0                       ; obere 16 Bit
            move.l  d3,d1
            addq.l  #1,d1
            mulu.l  d1,d0
            clr.w   d0
            swap    d0                       ; r = 0..j
            mvz.b   0(a1,d3.l),d1            ; tauschen
            mvz.b   0(a1,d0.l),d2
            move.b  d2,0(a1,d3.l)
            move.b  d1,0(a1,d0.l)
            subq.l  #1,d3
            bne     pm2
            rts
'''


def st3_text():
    return f'''
    ; STEP8: d0 = Wert 0..127 -> d0 = Abstand in 1/8 Bloecken (0 = alle zusammen; smp36: 1..NMS = ms, je 3000 / NMS;
    ; danach Notenwerte wie Patch 04: NUN = Laenge in 1/768 ganzer Note, * KC / Tempo). Benutzt d1.
    STEP8:  tst.l   d0
            beq     sp9
            moveq   #{C.STRUM_NMS},d1
            cmp.l   d1,d0
            bhi     sp1
            move.l  #3000,d1
            mulu.l  d1,d0
            moveq   #{C.STRUM_NMS},d1
            divu.l  d1,d0
            rts
    sp1:    cmpi.l  #127,d0
            bls     sp2
            moveq   #127,d0
    sp2:    subi.l  #{C.STRUM_NMS + 1},d0
            move.l  a0,-(sp)
            lea     NUN,a0
            mvz.w   0(a0,d0.l*2),d0
            movea.l (sp)+,a0
            move.l  #{C.STRUM_KC},d1
            mulu.l  d1,d0
            move.l  {TEMPO:#x},d1
            beq     spz
            divu.l  d1,d0
    sp9:    rts
    spz:    moveq   #0,d0
            rts
'''


def fmt_text():
    return f'''
    ; Formatierer (8(sp) = Wert 8.8, 12(sp) = Puffer) ueber den sprintf der Firmware
    TFMT:   move.l  8(sp),d0                 ; smp36: 0 = OFF, 1..NMS ms (Zahl), danach Etikett des Notenwerts
            addi.l  #0x80,d0
            asr.l   #8,d0
            bgt     tf1
            move.l  #S_OFF,d0
            bra     tfs
    tf1:    cmpi.l  #127,d0
            ble     tf2
            moveq   #127,d0
    tf2:    moveq   #{C.STRUM_NMS},d1
            cmp.l   d1,d0
            bhi     tf4
            move.l  #250,d1                  ; ms = (v * 250 + NMS / 2) / NMS
            mulu.l  d1,d0
            addi.l  #{C.STRUM_NMS // 2},d0
            moveq   #{C.STRUM_NMS},d1
            divu.l  d1,d0
            move.l  12(sp),d1
            move.l  d1,4(sp)
            move.l  #{FMT_D:#x},d1
            move.l  d1,8(sp)
            move.l  d0,12(sp)
            jmp     0x40000E6E
    tf4:    subi.l  #{C.STRUM_NMS + 1},d0
            lsl.l   #2,d0
            addi.l  #LBL,d0                  ; Text (3 Zeichen + 0)
            bra     tfs
    PFMT:   move.l  8(sp),d0
            addi.l  #0x80,d0
            asr.l   #8,d0
            bpl     pf1
            moveq   #0,d0
    pf1:    moveq   #{len(PATS) - 1},d1
            cmp.l   d1,d0
            ble     pf2
            move.l  d1,d0
    pf2:    lea     PNAMES,a0
            move.l  0(a0,d0.l*4),d0
    tfs:    move.l  12(sp),d1
            move.l  d1,4(sp)
            move.l  d0,8(sp)
            jmp     0x40000E6E
'''


def data_st(org):
    """RAM / Tabellen: CNT (6 x 4), RNK (6 x 4), RNG, STG (6 x 4)"""
    lab, b = {}, bytearray()
    def at(): return org + len(b)
    lab['CNT'] = at(); b += bytes(24)
    lab['RNK'] = at(); b += bytes(24)
    lab['RNG'] = at(); b += struct.pack('>I', 0x2545F491)
    lab['STG'] = at(); b += bytes(24)                                   # smp24: Stufe je Ton (6 x 4)
    return bytes(b), lab                                                # smp37: RTAB jetzt in data_fmt (9 Pattern)


def data_env(org):
    return bytes(96), {'ENV': org}                                      # smp24: Huellkurve je Ton (6 x 4 x 4)


def data_st3(org):
    """smp36: NUN (Laenge der Notenwerte in 1/768 ganzer Note, Woerter), LBL (Etiketten wie Patch 04, je 4 B)"""
    nun = b''.join(struct.pack('>H', C.strum_units(p)) for p in C.STRUM_NOTEP)
    lbl = b''.join(C.STRUM_LABELS[p].encode().ljust(4, b'\0') for p in C.STRUM_NOTEP)
    return nun + lbl, {'NUN': org, 'LBL': org + len(nun)}


def data_fmt(org):
    lab, b = {}, bytearray()
    def at(): return org + len(b)
    lab['PNAMES'] = at(); b += bytes(4 * len(PATS))
    lab['RTAB'] = at(); b += C.strum_rtab()                             # Raenge je Pattern (4 B)
    strs = {}
    for s in PATS + ('OFF', 'Strum Time', 'STIM', 'Strum Pattern', 'SPAT'):
        strs[s] = at(); b += s.encode() + b'\0'
    struct.pack_into('>%dI' % len(PATS), b, lab['PNAMES'] - org, *[strs[s] for s in PATS])
    lab['S_OFF'] = strs['OFF']
    return bytes(b), lab, strs


def no_data(org):
    return b'', {}


def build():
    parts = ((M_ST, st_text, no_data), (M_ST2, st2_text, no_data), (M_SD, lambda: '', data_st), (M_ST3, st3_text, data_st3), (M_OP, ope_text, no_data), (M_OPA, opea_text, no_data), (M_OP2, ope2_text, no_data), (M_OP3, ope3_text, no_data), (M_ENV, lambda: '', data_env), (M_FMT, fmt_text, data_fmt))
    lab = collections.defaultdict(int)
    for _ in range(3):
        new, out, extra = dict(), {}, None
        for org, tf, df in parts:
            a = A(org); asm(a, tf(), lab)
            dorg = org + ((len(a.b) + 3) & ~3)
            r = df(dorg)
            new.update(a.lab); new.update(r[1])
            out[org] = (a, dorg, r[0])
            if len(r) > 2: extra = r[2]
        lab = collections.defaultdict(int, new)
    blobs = {}
    for org, (a, dorg, d) in out.items():
        code = adone(a, lab)
        blobs[org] = code + bytes(dorg - org - len(code)) + d
    return blobs, dict(lab), extra


def tweak(img):
    base = apply(img, core.tweak(img))
    parts, lab, strs = build()
    W = Writes(base)
    for va, b in parts.items():
        W.mask(va, b, SIZE[va])
    W.hook(ST_HOOK, ST_ORIG, jmp(lab['ST']))
    W.hook(R_HOOK, R_ORIG, jsr(lab['G0F']))
    core.psx_write(W, 'strum', [(M_CHORD, C.K_STIME, DBASE), (M_CHORD, C.K_SPAT, DBASE + 1), (M_VLVT, C.K_STIME, DBASE + 2),
                                (M_VLVT, C.K_SPAT, DBASE + 3)])   # smp37: Parameter-Suche jetzt im Core (PSX)
    # Deskriptoren 86..89 in der Tabelle des Cores (Nutzlast), Spender-Objekte, Maschine, Formatierer, FUNC-Knoepfe
    rows = [(M_CHORD, C.K_STIME, 0x7F00, 'Strum Time', 'STIM', OBJ_TIME, 'TFMT', KNOB_SHAPE),
            (M_CHORD, C.K_SPAT, (len(PATS) - 1) << 8, 'Strum Pattern', 'SPAT', OBJ_PAT, 'PFMT', KNOB_COLOR),
            (M_VLVT, C.K_STIME, 0x7F00, 'Strum Time', 'STIM', OBJ_TIME, 'TFMT', KNOB_SHAPE),
            (M_VLVT, C.K_SPAT, (len(PATS) - 1) << 8, 'Strum Pattern', 'SPAT', OBJ_PAT, 'PFMT', KNOB_COLOR)]
    l0, ln = C.LKX_SLOT['strum']
    assert ln == len(rows) == DN
    for i, (mach, k, top, nm, sh, obj, fm, knob) in enumerate(rows):
        d = DBASE + i
        W.put(C.PIMG(C.DTD(d)), DT.desc_row(FIELD, k, top, 0, 80 + (i & 1), strs[nm], 0x4012996F, strs[sh]))
        W.put(C.PIMG(C.DONOR + d - C.NDESC0), bytes([obj]))
        W.put(C.PIMG(C.MACHMAP + d - C.NDESC0), bytes([mach]))
        W.put(C.PIMG(C.FMTX + 4 * (d - C.NDESC0)), struct.pack('>I', lab[fm]))
        W.put(C.PIMG(C.STYX + d - C.NDESC0), bytes([C.STY_PFONT]))       # smp32: Popup in der schmalen grossen Schrift
        W.put(C.PIMG(C.LKXT + 4 * (l0 + i)), struct.pack('>BBH', mach, knob, d))
    return patch('strum', 7, 'Strum for CHORD and Vlvt',
                 ["On CHORD / Vlvt tracks: FUNC + SHAPE = strum time (OFF = together, 2..250 ms, then the delay note values /64 .. 1/1 in tempo),",
                  "FUNC + COLOR = strum pattern (UP, DOWN, RND = new order on every trig, 1324, 1423, 4132, 4231, ROOT = lowest note then the other three together, TOP = highest note first).",
                  "Per track in the sound (p-locks, LFO / velocity target). Replaces the global strum (SETTINGS + SHAPE).",
                  "Each chord note has its own envelope from its strum onset: attack (FUNC + DECAY), hold while GATE, decay (DECAY).",
                  "Erzeugt von v2/g2_strum.py."], W, requires=['core'],
                 hooks=[f"{x:#x}" for x in (ST_HOOK, R_HOOK)],
                 memory=[{"va": f"{G0:#x}", "size": 4, "ram": True, "use": "root note level"}],
                 symbols={k: f"{lab[k]:#x}" for k in ('ST', 'G0F', 'PERM', 'STEP8', 'TFMT', 'PFMT', 'CNT', 'RNK', 'RNG',
                                                     'RTAB', 'PNAMES')},
                 params={"desc": list(range(DBASE, DBASE + DN)), "k_time": C.K_STIME, "k_pat": C.K_SPAT, "patterns": list(PATS),
                         "time": "0 = OFF, 1..127 = delay time 0..126", "tempo": f"{TEMPO:#x}"})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    parts, lab, _ = build()
    print({f"{va:#x}": len(b) for va, b in parts.items()})
