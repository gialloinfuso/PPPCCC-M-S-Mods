#!/usr/bin/env python3
"""Mod 'pad-mode' (v2, Patch 21, smp27): PAD-Spuren - der Sequencer spielt sie nicht, die Trig-Tasten spielen ihre Steps.
Braucht den Core (Popup, GEST, LED-Filter, Nutzlast).

Bedienung (Pip 06.-09.11.2026):
  TRACK + RETRIG halten: Trig 1..6 zeigen die PAD-Spuren (an = PAD, blinkt schnell). TRACK + RETRIG + Trig 1..6: Spur PAD an / aus
    (Popup 'Pad Mode'; smp42, Pip 11.11.: vorher TRACK + FUNC - das rastet aber den Mute-Modus ein (latching-mute);
    smp28 davor SETTINGS + Trig). RETRIG wird bei gehaltenem TRACK verbraucht (beendet so nicht den Filter-Modus von track-filter).
    Gespeichert pro Pattern (Kopf-Byte 57, Bits 0..5; alte Patterns und neue: 0 = keine).
  Ist die aktive Spur eine PAD-Spur (smp29: mit und ohne REC; ohne REC kein chromatisches Spiel mehr, KeyboardView 0x400ff9cc
    -> PKB): Trig 1..16 antippen = diesen Step spielen (16 Slots = die Steps der Seite) mit seinen
    p-locks, Note, Laenge und Sample-Lock, unabhaengig von Bedingung und Wahrscheinlichkeit. Halten + Regler = p-lock des
    Steps bearbeiten (wie immer). FUNC + Trig = Trig anlegen / loeschen (antippen schaltet nichts mehr um).
  Der Sequencer ueberspringt PAD-Spuren (kein Ereignis); gemutete PAD-Spuren spielen auch beim Antippen nicht.
  (MIDI-Noten 36..51 folgen in einem eigenen Schritt.)
Firmware 1.13 / Idee des Abspielens: Tweak 'trig-preview' von drumkilla (drumkilla/elektron-model-tweaks, MIT; Analyse
  Modded-Cycles notes/34): Ereignisbau 0x400548ce(Spur, Pattern, Kit, Step, 0, 0) mit Wahrscheinlichkeit (Spur +0x2cf) = 100
  und Bedingung (Spur +0x204 + Step) = 0xff, Ereignis +0xc = 2, Warteschlange 0x40092116. Spur = Pattern + 0x2d2 n.
  Eigener Code: Interrupts aus waehrend Ereignisbau + Warteschlange (der Sequencer laeuft evtl.).
  TrackSelectionView (TRACK gehalten): Tasten ueber den Core-Slot (TSVK) -> PTSK (vor control-mode).
  Grid (PatternGridView::consumeKeyEvent 0x40022382): gedrueckt ohne FUNC
  0x40022c22 -> PPR (Halten 0x4006b836(UI, Step, 1), Loslass-Aktion 0x4006b91a(UI, Step, 0), Spielen, Neuzeichnen
  0x400760ba); FUNC gedrueckt 0x40022cda -> PFN (Note-Trig 0x40015c20(Spur, Step): loeschen 0x40017c4e(.., 0) / anlegen
  0x40017b48(.., 1)). Ende 0x40022ff4 (d2.b = behandelt). Loslassen: Firmware (Aktion 0 = nichts, Halten aus).
  Sequencer: Anfang des Ereignisbaus 0x400548ce -> SQS (PAD-Spur und nicht MANUAL -> d0 = 0, kein Ereignis).
  Mute: 0x4001263c(Kit, Spur), Kit = 0x4000eb9c(0x400cf866()).
Speicher: Nutzlast-Platz 'pad-mode' (Code, Texte, MANUAL).
Aufruf: g2_pad.py [out.json]
"""
import collections, struct, sys
from common import *                 # noqa: F401,F403
import common as C
import g2_core as core
from cfasm import asm, done as adone

OFF, ROOM = C.PAY_SLOT['pad-mode']
ORG = C.PAY + OFF
PPR_HOOK, PPR_CK, PPR_BACK = 0x40022C22, (6, 'a0e245013e897c17e78bac0ad2df77f1b868b57ef37bf9577f8e4c0b32369f03'), 0x40022C28
PFN_HOOK, PFN_CK, PFN_BACK = 0x40022CDA, (6, '68578cf45bfaa7a4bbb4d5acaecc7e433721bbf7ff5bbb33e359a555fa2bcdd7'), 0x40022CE0
SQS_HOOK, SQS_CK, SQS_BACK = 0x400548CE, (6, 'd3de965f7fbce71e0cbba307ce788a642cf92f0a8b2bf73468e9d944e93234ce'), 0x400548D4
GRID_DONE = 0x40022FF4
UIS, U_SET, U_ACT, REDRAW = 0x400CF9A8, 0x4006B836, 0x4006B91A, 0x400760BA
HAS_NOTE, TRIG_ON, TRIG_DEL = 0x40015C20, 0x40017B48, 0x40017C4E
MUTED, KIT_OF = 0x4001263C, 0x4000EB9C
EVB, EVQ, PATP, KITP = 0x400548CE, 0x40092116, 0x40A7887C, 0x40A78888
TSTRIDE, T_PROB, T_COND = 0x2D2, 0x2CF, 0x204
K_PRESS, LED_OF, KEY_OF = 0x400724A0, 0x4000608C, 0x4007240C
KB_SLOT, KB_KEY = 0x400FF9CC, 0x4001A0D2          # smp29: KeyboardView (Trigs ohne REC = chromatisch), Konsument der Firmware
UI_REC, UI_ALT, PAGE_OF = 0x4006B978, 0x4006BB18, 0x400124B8   # Grid-Bearbeitung (REC) / anderer UI-Modus; Seite (B(A()))
MIDI_HOOK, MIDI_CK = 0x400819FC, (8, 'ca9d9803dc411affd9bd13cfe13ef2e0dcced60afe6df95b74e166fd9b3ac8eb')   # smp34: Note-On-Verteiler
MIDI_LIVE, MIDI_NOTE0, EV_VEL = 0x4008171E, 36, 0x16   # Live-Note der Firmware (danach in a2); Note 36 = Trig 1; Ereignis +0x16 = Velocity
M_PROJ, M_TRKO, M_SENDS, M_CHAN = 0x4000F208, 0x4000CFCC, 0x40016E90, 0x40012E82   # MIDI-Ausgang der Spur (wie 0x40019e7a)
M_NON, M_NOFF = 0x4008273C, 0x400827A8                   # Note-On(Kanal, Note, Velocity) / Note-Off(Kanal, Note)
GLR_HOOK, GLR_CK = 0x40021E28, (12, 'fa82b8b113247dd39fea2fce90c15577b69f73bbb494c2b6a311a51f85947dc0')   # smp30: REC-Pruefung der Grid-LEDs
LED_ON_STATE, LED_OFF_STATE = 4, 1
TXT = {'pad': 'Pad Mode', 'on': 'On', 'off': 'Off'}


def text(cs, at):
    hp = C.HDR + C.P_PAD
    return f"""
    ; PADS: d0 = PAD-Bits des laufenden Patterns (0 ohne Pattern). Zerstoert a0
    PADS:   move.l  {C.CUR_PAT:#x},d0
            beq     pd9
            movea.l d0,a0
            mvz.b   {hp}(a0),d0
    pd9:    rts
    ; ACTV: d0 = aktive Spur, d1 = 1 wenn sie PAD ist. Zerstoert a0, a1
    ACTV:   jsr     {C.SEL_A:#x}
            move.l  d0,-(sp)
            jsr     {C.SEL_B:#x}
            move.l  d0,(sp)
            jsr     {C.SEL_C:#x}
            move.l  d0,(sp)
            jsr     PADS
            move.l  d0,d1
            move.l  (sp)+,d0
            btst    d0,d1
            sne     d1
            andi.l  #1,d1
            rts
    ; PTSK(Ansicht, Ereignis) (smp28, Slot des Cores TSVK, TRACK gehalten): RETRIG + Trig 1..6 = Spur PAD an / aus (Popup), jedes
    ; Ereignis dieser Tasten mit RETRIG verbraucht, RETRIG selbst auch (smp42); sonst d0 = 0 (control-mode, Firmware)
    PTSK:   move.l  8(sp),-(sp)
            jsr     {KEY_OF:#x}
            addq.l  #4,sp
            moveq   #{C.KEY_RETRIG},d1
            cmp.l   d0,d1
            bne     pt1
            moveq   #1,d0                    ; RETRIG mit TRACK: verbraucht (Firmware / track-filter sehen es nicht)
            rts
    pt1:    subi.l  #16,d0
            moveq   #5,d1
            cmp.l   d0,d1
            bcs     pt0
            move.l  d2,-(sp)
            move.l  d0,d2                    ; Spur 0..5
            pea     {C.KEY_RETRIG}.w
            jsr     {C.HELD:#x}
            addq.l  #4,sp
            tst.l   d0
            beq     pt8
            move.l  12(sp),-(sp)
            jsr     {K_PRESS:#x}
            addq.l  #4,sp
            tst.b   d0
            beq     pt7
            move.l  {C.CUR_PAT:#x},d0
            beq     pt7
            movea.l d0,a0
            mvz.b   {hp}(a0),d0
            bchg    d2,d0
            move.b  d0,{hp}(a0)
            lea     TNAMES,a0
            movea.l 0(a0,d2.l*4),a1
            btst    d2,d0
            beq     pk2
            move.l  #{at['on']:#x},d1
            bra     pk3
    pk2:    move.l  #{at['off']:#x},d1
    pk3:    lea     {at['pad']:#x},a0
            moveq   #{C.OV_TEXT},d0
            jsr     {cs['OVS']:#x}
    pt7:    move.l  (sp)+,d2
            moveq   #1,d0
            rts
    pt8:    move.l  (sp)+,d2
    pt0:    moveq   #0,d0
            rts
    ; PPR (gedrueckt ohne FUNC; a3 Step, d4 Spur-Objekt, a2 Ansicht, a5 = UIStates): PAD -> halten, spielen; sonst Firmware
    PPR:    jsr     ACTV
            tst.l   d1
            bne     pp1
            jsr     (a5)
            pea     1.w
            jmp     {PPR_BACK:#x}
    pp1:    move.l  d0,-(sp)                 ; aktive Spur
            jsr     {UIS:#x}
            pea     1.w
            move.l  a3,-(sp)
            move.l  d0,-(sp)
            jsr     {U_SET:#x}
            lea     12(sp),sp
            jsr     {UIS:#x}
            clr.l   -(sp)
            move.l  a3,-(sp)
            move.l  d0,-(sp)
            jsr     {U_ACT:#x}
            lea     12(sp),sp
            move.l  a3,-(sp)
            move.l  4(sp),-(sp)
            jsr     PLAY
            lea     12(sp),sp
            move.l  a2,-(sp)
            jsr     {REDRAW:#x}
            addq.l  #4,sp
            moveq   #1,d2
            jmp     {GRID_DONE:#x}
    ; PFN (FUNC gedrueckt; a3 Step, d4 Spur-Objekt, a2 Ansicht, a4 = UIStates): PAD -> Note-Trig anlegen / loeschen
    PFN:    jsr     ACTV
            tst.l   d1
            bne     pf1
            jsr     (a4)
            pea     1.w
            jmp     {PFN_BACK:#x}
    pf1:    move.l  a3,-(sp)
            move.l  d4,-(sp)
            jsr     {HAS_NOTE:#x}
            addq.l  #8,sp
            tst.b   d0
            beq     pf2
            clr.l   -(sp)
            move.l  a3,-(sp)
            move.l  d4,-(sp)
            jsr     {TRIG_DEL:#x}
            bra     pf3
    pf2:    pea     1.w
            move.l  a3,-(sp)
            move.l  d4,-(sp)
            jsr     {TRIG_ON:#x}
    pf3:    lea     12(sp),sp
            jsr     {UIS:#x}
            clr.l   -(sp)
            move.l  a3,-(sp)
            move.l  d0,-(sp)
            jsr     {U_ACT:#x}
            lea     12(sp),sp
            move.l  a2,-(sp)
            jsr     {REDRAW:#x}
            addq.l  #4,sp
            moveq   #1,d2
            jmp     {GRID_DONE:#x}
    ; SQS (Anfang des Ereignisbaus 0x400548ce: Spur, Pattern, Kit, Step, ..): PAD-Spur ohne MANUAL -> kein Ereignis
    SQS:    tst.b   MANUAL
            bne     sq9
            move.l  8(sp),d0
            beq     sq9
            movea.l d0,a0
            mvz.b   {hp}(a0),d0
            move.l  4(sp),d1
            btst    d1,d0
            beq     sq9
            moveq   #0,d0
            rts
    sq9:    lea     -60(sp),sp
            moveq   #1,d1
            jmp     {SQS_BACK:#x}
    ; PKB(Ansicht, Ereignis) (smp29, Vtable der KeyboardView 0x400ff9cc statt 0x4001a0d2; Pip: ohne REC spielten die Trigs der
    ; PAD-Spur chromatisch): Trig 1..16 ohne REC / Sondermodus auf einer PAD-Spur -> Druecken spielt den Step der Seite (leer =
    ; stumm; mit FUNC nichts, smp30), jedes Ereignis verbraucht; sonst der Konsument der Firmware
    PKB:    move.l  8(sp),-(sp)
            jsr     {KEY_OF:#x}
            addq.l  #4,sp
            subi.l  #16,d0
            moveq   #15,d1
            cmp.l   d0,d1
            bcs     kb9
            move.l  d2,-(sp)
            move.l  d3,-(sp)
            move.l  d0,d2                    ; Trig 0..15
            jsr     {UIS:#x}
            move.l  d0,-(sp)
            jsr     {UI_REC:#x}
            addq.l  #4,sp
            tst.b   d0
            bne     kb8
            jsr     {UIS:#x}
            move.l  d0,-(sp)
            jsr     {UI_ALT:#x}
            addq.l  #4,sp
            tst.b   d0
            bne     kb8
            jsr     ACTV
            tst.l   d1
            beq     kb8
            move.l  d0,d3                    ; aktive PAD-Spur
            pea     {C.KEY_FUNC}.w           ; smp30: FUNC + Trig auf der PAD-Spur verbraucht, nichts gespielt (Pip: spielte chromatisch)
            jsr     {C.HELD:#x}
            addq.l  #4,sp
            tst.l   d0
            bne     kb7
            move.l  16(sp),-(sp)
            jsr     {K_PRESS:#x}
            addq.l  #4,sp
            tst.b   d0
            beq     kb7
            jsr     {C.SEL_A:#x}
            move.l  d0,-(sp)
            jsr     {C.SEL_B:#x}
            move.l  d0,(sp)
            jsr     {PAGE_OF:#x}
            addq.l  #4,sp
            lsl.l   #4,d0
            add.l   d0,d2                    ; Step = Seite * 16 + Trig
            move.l  d2,-(sp)
            move.l  d3,-(sp)
            jsr     PLAY
            addq.l  #8,sp
    kb7:    move.l  (sp)+,d3
            move.l  (sp)+,d2
            moveq   #1,d0
            rts
    kb8:    move.l  (sp)+,d3
            move.l  (sp)+,d2
    kb9:    jmp     {KB_KEY:#x}
    ; GLR (smp30, Grid-LEDs 0x40021e28 statt 'jsr UIStates ; move.l d0,-(sp) ; jsr (a5) = 0x4006b978 ; addq'): d0 = REC oder
    ; aktive Spur PAD -> die Trig-LEDs zeigen die Steps wie mit REC (Pip: ohne REC waren sie aus)
    GLR:    jsr     {UIS:#x}
            move.l  d0,-(sp)
            jsr     {UI_REC:#x}
            addq.l  #4,sp
            tst.b   d0
            bne     gl9
            jsr     ACTV
            move.l  d1,d0
    gl9:    rts
    ; PLAY(Spur, Step): Trig-Taste einer PAD-Spur -> PLAYV ohne eigene Velocity, dann (smp34) MIDI-Note 36 + Trig der Seite
    ; (Note-On + Note-Off) auf dem Kanal der Spur, wenn die Firmware fuer die Spur MIDI sendet. C-Aufruf
    PLAY:   move.l  d2,-(sp)
            move.l  d3,-(sp)
            move.l  12(sp),d2                ; Spur
            move.l  16(sp),d3                ; Step
            pea     -1.w
            move.l  d3,-(sp)
            move.l  d2,-(sp)
            jsr     PLAYV
            lea     12(sp),sp
            tst.l   d0
            beq     pk9
            move.l  d0,-(sp)                 ; Velocity
            moveq   #15,d0
            and.l   d3,d0
            addi.l  #{MIDI_NOTE0},d0
            move.l  d0,-(sp)                 ; Note
            move.l  d2,-(sp)
            jsr     MOUT
            lea     12(sp),sp
    pk9:    move.l  (sp)+,d3
            move.l  (sp)+,d2
            rts
    ; MOUT(Spur, Note, Velocity): wie der Tastatur-Helfer der Firmware (0x40019e7a): sendet die Spur MIDI (0x40016e90(
    ; 0x4000cfcc(0x4000f208(A), Spur))), Kanal = 0x40012e82(B(A), Spur) -> 0x4008273c (Note-On), 0x400827a8 (Note-Off)
    MOUT:   move.l  d2,-(sp)
            jsr     {C.SEL_A:#x}
            move.l  d0,-(sp)
            jsr     {M_PROJ:#x}
            move.l  12(sp),(sp)
            move.l  d0,-(sp)
            jsr     {M_TRKO:#x}
            move.l  d0,(sp)
            jsr     {M_SENDS:#x}
            addq.l  #8,sp
            tst.b   d0
            beq     mo9
            jsr     {C.SEL_A:#x}
            move.l  d0,-(sp)
            jsr     {C.SEL_B:#x}
            move.l  12(sp),(sp)
            move.l  d0,-(sp)
            jsr     {M_CHAN:#x}
            addq.l  #8,sp
            move.l  d0,d2                    ; Kanal
            move.l  16(sp),-(sp)
            move.l  16(sp),-(sp)
            move.l  d2,-(sp)
            jsr     {M_NON:#x}
            addq.l  #4,sp                    ; (sp) = Note, 4(sp) = Velocity
            move.l  d2,-(sp)
            jsr     {M_NOFF:#x}
            lea     12(sp),sp
    mo9:    move.l  (sp)+,d2
            rts
    ; PLAYV(Spur, Step, Velocity): den Step der Spur jetzt spielen (p-locks, Note, Laenge, Sample-Lock), ohne Bedingung /
    ; Wahrscheinlichkeit; gemutet -> nichts. Velocity 1..127 ersetzt die des Steps (Ereignis +0x16, smp34), sonst die des Steps.
    ; -> d0 = gespielte Velocity (0 = nichts gespielt). C-Aufruf
    PLAYV:  lea     -24(sp),sp
            movem.l d2-d6/a2,(sp)
            moveq   #0,d6
            move.l  28(sp),d2                ; Spur
            move.l  32(sp),d3                ; Step
            moveq   #5,d0
            cmp.l   d2,d0
            bcs     py9
            moveq   #63,d0
            cmp.l   d3,d0
            bcs     py9
            jsr     {C.SEL_A:#x}
            move.l  d0,-(sp)
            jsr     {KIT_OF:#x}
            move.l  d2,(sp)
            move.l  d0,-(sp)
            jsr     {MUTED:#x}
            addq.l  #8,sp
            tst.b   d0
            bne     py9
            move.l  {PATP:#x},d0
            beq     py9
            movea.l d0,a2
            move.l  {KITP:#x},d4
            beq     py9
            move.l  #{TSTRIDE},d0
            muls.l  d2,d0
            adda.l  d0,a2                    ; Spur im Pattern (a2 + Pattern-Anfang: a2 - 0x2d2 n)
            mvz.b   {T_PROB}(a2),d5
            moveq   #100,d0
            move.b  d0,{T_PROB}(a2)
            lea     {T_COND}(a2),a0
            mvz.b   0(a0,d3.l),d0
            swap    d5
            move.b  d0,d5                    ; d5 = Wahrscheinlichkeit << 16 | Bedingung
            moveq   #-1,d0
            move.b  d0,0(a0,d3.l)
            dc.w    0x40c1                   ; move.w sr,d1
            move.l  d1,-(sp)
            dc.w    0x46fc,0x2700            ; move.w #$2700,sr
            moveq   #1,d0
            move.b  d0,MANUAL
            clr.l   -(sp)
            clr.l   -(sp)
            move.l  d3,-(sp)
            move.l  d4,-(sp)
            move.l  {PATP:#x},-(sp)
            move.l  d2,-(sp)
            jsr     {EVB:#x}
            lea     24(sp),sp
            tst.l   d0
            beq     py5
            movea.l d0,a0
            moveq   #2,d1
            move.l  d1,12(a0)
            move.l  40(sp),d1                ; Velocity des Aufrufs (Stapel: SR, 6 Register, Ruecksprung, Spur, Step)
            subq.l  #1,d1
            moveq   #126,d4
            cmp.l   d4,d1
            bhi     py3
            addq.l  #1,d1
            move.b  d1,{EV_VEL}(a0)
            clr.b   {EV_VEL + 1}(a0)
    py3:    mvz.b   {EV_VEL}(a0),d6
            move.l  d0,-(sp)
            jsr     {EVQ:#x}
            addq.l  #4,sp
    py5:    clr.b   MANUAL
            move.l  (sp)+,d1
            dc.w    0x46c1                   ; move.w d1,sr
            lea     {T_COND}(a2),a0
            move.b  d5,0(a0,d3.l)
            swap    d5
            move.b  d5,{T_PROB}(a2)
    py9:    move.l  d6,d0
            movem.l (sp),d2-d6/a2
            lea     24(sp),sp
            rts
    ; PADM (smp34, MIDI-Eingang, Note-On-Verteiler 0x40081918 bei 0x400819fc statt 'mvz.w d3,d3 ; clr.l d5 ; lea 0x4008171e,a2';
    ; d3 = Spuren, die die Note spielen sollen; Note 0x30(sp), Velocity 0x34(sp)): PAD-Spuren aus d3 nehmen (nie chromatisch);
    ; Note 36..51 -> Step der angezeigten Seite mit der Velocity der Note (PLAYV). Note-Off: nichts (one-shot)
    PADM:   mvz.w   d3,d3
            lea     -16(sp),sp
            movem.l d2/d4/d6-d7,(sp)
            jsr     PADS
            and.l   d3,d0
            move.l  d0,d7                    ; PAD-Spuren dieser Note
            beq     pm9
            eor.l   d7,d3
            move.l  0x40(sp),d4              ; Note
            subi.l  #{MIDI_NOTE0},d4
            moveq   #15,d0
            cmp.l   d0,d4
            bhi     pm9
            jsr     {C.SEL_A:#x}
            move.l  d0,-(sp)
            jsr     {C.SEL_B:#x}
            move.l  d0,(sp)
            jsr     {PAGE_OF:#x}
            addq.l  #4,sp
            lsl.l   #4,d0
            add.l   d0,d4                    ; Step
            moveq   #0,d2
    pm1:    btst    d2,d7
            beq     pm2
            move.l  0x44(sp),-(sp)           ; Velocity
            move.l  d4,-(sp)
            move.l  d2,-(sp)
            jsr     PLAYV
            lea     12(sp),sp
    pm2:    addq.l  #1,d2
            moveq   #6,d0
            cmp.l   d0,d2
            bne     pm1
    pm9:    movem.l (sp),d2/d4/d6-d7
            lea     16(sp),sp
            moveq   #0,d5
            lea     {MIDI_LIVE:#x},a2
            rts
    ; PLSF (LED-Filter des Cores, d0 = LED, d1 = Zustand -> d1): TRACK + RETRIG gehalten -> Trig 1..6 = PAD-Spuren (blinkt / 1)
    PLSF:   move.l  d2,-(sp)
            move.l  d3,-(sp)
            move.l  d0,d3
            move.l  d1,-(sp)
            pea     {C.KEY_TRACK}.w
            jsr     {C.HELD:#x}
            tst.l   d0
            beq     pl7
            move.l  #{C.KEY_RETRIG},(sp)
            jsr     {C.HELD:#x}
    pl7:    addq.l  #4,sp
            tst.l   d0
            beq     pl8
            moveq   #0,d2
    pl1:    move.l  d2,-(sp)
            jsr     {LED_OF:#x}
            addq.l  #4,sp
            cmp.l   d3,d0
            beq     pl2
            addq.l  #1,d2
            moveq   #6,d0
            cmp.l   d2,d0
            bne     pl1
            bra     pl8
    pl2:    jsr     PADS
            btst    d2,d0
            beq     pl3{C.blink_state('d0', 'pb')}
            bra     pl4
    pl3:    moveq   #{LED_OFF_STATE},d0
    pl4:    move.l  d0,(sp)
    pl8:    move.l  (sp)+,d1
            move.l  (sp)+,d3
            move.l  (sp)+,d2
            rts
"""


def build_pay():
    cs = core.sym()
    def data(org):
        b = bytearray(); at = {}
        at['MANUAL'] = org + len(b); b += bytes(4)
        at['TNAMES'] = org + len(b); b += bytes(24)
        for k, t in list(TXT.items()) + [('t%d' % i, 'Track %d' % (i + 1)) for i in range(6)]:
            at[k] = org + len(b); b += t.encode() + b'\0'
        struct.pack_into('>6I', b, at['TNAMES'] - org, *[at['t%d' % i] for i in range(6)])
        return bytes(b), at
    lab = collections.defaultdict(int); at = data(ORG + 0x400)[1]
    for _ in range(3):
        a = A(ORG); asm(a, text(cs, at), lab)
        dorg = ORG + ((len(a.b) + 3) & ~3)
        blob, at = data(dorg)
        lab = collections.defaultdict(int, {**a.lab, **at})
    code = adone(a, dict(lab))
    out = code + bytes(dorg - ORG - len(code)) + blob
    assert len(out) <= ROOM, len(out)
    return out, dict(lab)


def tweak(img):
    base = apply(img, core.tweak(img))
    pay, lab = build_pay()
    W = Writes(base)
    W.put(C.PIMG(ORG), pay)
    W.hook(PPR_HOOK, PPR_CK, jmp(lab['PPR']))
    W.hook(PFN_HOOK, PFN_CK, jmp(lab['PFN']))
    W.hook(SQS_HOOK, SQS_CK, jmp(lab['SQS']))
    W.hook(KB_SLOT, struct.pack('>I', KB_KEY), struct.pack('>I', lab['PKB']))   # smp29: PAD auch ohne REC
    W.hook(GLR_HOOK, GLR_CK, jsr(lab['GLR']) + bytes.fromhex('4e71') * 3)      # smp30: Trig-LEDs der PAD-Spur ohne REC
    W.hook(MIDI_HOOK, MIDI_CK, jsr(lab['PADM']) + bytes.fromhex('4e71'))       # smp34: MIDI-Noten 36..51 auf PAD-Spuren
    core.lslot_write(W, 'pad-mode', lab['PLSF'])
    core.tkslot_write(W, 'pad-mode', lab['PTSK'])                  # smp28 / smp42: TRACK + RETRIG + Trig 1..6
    return patch('pad-mode', 21, 'Pad Mode',
                 ["Hold TRACK + RETRIG: trigs 1..6 show the PAD tracks (blinking); TRACK + RETRIG + trig 1..6 turns a track into a PAD track (per pattern).",
                  "The sequencer does not play PAD tracks. On an active PAD track the trig keys play their steps (with p-locks,",
                  "with or without REC; no chromatic keyboard on PAD tracks, keys without a trig and FUNC + trig stay silent;",
                  "the trig LEDs show the steps of a PAD track also without REC)",
                  "note, length, sample lock) instead of toggling them; hold + knob edits the step, FUNC + trig adds / clears it.",
                  "MIDI: notes 36..51 on a PAD track's channel play trigs 1..16 of the page shown, with the note's velocity (note-off ignored;",
                  "other notes do nothing on PAD tracks); trig keys of a PAD track send notes 36..51 on its channel.",
                  "Muted PAD tracks stay silent. Playing a step: idea from the 'trig-preview' tweak by drumkilla (MIT).",
                  "Erzeugt von v2/g2_pad.py."], W, requires=['core'],
                 hooks=[f"{x:#x}" for x in (PPR_HOOK, PFN_HOOK, SQS_HOOK, KB_SLOT, GLR_HOOK, MIDI_HOOK)],
                 symbols={k: f"{v:#x}" for k, v in lab.items() if k[0].isupper()},
                 params={"header_byte": C.P_PAD, "track_stride": TSTRIDE, "texts": TXT})


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    print(len(build_pay()[0]))
