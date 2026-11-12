#!/usr/bin/env python3
"""Mod 'browser-keys' (v2, Patch 19, smp24): im Preset-/Sample-Browser oeffnet RETRIG das Speicher-Menue der Firmware
('Save Preset / Save Kit ...') statt FUNC. Unabhaengig (kein Core).

Pip 08.11.2026: FUNC loslassen im Browser oeffnete immer die Speicher-Frage; das Menue soll auf RETRIG.
Firmware 1.13: Tasten des Browsers 0x400a6d5c (Taste ueber 0x4007240c): Taste 1 (FUNC) -> 0x400a6da2 (beim Loslassen
  Speicher-Menue 0x400a6dd8 bzw. 0x400a714c), sonst 0x400a7120 (Grundklasse 0x4006ed84). Haken BRK bei 0x400a6d80
  (move.b #1,d1 ; cmp.l d0,d1 ; beq.b, d0 = Taste < 5): RETRIG (4) -> 0x400a6da2 (derselbe Ablauf wie bisher FUNC),
  alles andere (auch FUNC) -> 0x400a7120. FUNC als Modifier (gehalten) bleibt unberuehrt.
Speicher: Maske 0x40163b38 (104 B).
Aufruf: g2_browserkeys.py [out.json]
"""
import collections, struct, sys
from common import *                 # noqa: F401,F403
import common as C
from cfasm import asm, done as adone

M_BK = 0x40163B38
SIZE = {M_BK: 104}
BRK_HOOK, BRK_CK = 0x400A6D80, (8, 'bbbea8db6149b549eed3f984bf68c01fecc2faab48f062a47373c9e0b7ecc708')
BR_MENU, BR_DEFAULT = 0x400A6DA2, 0x400A7120
KEY_RETRIG = 4
# smp40 (Pip 11.11.): Hinweis unten rechts im Browser 'Fn=Menu' (Text der Firmware, einziger Verweis: pea bei 0x400a571e)
# -> eigener Text 'RT=MENU' (gleiche Laenge) in der Maske
HINT_REF, HINT_FW, HINT = 0x400A5720, 0x401301F6, b'RT=MENU'


def text():
    return f'''
    ; Browser-Tasten (d0 = Taste < 5, d2 = Ereignis, a2 = Browser): RETRIG -> Speicher-Menue, sonst Grundklasse
    BRK:    moveq   #{KEY_RETRIG},d1
            cmp.l   d0,d1
            bne     bk1
            jmp     {BR_MENU:#x}
    bk1:    jmp     {BR_DEFAULT:#x}
'''


def build():
    a = A(M_BK); asm(a, text(), collections.defaultdict(int))
    a = A(M_BK); asm(a, text(), dict(a.lab))
    code = adone(a, dict(a.lab)); lab = dict(a.lab)
    lab['HINT'] = M_BK + len(code); code += HINT + b'\0'
    return code, lab


def tweak(img):
    code, lab = build()
    W = Writes(img)
    W.mask(M_BK, code, SIZE[M_BK])
    W.hook(BRK_HOOK, BRK_CK, jmp(lab['BRK']) + bytes.fromhex('4e71'))
    W.hook(HINT_REF, struct.pack('>I', HINT_FW), struct.pack('>I', lab['HINT']))   # smp40: Hinweis 'RT=MENU'
    return patch('browser-keys', 19, 'Browser save menu on RETRIG',
                 ["In the preset / sample browser RETRIG opens the firmware's save menu (Save Preset / Save Kit ...) instead of FUNC.",
                  "FUNC alone does nothing there any more (still works as a modifier). The hint at the bottom right reads RT=MENU.",
                  "Erzeugt von v2/g2_browserkeys.py."], W,
                 hooks=[f"{BRK_HOOK:#x}", f"{HINT_REF:#x}"], symbols={'BRK': f"{lab['BRK']:#x}", 'BK_HINT': f"{lab['HINT']:#x}"},
                 params={"key": KEY_RETRIG, "menu": f"{BR_MENU:#x}", "default": f"{BR_DEFAULT:#x}"})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    print(len(build()[0]))
