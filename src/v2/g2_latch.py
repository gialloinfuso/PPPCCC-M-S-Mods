#!/usr/bin/env python3
"""Teil 'latching-mute' von 01 mute-solo (v2.3): Mute-Modus einrasten. Eigener Code (12.11.2026, Pip: drumkillas Tweak
nachbauen, damit das Repo nicht von seinem abhaengt); Verhalten wie drumkillas Tweak 01-latching-mute
(drumkilla/elektron-model-tweaks, MIT), Idee und Bedienung von dort.

Bedienung: TRACK halten + FUNC antippen: der Mute-Modus rastet ein (FUNC leuchtet); FUNC kurz allein antippen: aus.
  FUNC lange halten oder mit einer anderen Taste benutzen (z. B. FUNC + Track-Taste = Solo, FUNC + Regler) beendet nichts.
  TRACK, PATTERN (Taste 3) und RETRIG wirken im eingerasteten Modus wie sonst (Track-Tasten schalten dann nicht).
Firmware 1.13 (Mute-Ansicht, MuteView):
  Vtable 0x40100c44 = Tasten 0x400234b6: FUNC losgelassen -> Ansicht schliessen (vt[0x28]); sonst Grundklasse. -> LKH:
    FUNC gedrueckt: Zeit merken, USED = 0; FUNC losgelassen und KEEP: verbraucht, Ansicht bleibt; andere Taste gedrueckt bei
    gehaltenem FUNC im Modus: USED = 1; dann weiter 0x400234b6.
  Track-Tasten 0x4002350a: bei 0x4002351a (Taste -> Spur, 8 B) -> jmp LTK: UI-Zustand 0x4006bb18 oder TRACK / PATTERN /
    RETRIG gehalten (ohne FUNC) -> Grundklasse (0x4002357e); sonst die verschobenen Befehle und weiter (0x40023522).
  LEDs je Bild 0x4002336a: bei 0x400233a0 (jsr LED-Steuerung) -> jmp LLED: FUNC-LED (0x18) an und beansprucht (Maske (a2)).
  Zeit: Takt 0x40a78e28; kurzes Antippen < 0x400 Takte.
Speicher: unbenutzte Bereiche (0xff) 0x40148662..0x401487e0 und 0x40148328..0x401483a8 (Code), 0x401487e0 T0, 0x401487ec USED, 0x401487ed LATCH (wie
  bei drumkilla, Solo liest LATCH)."""
import sys
from common import *                 # noqa: F401,F403
import common as C
from cfasm import asm, done as adone

ORG, ORG_END = 0x40148662, 0x401487E0          # LKH, KEEP, LLED
ORG2, ORG2_END = 0x40148328, 0x401483A8        # LTK
T0, USED, LATCH = 0x401487E0, 0x401487EC, 0x401487ED
MV_VT, MV_KEYH = 0x40100C44, 0x400234B6
TK_HOOK, TK_CK, TK_CONT, TK_BASE = 0x4002351A, (8, '4acd7c9697a37a9cff865c775a2c084a98eb2638bb2f864c9a776fa1d93f8ef1'), 0x40023522, 0x4002357E
LED_HOOK, LED_CK, LED_BACK = 0x400233A0, (6, 'a8daba117e6cfe9d4daf86594645b03e2dca0360ba0399d9d8c9401324082da2'), 0x400233A6
KEYCODE, K_PRESS, K_REL = 0x4007240C, 0x400724A0, 0x40072470
UIS, UI_BUSY = 0x400CF9A8, 0x4006BB18
LED_CTRL, LED_SET, LED_LAYER, LED_FUNC, LED_ON = 0x400CFAF4, 0x40005F86, 0x404A8CB8, 0x18, 2
TICK, TAP = 0x40A78E28, 0x400
KEY_PATTERN = 3
PASS_KEYS = (C.KEY_TRACK, KEY_PATTERN, C.KEY_RETRIG)    # im eingerasteten Modus: Tasten der Firmware


def held(k, to):
    return f'''
            pea     {k}.w
            jsr     {C.HELD:#x}
            addq.l  #4,sp
            tst.l   d0
            bne     {to}'''


def code():
    a = A(ORG)
    asm(a, f'''
    ; ---------------- LKH(Ansicht, Ereignis): Tasten der Mute-Ansicht (Vtable statt 0x400234b6)
    LKH:    move.l  d2,-(sp)
            move.l  12(sp),d2                ; d2 = Ereignis
            move.l  d2,-(sp)
            jsr     {KEYCODE:#x}
            addq.l  #4,sp
            moveq   #{C.KEY_FUNC},d1
            cmp.l   d1,d0
            bne     lk_oth
            move.l  d2,-(sp)
            jsr     {K_PRESS:#x}
            addq.l  #4,sp
            tst.b   d0
            beq     lk_rel
            clr.b   {USED:#x}                ; FUNC gedrueckt: Zeit merken
            move.l  {TICK:#x},d0
            move.l  d0,{T0:#x}
            bra     lk_fw
    lk_rel: move.l  d2,-(sp)
            jsr     {K_REL:#x}
            addq.l  #4,sp
            tst.b   d0
            beq     lk_fw
            bsr     KEEP                     ; FUNC losgelassen: Ansicht offen lassen?
            tst.l   d0
            beq     lk_fw
            move.l  (sp)+,d2
            moveq   #1,d0                    ; ja: verbraucht
            rts
    lk_oth: tst.b   {LATCH:#x}               ; eingerastet, andere Taste gedrueckt, FUNC gehalten: FUNC war Modifier
            beq     lk_fw
            move.l  d2,-(sp)
            jsr     {K_PRESS:#x}
            addq.l  #4,sp
            tst.b   d0
            beq     lk_fw
            pea     {C.KEY_FUNC}.w
            jsr     {C.HELD:#x}
            addq.l  #4,sp
            tst.l   d0
            beq     lk_fw
            moveq   #1,d0
            move.b  d0,{USED:#x}
    lk_fw:  move.l  (sp)+,d2
            jmp     {MV_KEYH:#x}             ; Firmware
    ; ---------------- KEEP: d0 = 1, wenn die Ansicht nach dem Loslassen von FUNC offen bleibt (und LATCH = 1), sonst 0
    KEEP:   tst.b   {LATCH:#x}
            beq     kp_trk
            tst.b   {USED:#x}                ; FUNC benutzt oder lange gehalten: bleibt eingerastet
            bne     kp_on
            move.l  {TICK:#x},d0
            sub.l   {T0:#x},d0
            cmpi.l  #{TAP:#x},d0
            bcc     kp_on
    kp_trk:{held(C.KEY_TRACK, 'kp_on')}
            clr.b   {LATCH:#x}               ; kurz angetippt ohne TRACK: aus
            moveq   #0,d0
            rts
    kp_on:  moveq   #1,d0
            move.b  d0,{LATCH:#x}
            rts
    ; ---------------- LLED: LEDs der Mute-Ansicht (a2 = beanspruchte LEDs): FUNC-LED an
    LLED:   pea     {LED_LAYER:#x}
            pea     {LED_ON}.w
            pea     {LED_FUNC}.w
            jsr     {LED_CTRL:#x}
            move.l  d0,-(sp)
            jsr     {LED_SET:#x}
            lea     16(sp),sp
            move.l  (a2),d0
            ori.l   #{1 << LED_FUNC:#x},d0
            move.l  d0,(a2)
            orig    {LED_HOOK:#x},6          ; verschobener Befehl (aus dem Image)
            jmp     {LED_BACK:#x}
    ''')
    b = adone(a); check_cf(b, ORG)
    assert ORG + len(b) <= ORG_END, len(b)
    a2 = A(ORG2)
    asm(a2, f'''
    ; ---------------- LTK: Track-Tasten der Mute-Ansicht (d2 = Ereignis); TRACK / PATTERN / RETRIG gehalten: Firmware
    LTK:    jsr     {UIS:#x}
            move.l  d0,-(sp)
            jsr     {UI_BUSY:#x}
            addq.l  #4,sp
            tst.b   d0
            bne     lt_fw{held(C.KEY_FUNC, 'lt_mute')}''' + ''.join(held(k, 'lt_fw') for k in PASS_KEYS) + f'''
    lt_mute: orig   {TK_HOOK:#x},8           ; verschobene Befehle: Taste -> Spur (aus dem Image)
            jmp     {TK_CONT:#x}
    lt_fw:  jmp     {TK_BASE:#x}
    ''')
    b2 = adone(a2); check_cf(b2, ORG2)
    assert ORG2 + len(b2) <= ORG2_END, len(b2)
    return b, b2, dict(a.lab, **a2.lab)


def tweak(img):
    W = Writes(img)
    b, b2, lab = code()
    free = lambda va, n: bytes(img[va - BASE:va - BASE + n]) == b'\xff' * n
    assert free(ORG, len(b)) and free(ORG2, len(b2)) and free(T0, 4) and free(USED, 2), 'Bereich nicht frei'
    W.put(ORG, b); W.put(ORG2, b2)
    W.put(T0, bytes(4)); W.put(USED, bytes(2))
    W.hook(MV_VT, struct.pack('>I', MV_KEYH), struct.pack('>I', lab['LKH']))
    W.hook(TK_HOOK, TK_CK, jmp(lab['LTK']) + bytes.fromhex('4e71'))
    W.hook(LED_HOOK, LED_CK, jmp(lab['LLED']))
    return patch('latching-mute', 1, 'Latching mute',
                 ["Hold TRACK and tap FUNC: the mute mode latches and FUNC lights up. A short tap on FUNC alone leaves it.",
                  "Holding FUNC long or using it with another key does not leave it; TRACK, PATTERN and RETRIG work as usual.",
                  "Behaviour as in drumkilla's latching-mute tweak (elektron-model-tweaks, MIT); own code.",
                  "Erzeugt von v2/g2_latch.py."], W,
                 hooks=[f"{x:#x}" for x in (MV_VT, TK_HOOK, LED_HOOK)],
                 memory=[{"va": f"{ORG:#x}", "size": len(b), "use": "code (unused 0xff area)"},
                         {"va": f"{ORG2:#x}", "size": len(b2), "use": "code (unused 0xff area)"},
                         {"va": f"{T0:#x}", "size": 14, "ram": True, "use": "FUNC press time, FUNC used, latched flag"}],
                 symbols={**{k: f"{v:#x}" for k, v in lab.items() if k[0].isupper()},
                          "T0": f"{T0:#x}", "USED": f"{USED:#x}", "latch_flag": f"{LATCH:#x}"})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    print(len(t['writes']), 'writes')
