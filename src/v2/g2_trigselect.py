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
from cfasm import asm, done as adone

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


def held(k):
    """pea k ; jsr HELD ; addq #4 ; tst.l d0  (Z = nicht gehalten)"""
    return f'''
            pea     {k}.w
            jsr     {C.HELD:#x}
            addq.l  #4,sp
            tst.l   d0'''


# mvz.b CTRL_MODE,d0 ; moveq #ABS,d1 ; cmp.l d1,d0  (Z = absolut; zerstoert d0, d1)
IS_ABS = f'''
            mvz.b   {MODE:#x},d0
            moveq   #{ABS},d1
            cmp.l   d1,d0                    ; absolut?'''


def build_a(txt, ovs, gest, S):
    a = A(M_A)
    asm(a, f'''
    ; ================= TSK(this, Ereignis): statt PatternGridView::consumeKeyEvent
    TSK:    lea     -24(sp),sp
            movem.l d2-d5/a2-a3,(sp)
            movea.l 32(sp),a3                ; a3 = Ereignis ; d2 = Code ; d3 = Flags
            move.l  12(a3),d2
            move.l  16(a3),d3
            moveq   #9,d4
            and.l   d3,d4
            subq.l  #1,d4                    ; d4 = (Flags & 9) - 1  (0 = frisch gedrueckt)
            move.l  {TS_ON:#x},d0
            cmpi.l  #{TS_MAGIC:#x},d0
            beq     inm
    ; ---- Modus aus: SETTINGS + PAGE frisch -> an
            moveq   #15,d0
            cmp.l   d2,d0
            bne     orig
            tst.l   d4
            bne     orig{held(C.KEY_SET)}
            beq     orig
            move.l  #{TS_MAGIC:#x},d0
            move.l  d0,{TS_ON:#x}
            jsr     {S['CLRSEL']:#x}
            lea     {txt['on']:#x},a0
            bra     popg
    inm:    moveq   #15,d0
            cmp.l   d2,d0
            bne     ntp
            tst.l   d4                       ; PAGE gehalten / losgelassen: Firmware (Maske verdeckt)
            bne     pwrap{held(C.KEY_SET)}
            beq     nset
            clr.l   {TS_ON:#x}               ; SETTINGS + PAGE: aus
            jsr     {S['CLRSEL']:#x}
            lea     {txt['off']:#x},a0
            bra     popg
    nset:   btst.l  #1,d3                    ; FUNC?
            beq     pwrap
            jsr     {S['ALL']:#x}            ; a0 = 'All' / 'None'
            bra     pop
    ; ---- PAGE im Modus: Firmware mit verdeckter Auswahl (sonst waere es 'gehaltener Step + PAGE')
    pwrap:  jsr     {UIS:#x}
            movea.l d0,a2                    ; a2 = UIStates
            move.l  0x15c(a2),d4
            move.l  0x160(a2),d5
            move.b  0x164(a2),d3
            clr.l   0x15c(a2)
            clr.l   0x160(a2)
            clr.b   0x164(a2)
            move.l  a3,-(sp)
            move.l  32(sp),-(sp)
            jsr     {GRID_KEY:#x}            ; Original(this, Ereignis)
            addq.l  #8,sp
            move.l  d4,0x15c(a2)
            move.l  d5,0x160(a2)
            move.b  d3,0x164(a2)
            bra     out
    ; ---- Trig-Tasten im Modus (Code 16..31, nur im Grid-Bearbeiten wie die Firmware)
    ntp:    moveq   #16,d0
            cmp.l   d0,d2
            blt     orig
            moveq   #31,d0
            cmp.l   d0,d2
            bgt     orig
            jsr     {UIS:#x}
            move.l  d0,-(sp)
            jsr     {U_EDIT:#x}
            addq.l  #4,sp
            tst.b   d0
            beq     orig
            tst.l   d4
            bne     swal
            jsr     {S['TOG']:#x}
    swal:   moveq   #1,d0                    ; alle Ereignisse der Trig-Tasten verbraucht
            bra     out
    ; ---- Popup ; SETTINGS verbrauchen (popg) ; PAGE verbrauchen
    popg:   move.l  a0,-(sp)
            moveq   #{C.KEY_SET},d0
            jsr     {gest:#x}                ; GEST(13): kein Menue, kein Speichern
            movea.l (sp)+,a0
    pop:    move.l  a0,d1
            lea     {txt['l1']:#x},a0
            lea     {txt['l2']:#x},a1
            moveq   #{C.OV_TEXT},d0
            jsr     {ovs:#x}
            pea     15.w
            jsr     {C.CONSUME:#x}
            addq.l  #4,sp
            moveq   #1,d0
    out:    movem.l (sp),d2-d5/a2-a3
            lea     24(sp),sp
            rts
    orig:   movem.l (sp),d2-d5/a2-a3
            lea     24(sp),sp
            jmp     {GRID_KEY:#x}
    ''')
    code = adone(a); check_cf(code, M_A)
    return code, dict(a.lab)


def build_s(txt):
    has = ''.join(f'''
            move.l  d5,-(sp)
            move.l  a2,-(sp)
            jsr     {f:#x}
            addq.l  #8,sp
            tst.b   d0
            bne     sy''' for f in HAS)
    a = A(M_S)
    asm(a, f'''
    ; ================= CLRSEL: Auswahl (gehaltene Steps, Merker, Fokus) loeschen
    CLRSEL: jsr     {UIS:#x}
            move.l  d0,-(sp)
            jsr     {U_CLR:#x}
            addq.l  #4,sp
            rts
    ; ================= SELABLE: d5 = Step -> d0.b != 0 wenn Trig / Lock-Trig / P-Locks (a2 zerstoert)
    SELABLE:
            jsr     {PROJ:#x}
            move.l  d0,-(sp)
            jsr     {TRK:#x}
            addq.l  #4,sp
            movea.l d0,a2{has}
            moveq   #0,d0
            rts
    sy:     moveq   #1,d0
            rts
    ; ================= HOLDON: Auswahl nicht leer -> Halte-Merker wie nach dem Halten einer Trig-Taste
    HOLDON: jsr     {UIS:#x}
            movea.l d0,a0
            move.l  0x15c(a0),d1
            or.l    0x160(a0),d1
            beq     ho
            pea     1.w
            move.l  a0,-(sp)
            jsr     {U_HOLD:#x}
            addq.l  #8,sp
    ho:     rts
    ; ================= TOG (d2 = Code): Step = Seite * 16 + Code - 16 an/ab
    TOG:    jsr     {PROJ:#x}
            move.l  d0,-(sp)
            jsr     {PG_A:#x}
            move.l  d0,-(sp)
            jsr     {PG_B:#x}
            addq.l  #8,sp
            lsl.l   #4,d0
            add.l   d2,d0
            moveq   #16,d1
            sub.l   d1,d0
            move.l  d0,d5                    ; d5 = Step
            bsr     SELABLE
            tst.b   d0
            beq     tr
            jsr     {UIS:#x}
            movea.l d0,a2
            move.l  d5,-(sp)
            move.l  a2,-(sp)
            jsr     {U_HELD:#x}
            addq.l  #8,sp
            moveq   #1,d1
            and.l   d1,d0
            eor.l   d1,d0                    ; d0 = !gehalten
            move.l  d0,-(sp)
            move.l  d5,-(sp)
            move.l  a2,-(sp)
            jsr     {U_SET:#x}
            lea     12(sp),sp
            bsr     HOLDON
    tr:     rts
    ; ================= ALL: alle waehlbaren Steps bis zur Patternlaenge; waren schon alle gewaehlt -> keine. a0 = Text
    ALL:    jsr     {PROJ:#x}
            move.l  d0,-(sp)
            jsr     {TRK:#x}
            move.l  d0,(sp)
            jsr     {LEN:#x}
            addq.l  #4,sp
            move.l  d0,d3                    ; d3 = Laenge
            moveq   #64,d0                   ; hoechstens 64 (64 >= Laenge: so lassen)
            cmp.l   d3,d0
            bge     al0
            moveq   #64,d3
    al0:    jsr     {UIS:#x}
            movea.l d0,a3                    ; a3 = UIStates ; d4 = hinzugefuegt ; d5 = Step
            moveq   #0,d4
            moveq   #0,d5
    alp:    cmp.l   d3,d5
            bge     ald
            bsr     SELABLE
            tst.b   d0
            beq     aln
            move.l  d5,-(sp)
            move.l  a3,-(sp)
            jsr     {U_HELD:#x}
            addq.l  #8,sp
            btst.l  #0,d0
            bne     aln
            pea     1.w
            move.l  d5,-(sp)
            move.l  a3,-(sp)
            jsr     {U_SET:#x}
            lea     12(sp),sp
            moveq   #1,d4
    aln:    addq.l  #1,d5
            bra     alp
    ald:    tst.l   d4
            bne     ala
            move.l  a3,-(sp)
            jsr     {U_CLR:#x}
            addq.l  #4,sp
            lea     {txt['none']:#x},a0
            rts
    ala:    bsr     HOLDON
            lea     {txt['all']:#x},a0
            rts
    ''')
    code = adone(a); check_cf(code, M_S)
    return code, dict(a.lab)


def build_b(texts_at, P):
    text = f'''
    ; ================= TSF: Hauptbildschirm PAGE frisch, FUNC? Im Modus 'nein' -> Ereignis geht ans Grid (TSK)
    TSF:    movea.l (sp)+,a0
            orig    {TSF_HOOK:#x},2          ; verschobener Originalbefehl
            move.l  a0,-(sp)
            move.l  {TS_ON:#x},d0
            cmpi.l  #{TS_MAGIC:#x},d0
            beq     tf
            jmp     {BIT1:#x}
    tf:     moveq   #0,d0
            rts
    ; ================= TSL: LED-Schleife des Grids, Step-Zustand a5; ausgewaehlt -> 4 Hz an/aus
    TSL:    move.l  {TS_ON:#x},d0
            cmpi.l  #{TS_MAGIC:#x},d0
            bne     ln
            jsr     {UIS:#x}
            movea.l d0,a0
            move.l  60(sp),d0
            add.l   d3,d0                    ; d0 = Seite*16 + d3
            moveq   #31,d1
            cmp.l   d0,d1
            blt     lh
            move.l  0x160(a0),d1
            bra     lb
    lh:     move.l  0x15c(a0),d1
            subi.l  #32,d0
    lb:     btst.l  d0,d1
            beq     ln
            move.l  {C.TIMER:#x},d0
            btst.l  #{BLINK_BIT},d0
            beq     lo
            movea.w #2,a5
            bra     ln
    lo:     movea.w #1,a5
    ; Original: move.l d3,-(a7) ; jsr 0x4000608c ; pea LED_ARG
    ln:     orig    {TSL_HOOK:#x},2          ; verschobener Originalbefehl
            jsr     {LED_OF:#x}              ; LED-Funktion
            movea.l 4(sp),a1
            move.l  (sp),4(sp)
            move.l  #{LED_ARG:#x},(sp)
            jmp     (a1)
    ; ================= NVW (statt Aufruf 0x400296c4(view = a2, Drehung = d0)): absolut -> Wert des Fokus-Steps
    NVW:    orig    {NVW_HOOK:#x},4          ; verschobene Originalbefehle
            jsr     {NV_APPLY:#x}            ; Stapel: a2, d0, Ruecksprung
            lea     -24(sp),sp
            movem.l d2-d6/a3,(sp){IS_ABS}
            bne     nvx
            jsr     {FOCUS:#x}
            move.l  d0,d3                    ; d3 = Fokus
            bmi     nvx
            move.l  104(a2),d0               ; Feld 0..2 (Note, Velocity, Laenge)
            moveq   #2,d1
            cmp.l   d0,d1
            bcs     nvx
            lsl.l   #2,d0
            lea     NVTAB,a0
            move.l  0(a0,d0.l),d2            ; d2 = Getter
            lea     NVSET,a0
            move.l  0(a0,d0.l),d4            ; d4 = Setter
            jsr     {PROJ:#x}
            move.l  d0,-(sp)
            jsr     {TRK:#x}
            addq.l  #4,sp
            movea.l d0,a3                    ; a3 = Track
            movea.l d2,a0
            move.l  d3,-(sp)
            move.l  a3,-(sp)
            jsr     (a0)
            addq.l  #8,sp
            mvs.b   d0,d6                    ; d6 = Getter(trk, Fokus)
            moveq   #0,d5
    nvl:    cmp.l   d3,d5
            beq     nvn
            jsr     {P['HS']:#x}
            beq     nvn
            movea.l d4,a0
            move.l  d6,-(sp)
            move.l  d5,-(sp)
            move.l  a3,-(sp)
            jsr     (a0)
            lea     12(sp),sp
    nvn:    addq.l  #1,d5
            moveq   #64,d0
            cmp.l   d0,d5
            bne     nvl
    nvx:    movem.l (sp),d2-d6/a3
            lea     24(sp),sp
            movea.l 8(sp),a1
            move.l  4(sp),8(sp)
            move.l  (sp),4(sp)
            addq.l  #4,sp
            jmp     (a1)
'''
    def tail(end):                           # Getter / Setter von Note, Velocity, Laenge ; Texte
        pad = -end % 4
        tab = end + pad
        b = bytearray(pad) + struct.pack('>3I', *NV_GET) + struct.pack('>3I', *NV_SET)
        at = {'NVTAB': tab, 'NVSET': tab + 12}
        for k, s in TXT.items():
            at['T_' + k] = end + len(b); b += s.encode() + b'\0'
        return bytes(b), at
    code, lab = asm2(M_B, text, tail)
    at = {k[2:]: lab.pop(k) for k in list(lab) if k.startswith('T_')}
    del lab['NVSET']
    if texts_at is not None: assert at == texts_at, 'Textadressen verschoben'
    return code, lab, at


def build_p():
    a = A(M_P)
    asm(a, f'''
    ; ================= PL(view, param, delta): statt vt[0x74]; absolut -> Wert des Fokus-Steps in alle gehaltenen
    PL:     lea     -28(sp),sp
            movem.l d2-d6/a2-a3,(sp)
            move.l  40(sp),-(sp)
            move.l  40(sp),-(sp)
            move.l  40(sp),-(sp)
            jsr     {PL_ORIG:#x}
            lea     12(sp),sp
            move.l  d0,d4
            tst.b   d4
            beq     px{IS_ABS}
            bne     px
            movea.l 32(sp),a2                ; a2 = view ; d2 = param
            move.l  36(sp),d2
            jsr     {FOCUS:#x}
            move.l  d0,d3                    ; d3 = Fokus
            bmi     px
            moveq   #{NUDGE},d0
            cmp.l   d2,d0
            beq     pnud
            movea.l (a2),a0
            move.l  d2,-(sp)
            pea     -1.w
            move.l  a2,-(sp)
            movea.l 128(a0),a0
            jsr     (a0)
            lea     12(sp),sp
            movea.l d0,a3                    ; a3 = obj
            movea.l (a3),a0
            move.l  d3,-(sp)
            move.l  d2,-(sp)
            move.l  a3,-(sp)
            movea.l 36(a0),a0
            jsr     (a0)
            lea     12(sp),sp
            move.l  d0,d6                    ; d6 = Lock(Fokus)
            moveq   #0,d5
    plp:    cmp.l   d3,d5
            beq     pln
            bsr     HS
            beq     pln
            movea.l (a2),a0
            move.l  d2,-(sp)
            move.l  d5,-(sp)
            move.l  a2,-(sp)
            movea.l 96(a0),a0
            jsr     (a0)
            lea     12(sp),sp
            tst.l   d0                       ; hat Lock?
            bmi     pln
            movea.l (a3),a0
            move.l  d5,-(sp)
            move.l  d6,-(sp)
            move.l  d2,-(sp)
            move.l  a3,-(sp)
            movea.l 40(a0),a0
            jsr     (a0)                     ; setzen
            lea     16(sp),sp
    pln:    addq.l  #1,d5
            moveq   #64,d0
            cmp.l   d0,d5
            bne     plp
            bra     px
    ; Nudge (Mikro-Timing im Track, kein Lock)
    pnud:   jsr     {PROJ:#x}
            move.l  d0,-(sp)
            jsr     {TRK:#x}
            addq.l  #4,sp
            movea.l d0,a3
            move.l  d3,-(sp)
            move.l  a3,-(sp)
            jsr     {NUD_GET:#x}
            addq.l  #8,sp
            mvs.b   d0,d6                    ; d6 = Nudge(Fokus)
            moveq   #0,d5
    pnl:    cmp.l   d3,d5
            beq     pnn
            bsr     HS
            beq     pnn
            move.l  d6,-(sp)
            move.l  d5,-(sp)
            move.l  a3,-(sp)
            jsr     {NUD_SET:#x}
            lea     12(sp),sp
    pnn:    addq.l  #1,d5
            moveq   #64,d0
            cmp.l   d0,d5
            bne     pnl
    px:     move.l  d4,d0
            movem.l (sp),d2-d6/a2-a3
            lea     28(sp),sp
            rts
    ; ================= HS: d5 = Step gehalten? (Z = nein) ; zerstoert d0, d1, a0, a1
    HS:     jsr     {UIS:#x}
            move.l  d5,-(sp)
            move.l  d0,-(sp)
            jsr     {U_HELD:#x}
            addq.l  #8,sp
            btst.l  #0,d0
            rts
    ''')
    code = adone(a); check_cf(code, M_P)
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
    return patch('trig-select', 11, 'Trigger Select Mode',
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
