#!/usr/bin/env python3
"""Mod 'trig-select' (v2): Auswahlmodus fuer Trigs. Braucht nur 'core'.
Bedienung (Pip 26.10.2026, 'Eigener Auswahlmodus'):
  SETTINGS + PAGE      Modus an / aus (Popup 'Trig' / 'Select' + 'On' / 'Off'); aus = Auswahl geloescht.
  im Modus:
    Trig-Taste         Trig an- / abwaehlen (nur Steps mit Trig, Lock-Trig oder P-Locks); Trigs werden nicht gesetzt/geloescht.
    FUNC + PAGE        alle Trigs des Tracks (bis zur Patternlaenge) / keine ('All' / 'None').
    PAGE               Seite wechseln wie immer.
  Ausgewaehlte Trigs blinken schnell (4 Hz).
Prinzip: die Auswahl IST die Maske der gehaltenen Steps der Firmware (UIStates +0x15c/+0x160, Halte-Merker +0x164):
  P-Locks mit den Reglern, Note/Velocity/Laenge (NoteVelocityView), Nudge, Locks kopieren/einfuegen/loeschen wirken dann
  von selbst auf alle ausgewaehlten Steps, genau wie beim Halten mehrerer Trig-Tasten.
CONTROL ALL absolut (Byte des Cores, control-mode): nach jeder Aenderung bekommen alle gehaltenen Steps den Wert des
  Fokus-Steps (niedrigster gehaltener, 0x4014924c) - P-Locks (ParameterPageView vt[0x74]), Nudge, Note/Velocity/Laenge.
  Gilt auch fuer physisch gehaltene Trigs. Relativ = Firmware.
Haken: PatternGridView::consumeKeyEvent (vtable 0x40100af0 -> TSK), Hauptbildschirm FUNC + PAGE (0x4001c4a6 -> TSF, im
  Modus an das Grid weiter), LED-Schleife des Grids (0x40021f56 -> TSL), ParameterPageView vt[0x74] (0x401005a0 -> PL),
  NoteVelocityView (Aufruf 0x40029d9a -> NVW).
Speicher: Masken 0x40183118 (TSK), 0x40185018 (CLRSEL, SELABLE, HOLDON, TOG, ALL), 0x40185968 (TSF, TSL, NVW, Tabelle, Texte),
  0x40185c58 (PL, HS). RAM TS_ON 0x4a33c3ac (Langwort, 'TSEL' = an).
Aufruf: g2_trigselect.py [out.json]
"""
import struct, sys
from common import *                 # noqa: F401,F403
import common as C
import g2_core as core

M_A, M_S, M_B, M_P = 0x40183118, 0x40185018, 0x40185968, 0x40185C58
SIZE = {M_A: 376, M_S: 376, M_B: 376, M_P: 376}
TS_ON, TS_MAGIC = 0x4A33C3AC, 0x5453454C       # Modus an nur mit 'TSEL' (RAM nach dem Einschalten zufaellig)
# Firmware
GRID_VT, GRID_KEY = 0x40100AF0, 0x40022382           # PatternGridView vtable[2] = consumeKeyEvent
PL_VT, PL_ORIG = 0x401005A0, 0x4001E93E              # ParameterPageView vt[0x74]: P-Lock der gehaltenen Steps aendern
TSF_HOOK, TSF_ORIG = 0x4001C4A6, (8, '3ce931d7357a496e83843a4e65042d557eab086f9393fd43ae72ba28e3fad05f')   # Hauptbildschirm PAGE: move.l d3,-(a7) ; jsr BIT1
TSL_HOOK, TSL_ORIG = 0x40021F56, (10, '29444fae76bff4c9ff22efd8157a1194da998400ed9defdcde353aa5ece4db13')   # move.l d3,-(a7) ; jsr (a4) ; pea $404a8cb8
NVW_HOOK, NVW_ORIG = 0x40029D9A, (8, '21ec85e93a781511de0f0035feb699e39e9bfaa22d86f4a81295ab5b05542033')   # move.l d0,-(a7) ; move.l a2,-(a7) ; jsr 0x400296c4(pc)
NV_APPLY = 0x400296C4
BIT1 = 0x40072490
UIS = 0x400CF9A8                                     # UIStates
U_HELD, U_SET, U_CLR, U_HOLD, U_EDIT = 0x4006B7A0, 0x4006B836, 0x4006B8D6, 0x4006B740, 0x4006B978
PROJ, TRK, PG_A, PG_B, LEN = 0x400CF866, 0x4000F23E, 0x4000EB90, 0x400124B8, 0x40016402
HAS = (0x40015C20, 0x40015C7C, 0x400158CA)           # Note-Trig, Lock-Trig, P-Locks (wie die LED-Schleife)
LED_OF, LED_ARG = 0x4000608C, 0x404A8CB8
FOCUS = 0x40081BFE                                   # Fokus-Step (niedrigster gehaltener) oder -1
NUDGE, NUD_GET, NUD_SET = 0x12, 0x40015F82, 0x400167BC
NV_GET = (0x40015EAA, 0x40015EF2, 0x40015F3A)        # Note, Velocity, Laenge (trk, step) -> Byte (-1 = Track)
NV_SET = (0x40016642, 0x400166C2, 0x40016742)        # (trk, step, Wert)
BLINK_BIT = 24                                       # Zeitgeber-Bit: 2^24 / 135.168 MHz = 0.124 s -> 4 Hz
TXT = {'l1': "Trig", 'l2': "Select", 'on': "On", 'off': "Off", 'all': "All", 'none': "None"}
ABS, MODE = C.CTRL_ABS, C.CTRL_MODE


def held(w, l, k):
    w(0x4878, k, 0x4EB9); l(C.HELD); w(0x588F, 0x4A80)          # pea k ; jsr HELD ; addq #4 ; tst.l d0


def is_abs(w, l):
    w(0x71B9); l(MODE); w(0x7200 | ABS, 0xB081)                 # Z = absolut (zerstoert d0, d1)


def build_a(txt, ovs, gest, S):
    a = A(M_A); w, l = a.w, a.l32
    # ================= TSK(this, Ereignis): statt PatternGridView::consumeKeyEvent
    a.label('TSK')
    w(0x4FEF, 0xFFE8, 0x48D7, 0x0C3C)           # lea -24(a7),a7 ; movem.l d2-d5/a2-a3,(a7)
    w(0x266F, 0x0020, 0x242B, 0x000C, 0x262B, 0x0010)   # a3 = Ereignis ; d2 = Code ; d3 = Flags
    w(0x7809, 0xC883, 0x5384)                   # d4 = (Flags & 9) - 1  (0 = frisch gedrueckt)
    w(0x2039); l(TS_ON); w(0x0C80); l(TS_MAGIC); a.bcc(EQ, 'inm')
    # ---- Modus aus: SETTINGS + PAGE frisch -> an
    w(0x700F, 0xB082); a.bcc(NE, 'orig')
    w(0x4A84); a.bcc(NE, 'orig')
    held(w, l, C.KEY_SET); a.bcc(EQ, 'orig')
    w(0x203C); l(TS_MAGIC); w(0x23C0); l(TS_ON)
    w(0x4EB9); l(S['CLRSEL'])
    w(0x41F9); l(txt['on']); a.bcc(BRA, 'popg')
    a.label('inm')
    w(0x700F, 0xB082); a.bcc(NE, 'ntp')
    w(0x4A84); a.bcc(NE, 'pwrap')               # PAGE gehalten / losgelassen: Firmware (Maske verdeckt)
    held(w, l, C.KEY_SET); a.bcc(EQ, 'nset')
    w(0x42B9); l(TS_ON)                         # SETTINGS + PAGE: aus
    w(0x4EB9); l(S['CLRSEL'])
    w(0x41F9); l(txt['off']); a.bcc(BRA, 'popg')
    a.label('nset')
    w(0x0803, 0x0001); a.bcc(EQ, 'pwrap')       # btst #1,d3 (FUNC) ; beq
    w(0x4EB9); l(S['ALL']); a.bcc(BRA, 'pop')   # a0 = 'All' / 'None'
    # ---- PAGE im Modus: Firmware mit verdeckter Auswahl (sonst waere es 'gehaltener Step + PAGE')
    a.label('pwrap')
    w(0x4EB9); l(UIS); w(0x2440)                # a2 = UIStates
    w(0x282A, 0x015C, 0x2A2A, 0x0160, 0x162A, 0x0164)
    w(0x42AA, 0x015C, 0x42AA, 0x0160, 0x422A, 0x0164)
    w(0x2F0B, 0x2F2F, 0x0020, 0x4EB9); l(GRID_KEY); w(0x508F)   # Original(this, Ereignis)
    w(0x2544, 0x015C, 0x2545, 0x0160, 0x1543, 0x0164)
    a.bcc(BRA, 'out')
    # ---- Trig-Tasten im Modus (Code 16..31, nur im Grid-Bearbeiten wie die Firmware)
    a.label('ntp')
    w(0x7010, 0xB480); a.bcc(LT, 'orig')        # moveq #16,d0 ; cmp.l d0,d2 ; blt
    w(0x701F, 0xB480); a.bcc(GT, 'orig')
    w(0x4EB9); l(UIS); w(0x2F00, 0x4EB9); l(U_EDIT); w(0x588F, 0x4A00); a.bcc(EQ, 'orig')
    w(0x4A84); a.bcc(NE, 'swal')
    w(0x4EB9); l(S['TOG'])
    a.label('swal')
    w(0x7001); a.bcc(BRA, 'out')                # alle Ereignisse der Trig-Tasten verbraucht
    # ---- Popup ; SETTINGS verbrauchen (popg) ; PAGE verbrauchen
    a.label('popg')
    w(0x2F08, 0x7000 | C.KEY_SET, 0x4EB9); l(gest); w(0x205F)   # GEST(13): kein Menue, kein Speichern
    a.label('pop')
    w(0x2208, 0x41F9); l(txt['l1']); w(0x43F9); l(txt['l2']); w(0x7000 | C.OV_TEXT, 0x4EB9); l(ovs)
    w(0x4878, 0x000F, 0x4EB9); l(C.CONSUME); w(0x588F, 0x7001)
    a.label('out')
    w(0x4CD7, 0x0C3C, 0x4FEF, 0x0018, 0x4E75)
    a.label('orig')
    w(0x4CD7, 0x0C3C, 0x4FEF, 0x0018, 0x4EF9); l(GRID_KEY)
    code = a.done(); check_cf(code, M_A)
    return code, dict(a.lab)


def build_s(txt):
    a = A(M_S); w, l = a.w, a.l32
    # ================= CLRSEL: Auswahl (gehaltene Steps, Merker, Fokus) loeschen
    a.label('CLRSEL')
    w(0x4EB9); l(UIS); w(0x2F00, 0x4EB9); l(U_CLR); w(0x588F, 0x4E75)
    # ================= SELABLE: d5 = Step -> d0.b != 0 wenn Trig / Lock-Trig / P-Locks (a2 zerstoert)
    a.label('SELABLE')
    w(0x4EB9); l(PROJ); w(0x2F00, 0x4EB9); l(TRK); w(0x588F, 0x2440)
    for i, f in enumerate(HAS):
        w(0x2F05, 0x2F0A, 0x4EB9); l(f); w(0x508F, 0x4A00); a.bcc(NE, 'sy')
    w(0x7000, 0x4E75)
    a.label('sy'); w(0x7001, 0x4E75)
    # ================= HOLDON: Auswahl nicht leer -> Halte-Merker wie nach dem Halten einer Trig-Taste
    a.label('HOLDON')
    w(0x4EB9); l(UIS); w(0x2040, 0x2228, 0x015C, 0x82A8, 0x0160); a.bcc(EQ, 'ho')
    w(0x4878, 0x0001, 0x2F08, 0x4EB9); l(U_HOLD); w(0x508F)
    a.label('ho'); w(0x4E75)
    # ================= TOG (d2 = Code): Step = Seite * 16 + Code - 16 an/ab
    a.label('TOG')
    w(0x4EB9); l(PROJ); w(0x2F00, 0x4EB9); l(PG_A); w(0x2F00, 0x4EB9); l(PG_B); w(0x508F)
    w(0xE988, 0xD082, 0x7210, 0x9081, 0x2A00)  # lsl.l #4,d0 ; add.l d2,d0 ; moveq #16,d1 ; sub.l d1,d0 ; d5 = Step
    a.bcc(BSR, 'SELABLE'); w(0x4A00); a.bcc(EQ, 'tr')
    w(0x4EB9); l(UIS); w(0x2440)
    w(0x2F05, 0x2F0A, 0x4EB9); l(U_HELD); w(0x508F)
    w(0x7201, 0xC081, 0xB380)                   # d0 = !gehalten
    w(0x2F00, 0x2F05, 0x2F0A, 0x4EB9); l(U_SET); w(0x4FEF, 0x000C)
    a.bcc(BSR, 'HOLDON')
    a.label('tr'); w(0x4E75)
    # ================= ALL: alle waehlbaren Steps bis zur Patternlaenge; waren schon alle gewaehlt -> keine. a0 = Text
    a.label('ALL')
    w(0x4EB9); l(PROJ); w(0x2F00, 0x4EB9); l(TRK); w(0x2E80, 0x4EB9); l(LEN); w(0x588F, 0x2600)   # d3 = Laenge
    w(0x7040, 0xB083); a.bcc(GE, 'al0'); w(0x7640)                  # hoechstens 64 (64 >= Laenge: so lassen)
    a.label('al0')
    w(0x4EB9); l(UIS); w(0x2640, 0x7800, 0x7A00)                    # a3 = UIStates ; d4 = hinzugefuegt ; d5 = Step
    a.label('alp')
    w(0xBA83); a.bcc(GE, 'ald')
    a.bcc(BSR, 'SELABLE'); w(0x4A00); a.bcc(EQ, 'aln')
    w(0x2F05, 0x2F0B, 0x4EB9); l(U_HELD); w(0x508F, 0x0800, 0x0000); a.bcc(NE, 'aln')
    w(0x4878, 0x0001, 0x2F05, 0x2F0B, 0x4EB9); l(U_SET); w(0x4FEF, 0x000C, 0x7801)
    a.label('aln')
    w(0x5285); a.bcc(BRA, 'alp')
    a.label('ald')
    w(0x4A84); a.bcc(NE, 'ala')
    w(0x2F0B, 0x4EB9); l(U_CLR); w(0x588F, 0x41F9); l(txt['none']); w(0x4E75)
    a.label('ala')
    a.bcc(BSR, 'HOLDON'); w(0x41F9); l(txt['all']); w(0x4E75)
    code = a.done(); check_cf(code, M_S)
    return code, dict(a.lab)


def build_b(texts_at, P):
    a = A(M_B); w, l = a.w, a.l32
    # ================= TSF: Hauptbildschirm PAGE frisch, FUNC? Im Modus 'nein' -> Ereignis geht ans Grid (TSK)
    a.label('TSF')
    w(0x205F); a.orig(TSF_HOOK, 2); w(0x2F08)   # movea.l (a7)+,a0 ; verschobener Originalbefehl ; move.l a0,-(a7)
    w(0x2039); l(TS_ON); w(0x0C80); l(TS_MAGIC); a.bcc(EQ, 'tf')
    w(0x4EF9); l(BIT1)
    a.label('tf'); w(0x7000, 0x4E75)
    # ================= TSL: LED-Schleife des Grids, Step-Zustand a5; ausgewaehlt -> 4 Hz an/aus
    a.label('TSL')
    w(0x2039); l(TS_ON); w(0x0C80); l(TS_MAGIC); a.bcc(NE, 'ln')
    w(0x4EB9); l(UIS); w(0x2040)
    w(0x202F, 0x003C, 0xD083)                   # d0 = Seite*16 + d3
    w(0x721F, 0xB280); a.bcc(LT, 'lh')          # moveq #31,d1 ; cmp.l d0,d1 ; blt (Step > 31)
    w(0x2228, 0x0160); a.bcc(BRA, 'lb')
    a.label('lh')
    w(0x2228, 0x015C, 0x0480); l(32)
    a.label('lb')
    w(0x0101); a.bcc(EQ, 'ln')                  # btst d0,d1
    w(0x2039); l(C.TIMER); w(0x0800, BLINK_BIT); a.bcc(EQ, 'lo')
    w(0x3A7C, 0x0002); a.bcc(BRA, 'ln')
    a.label('lo'); w(0x3A7C, 0x0001)
    a.label('ln')                               # Original: move.l d3,-(a7) ; jsr 0x4000608c ; pea LED_ARG
    a.orig(TSL_HOOK, 2); w(0x4EB9); l(LED_OF)   # verschobener Originalbefehl ; jsr LED-Funktion
    w(0x226F, 0x0004, 0x2F57, 0x0004, 0x2EBC); l(LED_ARG); w(0x4ED1)
    # ================= NVW (statt Aufruf 0x400296c4(view = a2, Drehung = d0)): absolut -> Wert des Fokus-Steps
    a.label('NVW')
    a.orig(NVW_HOOK, 4); w(0x4EB9); l(NV_APPLY)   # verschobene Originalbefehle ; Stapel: a2, d0, Ruecksprung
    w(0x4FEF, 0xFFE8, 0x48D7, 0x087C)           # lea -24(a7),a7 ; movem.l d2-d6/a3,(a7)
    is_abs(w, l); a.bcc(NE, 'nvx')
    w(0x4EB9); l(FOCUS); w(0x2600); a.bcc(MI, 'nvx')   # d3 = Fokus
    w(0x202A, 0x0068, 0x7202, 0xB280); a.bcc(CS, 'nvx')   # Feld 0..2 (Note, Velocity, Laenge)
    w(0xE588, 0x41F9); l(0); fx_get = len(a.b) - 4
    w(0x2430, 0x0800)                           # d2 = Getter
    w(0x41F9); l(0); fx_set = len(a.b) - 4
    w(0x2830, 0x0800)                           # d4 = Setter
    w(0x4EB9); l(PROJ); w(0x2F00, 0x4EB9); l(TRK); w(0x588F, 0x2640)    # a3 = Track
    w(0x2042, 0x2F03, 0x2F0B, 0x4E90, 0x508F, 0x7D00)                   # d6 = Getter(trk, Fokus)
    w(0x7A00)
    a.label('nvl')
    w(0xBA83); a.bcc(EQ, 'nvn')
    w(0x4EB9); l(P['HS']); a.bcc(EQ, 'nvn')
    w(0x2044, 0x2F06, 0x2F05, 0x2F0B, 0x4E90, 0x4FEF, 0x000C)
    a.label('nvn')
    w(0x5285, 0x7040, 0xBA80); a.bcc(NE, 'nvl')
    a.label('nvx')
    w(0x4CD7, 0x087C, 0x4FEF, 0x0018)
    w(0x226F, 0x0008, 0x2F6F, 0x0004, 0x0008, 0x2F57, 0x0004, 0x588F, 0x4ED1)
    code = bytearray(a.done()); check_cf(bytes(code), M_B)
    while len(code) % 4: code += b'\0'
    tab = M_B + len(code)
    code += struct.pack('>3I', *NV_GET) + struct.pack('>3I', *NV_SET)
    code[fx_get:fx_get + 4] = struct.pack('>I', tab); code[fx_set:fx_set + 4] = struct.pack('>I', tab + 12)
    at = {}
    for k, s in TXT.items():
        at[k] = M_B + len(code); code += s.encode() + b'\0'
    if texts_at is not None: assert at == texts_at, 'Textadressen verschoben'
    return bytes(code), dict(a.lab, NVTAB=tab), at


def build_p():
    a = A(M_P); w, l = a.w, a.l32
    # ================= PL(view, param, delta): statt vt[0x74]; absolut -> Wert des Fokus-Steps in alle gehaltenen
    a.label('PL')
    w(0x4FEF, 0xFFE4, 0x48D7, 0x0C7C)           # lea -28(a7),a7 ; movem.l d2-d6/a2-a3,(a7)
    w(0x2F2F, 0x0028, 0x2F2F, 0x0028, 0x2F2F, 0x0028, 0x4EB9); l(PL_ORIG); w(0x4FEF, 0x000C, 0x2800)
    w(0x4A04); a.bcc(EQ, 'px')
    is_abs(w, l); a.bcc(NE, 'px')
    w(0x246F, 0x0020, 0x242F, 0x0024)           # a2 = view ; d2 = param
    w(0x4EB9); l(FOCUS); w(0x2600); a.bcc(MI, 'px')   # d3 = Fokus
    w(0x7012, 0xB082); a.bcc(EQ, 'pnud')
    w(0x2052, 0x2F02, 0x4878, 0xFFFF, 0x2F0A, 0x2068, 0x0080, 0x4E90, 0x4FEF, 0x000C, 0x2640)  # a3 = obj
    w(0x2053, 0x2F03, 0x2F02, 0x2F0B, 0x2068, 0x0024, 0x4E90, 0x4FEF, 0x000C, 0x2C00)          # d6 = Lock(Fokus)
    w(0x7A00)
    a.label('plp')
    w(0xBA83); a.bcc(EQ, 'pln')
    a.bcc(BSR, 'HS'); a.bcc(EQ, 'pln')
    w(0x2052, 0x2F02, 0x2F05, 0x2F0A, 0x2068, 0x0060, 0x4E90, 0x4FEF, 0x000C, 0x4A80); a.bcc(MI, 'pln')  # hat Lock?
    w(0x2053, 0x2F05, 0x2F06, 0x2F02, 0x2F0B, 0x2068, 0x0028, 0x4E90, 0x4FEF, 0x0010)              # setzen
    a.label('pln')
    w(0x5285, 0x7040, 0xBA80); a.bcc(NE, 'plp')
    a.bcc(BRA, 'px')
    a.label('pnud')                             # Nudge (Mikro-Timing im Track, kein Lock)
    w(0x4EB9); l(PROJ); w(0x2F00, 0x4EB9); l(TRK); w(0x588F, 0x2640)
    w(0x2F03, 0x2F0B, 0x4EB9); l(NUD_GET); w(0x508F, 0x7D00)             # d6 = mvs.b d0
    w(0x7A00)
    a.label('pnl')
    w(0xBA83); a.bcc(EQ, 'pnn')
    a.bcc(BSR, 'HS'); a.bcc(EQ, 'pnn')
    w(0x2F06, 0x2F05, 0x2F0B, 0x4EB9); l(NUD_SET); w(0x4FEF, 0x000C)
    a.label('pnn')
    w(0x5285, 0x7040, 0xBA80); a.bcc(NE, 'pnl')
    a.label('px')
    w(0x2004, 0x4CD7, 0x0C7C, 0x4FEF, 0x001C, 0x4E75)
    # ================= HS: d5 = Step gehalten? (Z = nein) ; zerstoert d0, d1, a0, a1
    a.label('HS')
    w(0x4EB9); l(UIS); w(0x2F05, 0x2F00, 0x4EB9); l(U_HELD); w(0x508F, 0x0800, 0x0000, 0x4E75)
    code = a.done(); check_cf(code, M_P)
    return code, dict(a.lab)


def build():
    cs = core.sym()
    cp, lp = build_p()
    _, _, at = build_b(None, lp)
    cb, lb, _ = build_b(at, lp)
    cs_, ls = build_s(at)
    ca, la = build_a(at, cs['OVS'], cs['GEST'], ls)
    lab = {}
    for x in (la, ls, lb, lp): lab.update(x)
    lab.update({'T_' + k.upper(): v for k, v in at.items()})
    return {M_A: ca, M_S: cs_, M_B: cb, M_P: cp}, lab


def tweak(img):
    base = apply(img, core.tweak(img))
    parts, lab = build()
    W = Writes(base)
    for va, b in parts.items():
        W.mask(va, b, SIZE[va])
    W.hook(GRID_VT, struct.pack('>I', GRID_KEY), struct.pack('>I', lab['TSK']))
    W.hook(PL_VT, struct.pack('>I', PL_ORIG), struct.pack('>I', lab['PL']))
    W.hook(TSF_HOOK, TSF_ORIG, jsr(lab['TSF']) + bytes.fromhex("4e71"))
    W.hook(TSL_HOOK, TSL_ORIG, jsr(lab['TSL']) + bytes.fromhex("4e714e71"))
    W.hook(NVW_HOOK, NVW_ORIG, jsr(lab['NVW']) + bytes.fromhex("4e71"))
    return patch('trig-select', 11, 'Trig select: selection mode for trigs',
                 ["SETTINGS + PAGE = selection mode on/off. In the mode a trig key selects/deselects that trig (selected trigs",
                  "blink fast), FUNC + PAGE = all/none, PAGE changes the page as usual. Knobs (p-locks), note/velocity/length,",
                  "nudge and lock copy/paste then act on all selected trigs, as if they were held. With control mode Absolute,",
                  "all selected trigs get the value of the first one. Erzeugt von v2/g2_trigselect.py."],
                 W, requires=['core'],
                 hooks=[f"{x:#x}" for x in (GRID_VT, PL_VT, TSF_HOOK, TSL_HOOK, NVW_HOOK)],
                 memory=[{"va": f"{TS_ON:#x}", "size": 4, "ram": True, "use": "selection mode on ('TSEL')"}],
                 symbols={k: f"{v:#x}" for k, v in lab.items() if k[0].isupper()},
                 params={"blink_bit": BLINK_BIT, "texts": TXT})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    parts, lab = build()
    print({f"{va:#x}": len(b) for va, b in parts.items()}, {k: hex(v) for k, v in lab.items() if k[0].isupper()})
