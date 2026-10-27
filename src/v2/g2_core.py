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
        Loslassen ohne Drehung speichert dann statt das Menue zu oeffnen.
  Pattern-Speicher: Haken 0x4005b4b0 (Pattern laden) kopiert zusaetzlich die Kopf-Bytes 40..63; fehlt die Kennung
        (Bytes 60..63 'PCv2', z. B. Pattern aus der Original-Firmware), werden 52..59 geloescht und die Kennung gesetzt
        (40..51 = Humanize bleiben wie in v1). 0x4006155e (neues Pattern) loescht 40..59 und setzt die Kennung.
        Belegung in common.py (P_*).
  KCALL / KSLOTS: SETTINGS im Hauptbildschirm ruft die Tasten-Slots beim ersten Druecken (d1 = 0) und beim Loslassen
        ohne FUNC und ohne langes Halten (d1 = 1; a0 = Ereignis). Gibt ein Handler beim Loslassen d0 != 0 zurueck, oeffnet
        sich das Menue nicht. Slots: control-mode 0.
  CTRL_MODE 0x404e9b5d (Einstellungsblock): == 0x5a CONTROL ALL absolut, sonst relativ (= Firmware); geschrieben von
        control-mode, gelesen von allen, die mehrere Werte auf einmal aendern (control-mode, groove).
Speicher: Masken 0x4018f4b4 (CED, SLOTS, Tasten, GEST, HL, HI), 0x4018dba8 (SLOW, MODESW), 0x4015c044 (OVS, OVT, NPD).
RAM: VARS 0x4a33c380 (40 B), ACC 0x4a33c3c0 (12 B).
Aufruf: g2_core.py [out.json]
"""
import struct, sys
from common import *                 # noqa: F401,F403
import common as C

M_C1, M_C2, M_C3 = 0x4018F4B4, 0x4018DBA8, 0x4015C044
SIZE = {M_C1: 376, M_C2: 376, M_C3: 720}
DUR = 202752000                      # 1.5 s in Zeitgeber-Ticks
OMAGIC = 0x4F564C32                  # 'OVL2'
VC_DIRTY = 0x20
RENDER_HOOK, RENDER_ORIG = 0x40076C88, (6, '447f49a6d517f875d837b9ccbe69eee0914d078600a16cd5cc6d626f3f27285d')
K_BIT5, K_SAVE, K_DONE = 0x40072444, 0x40039570, 0x4001C2A8
K_HOOK_A, K_ORIG_A = 0x4001C54C, (8, '5938f6ac8492a4497ca28a80e4fdd6a460c070f0f16a3e4a6e37bea24f79071f')
K_HOOK_L, K_ORIG_L = 0x4001C564, (6, 'c1af6619aaea3604f5c25cd0c68164acc4fec83581f35649e516c7c862ab487c')
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
    a = A(M_C1); w, l = a.w, a.l32
    # ---------------- CED: Encoder-Verteiler (jsr am Haken; a2 = Ereignis)
    a.label('CED')
    w(0x2F0B, 0x2F02)                           # move.l a3,-(a7) ; move.l d2,-(a7)
    w(0x47F9); l(0); fix_slots = len(a.b) - 4   # lea SLOTS,a3
    w(0x7400 | (C.NSLOT - 1))                   # moveq #NSLOT-1,d2
    a.label('lp')
    w(0x201B); a.bcc(EQ, 'nx')                  # move.l (a3)+,d0 ; beq nx
    w(0x2040, 0x4E90, 0x4A80); a.bcc(NE, 'hit') # movea.l d0,a0 ; jsr (a0) ; tst.l d0 ; bne hit
    a.label('nx')
    w(0x5382); a.bcc(PL, 'lp')                  # subq.l #1,d2 ; bpl lp
    w(0x241F, 0x265F)                           # move.l (a7)+,d2 ; movea.l (a7)+,a3
    w(0x205F); a.orig(C.H_HOOK, 6); w(0x4ED0)   # verschobene Originalbefehle (aus dem Image) ; zurueck
    a.label('hit')
    w(0x241F, 0x265F, 0x5380); a.bcc(EQ, 'skip')   # 1 -> verwerfen
    w(0x205F, 0x7200, 0x2F01, 0x4ED0)           # 2 -> Drehung 0 weitergeben
    a.label('skip')
    w(0x4FEF, 0x000C, 0x4EF9); l(C.ENC_SKIP)
    # ---------------- GEST(d0 = Taste)
    a.label('GEST')
    w(0x2F00, 0x4EB9); l(C.CONSUME); w(0x588F)
    w(0x42B9); l(V + C.V_PEND); w(0x4E75)
    # ---------------- SETTINGS im Hauptbildschirm (wie v1 gen_overlay_113.build_keys)
    a.label('C13A')                             # statt move.l d3,-(a7) ; jsr BIT5 (8 B: jsr C13A ; nop)
    w(0x2043, 0x2028, 0x0010, 0x7209, 0xC081, 0x5380); a.bcc(NE, 'k1')   # erstes Druecken: (Flags & 9) == 1
    w(0x42B9); l(V + C.V_PEND)
    w(0x7200, 0x4EB9); l(kcall)                 # moveq #0,d1 ; jsr KCALL   (a0 = Ereignis; Tasten-Slots: Druecken)
    a.label('k1')
    w(0x205F); a.orig(K_HOOK_A, 2); w(0x2F08, 0x4EF9); l(K_BIT5)   # verschobener Originalbefehl, dann BIT5(ev)
    a.label('LS')                               # statt jsr SAVE beim langen Halten
    w(0x7001, 0x23C0); l(V + C.V_PEND); w(0x4E75)
    a.label('C13R')                             # statt pea $9c(a2) ; move.l a6,d2 (Loslassen ohne FUNC -> Menue)
    w(0x4AB9); l(V + C.V_PEND); a.bcc(EQ, 'kn')
    w(0x42B9); l(V + C.V_PEND)
    w(0x4878, 0x0020); a.orig(K_HOOK_L, 6); w(0x508F, 0x4EF9); l(K_DONE)   # verschobener Aufruf (Speichern)
    a.label('kn')                               # Loslassen ohne FUNC, ohne langes Halten: Tasten-Slots, sonst Menue
    w(0x2043, 0x7201, 0x4EB9); l(kcall); w(0x4A80); a.bcc(NE, 'kh')   # movea.l d3,a0 ; moveq #1,d1 ; jsr KCALL ; tst.l d0
    w(0x205F); a.orig(K_HOOK_R, 6); w(0x4ED0)   # verschobene Originalbefehle
    a.label('kh')
    w(0x588F, 0x4EF9); l(K_DONE)                # behandelt: kein Menue
    # ---------------- HL: Pattern laden (a3 Datei-Kopf, a2 B-Kopf; d0 bleibt): zusaetzlich Kopf-Bytes 40..63.
    #   Ohne Kennung (60..63, z. B. Pattern aus der Original-Firmware): 52..59 = 0, Kennung setzen (40..51 bleiben, wie v1).
    a.label('HL')
    a.orig(L_HOOK, 6)                           # verschobener Originalbefehl
    w(0x41EB, C.P_FIRST, 0x43EA, C.P_FIRST, 0x7200 | (NCOPY - 1))
    a.label('hl'); w(0x12D8, 0x5381); a.bcc(PL, 'hl')
    w(0x73E9, 0xFFFC, 0x0C81); l(C.SIG[0]); a.bcc(NE, 'fx')        # mvz.w -4(a1),d1 ; cmpi.l #SIG0,d1
    w(0x73E9, 0xFFFE, 0x0C81); l(C.SIG[1]); a.bcc(EQ, 'hok')                          # mvz.w -2(a1),d1
    a.label('fx')
    w(0x41EA, C.P_RFX, 0x7200 | (C.P_SIG - C.P_RFX - 1))
    a.label('fl'); w(0x4218, 0x5381); a.bcc(PL, 'fl')                                  # clr.b (a0)+
    w(0x30FC, C.SIG[0], 0x30BC, C.SIG[1])                                              # move.w #SIG0,(a0)+ ; move.w #SIG1,(a0)
    a.label('hok'); w(0x4E75)
    # ---------------- HI: neues Pattern (a0 Kopf): Kopf-Bytes 40..59 = 0, Kennung ; d0.b = 0 wie im Original
    a.label('HI')
    a.orig(I_HOOK, 6)                           # verschobene Originalbefehle
    w(0x43E8, C.P_FIRST, 0x7200 | (C.P_SIG - C.P_FIRST - 1))
    a.label('hi'); w(0x4219, 0x5381); a.bcc(PL, 'hi')
    w(0x32FC, C.SIG[0], 0x32BC, C.SIG[1], 0x4E75)                                      # move.w #SIG0,(a1)+ ; move.w #SIG1,(a1)
    code = bytearray(a.done()); check_cf(bytes(code), M_C1)
    while len(code) % 4: code += b'\0'
    slots = M_C1 + len(code); code += bytes(4 * C.NSLOT)
    code[fix_slots:fix_slots + 4] = struct.pack('>I', slots)
    return bytes(code), dict(a.lab, SLOTS=slots)


def build_c2():
    a = A(M_C2); w, l = a.w, a.l32
    # ---------------- SLOW (d4 Drehung, d5 Ziel) -> d0 ; veraendert d1, a0  (wie v1 gen_overlay_113.build_slow)
    a.label('SLOW')
    w(0x41F9); l(C.ACC)
    w(0x2239); l(C.TIMER); w(0x2001, 0x90A8, 0x0008, 0x2141, 0x0008)
    w(0x0C80); l(SLOW_T); a.bcc(CS, 'st1'); w(0x4290)
    a.label('st1')
    w(0xBAA8, 0x0004); a.bcc(EQ, 'st2'); w(0x4290, 0x2145, 0x0004)
    a.label('st2')
    w(0x2010, 0x2200, 0xB981); a.bcc(PL, 'st3'); w(0x7000)
    a.label('st3')
    w(0xD084, 0x2080, 0x2200); a.bcc(PL, 'st4'); w(0x4481)
    a.label('st4')
    w(0x0C81); l(SLOW_N); a.bcc(CS, 'st5')
    w(0x4290, 0x7001, 0x4E75)
    a.label('st5'); w(0x7000, 0x4E75)
    # ---------------- MODESW (a0 Byte, d1 Max, a1 Rueckruf; a2 Ereignis) -> d0 = 2
    a.label('MODESW')
    w(0x4FEF, 0xFFEC, 0x48D7, 0x1838)           # lea -20(a7),a7 ; movem.l d3-d5/a3-a4,(a7)
    w(0x2648, 0x2601, 0x2849)                   # movea.l a0,a3 ; move.l d1,d3 ; movea.l a1,a4
    w(0x792A, 0x0008); a.bcc(EQ, 'mo')          # mvs.b 8(a2),d4 ; beq out
    w(0x2A0B); a.bcc(BSR, 'SLOW')               # move.l a3,d5 ; bsr SLOW
    w(0x4A80); a.bcc(EQ, 'mo')
    w(0x7193)                                   # mvz.b (a3),d0
    w(0xB083); a.bcc(LS, 'v'); w(0x7000)        # cmp.l d3,d0 ; bls v ; moveq #0,d0  (ungueltig -> 0)
    a.label('v')
    w(0x2200, 0x4A84); a.bcc(LE, 'dec')
    w(0x5281); a.bcc(BRA, 'cl')
    a.label('dec'); w(0x5381)
    a.label('cl')
    w(0x4A81); a.bcc(PL, 'c1'); w(0x7200)
    a.label('c1')
    w(0xB283); a.bcc(LE, 'c2'); w(0x2203)
    a.label('c2')
    w(0x7193, 0xB081); a.bcc(EQ, 'mo')          # mvz.b (a3),d0 ; cmp.l d1,d0 (Rohwert: Muell wird ersetzt)
    w(0x1681)                                   # move.b d1,(a3)
    w(0x200C); a.bcc(EQ, 'mo'); w(0x4E94)       # move.l a4,d0 ; beq ; jsr (a4)
    a.label('mo')
    w(0x7002, 0x4CD7, 0x1838, 0x4FEF, 0x0014, 0x4E75)
    # ---------------- KCALL (d1 = 0 Druecken / 1 Loslassen, a0 = Tasten-Ereignis) -> d0: erster Rueckgabewert != 0, sonst 0
    #   Tasten-Slots (KSLOTS) fuer SETTINGS im Hauptbildschirm; Handler: C-ABI, a0 = Ereignis, d1 = Art.
    a.label('KCALL')
    w(0x4FEF, 0xFFF0, 0x48D7, 0x0C0C)           # lea -16(a7),a7 ; movem.l d2-d3/a2-a3,(a7)
    w(0x2601, 0x2448, 0x47F9); l(0); fix_k = len(a.b) - 4   # move.l d1,d3 ; movea.l a0,a2 ; lea KSLOTS,a3
    w(0x7400 | (C.NKSLOT - 1))
    a.label('kl')
    w(0x201B); a.bcc(EQ, 'kx')                  # move.l (a3)+,d0 ; beq
    w(0x2240, 0x204A, 0x2203, 0x4E91, 0x4A80); a.bcc(NE, 'ko')
    a.label('kx')
    w(0x5382); a.bcc(PL, 'kl'); w(0x7000)
    a.label('ko')
    w(0x4CD7, 0x0C0C, 0x4FEF, 0x0010, 0x4E75)
    code = bytearray(a.done()); check_cf(bytes(code), M_C2)
    while len(code) % 4: code += b'\0'
    ks = M_C2 + len(code); code += bytes(4 * C.NKSLOT)
    code[fix_k:fix_k + 4] = struct.pack('>I', ks)
    return bytes(code), dict(a.lab, KSLOTS=ks)


def build_c3():
    a = A(M_C3); w, l = a.w, a.l32
    # ---------------- OVS (d0 Art, d1 Wert, a0 Zeile 1 / Funktion, a1 Zeile 2)
    a.label('OVS')
    w(0x2F0A, 0x45F9); l(V)
    w(0x2540, C.V_KIND, 0x2541, C.V_VAL, 0x2548, C.V_L1, 0x2549, C.V_L2)
    w(0x2039); l(C.TIMER); w(0x0680); l(DUR); w(0x2540, C.V_DL)
    w(0x202A, C.V_MAGIC, 0x0C80); l(OMAGIC); a.bcc(NE, 'ovr')
    w(0x202A, C.V_VC); a.bcc(EQ, 'ovr')
    w(0x2040, 0x7001, 0x1140, VC_DIRTY)         # movea.l d0,a0 ; moveq #1,d0 ; move.b d0,$20(a0)
    a.label('ovr'); w(0x245F, 0x4E75)
    # ---------------- OVT: Ende des ViewController-Zeichnens (a2 VC, d3 Bitmap); d0 = 0 wie im Original
    a.label('OVT')
    w(0x41F9); l(V)
    w(0x2028, C.V_MAGIC, 0x0C80); l(OMAGIC); a.bcc(EQ, 'm1')
    w(0x203C); l(OMAGIC); w(0x2140, C.V_MAGIC, 0x42A8, C.V_KIND, 0x42A8, C.V_PEND, 0x42A8, C.V_MPEND)
    a.label('m1')
    w(0x214A, C.V_VC, 0x7000); a.orig(RENDER_HOOK + 2, 4)   # d0 = 0 ; verschobener Originalbefehl (Neuzeichnen erledigt)
    w(0x4AA8, C.V_KIND); a.bcc(EQ, 'out')
    w(0x2039); l(C.TIMER); w(0x90A8, C.V_DL); a.bcc(MI, 'live')
    w(0x42A8, C.V_KIND); a.bcc(BRA, 'out')
    a.label('live')
    w(0x7003, 0xB0A8, C.V_KIND); a.bcc(EQ, 'nk')    # Art 3: Neuzeichnen kommt vom Aufrufer
    w(0x7001, 0x1540, VC_DIRTY)
    a.label('nk')
    w(0x4FEF, 0xFFE0, 0x48D7, 0x0CFC)           # lea -32(a7),a7 ; movem.l d2-d7/a2-a3,(a7)
    w(0x2443, 0x47F9); l(V)                     # movea.l d3,a2 ; lea VARS,a3
    w(0x7003, 0xB0AB, C.V_KIND); a.bcc(NE, 'np')
    w(0x206B, C.V_L1, 0x4E90); a.bcc(BRA, 'done')   # eigene Zeichenfunktion
    a.label('np')
    a.bcc(BSR, 'NPD')
    a.label('done')
    w(0x4CD7, 0x0CFC, 0x4FEF, 0x0020)
    a.label('out')
    w(0x7000, 0x4E75)
    # ---------------- NPD: Popup wie ParameterPageView::draw (a2 Bitmap, a3 VARS)
    def rect(fn, x0, y0, x1, y1, col):
        w(0x7000 | x0, 0x7200 | y0, 0x7400 | x1, 0x7600 | y1, 0x7800 | (col & 0xFF))
        w(0x43F9); l(fn); a.bcc(BSR, 'RCT')
    a.label('NPD')
    rect(FILL_F, 0, 0, 63, 63, 1); rect(FRAME_F, 0, 0, 63, 63, 0); rect(FILL_F, 64, 0, 127, 63, 0)
    w(0x206B, C.V_L1, 0x7200 | 47); a.bcc(BSR, 'TXN')
    w(0x202B, C.V_L2); a.bcc(EQ, 'vv'); w(0x2040, 0x7200 | 34); a.bcc(BSR, 'TXN')
    a.label('vv')
    w(0x2F2B, C.V_VAL, 0x7002, 0xB0AB, C.V_KIND); a.bcc(NE, 'vn')
    w(0x4879); l(FMT_S); w(0x43F9); l(F_NAME); a.bcc(BRA, 'vt')
    a.label('vn')
    w(0x4879); l(FMT_D); w(0x43F9); l(F_VAL)
    a.label('vt')
    w(0x4878, 0x0002, 0x4878, 34, 0x4878, 96, 0x2F09, 0x2F0A, 0x4EB9); l(TXT_F); w(0x4FEF, 0x001C)
    rect(FILL_F, 0, 0, 63, 63, -1)
    w(0x4E75)
    a.label('TXN')                              # a0 Text, d1 y: Namen-Schrift, x = 32 mittig
    w(0x2F08, 0x4878, 0x0002, 0x2F01, 0x4878, 32, 0x4879); l(F_NAME); w(0x2F0A, 0x4EB9); l(TXT_F); w(0x4FEF, 0x0018, 0x4E75)
    a.label('RCT')                              # (a1)(bmp, d0, d1, d2, d3, d4 als Byte mit Vorzeichen)
    w(0x49C4, 0x2F04, 0x2F03, 0x2F02, 0x2F01, 0x2F00, 0x2F0A, 0x4E91, 0x4FEF, 0x0018, 0x4E75)
    code = a.done(); check_cf(code, M_C3)
    return code, dict(a.lab)


def build():
    c2, l2 = build_c2(); c1, l1 = build_c1(l2['KCALL']); c3, l3 = build_c3()
    lab = {}; lab.update(l1); lab.update(l2); lab.update(l3)
    return {M_C1: c1, M_C2: c2, M_C3: c3}, lab


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
    keys = ('CED', 'SLOTS', 'KCALL', 'KSLOTS', 'GEST', 'SLOW', 'MODESW', 'OVS', 'OVT', 'NPD', 'C13A', 'LS', 'C13R', 'HL', 'HI')
    return patch('core', 0, 'Core: shared services for the modular mods',
                 ["Encoder gesture dispatcher, firmware-style value popups, SETTINGS as a modifier, slow effect selection,",
                  "pattern storage for header bytes 40..63. Erzeugt von v2/g2_core.py."], W,
                 hooks=[f"{x:#x}" for x in (C.H_HOOK, RENDER_HOOK, K_HOOK_A, K_HOOK_L, K_HOOK_R, L_HOOK, I_HOOK)],
                 memory=[{"va": f"{V:#x}", "size": 40, "ram": True, "use": "popup + key state (VARS)"},
                         {"va": f"{C.ACC:#x}", "size": 12, "ram": True, "use": "detent counter (SLOW)"}],
                 settings=[f"{C.CTRL_MODE:#x} (control mode, written by control-mode: {C.CTRL_ABS:#x} absolute, anything else relative)"],
                 pattern="header bytes 40..63 are copied on pattern load (without the PCv2 tag in 60..63: 52..59 cleared, tag set); new patterns: 40..59 = 0 + tag",
                 symbols={k: f"{lab[k]:#x}" for k in keys},
                 params={"nslot": C.NSLOT, "slots": {k: v for k, v in C.SLOT.items()}, "vars": f"{V:#x}",
                         "nkslot": C.NKSLOT, "kslots": dict(C.KSLOT), "ctrl_abs": C.CTRL_ABS,
                         "slow": [SLOW_N, SLOW_T], "dur": DUR})


SYM = None
def sym():
    """Symbole des Cores (fuer die anderen Generatoren)."""
    global SYM
    if SYM is None:
        _, lab = build(); SYM = lab
    return SYM


def kslot_write(W, pid, handler):
    """Handler in den SETTINGS-Tasten-Slot der Mod (Druecken d1 = 0 / Loslassen d1 = 1, a0 = Ereignis; Loslassen:
    d0 != 0 = behandelt, kein Menue)."""
    at = sym()['KSLOTS'] + 4 * C.KSLOT[pid]
    assert bytes(W.base[at - BASE:at - BASE + 4]) == bytes(4), f"Tasten-Slot {pid} nicht frei (Core fehlt?)"
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
