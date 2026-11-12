#!/usr/bin/env python3
"""Mod 'level-pan-values' (v2, Patch 19): Lautstaerke und Pan der Spur als Zahl auf dem Hauptbildschirm.

LEVEL/DATA drehen: Lautstaerke der gewaehlten Spur (0..127) in kleinen Ziffern statt des Lautsprechers der Volume-Leiste;
FUNC + LEVEL/DATA: Pan (-64..63) statt des 'R' der Pan-Leiste. Die Zahl bleibt 3 s nach der letzten Bewegung. LEVEL/DATA
geht auf dem Hauptbildschirm in Schritten von 1 statt 2 (damit die Zahl jeden Wert zeigt; schneller Modus x16 bleibt).

Portierung (Pip 02.11.2026: "volume & pan as numbers" aus dem 18nelli-Branch) von 'level-pan-values' aus Modded-Cycles
(18nelli18/Modded-Cycles, MIT; notes/44, tools/machines/level_pan/level_pan.S), dort nach dem Mod von djd_oz neu geschrieben
(gleiche Schrift 3x7, gleiche Positionen, gleiche Ablaufzeit). Hier mit cfasm neu geschrieben, in kleinen Masken.
Firmware 1.13 (aus notes/44): UI-Takt 0x400081f2 (jsr 0x40090f48, 30 Hz); der Haken sitzt hier am Anfang von 0x40090f48
  (jmp LP_TICK), weil hold-mute (Patch 03) schon 0x400081f2 belegt; Encoder des Hauptbildschirms
  0x4001aa4e -> jmp LP_ENC; MainScreenView::draw 0x4001b22a -> jmp LP_DRAW; Schrittweite 0x4001aaba pea 2 -> pea 1.
Aufruf: g2_levelpan.py [out.json]
"""
import struct, sys
from common import *                 # noqa: F401,F403
from cfasm import asm, done as adone

M_1, M_2, M_3, M_4, M_5, M_6, M_7 = 0x40194AD4, 0x40195A7C, 0x4014B784, 0x4014E608, 0x40152F88, 0x40159A04, 0x40159ADC
M_8, M_9, M_10, M_11 = 0x4015B820, 0x4015BF24, 0x4015C9A4, 0x4015FB6C
SIZE = {M_9: 108, M_10: 108, M_11: 108, M_1: 124, M_2: 124, M_3: 108, M_4: 108, M_5: 108, M_6: 108, M_7: 108, M_8: 108}
CUR_PROJ, PROJ_SEQ, SEL_TRACK, PROJ_KIT = 0x400CF866, 0x4000EB90, 0x40012412, 0x4000EB9C
KEY_HELD, NEEDS_REDRAW, UISTATES, POPUP = 0x4007FAF4, 0x40076082, 0x400CF9A8, 0x4006B704
TRACK_PARAM, TRACK_LEVEL, FILL_RECT, TIMERS = 0x400097F0, 0x40009C5A, 0x40070DEA, 0x40090F48
PAN_PARAM, SHOW_TICKS = 0x1C, 90
ENC_CONT, DRAW_CONT = 0x4001AA56, 0x4001B232
TICK_HOOK = (0x40090F48, (8, 'ea66ce1cc799c3b41751a76538f39ad339150217cede945af5a7742687f44dd3'))         # Anfang des Timer-Dienstes (einziger Aufrufer: UI-Takt 0x400081f2,
TIMERS_CONT = 0x40090F50                          # dort haengt schon hold-mute; so laufen beide)
ENC_HOOK = (0x4001AA4E, (8, '14607b32e7a5a2eae6fcb2e63e1770b2f2387c64c63e6289faf0eb8e75f9aa40'))
DRAW_HOOK = (0x4001B22A, (8, 'be792a6e18460b96600542b2cbd5cf9fb868e734f3020d5381a81d098a22e2e4'))
STEP_HOOK = (0x4001AABA, (4, 'a0d3a32cc07dd24bdd647b5a4c9f63dd1a1f782590e6da5f72c0d76bbe807fd6'))
FONT = (0x1EDB6F, 0x0B2497, 0x1C9F27, 0x1C9E4F, 0x16DE49, 0x1E4E4F, 0x1E4F6F, 0x1C9492, 0x1EDF6F, 0x1EDE4F, 0x000E00)


def code(S):
    out, labs = [], {}
    text = f'''
    ; Encoder des Hauptbildschirms: erst das Original; Encoder 1 (LEVEL/DATA): FUNC -> Pan, sonst Lautstaerke; Ablauf
    ; = Takt + 90 und Merker der gewaehlten Spur, dann neu zeichnen
    LP_ENC: move.l  8(sp),-(sp)
            move.l  8(sp),-(sp)
            jsr     LP_EORIG
            addq.l  #8,sp
            movea.l 8(sp),a0
            moveq   #1,d1
            cmp.l   12(a0),d1
            bne     le9
            move.l  d0,-(sp)
            move.l  a2,-(sp)
            pea     1.w
            jsr     {KEY_HELD}
            addq.l  #4,sp
            lea     LP_LVL,a2
            tst.l   d0
            beq     le1
            lea     LP_PAN,a2
    le1:    jsr     LP_TRK
            moveq   #6,d1
            cmp.l   d1,d0
            bcc     le8
            move.l  LP_CNT,d1
            addi.l  #{SHOW_TICKS},d1
            move.l  d1,0(a2,d0.l*4)
            moveq   #1,d1
            move.b  d1,24(a2,d0.l)
            move.l  12(sp),-(sp)
            jsr     {NEEDS_REDRAW}
            addq.l  #4,sp
    le8:    movea.l (sp)+,a2
            move.l  (sp)+,d0
    le9:    rts
    ;@SEG
    ; MainScreenView::draw: erst das Original; ohne offenes Parameter-Popup Pan, dann Lautstaerke, solange faellig
    LP_DRAW: move.l 8(sp),-(sp)
            move.l  8(sp),-(sp)
            jsr     LP_DORIG
            addq.l  #8,sp
            lea     -20(sp),sp
            movem.l d2-d4/a2-a3,(sp)
            movea.l 28(sp),a2
            jsr     {UISTATES}
            move.l  d0,-(sp)
            jsr     {POPUP}
            addq.l  #4,sp
            tst.b   d0
            bne     ld9
            jsr     LP_TRK
            moveq   #6,d1
            cmp.l   d1,d0
            bcc     ld9
            move.l  d0,d2
            lea     LP_PAN,a3
            jsr     LP_DUE
            beq     ld1
            jsr     LP_DPAN
    ld1:    lea     LP_LVL,a3
            jsr     LP_DUE
            beq     ld9
            jsr     LP_DLVL
    ld9:    movem.l (sp),d2-d4/a2-a3
            lea     20(sp),sp
            rts
    ;@SEG
    ; a3 = LP_PAN / LP_LVL, d2 = Spur: Z = 0, solange die Zahl zu zeigen ist; beim Ablauf Merker loeschen
    LP_DUE: tst.b   24(a3,d2.l)
            beq     du9
            move.l  LP_CNT,d1
            sub.l   0(a3,d2.l*4),d1
            bmi     du1
            clr.b   24(a3,d2.l)
            moveq   #0,d0
            rts
    du1:    moveq   #1,d0
    du9:    rts
    ;@SEG
    ; Pan der Spur d2 (-64..63) im Rechteck (114, 21)-(127, 29) ab x = 115: '-', Zehner (nicht 0), Einer
    LP_DPAN: jsr    {CUR_PROJ}
            move.l  d0,-(sp)
            jsr     {PROJ_KIT}
            move.l  d2,-(sp)
            move.l  d0,-(sp)
            jsr     {TRACK_PARAM}
            lea     12(sp),sp
            movea.l d0,a0
            movea.l (a0),a1
            movea.l 28(a1),a1
            pea     {PAN_PARAM}.w
            move.l  a0,-(sp)
            jsr     (a1)
            addq.l  #8,sp
            asr.l   #8,d0
            moveq   #64,d1
            sub.l   d1,d0
            move.l  d0,d4
            clr.l   -(sp)
            pea     29.w
            pea     127.w
            pea     21.w
            pea     114.w
            move.l  a2,-(sp)
            jsr     {FILL_RECT}
            lea     24(sp),sp
            jmp     LP_DP2
    ;@SEG
    LP_DP2: moveq   #115,d3
            tst.l   d4
            bpl     dp1
            neg.l   d4
            moveq   #10,d0
            jsr     LP_GLP
    dp1:    jsr     LP_TENS
            tst.l   d0
            beq     dp2
            jsr     LP_GLP
    dp2:    move.l  d4,d0
            jmp     LP_GLP
    ;@SEG
    ; UI-Takt (30 Hz): Anfang des Timer-Dienstes 0x40090f48 (lea / movem nachgespielt)
    LP_TICK: addq.l #1,LP_CNT
            lea     -24(sp),sp
            movem.l d2/a2-a4,(sp)
            jmp     {TIMERS_CONT}
    ; d0 = gewaehlte Spur
    LP_TRK: jsr     {CUR_PROJ}
            move.l  d0,-(sp)
            jsr     {PROJ_SEQ}
            move.l  d0,(sp)
            jsr     {SEL_TRACK}
            addq.l  #4,sp
            rts
    ; die verschobenen Anfaenge der beiden Funktionen, dann ihre Fortsetzung
    LP_EORIG: lea   -32(sp),sp
            movem.l d2-d7/a2-a3,(sp)
            jmp     {ENC_CONT}
    LP_DORIG: link  a6,#-64
            movem.l d2-d7/a2-a5,(sp)
            jmp     {DRAW_CONT}
    ; d0 = d4 / 10, d4 = d4 % 10 (d4 < 128)
    LP_TENS: moveq  #0,d0
            moveq   #10,d1
    tn1:    cmp.l   d1,d4
            bcs     tn9
            sub.l   d1,d4
            addq.l  #1,d0
            bra     tn1
    tn9:    rts
    ;@SEG
    ; Lautstaerke der Spur d2 (0..127) im Rechteck (65, 8)-(77, 16), rechtsbuendig auf x = 66 / 70 / 74
    LP_DLVL: jsr    {CUR_PROJ}
            move.l  d0,-(sp)
            jsr     {PROJ_KIT}
            move.l  d2,-(sp)
            move.l  d0,-(sp)
            jsr     {TRACK_LEVEL}
            lea     12(sp),sp
            moveq   #0,d4
            move.b  d0,d4
            clr.l   -(sp)
            pea     16.w
            pea     77.w
            pea     8.w
            pea     65.w
            move.l  a2,-(sp)
            jsr     {FILL_RECT}
            lea     24(sp),sp
            jmp     LP_DL2
    ;@SEG
    LP_DL2: moveq   #66,d3
            moveq   #100,d1
            cmp.l   d1,d4
            bcs     dl1
            sub.l   d1,d4
            moveq   #1,d0
            jsr     LP_GLL
            bra     dl3
    dl1:    addq.l  #4,d3
            moveq   #10,d1
            cmp.l   d1,d4
            bcc     dl3
            addq.l  #4,d3
            bra     dl4
    dl3:    jsr     LP_TENS
            jsr     LP_GLL
    dl4:    move.l  d4,d0
            jmp     LP_GLL
    ;@SEG
    ; Zeichen d0 (0..9, 10 = '-') bei x = d3, Zeilen y0..y0+6 (Pixel (x, y) = Bit 31 - y des Worts x * Schritt (+12) der
    ; Bilddaten (+16), wie Bitmap::setPixel), dann d3 += 4
    LP_GLL: moveq   #9,d1
            bra     gl0
    LP_GLP: moveq   #22,d1
    gl0:    lea     -16(sp),sp
            movem.l d2/d4-d6,(sp)
            lea     LP_FONT,a0
            move.l  0(a0,d0.l*4),d5
            moveq   #31,d6
            sub.l   d1,d6
            moveq   #7,d4
    gl1:    moveq   #1,d0
            lsl.l   d6,d0
            moveq   #2,d2
    gl2:    btst    d2,d5
            beq     gl3
            moveq   #2,d1
            sub.l   d2,d1
            add.l   d3,d1
            muls.l  12(a2),d1
            lsl.l   #2,d1
            movea.l 16(a2),a1
            or.l    d0,0(a1,d1.l)
    gl3:    subq.l  #1,d2
            bpl     gl2
            lsr.l   #3,d5
            subq.l  #1,d6
            subq.l  #1,d4
            bne     gl1
            movem.l (sp),d2/d4-d6
            lea     16(sp),sp
            addq.l  #4,d3
            rts
    ;@SEG
    LP_FONT: dc.l   {", ".join(str(x) for x in FONT)}
    ;@SEG
    LP_CNT: dc.l    0
    LP_PAN: dc.l    0, 0, 0, 0, 0, 0, 0, 0
    LP_LVL: dc.l    0, 0, 0, 0, 0, 0, 0, 0
    '''
    for va, piece in zip([M_1, M_2, M_8, M_3, M_9, M_4, M_5, M_10, M_6, M_7, M_11], text.split(';@SEG')):
        a = A(va); asm(a, piece, S); out.append((va, adone(a, S))); labs.update(a.lab)
    return out, labs


def build():
    import collections
    S = collections.defaultdict(int)
    for _ in range(2):
        parts, lab = code(S); S = dict(lab)
    return parts, S


def tweak(img):
    parts, S = build()
    W = Writes(img)
    for va, b in parts:
        W.mask(va, b, SIZE[va])
    W.hook(*TICK_HOOK, jmp(S['LP_TICK']) + bytes.fromhex('4e71'))
    W.hook(*ENC_HOOK, jmp(S['LP_ENC']) + bytes.fromhex('4e71'))
    W.hook(*DRAW_HOOK, jmp(S['LP_DRAW']) + bytes.fromhex('4e71'))
    W.hook(*STEP_HOOK, bytes.fromhex('48780001'))          # pea 1.w (Schrittweite von LEVEL/DATA)
    return patch('level-pan-values', 19, 'Volume and pan as numbers',
                 ["Main screen: turning LEVEL/DATA shows the selected track's volume (0..127) instead of the speaker icon;",
                  "FUNC + LEVEL/DATA shows its pan (-64..63) instead of the 'R'. The number stays 3 s after the last move.",
                  "LEVEL/DATA moves by 1 per detent on the main screen (instead of 2); fast mode (x16) unchanged.",
                  "Port of 'level-pan-values' from Modded-Cycles (18nelli18, MIT), after the mod by djd_oz.",
                  "Erzeugt von v2/g2_levelpan.py."], W,
                 hooks=[f"{x[0]:#x}" for x in (TICK_HOOK, ENC_HOOK, DRAW_HOOK, STEP_HOOK)],
                 symbols={k: f"{S[k]:#x}" for k in ('LP_TICK', 'LP_ENC', 'LP_DRAW', 'LP_CNT', 'LP_PAN', 'LP_LVL', 'LP_FONT')})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    print({f"{va:#x}": len(b) for va, b in build()[0]})
