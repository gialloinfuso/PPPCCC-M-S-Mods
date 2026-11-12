#!/usr/bin/env python3
"""Mod 'control-mode' (v2): CONTROL ALL relativ oder absolut. Braucht nur 'core'.
Umschalten: TRACK halten + SETTINGS kurz druecken (Loslassen ohne Drehung dazwischen) -> Popup 'Control' / 'All' +
  'Absolute' / 'Relative'. Global im Einstellungsblock (CTRL_MODE 0x404e9b5d, beim Ausschalten gespeichert);
  0x5a = absolut, alles andere = relativ (Firmware; nach dem Zuruecksetzen 0, v1-Reste 1..4 ebenfalls relativ).
Relativ = Firmware: jeder Track eigener Wert + Drehung, am Anschlag bleibt er stehen (der Setter klemmt).
Absolut: der ausgewaehlte Track macht den Schritt wie in der Firmware, alle anderen Tracks bekommen genau seinen neuen Wert
  (geklemmt auf ihren Bereich).
Betrifft:
  - TRACK + Regler (ParameterPageView, vtable 0x4010052c + 0x5c = 0x4001d6e4, die Firmware-Schleife ueber 6 Tracks):
    Eintrag 0x40100588 -> CA; relativ springt CA in die Firmware-Funktion.
  - TRACK + LEVEL/DATA (Lautstaerke) und FUNC + TRACK + LEVEL/DATA (Pan) im Hauptbildschirm (0x4001aa4e): Haken an den
    Anfaengen der Lautstaerke- und Pan-Zweige 0x4001ab7a (LV) und 0x4001aaec (LP); die Schleifen selbst bleiben unberuehrt
    (ihr Sprungziel liegt 4 Byte hinter dem Schleifenanfang, dort ist kein Platz fuer einen Haken).
  - groove liest dasselbe Byte fuer TRACK + SETTINGS/MACHINE + Swing (Humanize aller Tracks).
Gesten: Tasten-Slot 0 des Cores (SETTINGS Druecken / Loslassen) = CMK; Encoder-Slot 5 = CME (SETTINGS gehalten und ein
  Regler gedreht -> CM_SU, dann schaltet das Loslassen nicht um).
Speicher: Masken 0x40182b38 (CA, PO, LV), 0x40182e28 (LP, CMK, CME, Texte). RAM CM_SU 0x4a33c3a8, CM_SCR 0x4a33c3a9.
Aufruf: g2_control.py [out.json]
"""
import struct, sys
from common import *                 # noqa: F401,F403
import common as C
import g2_core as core
import collections
from cfasm import asm, done as adone

M_A, M_B = 0x40182B38, 0x40182E28
SIZE = {M_A: 376, M_B: 376}
VT_SLOT, VT_ORIG = 0x40100588, 0x4001D6E4          # ParameterPageView vtable +0x5c: CONTROL ALL
LV_HOOK, LV_BACK = 0x4001AB7A, 0x4001AB80         # Lautstaerke: lea 0x40009ca0,a3 (Getter) ; danach lea Setter,a2
LP_HOOK, LP_BACK = 0x4001AAEC, 0x4001AAF2         # Pan: lea 0x400097f0,a2 (Klang-Objekt) ; danach lea 0x4000b274,a3
LV_ORIG, LP_ORIG = (6, 'a9582d71004325d3910cf00e3f68321081f3275f410d6fb86f72c9e44125efec'), (6, '374b55394d625229746501ff009282acfaca2cf2afe019f5f928d4e0a75a5288')   # Laenge + SHA-256
VGET, VSET, SOBJ = 0x40009CA0, 0x4000A3AE, 0x400097F0
L_END = 0x4001ABCE                                # Ende des Encoder-Handlers (move.b d5,d0 ; Register zurueck)
SETP = 0x4000B274                                 # Parameter setzen (obj, param, wert, track, f1, f2) -> Wert (Getter)
# ---- smp26 Control-All-Spurauswahl (Idee: Mod von jemandem auf GitHub, Name folgt; eigener Code). Nutzlast-Platz 'control-mode'.
POFF, PROOM = C.PAY_SLOT['control-mode']
PORG = C.PAY + POFF
CAK_HOOK, CAK_CK, CAK_BACK = 0x400223FA, (6, 'ba0e97ddfca0a59e7d56b0fa1ca656a667459a8bcc2554cc0d01aa11d1f0fab5'), 0x40022400   # Grid: Trig-Taste (lea UIStates,a5)
GRID_DONE = 0x40022FF4                            # Ende von consumeKeyEvent (d2.b = behandelt)
CLE_HOOK, CLE_CK = 0x40021F86, (8, 'f1d2faca5bd76caf9fa1574bdfde900204d8989f4c39dd04d04d80d76bb15f3d')   # LED-Schleife: moveq #16 ; cmp ; bne.w
CLE_LOOP, CLE_DONE = 0x40021ED6, 0x40021F8E
LED_ARG, K_PRESS = 0x404A8CB8, 0x400724A0
CA_TXT = {'ca': 'Ctrl All', 'on': 'On', 'off': 'Off'}
# smp26b: TRACK gehalten = TrackSelectionView (Konstruktor 0x40023a7a, Vtable 0x40100ee0) liegt oben und bekommt die Trig-Tasten;
#   +8 Tasten (0x40024078), +0x44 LEDs (0x40023d18: Ansicht, Maske; setzt LED 0x1f und belegt sie in der Maske)
TSV_KEY_SLOT, TSV_KEY = 0x40100EE8, 0x40024078
TSV_LED_SLOT, TSV_LED = 0x40100F24, 0x40023D18
LED_CTX, LED_SET, LED_OF, KEY_OF = 0x400CFAF4, 0x40005F86, 0x4000608C, 0x4007240C
# smp26c: LED_SET(ctx, LED, Zustand, Tabelle) schreibt nur, wenn die LED in diesem Durchlauf noch frei ist (ctx +0x28 + 4 LED) und
#   Zustand != 0 (erster gewinnt). Die Grid-LED-Schleife schreibt die Trigs vor uns -> eigener Haken CLB vor der Schleife
#   (0x40021ec2: lea 0x4000608c,a4); aus = Zustand 1 (wie Steps hinter der Pattern-Laenge).
LSW_HOOK, LSW_CK, LSW_BACK = 0x40005F86, (8, 'd43e64e0210fdd98e9dd8476d7cea57c93492ec611d50eddcbf6fd90ea80cef7'), 0x40005F8E
LED_ON, LED_OFF = 0x4008E964, 0x4008E998          # LED-Bit direkt an / aus (logische LED 0..0x35)
# smp26d: LSW am Anfang von LED_SET: mit TRACK gehalten bekommt jede Trig-LED 1..6 den Zustand der Auswahl, egal wer schreibt;
#   CALEDS schaltet die LED-Bits zusaetzlich direkt (unabhaengig von den Belegt-Plaetzen des Durchlaufs).
CLB_HOOK, CLB_CK = 0x40021EC2, (6, '0b8070be0fe54b93b70466f8f7c9ddb151156d2ee713ecb195f1775576991413')
PAN = 0x1C
TXT = {'l1': "Control", 'l2': "All", 'abs': "Absolute", 'rel': "Relative"}
ABS, MODE, SU, SCR = C.CTRL_ABS, C.CTRL_MODE, C.CM_SU, C.CM_SCR


# mvz.b CTRL_MODE,d0 ; moveq #ABS,d1 ; cmp.l d1,d0  (Z = absolut; zerstoert d0, d1)
IS_ABS = f'''
            mvz.b   {MODE:#x},d0
            moveq   #{ABS},d1
            cmp.l   d1,d0                    ; absolut?'''


def build_a(P):
    a = A(M_A)
    asm(a, f'''
    ; ---------------- CA(this, Encoder, Drehung): statt 0x4001d6e4
    CA:{IS_ABS}
            beq     abs
            jmp     {P['CAR']:#x}            ; relativ: wie die Firmware, nur ausgewaehlte Spuren (smp26)
    abs:    lea     -32(sp),sp
            movem.l d2-d7/a2-a3,(sp)
            movea.l 36(sp),a2                ; a2 = this ; d6 = Encoder ; d7 = Drehung
            move.l  40(sp),d6
            move.l  44(sp),d7
            jsr     {C.SEL_A:#x}             ; d4 = Track
            move.l  d0,-(sp)
            jsr     {C.SEL_B:#x}
            move.l  d0,-(sp)
            jsr     {C.SEL_C:#x}
            addq.l  #8,sp
            move.l  d0,d4
            pea     {C.KEY_FUNC}.w           ; FUNC wie die Firmware: 0 / 1
            jsr     {C.HELD:#x}
            addq.l  #4,sp
            tst.l   d0
            sne.b   d0
            mvs.b   d0,d0
            neg.l   d0
            move.l  d0,d5
            move.l  d4,d2                    ; ausgewaehlter Track: d3 = Parameter, d0 = Objekt
            bsr     PO
            movea.l d0,a1
            movea.l (a1),a0
            clr.l   -(sp)
            clr.l   -(sp)
            clr.l   -(sp)
            clr.l   -(sp)
            move.l  d2,-(sp)
            move.l  d7,-(sp)
            move.l  d3,-(sp)
            move.l  d0,-(sp)
            movea.l 32(a0),a0                ; obj->vt[0x20](obj, param, Drehung, track, 0,0,0,0) -> neuer Wert
            jsr     (a0)
            lea     32(sp),sp
            move.l  d0,d7                    ; d7 = Zielwert ; d2 = 0
            moveq   #0,d2
    lp:     cmp.l   d4,d2
            beq     nx
            move.l  d2,d0                    ; smp26: Spur ausgenommen
            jsr     {P['ALLOWED']:#x}
            tst.l   d0
            beq     nx
            bsr     PO
            movea.l d0,a3                    ; a3 = obj ; Zielwert auf erlaubten Wert des Tracks:
            movea.l (a3),a0
            clr.l   -(sp)
            move.l  d7,-(sp)
            move.l  d3,-(sp)
            move.l  a3,-(sp)
            movea.l 20(a0),a0                ; obj->vt[0x14](obj, param, Ziel, 0) (klemmt, naechster erlaubter Wert)
            jsr     (a0)
            lea     16(sp),sp
            clr.l   -(sp)                    ; setzen wie die Firmware
            clr.l   -(sp)
            move.l  d2,-(sp)
            move.l  d0,-(sp)
            move.l  d3,-(sp)
            move.l  a3,-(sp)
            jsr     {SETP:#x}
            lea     24(sp),sp
    nx:     addq.l  #1,d2
            moveq   #6,d0
            cmp.l   d2,d0
            bne     lp
            movem.l (sp),d2-d7/a2-a3
            lea     32(sp),sp
            rts
    ; ---------------- PO: d2 = Track -> d3 = Parameter unter dem Regler, d0 = Objekt (a2 this, d5 FUNC, d6 Encoder)
    PO:     movea.l (a2),a0
            movea.l 124(a0),a0
            move.l  d2,-(sp)
            move.l  d5,-(sp)
            move.l  d6,-(sp)
            move.l  a2,-(sp)
            jsr     (a0)
            lea     16(sp),sp
            move.l  d0,d3
            movea.l (a2),a0
            movea.l 128(a0),a0
            move.l  d3,-(sp)
            move.l  d2,-(sp)
            move.l  a2,-(sp)
            jsr     (a0)
            lea     12(sp),sp
            rts
    ; ---------------- LV (Haken 0x4001ab7a): Lautstaerke. d2 Kit, d3 Track, d6.b TRACK gehalten, d7.w Schritt
    LV:     orig    {LV_HOOK:#x},6           ; verschobener Originalbefehl: lea Getter,a3
            tst.b   d6                       ; ohne TRACK: Firmware
            beq     lo{IS_ABS}
            beq     la
    lo:     lea     {P['VSETW']:#x},a2       ; relativ: Firmware mit gefiltertem Setter (smp26)
            jmp     {LV_BACK + 6:#x}
    la:     lea     {P['VSETW']:#x},a2
            mvs.w   d7,d7
            move.l  d3,-(sp)                 ; get(kit, track) + Schritt
            move.l  d2,-(sp)
            jsr     (a3)
            addq.l  #8,sp
            add.l   d7,d0
            pea     1.w                      ; set(kit, track, v, 1) (klemmt)
            move.l  d0,-(sp)
            move.l  d3,-(sp)
            move.l  d2,-(sp)
            jsr     (a2)
            lea     16(sp),sp
            move.l  d3,-(sp)                 ; d7 = get(kit, track) ; d3 = 0
            move.l  d2,-(sp)
            jsr     (a3)
            addq.l  #8,sp
            move.l  d0,d7
            moveq   #0,d3
    lb:     pea     1.w
            move.l  d7,-(sp)
            move.l  d3,-(sp)
            move.l  d2,-(sp)
            jsr     (a2)
            lea     16(sp),sp
            addq.l  #1,d3
            moveq   #6,d0
            cmp.l   d3,d0
            bne     lb
            jmp     {L_END:#x}
    ''')
    code = adone(a); check_cf(code, M_A)
    return code, dict(a.lab)


def build_b(P):
    cs = core.sym()
    text = f'''
    ; ---------------- LP (Haken 0x4001aaec): Pan. a2 = Klang-Objekt(kit, track), a3 = Setter 0x4000b274
    LP:     orig    {LP_HOOK:#x},6           ; verschobener Originalbefehl: lea Klang-Objekt,a2
            tst.b   d6
            beq     po{IS_ABS}
            beq     pa
    po:     lea     {P['SETW']:#x},a3        ; Firmware mit gefiltertem Setter (smp26)
            jmp     {LP_BACK + 6:#x}
    pa:     lea     {P['SETW']:#x},a3        ; Setter (gefiltert)
            mvs.w   d7,d7
            move.l  d3,-(sp)
            move.l  d2,-(sp)
            jsr     (a2)
            addq.l  #8,sp
            move.l  d0,d6                    ; d6 = Objekt des Tracks
            movea.l d0,a1
            movea.l (a1),a0
            pea     {PAN}.w
            move.l  d0,-(sp)
            movea.l 28(a0),a0
            jsr     (a0)                     ; Getter(obj, PAN)
            addq.l  #8,sp
            add.l   d7,d0                    ; + Schritt
            pea     1.w
            clr.l   -(sp)
            move.l  d3,-(sp)
            move.l  d0,-(sp)
            pea     {PAN}.w
            move.l  d6,-(sp)
            jsr     (a3)                     ; setzen (klemmt)
            lea     24(sp),sp
            move.l  d0,d7                    ; d7 = Zielwert ; d3 = 0
            moveq   #0,d3
    pb:     move.l  d3,-(sp)
            move.l  d2,-(sp)
            jsr     (a2)                     ; Objekt des Tracks d3
            addq.l  #8,sp
            pea     1.w
            clr.l   -(sp)
            move.l  d3,-(sp)
            move.l  d7,-(sp)
            pea     {PAN}.w
            move.l  d0,-(sp)
            jsr     (a3)
            lea     24(sp),sp
            addq.l  #1,d3
            moveq   #6,d0
            cmp.l   d3,d0
            bne     pb
            jmp     {L_END:#x}
    ; ---------------- CMK: Tasten-Slot (d1 = 0 Druecken / 1 Loslassen) ; Loslassen + TRACK gehalten + unbenutzt -> umschalten
    CMK:    tst.l   d1
            bne     rel
            clr.b   {SU:#x}                  ; Druecken: SU loeschen
            moveq   #0,d0
            rts
    rel:    tst.b   {SU:#x}
            bne     no
            pea     {C.KEY_TRACK}.w
            jsr     {C.HELD:#x}
            addq.l  #4,sp
            tst.l   d0
            beq     no{IS_ABS}
            bne     wr                       ; bisher relativ -> d1 = ABS
            moveq   #0,d1                    ; bisher absolut -> 0
    wr:     move.b  d1,{SCR:#x}
            pea     1.w
            pea     {SCR:#x}
            pea     {MODE:#x}
            jsr     {C.COPY:#x}
            lea     12(sp),sp
            lea     T_REL,a0
            tst.b   {SCR:#x}
            beq     tx
            lea     T_ABS,a0
    tx:     move.l  a0,d1
            lea     T_L1,a0
            lea     T_L2,a1
            moveq   #{C.OV_TEXT},d0
            jsr     {cs['OVS']:#x}
            moveq   #1,d0
            rts
    no:     clr.b   {SU:#x}
            moveq   #0,d0
            rts
    ; ---------------- CME: Encoder-Slot; SETTINGS gehalten -> SU (das Loslassen schaltet dann nicht um) ; nie 'meins'
    CME:    pea     {C.KEY_SET}.w
            jsr     {C.HELD:#x}
            addq.l  #4,sp
            tst.l   d0
            beq     ce
            moveq   #1,d0
            move.b  d0,{SU:#x}
    ce:     moveq   #0,d0
            rts
'''
    def tail(end):
        b = bytearray(); at = {}
        for k, s in TXT.items():
            at['T_' + k.upper()] = end + len(b); b += s.encode() + b'\0'
        return bytes(b), at
    return asm2(M_B, text, tail)


def pay_text(cs, at):
    allowed_skip = C.ca_skip('d2', 'd0', 'd1', 'al1', 'al')
    led_skip = C.ca_skip('d3', 'd0', 'd1', 'ce3', 'ce')   # in CALEDS: d3 = Spur
    lsw_skip = C.ca_skip('d2', 'd0', 'd1', 'ls3', 'lw')
    return f"""
    ; ALLOWED: d0 = Spur -> d0 = 1, wenn sie Control All mitmacht (ausgewaehlt oder die aktive Spur), sonst 0. Zerstoert d1, a0, a1
    ALLOWED: move.l d2,-(sp)
            move.l  d0,d2{allowed_skip}
            moveq   #1,d0
            bra     al9
    al1:    jsr     {C.SEL_A:#x}
            move.l  d0,-(sp)
            jsr     {C.SEL_B:#x}
            move.l  d0,(sp)
            jsr     {C.SEL_C:#x}
            addq.l  #4,sp
            cmp.l   d2,d0
            beq     al2
            moveq   #0,d0
            bra     al9
    al2:    moveq   #1,d0
    al9:    move.l  (sp)+,d2
            rts
    ; Setter der Firmware nur fuer erlaubte Spuren: Lautstaerke (Kit, Spur, Wert, 1), Parameter (Objekt, Param, Wert, Spur, 0, 1)
    VSETW:  move.l  8(sp),d0
            jsr     ALLOWED
            tst.l   d0
            beq     vw9
            jmp     {VSET:#x}
    vw9:    rts
    SETW:   move.l  16(sp),d0
            jsr     ALLOWED
            tst.l   d0
            beq     sw9
            jmp     {SETP:#x}
    sw9:    rts
    ; CAR(this, Encoder, Drehung): CONTROL ALL relativ wie die Firmware 0x4001d6e4, nur erlaubte Spuren
    CAR:    lea     -20(sp),sp
            movem.l d2-d3/a2-a4,(sp)
            movea.l 24(sp),a2
            moveq   #0,d2
            lea     {C.HELD:#x},a4
    car1:   move.l  d2,d0
            jsr     ALLOWED
            tst.l   d0
            beq     car9
            movea.l (a2),a0
            movea.l 0x7c(a0),a3
            pea     {C.KEY_FUNC}.w
            jsr     (a4)
            move.l  d2,-(sp)
            tst.l   d0
            beq     car2
            moveq   #1,d0
    ; Parameter und neuer Wert wie die Firmware (Befehle aus dem Image): d3 = Parameter, obj->vt[0x20](...)
    car2:   orig    0x4001d70e,44
            orig    0x4001d73c,18
    car9:   addq.l  #1,d2
            moveq   #6,d0
            cmp.l   d2,d0
            bne     car1
            movem.l (sp),d2-d3/a2-a4
            lea     20(sp),sp
            rts
    ; TSK2(Ansicht, Ereignis): Tasten der TrackSelectionView (TRACK gehalten). Trig 1..6: gedrueckt -> Spur fuer Control All an / aus
    ; (Popup, LEDs), jedes Ereignis dieser Tasten verbraucht; sonst d0 = 0 (smp28: Slot des Cores TSVK, danach die Firmware)
    TSK2:   move.l  8(sp),-(sp)
            jsr     {KEY_OF:#x}
            addq.l  #4,sp
            subi.l  #16,d0
            moveq   #5,d1
            cmp.l   d0,d1
            bcc     tk1
            moveq   #0,d0                    ; smp28: nicht behandelt -> naechster Slot / Firmware (Core TSVK)
            rts
    tk1:    move.l  d2,-(sp)
            move.l  d0,d2                    ; Spur 0..5
            move.l  12(sp),-(sp)
            jsr     {K_PRESS:#x}
            addq.l  #4,sp
            tst.b   d0
            beq     tk9
            mvz.b   {C.CA_SEL:#x},d0
            move.l  d0,d1
            andi.l  #0xc0,d1
            cmpi.l  #0x80,d1
            beq     tk2
            move.l  #0x80,d0
    tk2:    bchg    d2,d0
            move.b  d0,{C.CA_SEL:#x}
            lea     TNAMES,a0
            movea.l 0(a0,d2.l*4),a1
            btst    d2,d0
            beq     tk3
            move.l  #{at['off']:#x},d1
            bra     tk4
    tk3:    move.l  #{at['on']:#x},d1
    tk4:    lea     {at['ca']:#x},a0
            moveq   #{C.OV_TEXT},d0
            jsr     {cs['OVS']:#x}
            pea     1.w
            clr.l   -(sp)
            jsr     CALEDS
            addq.l  #8,sp
    tk9:    move.l  (sp)+,d2
            moveq   #1,d0
            rts
    ; TSLW(Ansicht, Maske): LEDs der TrackSelectionView wie die Firmware, dazu Trig 1..6 = Auswahl (in der Maske belegt)
    TSLW:   move.l  8(sp),-(sp)
            move.l  8(sp),-(sp)
            jsr     {TSV_LED:#x}
            addq.l  #8,sp
            pea     1.w
            move.l  12(sp),-(sp)
            jsr     CALEDS
            addq.l  #8,sp
            rts
    ; CLB (Grid-LED-Schleife, vor dem ersten Step; statt lea 0x4000608c,a4): TRACK gehalten -> Trig 1..6 zuerst = Auswahl
    CLB:    lea     {LED_OF:#x},a4
            pea     {C.KEY_TRACK}.w
            jsr     {C.HELD:#x}
            addq.l  #4,sp
            tst.l   d0
            beq     cb9
            pea     1.w
            clr.l   -(sp)
            jsr     CALEDS
            addq.l  #8,sp
    cb9:    rts
    ; CALSF (LED-Filter des Cores, d0 = LED, d1 = Zustand -> d1): mit TRACK gehalten Trig 1..6 = Auswahl (4 / 1)
    CALSF:  move.l  d2,-(sp)
            move.l  d3,-(sp)
            move.l  d0,d3                    ; LED
            move.l  d1,-(sp)                 ; Zustand
            pea     {C.KEY_TRACK}.w
            jsr     {C.HELD:#x}
            addq.l  #4,sp
            tst.l   d0
            beq     ls8
            pea     {C.KEY_RETRIG}.w         ; smp41/42: TRACK + RETRIG = PAD-Auswahl (pad-mode zeigt seine Spuren), hier nichts
            jsr     {C.HELD:#x}
            addq.l  #4,sp
            tst.l   d0
            bne     ls8
            moveq   #0,d2
    ls1:    move.l  d2,-(sp)
            jsr     {LED_OF:#x}
            addq.l  #4,sp
            cmp.l   d3,d0
            beq     ls2
            addq.l  #1,d2
            moveq   #6,d0
            cmp.l   d2,d0
            bne     ls1
            bra     ls8
    ls2:{lsw_skip}{C.blink_state('d0', 'lb')}
            bra     ls4
    ls3:    moveq   #1,d0
    ls4:    move.l  d0,(sp)
    ls8:    move.l  (sp)+,d1
            move.l  (sp)+,d3
            move.l  (sp)+,d2
            rts
    ; CALEDS(Maske oder 0, Zustand aus): Trig 1..6 an (4, ausgewaehlt) / aus, LED in der Maske belegen
    CALEDS: pea     {C.KEY_RETRIG}.w         ; smp41/42: mit RETRIG (TRACK + RETRIG = PAD-Auswahl) keine Control-All-LEDs
            jsr     {C.HELD:#x}
            addq.l  #4,sp
            tst.l   d0
            beq     cl0
            rts
    cl0:    lea     -12(sp),sp
            movem.l d2-d4,(sp)
            moveq   #0,d3
    cl1:    move.l  d3,-(sp)
            jsr     {LED_OF:#x}
            addq.l  #4,sp
            move.l  d0,d4                    ; LED
{led_skip}{C.blink_state('d2', 'cb')}
            bra     cl3
    ce3:    move.l  20(sp),d2
    cl3:    jsr     {LED_CTX:#x}
            pea     {LED_ARG:#x}
            move.l  d2,-(sp)
            move.l  d4,-(sp)
            move.l  d0,-(sp)
            jsr     {LED_SET:#x}
            lea     16(sp),sp
            move.l  d4,-(sp)                 ; LED-Bit direkt (der Durchlauf kann den Platz schon belegt haben)
            moveq   #1,d0
            cmp.l   d2,d0
            beq     cl5
            jsr     {LED_ON:#x}
            bra     cl6
    cl5:    jsr     {LED_OFF:#x}
    cl6:    addq.l  #4,sp
            move.l  16(sp),d0                ; Maske
            beq     cl4
            moveq   #0x35,d1
            cmp.l   d4,d1
            bcs     cl4
            movea.l d0,a0
            move.l  d4,d0
            lsr.l   #5,d0
            moveq   #31,d1
            and.l   d4,d1
            moveq   #1,d2
            lsl.l   d1,d2
            move.l  0(a0,d0.l*4),d1
            or.l    d2,d1
            move.l  d1,0(a0,d0.l*4)
    cl4:    addq.l  #1,d3
            moveq   #6,d0
            cmp.l   d3,d0
            bne     cl1
            movem.l (sp),d2-d4
            lea     12(sp),sp
            rts
"""


def build_pay():
    cs = core.sym()
    def data(org):
        b = bytearray(); at = {}
        while (org + len(b)) % 4: b += b'\0'
        at['TNAMES'] = org + len(b); b += bytes(24)
        for k, t in list(CA_TXT.items()) + [('t%d' % i, 'Track %d' % (i + 1)) for i in range(6)]:
            at[k] = org + len(b); b += t.encode() + b'\0'
        struct.pack_into('>6I', b, at['TNAMES'] - org, *[at['t%d' % i] for i in range(6)])
        return bytes(b), at
    lab = collections.defaultdict(int); at = data(PORG + 0x400)[1]
    for _ in range(3):
        a = A(PORG); asm(a, pay_text(cs, at), lab)
        dorg = PORG + len(a.b)
        blob, at = data(dorg)
        lab = collections.defaultdict(int, {**a.lab, **at})
    code = adone(a, dict(lab))
    out = code + blob
    assert len(out) <= PROOM - 4 and C.CA_SEL == C.PAY + POFF + PROOM - 4   # smp29: letztes Wort = CA_SEL (RAM)
    return out, dict(lab)


def build():
    pay, P = build_pay()
    ca, la = build_a(P); cb, lb = build_b(P)
    lab = dict(la); lab.update(lb); lab.update({k: v for k, v in P.items() if k[0].isupper()})
    return {M_A: ca, M_B: cb}, lab, pay


def tweak(img):
    base = apply(img, core.tweak(img))
    parts, lab, pay = build()
    W = Writes(base)
    for va, b in parts.items():
        W.mask(va, b, SIZE[va])
    W.put(C.PIMG(PORG), pay)                                            # smp26: Nutzlast (Control-All-Auswahl)
    core.tkslot_write(W, 'control-mode', lab['TSK2'])              # smp28: ueber den Core (TSVK), pad-mode davor
    W.hook(TSV_LED_SLOT, struct.pack('>I', TSV_LED), struct.pack('>I', lab['TSLW']))
    W.hook(CLB_HOOK, CLB_CK, jsr(lab['CLB']))
    core.lslot_write(W, 'control-mode', lab['CALSF'])            # smp27: LED-Filter des Cores (vorher eigener Haken LSW)
    W.hook(VT_SLOT, struct.pack('>I', VT_ORIG), struct.pack('>I', lab['CA']))
    W.hook(LV_HOOK, LV_ORIG, jmp(lab['LV']))
    W.hook(LP_HOOK, LP_ORIG, jmp(lab['LP']))
    core.slot_write(W, 'control-mode', lab['CME'])
    core.kslot_write(W, 'control-mode', lab['CMK'])
    return patch('control-mode', 10, 'Control All & Parameter change absolute/relative',
                 ["Hold TRACK + tap SETTINGS: CONTROL ALL switches between Relative (firmware: every track moves by the same",
                  "amount and stops at its limit) and Absolute (all tracks take the new value of the selected track).",
                  "Applies to TRACK + knob, TRACK + LEVEL (volume), FUNC + TRACK + LEVEL (pan) and the humanize of groove.",
                  "Global setting, kept after power-off.",
                  "Hold TRACK: trigs 1..6 show which tracks CONTROL ALL affects; TRACK + trig 1..6 toggles a track (the active track",
                  "always follows). All tracks are on after every start. Idea from a GitHub mod by another author (credit to follow).",
                  "Erzeugt von v2/g2_control.py."],
                 W, requires=['core'], hooks=[f"{VT_SLOT:#x}", f"{LV_HOOK:#x}", f"{LP_HOOK:#x}", f"{TSV_LED_SLOT:#x}", f"{CLB_HOOK:#x}"],
                 memory=[{"va": f"{SU:#x}", "size": 2, "ram": True, "use": "SETTINGS used since press, byte for COPY"},
                         {"va": f"{C.CA_SEL:#x}", "size": 1, "ram": True, "use": "Control All track selection (0 at start = all tracks)"}],
                 settings=[f"{MODE:#x} ({ABS:#x} absolute, anything else relative)"],
                 symbols={k: f"{v:#x}" for k, v in lab.items() if k[0].isupper()},
                 params={"slot": C.SLOT['control-mode'], "kslot": C.KSLOT['control-mode'], "abs": ABS, "texts": TXT})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    parts, lab, pay = build()
    print({f"{va:#x}": len(b) for va, b in parts.items()}, len(pay))
