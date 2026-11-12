#!/usr/bin/env python3
"""Mod 'param-undo' (v2, Patch 20): das Parameter-Popup (alter -> neuer Wert, BACK = rueckgaengig) steht 3x so lange.
Unabhaengig (kein Core).

Pip 09.11.2026: das Undo eines Parameters (BACK, solange das Pfeil-Popup steht) soll laenger gehen. smp27: ohne Zeitlimit
(Variante A); smp29 (Pip): doch lieber mit Timer, 3x so lang wie normal (180 statt 60 Takte).
Firmware 1.13, ParameterPageView (Vtable 0x4010052c): beim Drehen setzt 0x4001f760 'moveq #60,d0 ; move.l d0,$238(a2)' den
  Zaehler +0x238; der Takt (+0x2c, 0x4001efaa) zaehlt > 0 herunter und schliesst bei 0 Popup + Undo (0x4001ef0e). 180 passt
  nicht in moveq: die 6 Bytes werden 'jsr PUT' (Maske, frei seit smp28: M_EV des Samplers), PUT setzt 180 und kehrt zurueck.
  Nach BACK setzt die Firmware weiter 15 Takte (0x4001fb06). Ein neuer Regler ersetzt Popup und Undo.
Aufruf: g2_paramundo.py [out.json]
"""
import sys
from common import *                 # noqa: F401,F403

HOOK, CK = 0x4001F760, (6, 'da5d72dc1fc9ef5ba10d40135404e55a421a7c22053edbb0b475310257e46773')   # moveq #$3c,d0 ; move.l d0,$238(a2)
M_PUT = 0x40178888                   # Maske (124 B)
TICKS, FW_TICKS = 180, 60


def put_code():
    from cfasm import asm, done as adone
    a = A(M_PUT)
    asm(a, f'''
    ; PUT: statt moveq #60,d0 ; move.l d0,$238(a2) (Zaehler des Popups)
    PUT:    move.l  #{TICKS},d0
            move.l  d0,0x238(a2)
            rts
    ''')
    return adone(a)


def tweak(img):
    W = Writes(img)
    W.mask(M_PUT, put_code(), 124)
    W.hook(HOOK, CK, jsr(M_PUT))
    return patch('param-undo', 20, 'Parameter undo: 3x longer',
                 ["The value popup after turning a knob (old -> new, BACK = undo) stays 3x as long as normal (180 instead of 60",
                  "ticks): BACK undoes the change while it is shown. After BACK the restored value shows briefly as before.",
                  "Erzeugt von v2/g2_paramundo.py."], W, hooks=[f"{HOOK:#x}"],
                 params={"ticks": TICKS, "firmware_ticks": FW_TICKS}, symbols={"PUT": f"{M_PUT:#x}"})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    print(len(t['writes']))
