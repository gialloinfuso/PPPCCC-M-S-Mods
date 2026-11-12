#!/usr/bin/env python3
"""Mod 'core' (v2): gemeinsame Dienste fuer die modularen Mods. Allein installiert aendert sich nur SETTINGS (langes Halten
speichert erst beim Loslassen ohne Drehung).

Dienste (Adressen in symbols):
  CED   Encoder-Verteiler am Haken 0x400081b8: ruft nacheinander die Handler in SLOTS (8 Zeiger, 0 = frei).
        Handler(a2 = EncoderEvent: +4 Encoder, +8 Drehung als Byte), C-ABI (d2-d7/a2-a6 bleiben), Rueckgabe d0:
        0 = nicht meins, 1 = Ereignis ganz verwerfen (Firmware sieht nichts), 2 = mit Drehung 0 weitergeben
        (die Firmware zeigt dann ihr Parameter-Popup, z. B. nach dem Umschalten eines Effekts).
        Jede Mod schreibt ihren Handler in ihren eigenen Platz (common.SLOT): keine Mod haengt von einer anderen ab.
  GEST  (d0 = Tastencode) consume(Taste) + aufgeschobenes Speichern loeschen: nach einer Geste oeffnet das Loslassen
        des Modifiers kein Menue und speichert nicht.
  SLOW  (d4 Drehung, d5 Ziel-Kennung) -> d0 = 1 eine Stufe / 0 noch nicht (4 Rastungen, Reset nach 0.4 s Pause,
        Richtungswechsel oder anderem Ziel).
  MODESW (a0 = Byte, d1 = Maximum, a1 = Rueckruf oder 0; a2 = Ereignis): Effektwahl mit SLOW, Wert 0..Max
        (ungueltig -> 0), schreibt das Byte, ruft den Rueckruf (Namen), d0 = 2.
  OVS   (d0 Art, d1 Wert, a0 Zeile 1 bzw. Zeichenfunktion, a1 Zeile 2 oder 0): Popup 1.5 s im Stil der Firmware.
        Art 0 = weg, 1 = Zahl (d1), 2 = Text (d1 = Zeiger), 3 = eigene Zeichenfunktion a0(a2 = Bitmap, a3 = VARS),
        die nicht jedes Bild neu zeichnet (Lastanzeige). Texte duerfen kein '%' enthalten.
  OVT   Render-Haken 0x40076c88 (Ende des ViewController-Zeichnens): zeichnet das Popup ueber allem.
  SETTINGS-Taste im Hauptbildschirm (Haken 0x4001c54c, 0x4001c564, 0x4001c5bc): langes Halten merkt nur PEND,
        Loslassen ohne Drehung speichert dann statt das Menue zu oeffnen - aber nur, wenn seit dem Druecken keine andere
        Taste gedrueckt wurde (01.11.2026, Pip: 'Pattern-Save-Menue' nach SETTINGS als Modifier mit einer Taste, z. B.
        + MACHINES fuer den Browser; 0x40148cd8 = zuletzt gedrueckte Taste, -1 nach dem Verbrauchen beim langen Halten).
  Pattern-Speicher: Haken 0x4005b4b0 (Pattern laden) kopiert zusaetzlich die Kopf-Bytes 40..63; fehlt die Kennung
        (Bytes 60..63 'PCv2', z. B. Pattern aus der Original-Firmware), werden 52..59 geloescht und die Kennung gesetzt
        (40..51 = Humanize bleiben wie in v1). 0x4006155e (neues Pattern) loescht 40..59 und setzt die Kennung.
        Belegung in common.py (P_*).
  KCALL / KSLOTS: SETTINGS im Hauptbildschirm ruft die Tasten-Slots beim ersten Druecken (d1 = 0) und beim Loslassen
        ohne FUNC und ohne langes Halten (d1 = 1; a0 = Ereignis). Gibt ein Handler beim Loslassen d0 != 0 zurueck, oeffnet
        sich das Menue nicht. Slots: control-mode 0.
  CTRL_MODE 0x404e9b5d (Einstellungsblock): == 0x5a CONTROL ALL absolut, sonst relativ (= Firmware); geschrieben von
        control-mode, gelesen von allen, die mehrere Werte auf einmal aendern (control-mode, groove).
  SND / SSLOTS (seit Patch 13/14): Sound laden / speichern (Haken 0x4005aecc, 0x4005afa0, 0x4005b054, Prolog nachgespielt)
        ruft die Sound-Slots (a0 Satz, a1 Sound, d1 = 0 Laden / 1 Speichern; duerfen d0/d1/a0/a1 aendern). Der Core selbst
        legt LFO- und Velocity-Ziel k 23..32 in Satz +82 / +83 ab (die Firmware kann sie nicht speichern) und loescht beim
        Laden k0 (die Firmware legt dort Satz-Platz 18 = +64 ab).
  p-locks k 23..32: Tabelle k -> Index (PTAB, 0x4005b998 / 0x4005baca; Eintraege 0..22 aus dem Image kopiert, dann 24..33)
        und Index -> k (Haken 0x4005aa34: 24..33 -> 23..32). Nach Modded-Cycles notes/47 (MIT); eigener Code.
Speicher: Masken 0x4018f4b4 (CED, SLOTS, Tasten, GEST, HL, HI), 0x4018dba8 (SLOW, MODESW), 0x4015c044 (OVS, OVT, NPD),
  0x401835b8 (SND), 0x40184808 (PTAB, CONV, SSLOTS).
RAM: VARS 0x4a33c380 (40 B), ACC 0x4a33c3c0 (12 B).
Aufruf: g2_core.py [out.json]
"""
import struct, sys
from common import *                 # noqa: F401,F403
import common as C
from cfasm import asm, done as adone
import g2_dtab as DT

M_C1, M_C2, M_C3, M_C4, M_C5 = 0x4018F4B4, 0x4018DBA8, 0x4015C044, 0x401835B8, 0x40184808
M_C6, M_C7, M_C8, M_C9, M_CA, M_CB = 0x40167900, 0x40167AA8, 0x40168440, 0x401688B4, 0x40160D9C, 0x40162AB4   # smp12
M_BOOT = 0x40163A60                   # smp14: Start-Kopie der Nutzlast (vorher in reverb-fx), 27x27 (108 B)
SIZE = {M_C1: 376, M_C2: 376, M_C3: 720, M_C4: 272, M_C5: 192, M_C6: 108, M_C7: 108, M_C8: 108, M_C9: 108, M_CA: 104, M_CB: 104,
        M_BOOT: 108}
BOOT_HOOK, BOOT_CK, BOOT_BACK = 0x400004B2, (8, '02baba67a7ec7d7bdf683fa37f268620e3a694853b398205df521c64128da818'), 0x400004BA
# smp12 (Pip 03.11.2026):
#  * T1..T6 allein waehlen die Spur nicht mehr aus (nur TRACK + T1..T6); im Pattern-Auswahlmodus wie die Firmware.
#    Pad-Handler 0x4001d180: jsr 0x40023c90 (Spur waehlen, einziger Aufrufer) bei 0x4001d36a -> TSEL.
#  * Amp Attack auf dem DECAY-Knopf mit FUNC (alle Maschinen): Deskriptor 6 (k 23, wie Model-TG von TinyGregAudio, MIT;
#    eigener Code), p-locks / LFO- / Velocity-Ziel ueber die k-23..32-Dienste des Cores, Satz +86 (Sound-Slot 3).
#    Knopf-Suche 0x4001e814: Haken jetzt im Core (LKW / LKP), lfo-amount meldet sich ueber LKSLOT an.
#    Rampe hinter dem VCA der Firmware (0x400a9430, alle Maschinen und Sampl): Einsprung -> ATKV, eigene Rueckkehr ATKP.
#    Parameter aus dem Objekt der Klangerzeugung (Aufruf 0x4005981e jsr 0x400a7d4a -> RPH merkt es sich).
TSEL_AT, TSEL_FN = 0x4001D36A, 0x40023C90
LOOKUP, LOOKUP_CK, LOOKUP_CONT = 0x4001E814, (6, 'b806f010f13616a431043cb7fbc959a028b2fda3c89c9b829d70d30c346b9224'), 0x4001E81A
RP_AT, RENDERFN = 0x4005981E, 0x400A7D4A
VCA_FN, VCA_CK, VCA_CONT = 0x400A9430, (8, 'efa23c0a55aebcd8ffb29c8ba97d3970d8e88ed9c16272d7b5ea0b4e8309ecf5'), 0x400A9438
VOICE0, VSTRIDE = 0x42308828, 0x31C
# smp22: FUNC + Knopf ohne Grobschritte im Parameter-Knopf-Handler 0x4001f4f0. Firmware: mit FUNC gehalten (0x4001f81a,
#   HELD(1)) und Knopf <= 13 setzt sie den Zustand des Knopfs auf 2 (0x4006fb3a) und uebernimmt danach keine Drehung
#   (0x4006fb68), bis er wieder frei ist -> der Wert springt in grossen Schritten. Hier: FUNC zaehlt dort nicht (jsr HELD ->
#   moveq #0,d0); die FUNC-Belegungen (LKX: Attack, Monom Glide / Noise) bewegen wie ohne FUNC. (smp19 hatte faelschlich das
#   Flag des Ereignisses +0x14 = Taste 32 abgeschaltet; zurueckgenommen.)
FUNC_FLAT = (   # Stelle, (Laenge, SHA-256 Original), neu
    (0x4001F81E, (2, '77fd7852da28f8a5620e8aac5317d6570f489421bf13046635a8ad1c44872151'), bytes.fromhex('7000')),  # jsr (a4) -> moveq #0,d0
)
D_ATK, K_ATK, ENC_DECAY = 6, 23, 3
REC, FMT_INT = 0x40A71754, 0x400456C8
S_AMPGRP = 0x40129882                # Gruppenname 'Amp' (wie Amp Decay)
UIGET, UI_PMODE = 0x400CF9A8, 0x185
# Sound laden / speichern (v2, v1): Prolog lea -12(sp),sp ; movem.l a2-a4,(sp) (8 B) -> jmp; Fortsetzung + 8
PRO_CK = (8, 'b68bc7d23c230258939a138565f6ce0857c8519234b2e5f45b2120f58d4b44db')
LD_HOOK, SV2_HOOK, SV1_HOOK = 0x4005AECC, 0x4005AFA0, 0x4005B054
CONV_HOOK, CONV_CK = 0x4005AA34, (6, '600476b79e6941095c26cff35f0fee8db577d2caf26d0f88671af6b1598ffa03')
CONV_TAB, CONV_RET, CONV_ZERO = 0x4005AA46, 0x4005AA50, 0x4005AA3A
PTAB_REFS, PTAB_ORIG = (0x4005B998, 0x4005BACA), 0x4010EE4C
DUR = 202752000                      # 1.5 s in Zeitgeber-Ticks
OMAGIC = 0x4F564C32                  # 'OVL2'
VC_DIRTY = 0x20
RENDER_HOOK, RENDER_ORIG = 0x40076C88, (6, '447f49a6d517f875d837b9ccbe69eee0914d078600a16cd5cc6d626f3f27285d')
K_BIT5, K_SAVE, K_DONE = 0x40072444, 0x40039570, 0x4001C2A8
K_HOOK_A, K_ORIG_A = 0x4001C54C, (8, '5938f6ac8492a4497ca28a80e4fdd6a460c070f0f16a3e4a6e37bea24f79071f')
K_HOOK_L, K_ORIG_L = 0x4001C564, (6, 'c1af6619aaea3604f5c25cd0c68164acc4fec83581f35649e516c7c862ab487c')
# zuletzt gedrueckte Taste (Matrix-Index, Tastenabfrage 0x4007fbde); das Verbrauchen beim langen Halten (0x400723e0 ->
# 0x4007fbd4) setzt sie auf -1, jede danach gedrueckte Taste ueberschreibt sie
KEY_LAST = 0x40148CD8
K_HOOK_R, K_ORIG_R = 0x4001C5BC, (6, 'b210caad8dca87c456a21e7dbbc4a4450dad3ae26f6e9fe4143fb6c15cc9c202')
L_HOOK, L_ORIG = 0x4005B4B0, (6, 'ee28f31fe8e35208eaefb6360d0d28dc613f50670d545cf89908a49f66d0d7d2')
I_HOOK, I_ORIG = 0x4006155E, (6, 'f0f7ff9828d5fef4204e8fc3ba19a4718d910f35a87bb54b8cc1d3d83f638d74')
SLOW_N, SLOW_T = 4, 54067200
FILL_F, FRAME_F, TXT_F = 0x40070DEA, 0x40070F6E, 0x40071A04
F_NAME, F_VAL = 0x40EA14D4, 0x40EA14E4
FMT_D, FMT_S = 0x4012A9EA, 0x40124B58
V = C.VARS
NCOPY = C.P_LAST - C.P_FIRST + 1


def build_c1(kcall):
    text = f'''
    ; ---------------- CED: Encoder-Verteiler (jsr am Haken; a2 = Ereignis)
    CED:    move.l  a3,-(sp)
            move.l  d2,-(sp)
            lea     SLOTS,a3
            moveq   #{C.NSLOT - 1},d2
    lp:     move.l  (a3)+,d0
            beq     nx
            movea.l d0,a0
            jsr     (a0)
            tst.l   d0
            bne     hit
    nx:     subq.l  #1,d2
            bpl     lp
            move.l  (sp)+,d2
            movea.l (sp)+,a3
            movea.l (sp)+,a0
            orig    {C.H_HOOK:#x},6          ; verschobene Originalbefehle (aus dem Image) ; zurueck
            jmp     (a0)
    hit:    move.l  (sp)+,d2
            movea.l (sp)+,a3
            subq.l  #1,d0
            beq     skip                     ; 1 -> verwerfen
            movea.l (sp)+,a0                 ; 2 -> Drehung 0 weitergeben
            moveq   #0,d1
            move.l  d1,-(sp)
            jmp     (a0)
    skip:   lea     12(sp),sp
            jmp     {C.ENC_SKIP:#x}
    ; ---------------- GEST(d0 = Taste)
    GEST:   move.l  d0,-(sp)
            jsr     {C.CONSUME:#x}
            addq.l  #4,sp
            clr.l   {V + C.V_PEND:#x}
            rts
    ; ---------------- SETTINGS im Hauptbildschirm (wie v1 gen_overlay_113.build_keys)
    C13A:   movea.l d3,a0                    ; statt move.l d3,-(a7) ; jsr BIT5 (8 B: jsr C13A ; nop)
            move.l  16(a0),d0
            moveq   #9,d1
            and.l   d1,d0
            subq.l  #1,d0
            bne     k1                       ; erstes Druecken: (Flags & 9) == 1
            clr.l   {V + C.V_PEND:#x}
            moveq   #0,d1
            jsr     {kcall:#x}               ; a0 = Ereignis; Tasten-Slots: Druecken
    k1:     movea.l (sp)+,a0
            orig    {K_HOOK_A:#x},2          ; verschobener Originalbefehl, dann BIT5(ev)
            move.l  a0,-(sp)
            jmp     {K_BIT5:#x}
    LS:     moveq   #1,d0                    ; statt jsr SAVE beim langen Halten
            move.l  d0,{V + C.V_PEND:#x}
            rts
    C13R:   tst.l   {V + C.V_PEND:#x}        ; statt pea $9c(a2) ; move.l a6,d2 (Loslassen ohne FUNC -> Menue)
            beq     kn
            clr.l   {V + C.V_PEND:#x}
            moveq   #-1,d0
            cmp.l   {KEY_LAST:#x},d0
            bne     kh                       ; nach dem langen Halten eine andere Taste: nur Modifier
            pea     32.w
            orig    {K_HOOK_L:#x},6          ; verschobener Aufruf (Speichern)
            addq.l  #8,sp
            jmp     {K_DONE:#x}
    kn:     movea.l d3,a0                    ; Loslassen ohne FUNC, ohne langes Halten: Tasten-Slots, sonst Menue
            moveq   #1,d1
            jsr     {kcall:#x}
            tst.l   d0
            bne     kh
            movea.l (sp)+,a0
            orig    {K_HOOK_R:#x},6          ; verschobene Originalbefehle
            jmp     (a0)
    kh:     addq.l  #4,sp                    ; behandelt: kein Menue
            jmp     {K_DONE:#x}
    ; ---------------- HL: Pattern laden (a3 Datei-Kopf, a2 B-Kopf; d0 bleibt): zusaetzlich Kopf-Bytes 40..63.
    ;   Ohne Kennung (60..63, z. B. Pattern aus der Original-Firmware): 52..59 = 0, Kennung setzen (40..51 bleiben, wie v1).
    HL:     orig    {L_HOOK:#x},6            ; verschobener Originalbefehl
            lea     {C.P_FIRST}(a3),a0
            lea     {C.P_FIRST}(a2),a1
            moveq   #{NCOPY - 1},d1
    hl:     move.b  (a0)+,(a1)+
            subq.l  #1,d1
            bpl     hl
            mvz.w   -4(a1),d1
            cmpi.l  #{C.SIG[0]:#x},d1
            bne     fx
            mvz.w   -2(a1),d1
            cmpi.l  #{C.SIG[1]:#x},d1
            beq     hok
    fx:     lea     {C.P_RFX}(a2),a0
            moveq   #{C.P_SIG - C.P_RFX - 1},d1
    fl:     clr.b   (a0)+
            subq.l  #1,d1
            bpl     fl
            move.w  #{C.SIG[0]},(a0)+
            move.w  #{C.SIG[1]},(a0)
    hok:    rts
    ; ---------------- HI: neues Pattern (a0 Kopf): Kopf-Bytes 40..59 = 0, Kennung ; d0.b = 0 wie im Original
    HI:     orig    {I_HOOK:#x},6            ; verschobene Originalbefehle
            lea     {C.P_FIRST}(a0),a1
            moveq   #{C.P_SIG - C.P_FIRST - 1},d1
    hi:     clr.b   (a1)+
            subq.l  #1,d1
            bpl     hi
            move.w  #{C.SIG[0]},(a1)+
            move.w  #{C.SIG[1]},(a1)
            rts
'''
    def tail(end):
        pad = (-end) % 4
        return bytes(pad + 4 * C.NSLOT), {'SLOTS': end + pad}
    return asm2(M_C1, text, tail)


def build_c2():
    text = f'''
    ; ---------------- SLOW (d4 Drehung, d5 Ziel) -> d0 ; veraendert d1, a0  (wie v1 gen_overlay_113.build_slow)
    SLOW:   lea     {C.ACC:#x},a0            ; +0 Zaehler, +4 Ziel, +8 Zeit
            move.l  {C.TIMER:#x},d1
            move.l  d1,d0
            sub.l   8(a0),d0
            move.l  d1,8(a0)
            cmpi.l  #{SLOW_T:#x},d0
            bcs     st1
            clr.l   (a0)                     ; Pause: neu zaehlen
    st1:    cmp.l   4(a0),d5
            beq     st2
            clr.l   (a0)                     ; anderes Ziel
            move.l  d5,4(a0)
    st2:    move.l  (a0),d0
            move.l  d0,d1
            eor.l   d4,d1
            bpl     st3
            moveq   #0,d0                    ; Richtungswechsel
    st3:    add.l   d4,d0
            move.l  d0,(a0)
            move.l  d0,d1
            bpl     st4
            neg.l   d1
    st4:    cmpi.l  #{SLOW_N},d1
            bcs     st5
            clr.l   (a0)
            moveq   #1,d0                    ; ein Schritt
            rts
    st5:    moveq   #0,d0
            rts
    ; ---------------- MODESW (a0 Byte, d1 Max, a1 Rueckruf; a2 Ereignis) -> d0 = 2
    MODESW: lea     -20(sp),sp
            movem.l d3-d5/a3-a4,(sp)
            movea.l a0,a3
            move.l  d1,d3
            movea.l a1,a4
            mvs.b   8(a2),d4                 ; Drehung
            beq     mo
            move.l  a3,d5
            bsr     SLOW
            tst.l   d0
            beq     mo
            mvz.b   (a3),d0
            cmp.l   d3,d0
            bls     v
            moveq   #0,d0                    ; ungueltig -> 0
    v:      move.l  d0,d1
            tst.l   d4
            ble     dec
            addq.l  #1,d1
            bra     cl
    dec:    subq.l  #1,d1
    cl:     tst.l   d1
            bpl     c1
            moveq   #0,d1
    c1:     cmp.l   d3,d1
            ble     c2
            move.l  d3,d1
    c2:     mvz.b   (a3),d0
            cmp.l   d1,d0                    ; Rohwert: Muell wird ersetzt
            beq     mo
            move.b  d1,(a3)
            move.l  a4,d0
            beq     mo
            jsr     (a4)
    mo:     moveq   #2,d0
            movem.l (sp),d3-d5/a3-a4
            lea     20(sp),sp
            rts
    ; ---------------- KCALL (d1 = 0 Druecken / 1 Loslassen, a0 = Tasten-Ereignis) -> d0: erster Rueckgabewert != 0, sonst 0
    ;   Tasten-Slots (KSLOTS) fuer SETTINGS im Hauptbildschirm; Handler: C-ABI, a0 = Ereignis, d1 = Art.
    KCALL:  lea     -16(sp),sp
            movem.l d2-d3/a2-a3,(sp)
            move.l  d1,d3
            movea.l a0,a2
            lea     KSLOTS,a3
            moveq   #{C.NKSLOT - 1},d2
    kl:     move.l  (a3)+,d0
            beq     kx
            movea.l d0,a1
            movea.l a2,a0
            move.l  d3,d1
            jsr     (a1)
            tst.l   d0
            bne     ko
    kx:     subq.l  #1,d2
            bpl     kl
            moveq   #0,d0
    ko:     movem.l (sp),d2-d3/a2-a3
            lea     16(sp),sp
            rts
'''
    def tail(end):
        pad = (-end) % 4
        return bytes(pad + 4 * C.NKSLOT), {'KSLOTS': end + pad}
    return asm2(M_C2, text, tail)


def build_c3():
    def rect(fn, x0, y0, x1, y1, col):
        return f'''
            moveq   #{x0},d0
            moveq   #{y0},d1
            moveq   #{x1},d2
            moveq   #{y1},d3
            moveq   #{col},d4
            lea     {fn:#x},a1
            bsr     RCT'''
    text = f'''
    ; ---------------- OVS (d0 Art, d1 Wert, a0 Zeile 1 / Funktion, a1 Zeile 2)
    OVS:    move.l  a2,-(sp)
            lea     {V:#x},a2
            move.l  d0,{C.V_KIND}(a2)
            move.l  d1,{C.V_VAL}(a2)
            move.l  a0,{C.V_L1}(a2)
            move.l  a1,{C.V_L2}(a2)
            move.l  {C.TIMER:#x},d0
            addi.l  #{DUR:#x},d0
            move.l  d0,{C.V_DL}(a2)          ; Ablaufzeit
            move.l  {C.V_MAGIC}(a2),d0
            cmpi.l  #{OMAGIC:#x},d0
            bne     ovr
            move.l  {C.V_VC}(a2),d0
            beq     ovr
            movea.l d0,a0
            moveq   #1,d0
            move.b  d0,{VC_DIRTY}(a0)        ; Neuzeichnen anfordern
    ovr:    movea.l (sp)+,a2
            rts
    ; ---------------- OVT: Ende des ViewController-Zeichnens (a2 VC, d3 Bitmap); d0 = 0 wie im Original
    OVT:    lea     {V:#x},a0
            move.l  {C.V_MAGIC}(a0),d0
            cmpi.l  #{OMAGIC:#x},d0
            beq     m1
            move.l  #{OMAGIC:#x},d0          ; RAM nach dem Start: Zustand leeren
            move.l  d0,{C.V_MAGIC}(a0)
            clr.l   {C.V_KIND}(a0)
            clr.l   {C.V_PEND}(a0)
            clr.l   {C.V_MPEND}(a0)
    m1:     move.l  a2,{C.V_VC}(a0)
            moveq   #0,d0
            orig    {RENDER_HOOK + 2:#x},4   ; verschobener Originalbefehl (Neuzeichnen erledigt)
            tst.l   {C.V_KIND}(a0)
            beq     out
            move.l  {C.TIMER:#x},d0
            sub.l   {C.V_DL}(a0),d0
            bmi     live
            clr.l   {C.V_KIND}(a0)           ; abgelaufen
            bra     out
    live:   moveq   #3,d0
            cmp.l   {C.V_KIND}(a0),d0
            beq     nk                       ; Art 3: Neuzeichnen kommt vom Aufrufer
            moveq   #1,d0
            move.b  d0,{VC_DIRTY}(a2)
    nk:     lea     -32(sp),sp
            movem.l d2-d7/a2-a3,(sp)
            movea.l d3,a2
            lea     {V:#x},a3
            moveq   #3,d0
            cmp.l   {C.V_KIND}(a3),d0
            bne     np
            movea.l {C.V_L1}(a3),a0          ; eigene Zeichenfunktion
            jsr     (a0)
            bra     done
    np:     bsr     NPD
    done:   movem.l (sp),d2-d7/a2-a3
            lea     32(sp),sp
    out:    moveq   #0,d0
            rts
    ; ---------------- NPD: Popup wie ParameterPageView::draw (a2 Bitmap, a3 VARS)
    NPD:{rect(FILL_F, 0, 0, 63, 63, 1)}{rect(FRAME_F, 0, 0, 63, 63, 0)}{rect(FILL_F, 64, 0, 127, 63, 0)}
            movea.l {C.V_L1}(a3),a0
            moveq   #47,d1
            bsr     TXN                      ; Zeile 1
            move.l  {C.V_L2}(a3),d0
            beq     vv
            movea.l d0,a0
            moveq   #34,d1
            bsr     TXN                      ; Zeile 2
    vv:     move.l  {C.V_VAL}(a3),-(sp)
            moveq   #2,d0
            cmp.l   {C.V_KIND}(a3),d0
            bne     vn
            pea     {FMT_S:#x}               ; Art 2: Text
            lea     {F_NAME:#x},a1
            bra     vt
    vn:     pea     {FMT_D:#x}               ; Zahl
            lea     {F_VAL:#x},a1
    vt:     pea     2.w
            pea     34.w
            pea     96.w
            move.l  a1,-(sp)
            move.l  a2,-(sp)
            jsr     {TXT_F:#x}
            lea     28(sp),sp{rect(FILL_F, 0, 0, 63, 63, -1)}
            rts
    TXN:    move.l  a0,-(sp)                 ; a0 Text, d1 y: Namen-Schrift, x = 32 mittig
            pea     2.w
            move.l  d1,-(sp)
            pea     32.w
            pea     {F_NAME:#x}
            move.l  a2,-(sp)
            jsr     {TXT_F:#x}
            lea     24(sp),sp
            rts
    RCT:    extb.l  d4                       ; (a1)(bmp, d0, d1, d2, d3, d4 als Byte mit Vorzeichen)
            move.l  d4,-(sp)
            move.l  d3,-(sp)
            move.l  d2,-(sp)
            move.l  d1,-(sp)
            move.l  d0,-(sp)
            move.l  a2,-(sp)
            jsr     (a1)
            lea     24(sp),sp
            rts
'''
    return asm2(M_C3, text)


def build_c5():
    """PTAB (k 0..32 -> p-lock-Index), CONV, SSLOTS"""
    code = bytearray(orig_span(M_C5, PTAB_ORIG, 23 * 4))
    code += struct.pack('>10I', *range(24, 34))
    cv, lab = asm2(M_C5 + len(code), f'''
    CONV:   cmpi.l  #23,d0                   ; Index d0 -> k (Tracks 0..5)
            bhi     cv
            jmp     {CONV_TAB:#x}
    cv:     cmpi.l  #33,d0
            bhi     cz
            subq.l  #1,d0
            jmp     {CONV_RET:#x}
    cz:     jmp     {CONV_ZERO:#x}
''')
    code += cv
    ss = M_C5 + len(code); code += bytes(4 * C.NSSLOT)
    return bytes(code), dict(lab, PTAB=M_C5, SSLOTS=ss)


def build_c4(ss):
    hooks = ''.join(f'''
    {name}:  move.l  8(sp),-(sp)
            move.l  8(sp),-(sp)
            pea     {post}
            orig    {hook:#x},8              ; verschobener Prolog der Firmware
            jmp     {hook + 8:#x}''' for name, hook, post in (('LD', LD_HOOK, 'LDP'), ('SV2', SV2_HOOK, 'SVP'), ('SV1', SV1_HOOK, 'SVP')))
    text = hooks + f'''
    LDP:    movea.l (sp),a1                  ; nach dem Laden: 0(sp) Sound, 4(sp) Satz
            movea.l 4(sp),a0
            move.l  d0,(sp)
            clr.w   20(a1)                   ; k0 = 0
            mvz.b   82(a0),d0
            bsr     DST
            beq     l1
            lsl.l   #8,d0
            move.w  d0,28(a1)                ; LFO-Ziel (Wort +28 = k << 8)
    l1:     mvz.b   83(a0),d0
            bsr     DST
            beq     l2
            move.l  d0,88(a1)                ; Velocity-Ziel (+88)
    l2:     moveq   #0,d1
            bra     CALLS
    SVP:    movea.l (sp),a0                  ; nach dem Speichern: 0(sp) Satz, 4(sp) Sound
            movea.l 4(sp),a1
            move.l  d0,(sp)
            mvz.b   28(a1),d0
            bsr     DST
            move.b  d0,82(a0)
            move.l  88(a1),d0
            bsr     DST
            move.b  d0,83(a0)
            moveq   #1,d1
    CALLS:  lea     -20(sp),sp               ; a0 Satz, a1 Sound, d1 Art: alle Sound-Slots
            movem.l d2-d3/a2-a4,(sp)
            move.l  d1,d2
            movea.l a0,a2
            movea.l a1,a3
            moveq   #0,d3
    cl:     lea     {ss:#x},a0
            move.l  0(a0,d3.l*4),d0
            beq     nx
            movea.l d0,a4
            movea.l a2,a0
            movea.l a3,a1
            move.l  d2,d1
            jsr     (a4)
    nx:     addq.l  #1,d3
            moveq   #{C.NSSLOT},d0
            cmp.l   d3,d0
            bne     cl
            movem.l (sp),d2-d3/a2-a4
            lea     20(sp),sp
            move.l  (sp),d0
            addq.l  #8,sp
            rts
    DST:    subi.l  #{C.K_EXT0},d0           ; d0 = d0, wenn k 23..32, sonst 0 (mit Flags)
            cmpi.l  #{C.K_EXT1 - C.K_EXT0},d0
            bhi     dz
            addi.l  #{C.K_EXT0},d0
            rts
    dz:     moveq   #0,d0
            rts
'''
    return asm2(M_C4, text)


def build_c6(lkx=0):
    """smp12: TSEL, Knopf-Suche (LKW / LKP / LKSLOT), Attack (RPH, ATKV / ATKP, ATH, Zustand ATS)"""
    from cfasm import asm, done as adone
    import collections
    k = dict(C=C, UIGET=UIGET, UI_PMODE=UI_PMODE, TSEL_FN=TSEL_FN, RENDERFN=RENDERFN, LOOKUP_CONT=LOOKUP_CONT,
             ENC_DECAY=ENC_DECAY, FMT_INT=FMT_INT, REC=REC, D_ATK=D_ATK, K_ATK=K_ATK, VCA_CONT=VCA_CONT,
             VOICE0=VOICE0, VSTRIDE=VSTRIDE, LKX=lkx)
    segs = [(M_C6, ['''
    ; T1..T6: Spur nur mit TRACK waehlen (oder im Pattern-Auswahlmodus); 4(sp) = Spur
    TSEL:   pea     {C.KEY_TRACK}.w
            jsr     {C.HELD}
            addq.l  #4,sp
            tst.l   d0
            bne     ts1
            jsr     {UIGET}
            movea.l d0,a0
            tst.b   {UI_PMODE}(a0)
            bne     ts1
            rts
    ts1:    jmp     {TSEL_FN}
    ; Objekt der Klangerzeugung merken (8(sp) = Parameter), dann die Firmware
    RPH:    move.l  8(sp),d0
            move.l  d0,PARP
            jmp     {RENDERFN}
    ; Knopf-Suche (Ansicht, Knopf, FUNC, -1): Firmware mit Ruecksprung LKP (d0 = Deskriptor)
    LKW:    move.l  16(sp),-(sp)
            move.l  16(sp),-(sp)
            move.l  16(sp),-(sp)
            move.l  16(sp),-(sp)
            pea     LKP
    ''', ('orig', LOOKUP, 6), '''
            jmp     {LOOKUP_CONT}
    ''']),
            (M_C7, ['''
    LKP:    moveq   #{ENC_DECAY},d1          ; FUNC + DECAY -> Attack
            cmp.l   4(sp),d1
            bne     lk1
            tst.l   8(sp)
            beq     lk1
            move.l  #{FMT_INT},d1
            move.l  d1,{REC + 100 * D_ATK + 0x20}
            clr.l   {REC + 100 * D_ATK + 0x2C}
            moveq   #{D_ATK},d0
    lk1:
    LKP2:   jmp     {LKX}                    ; smp18: FUNC-Knoepfe der Maschinen (LKXT), dann LKSLOT (g2_dtab.LKX)
    ; VCA (Puffer, Stimme): Firmware mit eigener Rueckkehr ATKP
    ATKV:   move.l  8(sp),-(sp)
            move.l  8(sp),-(sp)
            pea     ATKP
    ''', ('orig', VCA_FN, 8), '''
            jmp     {VCA_CONT}
    ATKP:   lea     -20(sp),sp               ; 20(sp) Puffer, 24(sp) Stimme, 28(sp) Ruecksprung
            movem.l d2-d5/a2,(sp)
            jmp     ATK1
    ''']),
            (M_C8, ['''
    ATK1:   move.l  24(sp),d0
            subi.l  #{VOICE0},d0
            bmi     ax
            move.l  #{VSTRIDE},d1
            divu.l  d1,d0
            moveq   #5,d1
            cmp.l   d1,d0
            bhi     ax
            move.l  d0,d2                    ; Spur
            move.l  PARP,d1
            beq     ax
            movea.l d1,a0
            moveq   #66,d1
            muls.l  d2,d1
            mvz.b   {14 + 2 * K_ATK}(a0,d1.l),d3   ; Attack 0..127
            lea     ATS,a2
            moveq   #12,d1
            muls.l  d2,d1
            adda.l  d1,a2                    ; Zustand: Verstaerkung (Q24), Schritt, Knopf
            cmp.l   8(a2),d3
            beq     ak1
            move.l  d3,8(a2)
            jmp     ATK2
    ak1:    jmp     ATK4
    ax:     jmp     ATKX
    ''']),
            (M_C9, ['''
    ATK2:   moveq   #0,d4
            tst.l   d3
            beq     ak0
            move.l  d3,d4                    ; Dauer = 96000 * (a / 127)^2 Samples (bis 2 s), Schritt = 2^24 / Dauer
            mulu.l  d3,d4
            move.l  #96000,d1
            mulu.l  d1,d4
            move.l  #16129,d1
            divu.l  d1,d4
            bne     ak3
            moveq   #1,d4
    ak3:    move.l  #0x1000000,d1
            divu.l  d4,d1
            move.l  d1,d4
    ak0:    move.l  d4,4(a2)
    ATK4:   movea.l 24(sp),a0                ; neuer Trig in diesem Block: von 0
            tst.l   0x38(a0)
            beq     ak2
            clr.l   (a2)
    ak2:    move.l  4(a2),d4
            beq     ax9
            move.l  (a2),d5
            cmpi.l  #0x1000000,d5
            bcc     ax9
            jmp     ATK5
    ax9:    jmp     ATKX
    ''']),
            (M_CA, ['''
    ATK5:   lea     OWN,a0                   ; smp24: eigene Huellkurve je Ton (CHORD / Vlvt setzen OWN[t] in jedem Block)
            tst.b   0(a0,d2.l)
            beq     ak5
            clr.b   0(a0,d2.l)
            move.l  #0x1000000,(a2)
            jmp     ATKX
    ak5:    movea.l 20(sp),a0
            moveq   #31,d3
    al:     move.l  (a0),d0
            asr.l   #8,d0
            asr.l   #7,d0
            move.l  d5,d1
            lsr.l   #8,d1
            lsr.l   #1,d1                    ; Q15
            muls.l  d1,d0
            move.l  d0,(a0)+
            add.l   d4,d5
            cmpi.l  #0x1000000,d5
            bcs     an
            move.l  #0x1000000,d5
    an:     subq.l  #1,d3
            bpl     al
            move.l  d5,(a2)
    ATKX:   movem.l (sp),d2-d5/a2
            lea     28(sp),sp
            rts
    '''])]
    import re
    def fmt(t): return re.sub(r'\{([^{}]+)\}', lambda m: str(eval(m[1], {}, k)), t)
    def assemble(S):
        out, labs = {}, {}
        for va, items in segs:
            a = A(va)
            for it in items:
                if isinstance(it, tuple): a.orig(it[1], it[2])
                else: asm(a, fmt(it), S)
            out[va] = bytearray(adone(a, S)); labs.update(a.lab)
        return out, labs
    out, labs = assemble(collections.defaultdict(int, PARP=0, LKSLOT=0, ATS=0, OWN=0))
    # Daten (RAM in der Maske): PARP, LKSLOT, ATS (6 x 12 B), Texte
    d = bytearray(); at = {}
    at['PARP'] = M_CB + len(d); d += bytes(4)
    at['LKSLOT'] = M_CB + len(d); d += bytes(4)
    at['ATS'] = M_CB + len(d); d += bytes(72)
    at['OWN'] = M_CB + len(d); d += bytes(6)                            # smp24: Spur hat eigene Huellkurve je Ton (kein Attack hier)
    at['S_ATK'] = M_CB + len(d); d += b'Attack\0'
    at['S_ATKS'] = M_CB + len(d); d += b'ATK\0'
    out, labs = assemble(dict(labs, **at))
    out[M_CB] = bytes(d)
    labs.update(at)
    return {va: bytes(b) for va, b in out.items()}, labs


def atk_desc(lab):
    return struct.pack('>14I', 7, K_ATK, 0, 0x7F00, 0, 0, 0xFFFFFFFF, 0xFFFFFFFF, 0, 0x600, 77, lab['S_ATK'], S_AMPGRP, lab['S_ATKS'])


def build_boot(dtinit):
    """BOOT (Haken am Anfang der BSS-Loeschung 0x400004b2, Cache noch aus): Nutzlast IMG_END.. -> PAY (PAYSZ), dann die beiden
    ersetzten Befehle. Wie die Nutzlast der Syntakt-Mods von Modded-Cycles (notes/17 §3, MIT); eigener Code."""
    a = A(M_BOOT)
    asm(a, f'''
    BOOT:   lea     {C.IMG_END:#x},a0
            lea     {C.PAY:#x},a1
            move.l  #{C.PAYSZ // 4},d0
    bt1:    move.l  (a0)+,(a1)+
            subq.l  #1,d0
            bne     bt1
            jsr     {dtinit:#x}              ; smp18: Deskriptor-Tabelle (g2_dtab)
            lea     -16(sp),sp               ; die beiden ersetzten Befehle
            movem.l d4-d7,(sp)
            jmp     {BOOT_BACK:#x}
    ''', {})
    return adone(a), dict(a.lab)


def build():
    c2, l2 = build_c2(); c1, l1 = build_c1(l2['KCALL']); c3, l3 = build_c3()
    c5, l5 = build_c5(); c4, l4 = build_c4(l5['SSLOTS'])
    c6, l6 = build_c6()
    dc, dl = DT.build(l6['LKSLOT'])
    c6, l6 = build_c6(dl['LKX'])
    cb, lb = build_boot(dl['DTINIT'])
    lab = {}
    for x in (l1, l2, l3, l4, l5, l6, lb, dl): lab.update(x)
    lab['_DTCODE'] = dc
    # Sound-Slot 3 (Attack) gehoert dem Core selbst
    ss = l5['SSLOTS'] - M_C5 + 4 * C.SSLOT['core-attack']
    c5 = c5[:ss] + struct.pack('>I', dl['ATH']) + c5[ss + 4:]          # smp23: ATH liegt im Code von g2_dtab (Nutzlast)
    return {M_C1: c1, M_C2: c2, M_C3: c3, M_C4: c4, M_C5: c5, M_BOOT: cb, **c6}, lab


def tweak(img):
    parts, lab = build()
    W = Writes(img)
    for va, b in parts.items():
        W.mask(va, b, SIZE[va])
    W.hook(C.H_HOOK, C.H_ORIG, jsr(lab['CED']))
    W.hook(RENDER_HOOK, RENDER_ORIG, jsr(lab['OVT']))
    W.hook(K_HOOK_A, K_ORIG_A, jsr(lab['C13A']) + bytes.fromhex("4e71"))
    W.hook(K_HOOK_L, K_ORIG_L, jsr(lab['LS']))
    W.hook(K_HOOK_R, K_ORIG_R, jsr(lab['C13R']))
    W.hook(L_HOOK, L_ORIG, jsr(lab['HL']))
    W.hook(I_HOOK, I_ORIG, jsr(lab['HI']))
    for va, nm in ((LD_HOOK, 'LD'), (SV2_HOOK, 'SV2'), (SV1_HOOK, 'SV1')):
        W.hook(va, PRO_CK, jmp(lab[nm]) + bytes.fromhex('4e71'))
    W.hook(CONV_HOOK, CONV_CK, jmp(lab['CONV']))
    for va in PTAB_REFS:
        W.hook(va, struct.pack('>I', PTAB_ORIG), struct.pack('>I', lab['PTAB']))
    W.hook(TSEL_AT, jsr(TSEL_FN), jsr(lab['TSEL']))                     # smp12
    W.hook(RP_AT, jsr(RENDERFN), jsr(lab['RPH']))
    W.hook(LOOKUP, LOOKUP_CK, jmp(lab['LKW']))
    W.hook(VCA_FN, VCA_CK, jmp(lab['ATKV']) + bytes.fromhex('4e71'))
    assert struct.unpack_from('>i', img, C.DESC(D_ATK) - BASE)[0] == -1, "Deskriptor 6 nicht frei"
    W.put(C.DESC(D_ATK), atk_desc(lab))
    assert len(img) == C.IMG_END - BASE, hex(len(img))
    pay = bytearray(C.PAYSZ)                                       # smp14: Nutzlast (Plaetze der Mods: C.PAY_SLOT)
    o = C.CORE_ORG - C.PAY; t = DT.tables(); pay[o:o + len(t)] = t  # smp18: Platz 'core': Tabellen + Code von g2_dtab
    o = C.CORE_CODE - C.PAY; pay[o:o + len(lab['_DTCODE'])] = lab['_DTCODE']
    W.put(C.IMG_END, bytes(pay))
    dhooks = DT.hook_all(W, img, lab)
    W.hook(C.TSV_KEY_SLOT, struct.pack('>I', C.TSV_KEY), struct.pack('>I', lab['TSVK']))   # smp28: Tasten mit TRACK gehalten
    dhooks = list(dhooks) + [C.TSV_KEY_SLOT]
    W.hook(BOOT_HOOK, BOOT_CK, jmp(lab['BOOT']) + bytes.fromhex('4e71'))
    for va, ck, new in FUNC_FLAT:
        W.hook(va, ck, new)
    keys = ('CED', 'SLOTS', 'KCALL', 'KSLOTS', 'GEST', 'SLOW', 'MODESW', 'OVS', 'OVT', 'NPD', 'C13A', 'LS', 'C13R', 'HL', 'HI',
            'LD', 'SV2', 'SV1', 'LDP', 'SVP', 'CALLS', 'DST', 'CONV', 'PTAB', 'SSLOTS',
            'TSEL', 'RPH', 'LKW', 'LKP', 'LKP2', 'LKSLOT', 'ATH', 'ATKV', 'ATKP', 'ATKX', 'PARP', 'ATS', 'OWN', 'S_ATK', 'BOOT',
            'DTINIT', 'MAPK', 'ST_AT', 'ST_CN', 'DMACH', 'BROW', 'LKX', 'RBUILD', 'LEDF', 'TSVK', 'PFONT', 'PSX')
    return patch('core', 0, 'Core: shared services for the modular mods',
                 ["Encoder gesture dispatcher, firmware-style value popups, SETTINGS as a modifier, slow effect selection,",
                  "pattern storage for header bytes 40..63, sound slots and p-locks for extra parameters (k 23..32).",
                  "T1..T6 alone no longer select the track (TRACK + T1..T6 does; pattern selection mode unchanged).",
                  "FUNC + DECAY = Amp Attack (0 .. ~2 s, all machines; idea from Model-TG by TinyGregAudio, MIT): p-locks, LFO, saved with the sound.",
                  f"Payload area appended to the MAIN OS ({C.PAYSZ} B), copied to {C.PAY:#x} at start (hook {BOOT_HOOK:#x}); mods fill their own slot.",
                  f"Parameter descriptor table moved into the payload and extended to {C.NDESC} entries (idea and address list: Modded-Cycles notes/18-19, MIT; own code).",
                  "FUNC + knob on the parameter pages no longer jumps in coarse steps; it moves like the knob alone,",
                  "so FUNC + knob is free for alternate parameters (Attack, Mono Glide / Noise).",
                  "Erzeugt von v2/g2_core.py."], W,
                 hooks=[f"{x:#x}" for x in (C.H_HOOK, RENDER_HOOK, K_HOOK_A, K_HOOK_L, K_HOOK_R, L_HOOK, I_HOOK, LD_HOOK, SV2_HOOK,
                                             SV1_HOOK, CONV_HOOK) + PTAB_REFS + (TSEL_AT, RP_AT, LOOKUP, VCA_FN, BOOT_HOOK) + tuple(dhooks) + tuple(va for va, _, _ in FUNC_FLAT)],
                 memory=[{"va": f"{V:#x}", "size": 40, "ram": True, "use": "popup + key state (VARS)"},
                         {"va": f"{lab['PARP']:#x}", "size": 80, "ram": True, "use": "attack: render params pointer, lookup slot, ramp state (in mask)"},
                         {"va": f"{C.ACC:#x}", "size": 12, "ram": True, "use": "detent counter (SLOW)"},
                         {"va": f"{C.PAY:#x}", "size": C.PAYSZ, "ram": True, "use": "payload (slots: " + ", ".join(f"{k} +{o:#x}" for k, (o, n) in C.PAY_SLOT.items()) + "), copied at start"}],
                 settings=[f"{C.CTRL_MODE:#x} (control mode, written by control-mode: {C.CTRL_ABS:#x} absolute, anything else relative)"],
                 pattern="header bytes 40..63 are copied on pattern load (without the PCv2 tag in 60..63: 52..59 cleared, tag set); new patterns: 40..59 = 0 + tag",
                 symbols={k: f"{lab[k]:#x}" for k in keys},
                 params={"nslot": C.NSLOT, "slots": {k: v for k, v in C.SLOT.items()}, "vars": f"{V:#x}",
                         "nkslot": C.NKSLOT, "kslots": dict(C.KSLOT), "ctrl_abs": C.CTRL_ABS,
                         "nsslot": C.NSSLOT, "sslots": dict(C.SSLOT),
                         "slow": [SLOW_N, SLOW_T], "dur": DUR})


SYM = None
def sym():
    """Symbole des Cores (fuer die anderen Generatoren)."""
    global SYM
    if SYM is None:
        _, lab = build(); SYM = lab
    return SYM


def sslot_write(W, pid, handler):
    """Sound-Handler der Mod (a0 Satz, a1 Sound, d1 = 0 Laden / 1 Speichern) in ihren Sound-Slot."""
    at = sym()['SSLOTS'] + 4 * C.SSLOT[pid]
    assert bytes(W.base[at - BASE:at - BASE + 4]) == bytes(4), f"Sound-Slot {pid} nicht frei (Core fehlt?)"
    W.put(at, struct.pack('>I', handler))


def lkslot_write(W, handler):
    """POST-Handler einer Mod fuer die Knopf-Suche (Stapel: Ansicht, Knopf, FUNC, -1 kopiert; d0 = Deskriptor; Ende mit
    lea 16(sp),sp ; rts). Ein Platz (lfo-amount)."""
    at = sym()['LKSLOT']
    assert bytes(W.base[at - BASE:at - BASE + 4]) == bytes(4), "Knopf-Slot belegt (Core fehlt?)"
    W.put(at, struct.pack('>I', handler))


def kslot_write(W, pid, handler):
    """Handler in den SETTINGS-Tasten-Slot der Mod (Druecken d1 = 0 / Loslassen d1 = 1, a0 = Ereignis; Loslassen:
    d0 != 0 = behandelt, kein Menue)."""
    at = sym()['KSLOTS'] + 4 * C.KSLOT[pid]
    assert bytes(W.base[at - BASE:at - BASE + 4]) == bytes(4), f"Tasten-Slot {pid} nicht frei (Core fehlt?)"
    W.put(at, struct.pack('>I', handler))


def lslot_write(W, pid, handler):
    """smp27: LED-Filter der Mod (Core LEDF am Anfang von LED_SET): Handler(d0 = LED, d1 = Zustand) -> d1"""
    at = C.PIMG(C.LSLOTS + 4 * C.LSLOT[pid])
    assert bytes(W.base[at - BASE:at - BASE + 4]) == bytes(4), f"LED-Slot {pid} nicht frei"
    W.put(at, struct.pack('>I', handler))


def psx_write(W, pid, entries):
    """smp37: Parameter-Suche des Cores (PSX): (Maschine, k, Deskriptor) in die Plaetze der Mod"""
    i0, n = C.PSX_SLOT[pid]
    assert len(entries) <= n
    for i, (m, k, d) in enumerate(entries):
        W.put(C.PIMG(C.PSXT + 4 * (i0 + i)), struct.pack('>BBH', m, k, d))


def tkslot_write(W, pid, handler):
    """smp28: Tasten der TrackSelectionView (Core TSVK): Handler(Ansicht, Ereignis), C-Aufruf -> d0 != 0 = behandelt"""
    at = C.PIMG(C.TKSLOTS + 4 * C.TKSLOT[pid])
    assert bytes(W.base[at - BASE:at - BASE + 4]) == bytes(4), f"TRACK-Tasten-Slot {pid} nicht frei"
    W.put(at, struct.pack('>I', handler))


def slot_write(W, pid, handler):
    """Handler-Adresse in den Slot der Mod schreiben (gegen ein Image, auf dem der Core schon liegt)."""
    at = sym()['SLOTS'] + 4 * C.SLOT[pid]
    assert bytes(W.base[at - BASE:at - BASE + 4]) == bytes(4), f"Slot {pid} nicht frei (Core fehlt?)"
    W.put(at, struct.pack('>I', handler))


if __name__ == "__main__":
    t = tweak(stock())
    if len(sys.argv) > 1: save(t, sys.argv[1])
    parts, lab = build()
    print({f"{va:#x}": len(b) for va, b in parts.items()}, {k: hex(v) for k, v in lab.items() if k.isupper()})
