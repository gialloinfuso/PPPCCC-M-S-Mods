#!/usr/bin/env python3
"""Mod 'load-meter' (v2): Lastanzeige der Audio-Berechnung. Braucht nur 'core'. Nach dem Einschalten aus
(an nur, wenn METER = 'LDON'; der RAM hinter dem BSS wird beim Start nicht geloescht).
RETRIG halten + BPM (Taste 14, Hauptbildschirm) = an / aus (smp39, Pip 11.11.; vorher SETTINGS + REVERB SEND rechts / links):
  Kaestchen 'LOAD Spitze/Mittel' (% der Blockzeit, alle 0.5 s).
Messung wie v1 (gen_loadmeter_113): PROBE statt jsr Audio bei 0x40059382; Spitze% = (Ticks*1164)>>20,
  Mittel% = ((Summe>>10)*1589)>>20 ueber 750 Bloecke. Anzeige jetzt ueber Core-OVS (Art 3, eigene Zeichenfunktion LDRAW
  mit der 3x7-Schrift aus v1, nur noch die noetigen Zeichen).
LMK: Haken 0x4001c1ce (BPM im Hauptbildschirm 0x4001c0e4): Druecken bei gehaltenem RETRIG -> umschalten, angenommen
  (Rueckgabe 1, kein Tempo-Menue); sonst wie die Firmware. Core-Slot 3 bleibt leer.
Speicher: 0x4016b6f8 (PROBE, NUM), 0x4016b9e8 (LDRAW, Schrift), 0x40152d38 (LMH). RAM 0x4a33c3d0..0x4a33c3f3 (36 B).
Aufruf: g2_loadmeter.py [out.json]
"""
import struct, sys
from common import *                 # noqa: F401,F403
import common as C
from cfasm import asm, done as adone
import g2_core as core
import gen_overlay_113 as ovl

M_LM, M_LM2, M_LM3 = 0x4016B6F8, 0x4016B9E8, 0x40152D38
SIZES = {M_LM: 376, M_LM2: 376, M_LM3: 192}
P_HOOK, P_ORIG, AUDIO = 0x40059382, (6, 'bc2910c59a0d8e6999ccd601395bca9fd72e3e23d992899f38377b3b07ac2f81'), 0x4005979E   # jsr AUDIO (Laenge + SHA-256)
MV = 0x4A33C3D0
METER, PR_RET, PR_T0, PK, SUM, N, BUFN, BUF = 0, 4, 8, 12, 16, 20, 24, 28
LM_ON = 0x4C444F4E                    # 'LDON': an nur mit diesem Wort (RAM nach dem Einschalten zufaellig -> sonst aus)
NBLK, K_PK, K_AVG = 750, 1164, 1589
ORDER = "0123456789-/LOAD"
DASH, SLASH = ORDER.index('-'), ORDER.index('/')
BOX = (28, 18, 99, 47)
KEY_RETRIG, KEY_BPM = 4, 14
K_HOOK, K_CK, K_CONT, K_DONE = 0x4001C1CE, (8, 'e233a6f0b9d3f0020a3885be9ae1acaaf109f8b25f21fc5fab974d0969b8f10f'), 0x4001C1D6, 0x4001CBF2
PRESS = 0x400724A0                   # Ereignis: gedrueckt
LABEL, LABEL_X = "LOAD", 56


def build_probe(ldraw):
    cs = core.sym()
    a = A(M_LM)
    asm(a, f'''
    ; PROBE statt jsr AUDIO: Dauer der Audio-Berechnung messen (Zeitgeber vorher / nachher), alle NBLK Bloecke Text bauen
    PROBE:  move.l  {MV + METER:#x},d0
            cmpi.l  #{LM_ON:#x},d0
            beq     pm
            jmp     {AUDIO:#x}               ; aus: nur die Audio-Funktion
    pm:     move.l  (sp)+,{MV + PR_RET:#x}
            move.l  {C.TIMER:#x},d0
            move.l  d0,{MV + PR_T0:#x}
            orig    {P_HOOK:#x},6            ; verschobener Originalbefehl: jsr AUDIO
            move.l  d0,-(sp)
            move.l  {C.TIMER:#x},d0
            sub.l   {MV + PR_T0:#x},d0       ; Ticks dieses Blocks
            lea     {MV:#x},a0
            cmp.l   {PK}(a0),d0
            bls     p1
            move.l  d0,{PK}(a0)              ; Spitze
    p1:     add.l   d0,{SUM}(a0)
            addq.l  #1,{N}(a0)
            move.l  {N}(a0),d0
            cmpi.l  #{NBLK},d0
            bcs     pout
            lea     -16(sp),sp
            movem.l d2-d4/a2,(sp)
            move.l  {PK}(a0),d1
            move.l  #{K_PK},d2
            muls.l  d2,d1
            moveq   #20,d2
            lsr.l   d2,d1                    ; Spitze %
            move.l  {SUM}(a0),d3
            moveq   #10,d2
            lsr.l   d2,d3
            move.l  #{K_AVG},d2
            muls.l  d2,d3
            moveq   #20,d2
            lsr.l   d2,d3                    ; Mittel %
            clr.l   {PK}(a0)
            clr.l   {SUM}(a0)
            clr.l   {N}(a0)
            lea     {MV + BUF:#x},a2
            moveq   #0,d4
            move.l  d3,-(sp)
            move.l  d1,d0
            bsr     NUM
            moveq   #{SLASH},d0
            move.b  d0,(a2)+
            addq.l  #1,d4
            move.l  (sp)+,d0
            bsr     NUM
            move.l  d4,{MV + BUFN:#x}
            moveq   #{C.OV_CUSTOM},d0        ; OVS(3, -, LDRAW, 0)
            lea     {ldraw:#x},a0
            suba.l  a1,a1
            jsr     {cs['OVS']:#x}
            movem.l (sp),d2-d4/a2
            lea     16(sp),sp
    pout:   move.l  (sp)+,d0
            move.l  {MV + PR_RET:#x},-(sp)
            rts
    ; NUM: d0 (0..999) -> Ziffern ohne fuehrende Nullen nach (a2)+, d4 zaehlt
    NUM:    cmpi.l  #999,d0
            bls     n0
            move.l  #999,d0
    n0:     moveq   #0,d3
            moveq   #100,d1
            bsr     DIG
            moveq   #10,d1
            bsr     DIG
            moveq   #1,d3
            moveq   #1,d1
            bsr     DIG
            rts
    DIG:    moveq   #0,d2
    dl:     cmp.l   d1,d0
            bcs     dd
            sub.l   d1,d0
            addq.l  #1,d2
            bra     dl
    dd:     tst.l   d2
            bne     pr
            tst.l   d3
            beq     dr
    pr:     move.b  d2,(a2)+
            addq.l  #1,d4
            moveq   #1,d3
    dr:     rts
    ''')
    code = adone(a); check_cf(code, M_LM)
    return code, dict(a.lab)


def build_lmk(ldraw):
    cs = core.sym()
    a = A(M_LM3)
    asm(a, f'''
    ; LMK (jmp von 0x4001c1ce, BPM im Hauptbildschirm; a2 Ansicht, d3 Ereignis): gedrueckt und RETRIG gehalten -> umschalten
    LMK:    move.l  d3,-(sp)
            jsr     {PRESS:#x}
            addq.l  #4,sp
            tst.b   d0
            beq     fw
            pea     {KEY_RETRIG}.w
            jsr     {C.HELD:#x}
            addq.l  #4,sp
            tst.l   d0
            beq     fw
            move.l  {MV + METER:#x},d0
            cmpi.l  #{LM_ON:#x},d0
            beq     off
            clr.l   {MV + PK:#x}
            clr.l   {MV + SUM:#x}
            clr.l   {MV + N:#x}
            move.l  #{LM_ON:#x},d0
            move.l  d0,{MV + METER:#x}
            moveq   #{DASH},d0
            move.b  d0,{MV + BUF:#x}
            move.b  d0,{MV + BUF + 1:#x}
            moveq   #2,d0
            move.l  d0,{MV + BUFN:#x}
            moveq   #{C.OV_CUSTOM},d0
            lea     {ldraw:#x},a0
            suba.l  a1,a1
            jsr     {cs['OVS']:#x}
            bra     dn
    off:    clr.l   {MV + METER:#x}
            moveq   #{C.OV_HIDE},d0
            jsr     {cs['OVS']:#x}
    dn:     moveq   #1,d2                    ; angenommen (kein Tempo-Menue)
            jmp     {K_DONE:#x}
    fw:     move.l  d3,-(sp)                 ; verschobene Befehle der Firmware
            lea     {PRESS:#x},a3
            jmp     {K_CONT:#x}
    ''')
    code = adone(a); check_cf(code, M_LM3)
    return code, dict(a.lab)


def build_ui():
    def fill(x0, y0, x1, y1, col):
        return f'''
            moveq   #{x0},d2
            moveq   #{y0},d3
            moveq   #{x1},d4
            moveq   #{y1},d5
            moveq   #{col},d6
            bsr     RECT'''
    x0, y0, x1, y1 = BOX
    text = f'''
    ; LDRAW (a2 Bitmap): Kaestchen, 'LOAD', Wert (wie v1 gen_overlay_113 Art 3)
    LDRAW:{fill(x0, y0, x1, y1, 0)}{fill(x0, y1, x1, y1, 1)}{fill(x0, y0, x1, y0, 1)}{fill(x0, y0, x0, y1, 1)}{fill(x1, y0, x1, y1, 1)}
            lea     LBL,a0
            moveq   #{len(LABEL)},d3
            moveq   #{LABEL_X},d2
            moveq   #37,d7
            moveq   #1,d6
            bsr     DS                       ; 'LOAD'
            lea     {MV + BUF:#x},a0
            move.l  {MV + BUFN:#x},d3
            subq.l  #1,d3
            moveq   #7,d1
            cmp.l   d3,d1
            bcs     ld                       ; 1..8 Zeichen
            addq.l  #1,d3
            moveq   #65,d2
            move.l  d3,d0
            lsl.l   #2,d0
            sub.l   d0,d2                    ; mittig
            moveq   #2,d6
            moveq   #21,d7
            bsr     DS                       ; Wert doppelt gross
    ld:     rts
    ; DS: a0 Zeichen, d3 Anzahl, d2 x, d7 y unten, d6 Massstab
    DS:     moveq   #0,d0
            move.b  (a0)+,d0
            move.l  a0,-(sp)
            lsl.l   #2,d0
            lea     FONT,a1
            move.l  0(a1,d0.l),d5
            bsr     GL
            movea.l (sp)+,a0
            move.l  d6,d0
            lsl.l   #2,d0
            add.l   d0,d2
            subq.l  #1,d3
            bne     DS
            rts
    ; GL: ein Zeichen 3x7 (d5 Bits), Kaestchen d6 x d6
    GL:     move.l  d3,-(sp)
            move.l  d7,d4
            moveq   #7,d3
    gr:     btst    #2,d5
            beq     c1
            move.l  d2,d0
            bsr     BLK
    c1:     btst    #1,d5
            beq     c2
            move.l  d2,d0
            add.l   d6,d0
            bsr     BLK
    c2:     btst    #0,d5
            beq     c3
            move.l  d2,d0
            add.l   d6,d0
            add.l   d6,d0
            bsr     BLK
    c3:     lsr.l   #3,d5
            add.l   d6,d4
            subq.l  #1,d3
            bne     gr
            move.l  (sp)+,d3
            rts
    RECT:   move.l  d6,-(sp)
            move.l  d5,-(sp)
            move.l  d4,-(sp)
            move.l  d3,-(sp)
            move.l  d2,-(sp)
            move.l  a2,-(sp)
            jsr     {ovl.FILL:#x}
            lea     24(sp),sp
            rts
    BLK:    pea     1.w
            move.l  d4,d1
            add.l   d6,d1
            subq.l  #1,d1
            move.l  d1,-(sp)
            move.l  d0,d1
            add.l   d6,d1
            subq.l  #1,d1
            move.l  d1,-(sp)
            move.l  d4,-(sp)
            move.l  d0,-(sp)
            move.l  a2,-(sp)
            jsr     {ovl.FILL:#x}
            lea     24(sp),sp
            rts
'''
    def tail(end):
        pad = (-end) % 4
        font = struct.pack('>%dI' % len(ORDER), *[ovl.glyph(c) for c in ORDER])
        lbl = bytes(ORDER.index(c) for c in LABEL)
        return bytes(pad) + font + lbl, {'FONT': end + pad, 'LBL': end + pad + len(font)}
    code, lab = asm2(M_LM2, text, tail)
    lab.pop('LBL', None)
    return code, lab


def build():
    ui, lu = build_ui()
    pr, lp = build_probe(lu['LDRAW'])
    lh, ll = build_lmk(lu['LDRAW'])
    lu.update(lp); lu.update(ll)
    return {M_LM: pr, M_LM2: ui, M_LM3: lh}, lu


def tweak(img):
    base = apply(img, core.tweak(img))
    parts, lab = build()
    W = Writes(base)
    for va, b in parts.items():
        W.mask(va, b, SIZES[va])
    W.hook(P_HOOK, P_ORIG, jsr(lab['PROBE']))
    W.hook(K_HOOK, K_CK, jmp(lab['LMK']) + bytes.fromhex('4e71'))      # smp39: RETRIG + BPM
    return patch('load-meter', 8, 'Audio load meter',
                 ["RETRIG + BPM toggles 'LOAD peak/average' (percent of the audio block time, every 0.5 s).",
                  "Off after power-on. Erzeugt von v2/g2_loadmeter.py."], W, requires=['core'],
                 hooks=[f"{P_HOOK:#x}", f"{K_HOOK:#x}"],
                 memory=[{"va": f"{MV:#x}", "size": 36, "ram": True, "use": "meter state + text"}],
                 symbols={k: f"{lab[k]:#x}" for k in ('PROBE', 'NUM', 'LMK', 'LDRAW', 'FONT')},
                 params={"slot": C.SLOT['load-meter'], "mv": f"{MV:#x}", "nblk": NBLK, "k_pk": K_PK, "k_avg": K_AVG,
                         "block_ticks": 90112, "keys": "RETRIG + BPM"})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    parts, lab = build()
    print({f"{va:#x}": len(b) for va, b in parts.items()}, {k: hex(v) for k, v in lab.items() if k.isupper()})
