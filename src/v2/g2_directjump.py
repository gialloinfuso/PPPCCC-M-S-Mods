#!/usr/bin/env python3
"""Mod 'direct-jump' (v2, Patch 15): Pattern sofort wechseln und an der aktuellen Step-Position weiterspielen. Unabhaengig.

Bedienung (Pip 28.10.2026): PATTERN druecken (Pattern-Auswahl), dann FUNC + TRIG = Direct Jump: das neue Pattern uebernimmt
  auf einem der naechsten Steps und spielt an der Position weiter, an der das alte gerade war (modulo der neuen Laenge).
  TRIG allein = normaler Wechsel am Pattern-Ende wie bisher. Bei gestopptem Sequencer macht FUNC + TRIG dasselbe wie TRIG.
Firmware 1.13 (Sequencer-ISR 0x40054c1e; Patterns liegen im RAM, 0x406fa040 + 0x77f6 * n):
  Pattern-Auswahl 0x40020a7a, TRIG gedrueckt: 0x40020c84 fragt FUNC ab (mit FUNC passierte bisher nichts). Haken -> DJK:
    ohne FUNC oder gestoppt weiter wie die Firmware (0x40020c94); mit FUNC und laufendem Sequencer die Pattern-Wahl der
    Firmware 0x4002037c(Ansicht, Index) (stellt das Pattern als naechstes in die Kette, wie beim Loslassen von TRIG), dann
    REQ setzen und die Taste wie bisher beenden (0x40020d5e).
  Sequencer, Tick 0 eines Steps: 0x4005563e prueft 0x40a78920 (Wechsel faellig, sonst am Pattern-Ende gesetzt). Haken ->
    DJS: bei REQ Startposition 0x40a788a0 = aktueller Master-Step 0x40a78840 (modulo der Laenge des neuen Patterns), Ende
    0x40a788a4 = -1, 0x40a78920 = 1, MIDI-Programmwechsel wie am Pattern-Ende (0x4005419e). Den Wechsel selbst macht die
    Firmware (sie rechnet die Positionen der Spuren aus der Startposition; bisher immer 0).
    DJS merkt sich ausserdem den naechsten Step jeder Spur (0x40a78860, Bytes).
  Nach dem Wechsel (0x40055898, jeder Tick 0): Haken -> DJF: einmal nach einem Direct Jump die Startschritte der Spuren
    (0x40a788bc, Worte) = gemerkter Step der Spur modulo ihrer Laenge im neuen Pattern (Per-Track-Modus: Laenge der Spur),
    so spielt jede Spur an ihrer eigenen Position weiter (auch im Per-Track-Modus des alten Patterns).
  Tastenverteiler der Pattern-Auswahl (0x40020a8c: Code 10 / 3 / 9 / 11 / 16..31, Rest -> allgemeiner Handler 0x40075f3c, der
    die Auswahl schliesst; der Verteiler ist immer in der Kette der Tasten-Empfaenger): Haken 0x40020aa6 -> FK: Code 1 wird
    nur bei eingeschaltetem Auswahlmodus angenommen (sonst FUNC-Gesten wie Mute weg: jump3), sonst wie die Firmware.
  Nach PATTERN (Loslassen) liegt ueber der Auswahl ein Fenster (Vtable 0x40101164.., Tasten 0x40024af0); es schliesst bei FUNC
    (Code 1, 0x40024b3a) Fenster und Auswahl. Haken 0x40024b12 -> FO: Code 1 angenommen (Rueckgabe 1 ueber 0x40024ba2). TRIG
    geht dort wie bisher durch (Fenster zu, Ereignis weiter an die Auswahl -> DJK).
  Auswahl offen nach dem Sprung (Pip 29.10.): TRIG im Fenster ruft sonst den Abschluss-Rueckruf (+0x48) und schliesst (+0x28);
    mit FUNC bei laufendem Sequencer ueberspringt OT (Haken 0x40024bd0) beides und gibt das Ereignis weiter (DJK). Beim
    Loslassen des letzten TRIG schaltet die Auswahl den Modus aus, wenn PATTERN nicht gehalten ist (0x40020df0); nach einem
    Direct Jump (KEEP) ueberspringt RL das. Normaler TRIG: KEEP geloescht, alles wie die Firmware.
  Beobachter der Auswahl (0x400206c6, laeuft nach jeder Aenderung von UIStates): Modus aus und Fenster zu, wenn PATTERN nicht
    gehalten (+0x90) und die Auswahl nicht wartet (+0x7c; TRIG gedrueckt bei 0x40020c74 loescht es). jump5 schloss deshalb
    trotzdem (Pip 29.10.). DJK setzt +0x7c wieder auf 1 (wie nach PATTERN tippen); mit gehaltenem PATTERN oeffnet die
    Firmware beim Loslassen dann ihr Fenster (0x40020730), die Auswahl bleibt auch dort offen.
  smp39 (Pip 10.11.: Pattern kopieren / einfuegen schliesst die Auswahl): REC (Kopieren, 0x40020f14), STOP (Einfuegen?,
    0x4002113e) und PLAY (Loeschen?, 0x40020fb8) zeigen ein Popup 'Copy Pattern' bzw. eine Halte-Abfrage ueber 0x4007700e; das
    schliesst jedes Overlay mit einem gemeinsamen Bereichs-Kennzeichen (Vektor +0x1c..+0x20, 0x40076102) - auch das Fenster der
    Auswahl ('Select Ptn/Bank', schwacher Zeiger Auswahl +0x94). Haken an den drei Einstiegen -> UNT: Kennzeichen des Fensters
    leeren (Ende = Anfang), das Popup liegt dann darueber und das Fenster bleibt; zu nur noch ueber PATTERN / FUNC / Beobachter
    (die schliessen es direkt ueber +0x28).
Speicher: Masken 0x4015943c (REQ, FIX, SAVE, KEEP, DJS), 0x40168a84 (DJF, DJK), 0x4014af84 (FK, FO), 0x4014b05c (OT, RL),
  0x40168c4c (smp39: UNT, HC, HL, HP; frei seit smp37). Kein Core.
Aufruf: g2_directjump.py [out.json]
"""
import struct, sys
from common import *                 # noqa: F401,F403
import common as C
from cfasm import asm, done as adone

M_J1, M_J2, M_J3, M_J4 = 0x4015943C, 0x40168A84, 0x4014AF84, 0x4014B05C
M_J5 = 0x40168C4C                   # smp39 (104 B, frei seit smp37: frueher PS von strum)
SIZE = {M_J1: 192, M_J2: 192, M_J3: 108, M_J4: 108, M_J5: 104}
# smp39: Einstiege Kopieren / Loeschen / Einfuegen in der Pattern-Auswahl (a2 = Auswahl, d0 / d1 / a0 / a1 dort frei)
HC_HOOK, HC_CK, HC_CONT = 0x40020F14, (10, 'a271af95d1e2cc8ef137ae142f05f24c7b75c72168a9587c24c1ea0c1ad610c3'), 0x40020F1E
HL_HOOK, HL_CK, HL_CONT = 0x40020FB8, (6, '5c33adc71185f28590a4713d787f4acd54ff26e240f890326a6e9e678909cecd'), 0x40020FBE
HP_HOOK, HP_CK, HP_CONT = 0x4002113E, (6, '61d0b7321b38375cf48c82c393936528246d7ec59cc5ca8a3dbc430023b4b347'), 0x40021144
CNT1, EXPIRED = 0x400C5A0C, 0x400D8B24   # Zahl gehaltener TRIGs ; weak_ptr abgelaufen?
W_PTR, TAGS = 0x94, 0x1C                 # Auswahl +0x94 = Fenster (weak_ptr), Overlay +0x1c / +0x20 = Bereichs-Kennzeichen
OT_HOOK, OT_CK, OT_CONT, OT_KEEP = 0x40024BD0, (8, '6a1585e8dae2264f0ba0da30904344f3a876886a5ec1ee3ca23a59bc985e5115'), 0x40024BD8, 0x40024BE6
RL_HOOK, RL_CK, RL_SKIP, RL_OFF = 0x40020DF0, (6, '3627a910beef07b4b6e9af0c126a851478dd8f36148ce7169824ded3868f9a98'), 0x40020E04, 0x40020DF6
FK_HOOK, FK_CK, FK_CONT = 0x40020AA6, (6, '5d4b15b3b1405e54fae167d69ba86750fac2ff84764f27fa400396d893bd7a23'), 0x40020AAC
KEY_FUNC_CODE = 1
UI_STATES, PAT_MODE = 0x400CF9A8, 0x4006BB18   # UIStates-Objekt ; (UIStates) -> Auswahlmodus an (Byte +389)
FO_HOOK, FO_CK, FO_CONT, FO_TAKEN = 0x40024B12, (6, 'f91fe885810e5a81e95a9795a75e3838272cecaa85c7bdebd06ba4602758d885'), 0x40024B18, 0x40024BA2
WIN_TICK, TICK_ORIG, TICK_NONE = 0x401011B0, 0x400749B4, 0x40075F2E   # smp23: Vtable 0x40101184 +0x2c (Fenster der Auswahl)
K_FUNC_EV = 0x40072490               # Ereignis: FUNC gehalten
K_HOOK, K_CK, K_NORMAL, K_DONE = 0x40020C84, (8, '7f0bc1cbb3f557b6616dd07e7b2568fd7b4b176215b6dec7fc152ac1d9d8fb5b'), 0x40020C94, 0x40020D5E
CUE = 0x4002037C                     # (Ansicht, Pattern-Index): Pattern als naechstes in die Kette (Firmware)
S_HOOK, S_CK = 0x4005563E, (6, 'a2f1b7b4615108ce93e9d9fb006e40045a5fe8e37256caf0a6060d78671f3508')
F_HOOK, F_CK = 0x40055898, (6, '5a266c7d2608b261d2f19f942ffc908a092779c46ea63757febb96ee1964d9bc')
PLAYING, MSTEP, START, END, DUE = 0x40A7883C, 0x40A78840, 0x40A788A0, 0x40A788A4, 0x40A78920
CHAIN0, CUR_PAT, TSTART = 0x40A7863C, 0x40A7887C, 0x40A788BC
MIDI_PC = 0x4005419E
P_LEN, P_PERTRACK, T_LEN, T_STRIDE = 0x77C6, 0x77CB, 0x2C9, 722
MAGIC = 0x444A4D50                   # 'DJMP'


V_WAIT = 0x7C                        # Pattern-Auswahl +0x7c: wartet auf Auswahl (PATTERN getippt); TRIG gedrueckt loescht es
REQ, FIX, SAVE, KEEP = M_J1, M_J1 + 4, M_J1 + 8, M_J1 + 14   # Daten am Anfang von Maske 1: Anforderung, Merker, naechste Steps
                                     # der Spuren, KEEP (Wort): Auswahl nach dem Loslassen des Sprung-TRIG offen lassen
TPOS = 0x40A78860                    # naechster Step jeder Spur (Bytes)


def build_j2(nrm_at):
    a = A(M_J2)
    asm(a, f'''
    ; ---------------- DJF: nach dem Wechsel (jmp von 0x40055898; alle Register bleiben)
    DJF:    lea     -28(sp),sp
            movem.l d0-d3/a0-a2,(sp)
            lea     {FIX:#x},a1
            tst.l   (a1)
            beq     fo
            clr.l   (a1)
            movea.l {CUR_PAT:#x},a0          ; a0 neues Pattern (Spur 0)
            lea     {TSTART:#x},a1           ; a1 Startschritte
            lea     {SAVE:#x},a2             ; a2 gemerkte Steps (altes Pattern)
            moveq   #0,d3                    ; Per-Track-Modus: d3 = 0, sonst Pattern-Laenge
            mvs.b   {P_PERTRACK}(a0),d1
            subq.l  #1,d1
            beq     lp
            mvs.w   {P_LEN}(a0),d3
    lp:     mvz.b   (a2)+,d0                 ; naechster Step der Spur im alten Pattern
            move.l  d3,d1
            bne     l1
            mvs.w   {T_LEN}(a0),d1           ; Laenge der Spur
    l1:     tst.l   d1
            ble     nx
            remu.l  d1,d2:d0
            move.w  d2,(a1)                  ; Startschritt = alter Step modulo Laenge
    nx:     lea     {T_STRIDE}(a0),a0
            addq.l  #2,a1
            cmpa.l  #{TSTART + 12:#x},a1
            bne     lp
    fo:     movem.l (sp),d0-d3/a0-a2
            lea     28(sp),sp
            orig    {F_HOOK:#x},6            ; verschobener Befehl der Firmware
            jmp     {F_HOOK + 6:#x}
    ; ---------------- DJK: TRIG in der Pattern-Auswahl (jmp von 0x40020c84; a2 Ansicht, d2 Ereignis, -48(a6) Index)
    DJK:    orig    {K_HOOK:#x},8            ; verschobene Befehle (FUNC abfragen)
            addq.l  #4,sp
            tst.b   d0
            beq     nrm
            tst.l   {PLAYING:#x}
            beq     nrm                      ; gestoppt: wie TRIG
            moveq   #1,d0
            move.b  d0,{V_WAIT}(a2)          ; Auswahl bleibt wartend (+0x7c = 1)
            move.w  d0,{KEEP:#x}
            move.l  -48(a6),-(sp)
            move.l  a2,-(sp)
            jsr     {CUE:#x}                 ; Pattern-Wahl der Firmware
            addq.l  #8,sp
            move.l  #{MAGIC:#x},d0
            move.l  d0,{REQ:#x}              ; Anforderung fuer DJS
            jmp     {K_DONE:#x}
    nrm:    jmp     {nrm_at:#x}              ; smp23: NRM (Maske 4) -> +0x7c = 1, dann Firmware
    ''')
    code = adone(a)
    check_cf(code, M_J2)
    return code, a.lab


def build_j1():
    a = A(M_J1 + 16)
    asm(a, f'''
    ; ---------------- DJS: Tick 0 im Sequencer (jmp von 0x4005563e; alle Register bleiben)
    DJS:    lea     -20(sp),sp
            movem.l d0-d2/a0-a1,(sp)
            move.l  {REQ:#x},d0
            cmpi.l  #{MAGIC:#x},d0
            bne     so
            clr.l   {REQ:#x}
            movea.l {CHAIN0:#x},a0           ; a0 = naechstes Pattern (Kette, Eintrag 0)
            move.l  a0,d0
            beq     so
            move.l  {TPOS:#x},d0             ; naechste Steps der Spuren merken
            move.l  d0,{SAVE:#x}
            move.w  {TPOS + 4:#x},d0
            move.w  d0,{SAVE + 4:#x}
            move.l  {MSTEP:#x},d0            ; d0 = aktueller Master-Step
            mvs.b   {P_PERTRACK}(a0),d1
            subq.l  #1,d1
            beq     pt                       ; Per-Track-Modus: ohne Modulo
            mvs.w   {P_LEN}(a0),d1
            tst.l   d1
            ble     pt
            remu.l  d1,d2:d0
            move.l  d2,d0                    ; d0 = d0 mod Laenge
    pt:     move.l  d0,{START:#x}
            moveq   #-1,d0
            move.l  d0,{END:#x}
            moveq   #1,d0
            move.l  d0,{DUE:#x}
            move.l  d0,{FIX:#x}
            move.l  a0,-(sp)
            jsr     {MIDI_PC:#x}             ; MIDI-Programmwechsel wie am Pattern-Ende
            addq.l  #4,sp
    so:     movem.l (sp),d0-d2/a0-a1
            lea     20(sp),sp
            orig    {S_HOOK:#x},6            ; verschobener Befehl (Wechsel faellig?)
            jmp     {S_HOOK + 6:#x}
    ''')
    code = adone(a)
    check_cf(code, M_J1 + 16)
    return bytes(16) + code, a.lab


def build_j3():
    """FK: Tastenverteiler der Pattern-Auswahl (jmp von 0x40020aa6, d0 = Tastencode). Die Pattern-Auswahl sitzt immer in der Kette
    der Tasten-Empfaenger (vor PadsView, Hauptansicht): FUNC darf sie nur annehmen, solange der Auswahlmodus an ist
    (UIStates +389, 0x4006bb18), sonst gehen FUNC-Gesten wie Mute verloren (jump3, Pip 28.10.)."""
    a = A(M_J3)
    asm(a, f'''
    FK:     cmpi.l  #{KEY_FUNC_CODE},d0
            bne     fk
            jsr     {UI_STATES:#x}
            move.l  d0,-(sp)
            jsr     {PAT_MODE:#x}
            addq.l  #4,sp
            tst.b   d0
            beq     f1
            jmp     {K_DONE:#x}              ; Auswahl an: FUNC angenommen (Rueckgabe 1)
    f1:     moveq   #1,d0                    ; d0 = 1 (Tastencode) wie vorher
    fk:     orig    {FK_HOOK:#x},6           ; verschobene Befehle (Code 9?)
            jmp     {FK_CONT:#x}
    ; ---------------- FO: Tasten des Auswahl-Fensters (jmp von 0x40024b12, d0 = Tastencode): FUNC schloss Fenster und Auswahl
    FO:     cmpi.l  #{KEY_FUNC_CODE},d0
            bne     fo2
            jmp     {FO_TAKEN:#x}            ; angenommen (Rueckgabe 1), nichts schliessen
    fo2:    orig    {FO_HOOK:#x},6           ; verschobene Befehle (Code 1?)
            jmp     {FO_CONT:#x}
    ''')
    code = adone(a)
    check_cf(code, M_J3)
    return code, a.lab


def build_j4():
    a = A(M_J4)
    asm(a, f'''
    ; ---------------- OT: TRIG gedrueckt im Auswahl-Fenster (jmp von 0x40024bd0). smp23 (Pip 08.11.): die Pattern-Auswahl rastet
    ; ein - jeder TRIG im Fenster laesst Fenster und Auswahl offen (kein Abschluss-Rueckruf 0x400200ee, der den Modus
    ; ausschaltet, nicht schliessen), Ereignis weiter an die Pattern-Auswahl (Rueckgabe 0).
    OT:     jmp     {OT_KEEP:#x}
    ; ---------------- NRM: normaler TRIG gedrueckt (von DJK): Auswahl wartend
    NRM:    moveq   #1,d0
            move.b  d0,{V_WAIT}(a2)
            jmp     {K_NORMAL:#x}
    ; ---------------- RL: letzter TRIG losgelassen in der Pattern-Auswahl (jmp von 0x40020df0; a2 Auswahl). smp23: die Auswahl
    ; bleibt immer an und 'wartend' (+0x7c = 1, sonst schaltet der Beobachter 0x400206c6 sie aus); nur PATTERN schliesst.
    RL:     moveq   #1,d0
            move.b  d0,{V_WAIT}(a2)
            clr.w   {KEEP:#x}
            jmp     {RL_SKIP:#x}
    ''')
    code = adone(a)
    check_cf(code, M_J4)
    return code, a.lab


def build_j5():
    a = A(M_J5)
    asm(a, f'''
    UNT:    pea     {W_PTR}(a2)              ; Fenster der Auswahl noch da?
            jsr     {EXPIRED:#x}
            addq.l  #4,sp
            tst.b   d0
            bne     u9
            movea.l {W_PTR}(a2),a0
            move.l  {TAGS}(a0),{TAGS + 4}(a0)   ; keine Bereichs-Kennzeichen: neue Popups schliessen es nicht
    u9:     rts
    HC:     jsr     UNT                      ; REC: Kopieren
            move.l  0x8c(a2),-(sp)
            jsr     {CNT1:#x}
            jmp     {HC_CONT:#x}
    HL:     jsr     UNT                      ; PLAY
            lea     0x9c(a2),a4
            move.l  a4,-(sp)
            jmp     {HL_CONT:#x}
    HP:     jsr     UNT                      ; STOP
            lea     0xa4(a2),a5
            move.l  a5,-(sp)
            jmp     {HP_CONT:#x}
    ''')
    code = adone(a)
    check_cf(code, M_J5)
    return code, a.lab


def build():
    c4, l4 = build_j4(); c2, l2 = build_j2(l4['NRM']); c1, l1 = build_j1(); c3, l3 = build_j3(); c5, l5 = build_j5()
    return {M_J1: c1, M_J2: c2, M_J3: c3, M_J4: c4, M_J5: c5}, dict(l1, **l2, **l3, **l4, **l5, REQ=REQ, FIX=FIX, SAVE=SAVE, KEEP=KEEP)


def tweak(img):
    parts, lab = build()
    W = Writes(img)
    for va, b in parts.items():
        W.mask(va, b, SIZE[va])
    W.hook(K_HOOK, K_CK, jmp(lab['DJK']) + bytes.fromhex('4e71'))
    W.hook(S_HOOK, S_CK, jmp(lab['DJS']))
    W.hook(F_HOOK, F_CK, jmp(lab['DJF']))
    W.hook(FK_HOOK, FK_CK, jmp(lab['FK']))
    W.hook(FO_HOOK, FO_CK, jmp(lab['FO']))
    W.hook(OT_HOOK, OT_CK, jmp(lab['OT']) + bytes.fromhex('4e71'))
    W.hook(RL_HOOK, RL_CK, jmp(lab['RL']))
    W.hook(HC_HOOK, HC_CK, jmp(lab['HC']) + bytes.fromhex('4e714e71'))   # smp39
    W.hook(HL_HOOK, HL_CK, jmp(lab['HL']))
    W.hook(HP_HOOK, HP_CK, jmp(lab['HP']))
    # smp23: Fenster der Pattern-Auswahl ohne Zeitablauf - Vtable-Eintrag 'Tick' (0x400749b4 zaehlt $60 herunter, schliesst bei 0
    # und ruft den Abschluss) -> 0x40075f2e (rts, der Tick der Basisklasse ohne Zaehler)
    W.hook(WIN_TICK, struct.pack('>I', TICK_ORIG), struct.pack('>I', TICK_NONE))
    return patch('direct-jump', 15, 'Direct Pattern Jump',
                 ["PATTERN, then FUNC + TRIG = direct jump: the new pattern takes over within a step or two and continues at the",
                  "current step position (modulo its length). TRIG alone = normal change at the end of the pattern.",
                  "PATTERN latches the pattern selection: it stays open (no timeout) while you pick patterns or jump; only PATTERN closes it.",
                  "Copying / pasting / clearing a pattern (TRIG + REC / STOP / PLAY) keeps the selection window open: the message",
                  "shows on top of it.",
                  "Erzeugt von v2/g2_directjump.py."], W,
                 requires=[], hooks=[f"{x:#x}" for x in (K_HOOK, S_HOOK, F_HOOK, FK_HOOK, FO_HOOK, OT_HOOK, RL_HOOK, WIN_TICK, HC_HOOK, HL_HOOK, HP_HOOK)],
                 memory=[{"va": f"{REQ:#x}", "size": 16, "ram": True, "use": "jump request, fix flag, saved track steps, keep-open flag"}],
                 symbols={k: f"{lab[k]:#x}" for k in ('DJK', 'DJS', 'DJF', 'FK', 'FO', 'OT', 'RL', 'KEEP', 'REQ', 'FIX', 'SAVE', 'UNT', 'HC', 'HL', 'HP')},
                 params={"magic": f"{MAGIC:#x}"})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    parts, lab = build()
    print({f"{va:#x}": len(b) for va, b in parts.items()}, {k: hex(v) for k, v in lab.items() if k.isupper()})
