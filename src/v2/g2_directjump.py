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
Speicher: Masken 0x4015943c (REQ, FIX, SAVE, KEEP, DJS), 0x40168a84 (DJF, DJK), 0x4014af84 (FK, FO), 0x4014b05c (OT, RL). Kein Core.
Aufruf: g2_directjump.py [out.json]
"""
import struct, sys
from common import *                 # noqa: F401,F403
import common as C

M_J1, M_J2, M_J3, M_J4 = 0x4015943C, 0x40168A84, 0x4014AF84, 0x4014B05C
SIZE = {M_J1: 192, M_J2: 192, M_J3: 108, M_J4: 108}
OT_HOOK, OT_CK, OT_CONT, OT_KEEP = 0x40024BD0, (8, '6a1585e8dae2264f0ba0da30904344f3a876886a5ec1ee3ca23a59bc985e5115'), 0x40024BD8, 0x40024BE6
RL_HOOK, RL_CK, RL_SKIP, RL_OFF = 0x40020DF0, (6, '3627a910beef07b4b6e9af0c126a851478dd8f36148ce7169824ded3868f9a98'), 0x40020E04, 0x40020DF6
FK_HOOK, FK_CK, FK_CONT = 0x40020AA6, (6, '5d4b15b3b1405e54fae167d69ba86750fac2ff84764f27fa400396d893bd7a23'), 0x40020AAC
KEY_FUNC_CODE = 1
UI_STATES, PAT_MODE = 0x400CF9A8, 0x4006BB18   # UIStates-Objekt ; (UIStates) -> Auswahlmodus an (Byte +389)
FO_HOOK, FO_CK, FO_CONT, FO_TAKEN = 0x40024B12, (6, 'f91fe885810e5a81e95a9795a75e3838272cecaa85c7bdebd06ba4602758d885'), 0x40024B18, 0x40024BA2
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


def build_j2():
    a = A(M_J2); w, l = a.w, a.l32
    # ---------------- DJF: nach dem Wechsel (jmp von 0x40055898; alle Register bleiben)
    a.label('DJF')
    w(0x4FEF, 0xFFE4, 0x48D7, 0x070F)                                     # lea -28(sp),sp ; movem.l d0-d3/a0-a2,(sp)
    w(0x43F9); l(FIX); w(0x4A91); a.bcc(EQ, 'fo')                       # lea FIX,a1 ; tst.l (a1)
    w(0x4291)                                                             # clr.l (a1)
    w(0x2079); l(CUR_PAT); w(0x43F9); l(TSTART); w(0x45F9); l(SAVE)      # a0 neues Pattern (Spur 0), a1 Startschritte, a2 alt
    w(0x7600, 0x7328, P_PERTRACK, 0x5381); a.bcc(EQ, 'lp')                # Per-Track-Modus: d3 = 0, sonst Pattern-Laenge
    w(0x7768, P_LEN)
    a.label('lp')
    w(0x719A, 0x2203); a.bcc(NE, 'l1')                                    # d0 = naechster Step der Spur im alten Pattern
    w(0x7368, T_LEN)                                                      # Laenge der Spur
    a.label('l1')
    w(0x4A81); a.bcc(LE, 'nx')
    w(0x4C41, 0x0002, 0x3282)                                             # Startschritt = alter Step modulo Laenge
    a.label('nx')
    w(0x41E8, T_STRIDE, 0x5489, 0xB3FC); l(TSTART + 12); a.bcc(NE, 'lp')
    a.label('fo')
    w(0x4CD7, 0x070F, 0x4FEF, 0x001C)
    a.orig(F_HOOK, 6)                                                     # verschobener Befehl der Firmware
    w(0x4EF9); l(F_HOOK + 6)
    # ---------------- DJK: TRIG in der Pattern-Auswahl (jmp von 0x40020c84; a2 Ansicht, d2 Ereignis, -48(a6) Index)
    a.label('DJK')
    a.orig(K_HOOK, 8)                                                     # verschobene Befehle (FUNC abfragen)
    w(0x588F, 0x4A00); a.bcc(EQ, 'nrm')
    w(0x4AB9); l(PLAYING); a.bcc(EQ, 'nrm')                               # gestoppt: wie TRIG
    w(0x7001, 0x1540, V_WAIT, 0x33C0); l(KEEP)                            # Auswahl bleibt wartend (+0x7c = 1), KEEP
    w(0x2F2E, 0xFFD0, 0x2F0A, 0x4EB9); l(CUE); w(0x508F)                  # Pattern-Wahl der Firmware
    w(0x203C); l(MAGIC); w(0x23C0); l(REQ)
    w(0x4EF9); l(K_DONE)
    a.label('nrm')
    w(0x4EF9); l(K_NORMAL)
    code = a.done()
    check_cf(code, M_J2)
    return code, a.lab


def build_j1():
    a = A(M_J1 + 16); w, l = a.w, a.l32
    # ---------------- DJS: Tick 0 im Sequencer (jmp von 0x4005563e; alle Register bleiben)
    a.label('DJS')
    w(0x4FEF, 0xFFEC, 0x48D7, 0x0307)                                     # lea -20(sp),sp ; movem.l d0-d2/a0-a1,(sp)
    w(0x2039); l(REQ); w(0x0C80); l(MAGIC); a.bcc(NE, 'so')
    w(0x42B9); l(REQ)
    w(0x2079); l(CHAIN0); w(0x2008); a.bcc(EQ, 'so')                      # a0 = naechstes Pattern (Kette, Eintrag 0)
    w(0x2039); l(TPOS); w(0x23C0); l(SAVE); w(0x3039); l(TPOS + 4); w(0x33C0); l(SAVE + 4)   # naechste Steps der Spuren
    w(0x2039); l(MSTEP)                                                   # d0 = aktueller Master-Step
    w(0x7328, P_PERTRACK, 0x5381); a.bcc(EQ, 'pt')                        # Per-Track-Modus: ohne Modulo
    w(0x7368, P_LEN, 0x4A81); a.bcc(LE, 'pt')
    w(0x4C41, 0x0002, 0x2002)                                             # d0 = d0 mod Laenge
    a.label('pt')
    w(0x23C0); l(START); w(0x70FF, 0x23C0); l(END)
    w(0x7001, 0x23C0); l(DUE); w(0x23C0); l(FIX)
    w(0x2F08, 0x4EB9); l(MIDI_PC); w(0x588F)                              # MIDI-Programmwechsel wie am Pattern-Ende
    a.label('so')
    w(0x4CD7, 0x0307, 0x4FEF, 0x0014)
    a.orig(S_HOOK, 6)                                                     # verschobener Befehl (Wechsel faellig?)
    w(0x4EF9); l(S_HOOK + 6)
    code = a.done()
    check_cf(code, M_J1 + 16)
    return bytes(16) + code, a.lab


def build_j3():
    """FK: Tastenverteiler der Pattern-Auswahl (jmp von 0x40020aa6, d0 = Tastencode). Die Pattern-Auswahl sitzt immer in der Kette
    der Tasten-Empfaenger (vor PadsView, Hauptansicht): FUNC darf sie nur annehmen, solange der Auswahlmodus an ist
    (UIStates +389, 0x4006bb18), sonst gehen FUNC-Gesten wie Mute verloren (jump3, Pip 28.10.)."""
    a = A(M_J3); w, l = a.w, a.l32
    a.label('FK')
    w(0x0C80); l(KEY_FUNC_CODE); a.bcc(NE, 'fk')
    w(0x4EB9); l(UI_STATES); w(0x2F00, 0x4EB9); l(PAT_MODE); w(0x588F, 0x4A00); a.bcc(EQ, 'f1')
    w(0x4EF9); l(K_DONE)                                                  # Auswahl an: FUNC angenommen (Rueckgabe 1)
    a.label('f1')
    w(0x7001)                                                             # d0 = 1 (Tastencode) wie vorher
    a.label('fk')
    a.orig(FK_HOOK, 6)                                                    # verschobene Befehle (Code 9?)
    w(0x4EF9); l(FK_CONT)
    # ---------------- FO: Tasten des Auswahl-Fensters (jmp von 0x40024b12, d0 = Tastencode): FUNC schloss Fenster und Auswahl
    a.label('FO')
    w(0x0C80); l(KEY_FUNC_CODE); a.bcc(NE, 'fo2')
    w(0x4EF9); l(FO_TAKEN)                                                # angenommen (Rueckgabe 1), nichts schliessen
    a.label('fo2')
    a.orig(FO_HOOK, 6)                                                    # verschobene Befehle (Code 1?)
    w(0x4EF9); l(FO_CONT)
    code = a.done()
    check_cf(code, M_J3)
    return code, a.lab


def build_j4():
    a = A(M_J4); w, l = a.w, a.l32
    # ---------------- OT: TRIG gedrueckt im Auswahl-Fenster (jmp von 0x40024bd0; d2 Ereignis, a2 Fenster). Mit FUNC bei laufendem
    # Sequencer: Fenster nicht abschliessen (kein Abschluss-Rueckruf, nicht schliessen), Ereignis weiter (Rueckgabe 0) -> DJK.
    a.label('OT')
    w(0x2F02, 0x4EB9); l(K_FUNC_EV); w(0x588F, 0x4A00); a.bcc(EQ, 'on')
    w(0x4AB9); l(PLAYING); a.bcc(EQ, 'on')
    w(0x4EF9); l(OT_KEEP)
    a.label('on')
    w(0x4279); l(KEEP)                                                    # normaler TRIG: kein Offenhalten
    a.orig(OT_HOOK, 8)                                                    # verschobene Befehle (Abschluss-Rueckruf holen)
    w(0x4EF9); l(OT_CONT)
    # ---------------- RL: letzter TRIG losgelassen in der Pattern-Auswahl (jmp von 0x40020df0; a2 Auswahl). Nach einem Direct
    # Jump bleibt der Auswahlmodus an (wie mit gehaltenem PATTERN), sonst wie die Firmware (ohne PATTERN gehalten: aus).
    a.label('RL')
    w(0x4A79); l(KEEP); a.bcc(EQ, 'r0')
    w(0x4279); l(KEEP)
    w(0x4EF9); l(RL_SKIP)
    a.label('r0')
    a.orig(RL_HOOK, 4)                                                    # verschobener Befehl (PATTERN gehalten?)
    a.bcc(NE, 'rs')
    w(0x4EF9); l(RL_OFF)
    a.label('rs')
    w(0x4EF9); l(RL_SKIP)
    code = a.done()
    check_cf(code, M_J4)
    return code, a.lab


def build():
    c2, l2 = build_j2(); c1, l1 = build_j1(); c3, l3 = build_j3(); c4, l4 = build_j4()
    return {M_J1: c1, M_J2: c2, M_J3: c3, M_J4: c4}, dict(l1, **l2, **l3, **l4, REQ=REQ, FIX=FIX, SAVE=SAVE, KEEP=KEEP)


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
    return patch('direct-jump', 15, 'Direct jump',
                 ["PATTERN, then FUNC + TRIG = direct jump: the new pattern takes over within a step or two and continues at the",
                  "current step position (modulo its length). TRIG alone = normal change at the end of the pattern.",
                  "Erzeugt von v2/g2_directjump.py."], W,
                 requires=[], hooks=[f"{x:#x}" for x in (K_HOOK, S_HOOK, F_HOOK, FK_HOOK, FO_HOOK, OT_HOOK, RL_HOOK)],
                 memory=[{"va": f"{REQ:#x}", "size": 16, "ram": True, "use": "jump request, fix flag, saved track steps, keep-open flag"}],
                 symbols={k: f"{lab[k]:#x}" for k in ('DJK', 'DJS', 'DJF', 'FK', 'FO', 'OT', 'RL', 'KEEP', 'REQ', 'FIX', 'SAVE')},
                 params={"magic": f"{MAGIC:#x}"})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    parts, lab = build()
    print({f"{va:#x}": len(b) for va, b in parts.items()}, {k: hex(v) for k, v in lab.items() if k.isupper()})
