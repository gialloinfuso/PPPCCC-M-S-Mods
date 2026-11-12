#!/usr/bin/env python3
"""Mod 'multiline-browser' (v2, Patch 17): der Browser (Presets, Ordner, Samples) zeigt 3 Namen in kleiner Schrift statt
eines grossen; '>' vor der Zeile des Cursors, der geladene Sound invertiert, Ordner mit kleinem Zeichen statt Bild.

Portierung (Pip 02.11.2026: "aus dem 18nelli-Branch nach- und einbauen") von 'multiline-browser' aus Modded-Cycles
(18nelli18/Modded-Cycles, MIT; notes/40, tools/machines/multiline_browser/multiline_browser.S; Idee und erste Adressen von
einem Community-Script). Gleicher Ablauf, gleiche Werte und Pixel; hier mit cfasm neu geschrieben, in fuenf 124-B-Masken
(31x22) statt eines 47x47-Masks (die sind hier alle belegt), Sprungziele ueber jmp / jsr. Mit browser-scroll (Patch 18)
laeuft nur die Zeile des Cursors ueber dessen Laufschrift.

Firmware 1.13 (aus notes/40; Zeichnen des Browsers 0x400a539c, Rahmen a6, a2 Browser, d2 Bild, a3 x, a4 Name, d4 Text,
d7 geladener Sound, -32(a6) Zeichen die passen, -36(a6) Zeile i, -40(a6) Text-Destruktor 0x400f7d5c, -44(a6) Text-Konstr.
0x400f980c; Liste +16 Auswahl, +20 erste sichtbare Zeile, +24 Auswahl - erste):
  0x400a5588 jmp ML_ROW, 0x400a55a4 jmp ML_AFT, 0x400a5612 jsr ML_BND + bra.s 0x400a5624, 0x400a576e jsr ML_ICO;
  Konstanten: Unterordner 0x4003f622 clr.l 24(a2), 0x400406a8 (Fenster der Liste nicht ueberschreiben), kleine Schrift
  0x4003f752, Pfeile 0x400a547c / 0x400a54ac, x 0x400a54ca, <EMPTY> 0x400a5528 / 0x400a552c, nach Symbol 0x400a5776,
  3 Zeilen 0x400a69b4.
Aufruf: g2_mlbrowser.py [out.json]
"""
import struct, sys
from common import *                 # noqa: F401,F403
import common as C
from cfasm import asm, done as adone

M_1, M_2, M_3, M_4, M_5 = 0x4018F98C, 0x4018FA84, 0x4018FB7C, 0x401907A4, 0x40190A1C
SIZE = {M_1: 124, M_2: 124, M_3: 124, M_4: 124, M_5: 124}
ROWS, ROW_H, Y0, X_TEXT, CUR_X, X_MARK = 3, 13, 40, 9, 2, 9
UP_Y, DOWN_Y = Y0 + 4, Y0 - (ROWS - 1) * ROW_H
FONT_SMALL = 0x40EA14CC
FONT_H, TXT_DRAW, TXT_W, TXT_FH, RECT_F, FRAME_F, SPRITE = 0x400720F8, 0x4007199C, 0x400722B2, 0x40072296, 0x40070DEA, 0x40070F6E, 0x40071DA4
ORIG_CALL, CONT, ICON_FOLDER = 0x400A559E, 0x400A5608, 0x40FE2D60
HOOKS = ((0x400A5588, (6, 'a710957406ed96ba6ce98c5397769f171865b9cb5fde0df97c63a3c9ec8e34d0'), 'ML_ROW', 0x4EF9, b''),
         (0x400A55A4, (6, 'ecb2bdbe3364d4ead44587a543868abdd4df5fafd71939a51174417e44eb9a1b'), 'ML_AFT', 0x4EF9, b''),
         (0x400A5612, (8, 'de96f0f9c514b976b38aaf328fc7b10b9a9a51c32f33b0ea1d6190bb4fd9bbda'), 'ML_BND', 0x4EB9, b'\x60\x0a'),
         (0x400A576E, (6, '71bce7f04f112c253042f10eccf523f1c132e364e8bcefde4a14b9d969276aa1'), 'ML_ICO', 0x4EB9, b''))
W16 = lambda v: struct.pack('>H', v)
PATCHES = (   # (Adresse, (Laenge, SHA der Original-Bytes), neue Bytes)
    (0x4003F622, (4, '334cc791a77e2d005db55040368eae194a82dcacc39a2068303dfed80cabba88'), 'clr.l 24(a2)'),
    (0x400406A8, (18, '194052055fc2bc148a2d3e7b8098d6ec1408c178786749adc79ee9545eb1aa3e'), 'SUBDIR'),
    (0x4003F752, (4, '4d0ad98cbdc695c271a8f9324ac3f4040ea722c2a2204f2f33428f015b5032cf'), struct.pack('>I', FONT_SMALL)),
    (0x400A547C, (2, 'eb397f6553d3485bc197003a6be3e81c6f696675467b648f0791a8be05de1230'), W16(UP_Y)),
    (0x400A54AC, (2, 'f431a7f47862c05a44c40ef1f447d207ba15d339cef1fb9357564974137c1673'), W16(DOWN_Y)),
    (0x400A54CA, (2, 'fcf0a6c700dd13e274b6fba8deea8dd9b26e4eedde3495717cac8408c9c5177f'), W16(X_TEXT)),
    (0x400A5528, (2, 'f431a7f47862c05a44c40ef1f447d207ba15d339cef1fb9357564974137c1673'), W16(Y0)),
    (0x400A552C, (2, 'fcf0a6c700dd13e274b6fba8deea8dd9b26e4eedde3495717cac8408c9c5177f'), W16(X_TEXT)),
    (0x400A5776, (2, 'b894c5014be1934ed94625d131254ba84e97a2115ac9a697b680fe256f50e5cc'), W16(X_MARK)),
    (0x400A69B4, (2, 'b413f47d13ee2fe6c845b2ee141af81de858df4ec549a58b7970bb96645bc8d2'), W16(ROWS)),
)


def small(va, text):
    a = A(va); asm(a, text); return adone(a)


def multi(S, text, masks):
    out, labs = [], {}
    for va, piece in zip(masks, text.split(';@SEG')):
        a = A(va); asm(a, piece, S); out.append((va, adone(a, S))); labs.update(a.lab)
    return out, labs


def code(S):
    return multi(S, f'''
    ; d1 = y der Zeile -36(a6) (die Anzeige zaehlt y von unten: die 1. Zeile oben)
    ROWY:   moveq   #{-ROW_H},d1
            muls.l  -36(a6),d1
            addi.l  #{Y0},d1
            rts
    ; 0x400a5588: jede Zeile in ihrer Hoehe; die des Cursors ueber den Original-Aufruf (Laufschrift von browser-scroll)
    ML_ROW: move.l  652(a2),(sp)
            jsr     {FONT_H}
            jsr     ROWY
            move.l  a4,-(sp)
            move.l  -32(a6),-(sp)
            move.l  d1,-(sp)
            move.l  a3,-(sp)
            move.l  d0,-(sp)
            move.l  d2,-(sp)
            move.l  -36(a6),d0
            cmp.l   24(a2),d0
            beq     mr1
            jsr     {TXT_DRAW}
            jmp     ML_AFT
    mr1:    jmp     {ORIG_CALL}
    ;@SEG
    ; 0x400a55a4: '>' vor der Zeile des Cursors, dann der geladene Sound (ML_LD)
    ML_AFT: lea     28(sp),sp
            movea.l -40(a6),a5
            move.l  -36(a6),d0
            cmp.l   24(a2),d0
            bne     ma2
            move.l  652(a2),-(sp)
            jsr     {FONT_H}
            addq.l  #4,sp
            jsr     ROWY
            pea     ML_GT
            pea     1.w
            move.l  d1,-(sp)
            pea     {CUR_X}.w
            move.l  d0,-(sp)
            move.l  d2,-(sp)
            jsr     {TXT_DRAW}
            lea     24(sp),sp
    ma2:    tst.b   d7
            beq     ma3
            jmp     ML_LD
    ma3:    move.l  #{X_TEXT},d0
            movea.l d0,a3
            jmp     {CONT}
    ML_GT:  dc.b    0x3e, 0
    ;@SEG
    ; geladener Sound: sein Name invertiert, wie das Original (0x400a55b2..0x400a5604), in der Hoehe seiner Zeile
    ML_LD:  pea     -20(a6)
            move.l  a4,-(sp)
            move.l  d4,-(sp)
            movea.l -44(a6),a0
            orig    0x400a55be,38            ; Breite und Hoehe wie das Original (Befehle aus dem Image)
            jsr     ROWY
            pea     -1.w
            add.l   d1,d0
            addq.l  #1,d0
            move.l  d0,-(sp)
            pea     1(a3,a4.l)
            subq.l  #2,d1
            move.l  d1,-(sp)
            pea     -2(a3)
            move.l  d2,-(sp)
            jsr     {FRAME_F}
            lea     24(sp),sp
            move.l  #{X_TEXT},d0
            movea.l d0,a3
            jmp     {CONT}
    ;@SEG
    ; 0x400a5612: Zeilen = min(3, Eintraege - erste sichtbare Zeile)
    ML_BND: move.l  a2,-(sp)
            movea.l (a2),a0
            movea.l 12(a0),a0
            jsr     (a0)
            addq.l  #4,sp
            sub.l   20(a2),d0
            moveq   #{ROWS},d1
            cmp.l   d1,d0
            ble     mb1
            move.l  d1,d0
    mb1:    rts
    MKF:    dc.b    1, 5, {X_TEXT + 6}, 1, {X_TEXT}, 1, 6, {X_TEXT + 2}, 6, {X_TEXT}
    MKS:    dc.b    1, 7, {X_TEXT + 6}, 1, {X_TEXT}, 0, 6, {X_TEXT + 5}, 2, {X_TEXT + 1}
    ;@SEG
    ; 0x400a576e: statt des Ordner-Bilds (25x22) ein Zeichen von 7 px (zwei Rechtecke aus MKF / MKS)
    ML_ICO: lea     -16(sp),sp
            movem.l d2-d4/a2,(sp)
            move.l  20(sp),d2
            lea     MKF,a2
            move.l  24(sp),d0
            cmpi.l  #{ICON_FOLDER},d0
            beq     mi1
            lea     MKS,a2
    mi1:    jsr     ROWY
            move.l  d1,d3
            moveq   #2,d4
    mi2:    mvs.b   (a2)+,d0
            move.l  d0,-(sp)
            mvs.b   (a2)+,d0
            add.l   d3,d0
            move.l  d0,-(sp)
            mvs.b   (a2)+,d0
            move.l  d0,-(sp)
            mvs.b   (a2)+,d0
            add.l   d3,d0
            move.l  d0,-(sp)
            mvs.b   (a2)+,d0
            move.l  d0,-(sp)
            move.l  d2,-(sp)
            jsr     {RECT_F}
            lea     24(sp),sp
            subq.l  #1,d4
            bne     mi2
            movem.l (sp),d2-d4/a2
            lea     16(sp),sp
            rts
    ''', [M_1, M_2, M_3, M_4, M_5])


def build():
    import collections
    S = collections.defaultdict(int)
    for _ in range(2):
        parts, lab = code(S)
        S = dict(lab)
    return parts, S


def tweak(img):
    parts, S = build()
    W = Writes(img)
    for va, b in parts:
        W.mask(va, b, SIZE[va])
    for va, ck, sym, op, tail in HOOKS:
        W.hook(va, ck, struct.pack('>HI', op, S[sym]) + tail)
    for va, ck, new in PATCHES:
        if new == 'clr.l 24(a2)':
            new = small(va, '        clr.l   24(a2)')
        elif new == 'SUBDIR':      # nach jeder Bewegung im Unterordner: Eintrag 0 (zurueck) bleibt verboten, Fenster bleibt
            new = small(va, '''
            tst.l   d2
            dc.w    0x6e0a                   ; bgt.s +10 (hinter clr.l)
            moveq   #1,d2
            move.l  d2,20(a2)
            clr.l   24(a2)
            move.l  d2,16(a2)''')
        assert len(new) == ck[0], hex(va)
        W.hook(va, ck, new)
    return patch('multiline-browser', 17, 'Multi-line browser',
                 ["The browser (presets, folders, samples) shows 3 names in the small font instead of one big name.",
                  "'>' marks the cursor row, the loaded sound stays inverted, folders get a small mark.",
                  "Port of 'multiline-browser' from Modded-Cycles (18nelli18, MIT; idea from a community script).",
                  "Erzeugt von v2/g2_mlbrowser.py."], W,
                 hooks=[f"{x[0]:#x}" for x in HOOKS] + [f"{x[0]:#x}" for x in PATCHES],
                 symbols={k: f"{S[k]:#x}" for k in ('ML_ROW', 'ML_AFT', 'ML_BND', 'ML_ICO', 'ML_LD', 'ROWY')},
                 params={"rows": ROWS, "row_h": ROW_H, "y0": Y0})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    print({f"{va:#x}": len(b) for va, b in build()[0]})
