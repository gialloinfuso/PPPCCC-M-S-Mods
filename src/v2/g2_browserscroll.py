#!/usr/bin/env python3
"""Teil 'browser-scroll' des Cores (v2.3): ein zu langer Name im Browser (Sounds, Samples, Ordner) laeuft nach links durch.

Eigener Code (12.11.2026, Pip: drumkillas Tweak nachbauen, damit das Repo nicht von seinem abhaengt); Verhalten wie
drumkillas Tweak 03-browser-scroll (drumkilla/elektron-model-tweaks, MIT): etwa 0.17 s je Zeichen (256 Takte), am Anfang
und am Ende je drei Schritte Pause, ein Name, der passt, bleibt stehen. Mit multiline-browser laeuft nur die Zeile des Cursors
(die springt ueber den Original-Aufruf hierher).
Firmware 1.13: Browser-Zeile 0x400a559e jsr Text(ctx, Schrift, x, y, Zeichen, Name) 0x4007199c -> jsr BS. BS: Kennung des
  Namens (Laenge << 16 + Summe der Zeichen); neu -> von vorn; sonst neu zeichnen lassen (0x40069b84(UI)), je 256 Takte
  (0x40a78e28) einen Schritt; Name + Versatz an die Text-Funktion.
Speicher: unbenutzte Bereiche (0xff) 0x40147f22..0x40147fd8 (Code), 0x401485f0 (16 B Zustand)."""
import struct, sys
from common import *                 # noqa: F401,F403
from cfasm import asm, done as adone

ORG, ORG_END, ST = 0x40147F22, 0x40147FD8, 0x401485F0      # Zustand: +0 Kennung, +4 Versatz, +8 Takt, +12 Pause
CALL, TXT_DRAW = 0x400A559E, 0x4007199C
UIS, UI_DIRTY, TICK = 0x400CF9A8, 0x40069B84, 0x40A78E28
STEP_SHIFT, PAUSE = 8, 3


def code():
    a = A(ORG)
    asm(a, f'''
    ; BS(ctx, Schrift, x, y, Zeichen, Name): wie die Text-Funktion, mit Name + Versatz
    BS:     lea     -16(sp),sp
            movem.l d2-d4/a2,(sp)
            movea.l 40(sp),a0                ; Name
            lea     {ST:#x},a2
            moveq   #0,d2                    ; d2 = Laenge, d1 = Summe
            moveq   #0,d1
    bs1:    mvz.b   (a0)+,d0
            beq.s   bs2
            add.l   d0,d1
            addq.l  #1,d2
            bra.s   bs1
    bs2:    move.l  d2,d0
            swap    d0
            add.l   d1,d0                    ; Kennung
            cmp.l   (a2),d0
            beq.s   bs3
            move.l  d0,(a2)                  ; anderer Name: von vorn
            clr.l   4(a2)
            clr.l   12(a2)
            bra.s   bsx
    bs3:    jsr     {UIS:#x}
            move.l  d0,-(sp)
            jsr     {UI_DIRTY:#x}            ; weiter neu zeichnen (Laufschrift)
            addq.l  #4,sp
            move.l  {TICK:#x},d0
            move.l  d0,d1
            sub.l   8(a2),d1
            lsr.l   #{STEP_SHIFT},d1
            beq.s   bsx                      ; noch kein Schritt
            move.l  d0,8(a2)
            move.l  d2,d3
            sub.l   36(sp),d3                ; d3 = Zeichen ueber die Breite
            bpl.s   bs4
            moveq   #0,d3
    bs4:    move.l  4(a2),d1
            cmp.l   d3,d1
            bcc.s   bsend
            tst.l   d1
            beq.s   bsbeg
            addq.l  #1,d1                    ; ein Zeichen weiter
            move.l  d1,4(a2)
            bra.s   bsx
    bsend:  moveq   #-1,d1                   ; am Ende: Pause, dann von vorn
            bra.s   bsp
    bsbeg:  moveq   #0,d1                    ; am Anfang: Pause, dann los
    bsp:    move.l  12(a2),d0
            addq.l  #1,d0
            move.l  d0,12(a2)
            moveq   #{PAUSE},d4
            cmp.l   d4,d0
            bcs.s   bsx
            clr.l   12(a2)
            addq.l  #1,d1
            move.l  d1,4(a2)
    bsx:    move.l  4(a2),d0
            add.l   d0,40(sp)                ; Name + Versatz
            movem.l (sp),d2-d4/a2
            lea     16(sp),sp
            jmp     {TXT_DRAW:#x}
    ''')
    b = adone(a); check_cf(b, ORG)
    assert ORG + len(b) <= ORG_END, len(b)
    return b, dict(a.lab)


def tweak(img):
    W = Writes(img)
    b, lab = code()
    free = lambda va, n: bytes(img[va - BASE:va - BASE + n]) == b'\xff' * n
    assert free(ORG, len(b)) and free(ST, 16), 'Bereich nicht frei'
    W.put(ORG, b); W.put(ST, bytes(16))
    W.hook(CALL + 2, struct.pack('>I', TXT_DRAW), struct.pack('>I', lab['BS']))
    return patch('browser-scroll', 18, 'Scrolling names',
                 ["A selected name in the browser that does not fit scrolls left (about 0.17 s per character).",
                  "Behaviour as in drumkilla's browser-scroll tweak (elektron-model-tweaks, MIT); own code.",
                  "Erzeugt von v2/g2_browserscroll.py."], W, hooks=[f"{CALL:#x}"],
                 memory=[{"va": f"{ORG:#x}", "size": len(b), "use": "code (unused 0xff area)"},
                         {"va": f"{ST:#x}", "size": 16, "ram": True, "use": "name id, offset, tick, pause"}],
                 symbols={"BS": f"{lab['BS']:#x}", "BS_STATE": f"{ST:#x}"})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    print(len(t['writes']), 'writes')
