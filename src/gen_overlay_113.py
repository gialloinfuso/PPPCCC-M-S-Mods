#!/usr/bin/env python3
"""Anzeige-Baustein fuer die 1.13-Linie: kurzes Wertfenster ueber allem, was gerade auf dem Bildschirm ist (in gen_moddelay_113).

v2 (25.10.2026, nach Pips Hardwaretest 'nichts im Display, Maschine wird laggy'):
  v1 hing am Anfang von MainScreenView::draw (0x4001b22a, nach djd_oz notes/44) und zeichnete nur ohne offenes
  Parameter-Popup. Die Gesten liessen aber ein Encoder-Ereignis mit Schritt 0 an die Firmware weiter, das Popup ging auf,
  der Hauptbildschirm zeichnete nicht -> nie sichtbar. Jetzt:
  - Haken am Ende von ViewController-Zeichnen 0x40076c1a (bei 0x40076c88 statt 'clr.b d0 ; move.b d0,$20(a2)'):
    alle Views (Hauptbildschirm, Popups, Menues) sind gezeichnet, das Fenster kommt obendrauf; d3 = Bitmap, a2 = VC.
    Byte VC+0x20 = 'alles neu zeichnen' (setzt View::setNeedsRedraw ueber den Parent). Waehrend das Fenster sichtbar ist,
    bleibt es gesetzt (30 Bilder/s), also verschwindet es genau nach 1.5 s.
  - OVS (d0 = Art 1 SPEED / 2 STRUM, d1 = Wert): merkt Art/Wert, Ablauf = Zeitgeber + 1.5 s, setzt VC+0x20.
  Fenster: Rahmen (28,18)-(99,47), Beschriftung SPEED/STRUM in 3x7-Schrift (y 37..43), Wert doppelt gross (y 21..34), mittig.
  Zeichnen nur mit FILL_RECT 0x40070dea(bmp, x0, y0, x1, y1, Farbe): 0 loescht, 1 setzt, y = 0 unten.
  Zeitgeber: 0xfc07000c (135.168 MHz, wie Hold-Mute).
  Variablen im RAM (nicht beim Start genullt): Magic-Wort; ohne Magic setzt OVT alles zurueck.
build_keys: SETTINGS-Taste im Hauptbildschirm (langes Halten speichert erst beim Loslassen ohne Drehung), siehe dort.
SLOW (fuer H4, d4 = Drehung, d5 = Ziel-Byte): summiert die Drehung; erst bei |Summe| >= SLOW_N schaltet H4 um (d0 = 1),
  sonst d0 = 0 (verschlucken). Zuruecksetzen bei anderem Ziel, Richtungswechsel oder Pause > 0.4 s.
"""
import struct, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from gen_solo import A
from gen_chorusfx import check_cf

TIMER, DUR = 0xFC07000C, 202752000          # 1.5 s
FILL = 0x40070DEA
VARS = 0x4A33C380
MAGIC, KIND, VAL, DL, VC, BUF, BUFN, PEND = 0, 4, 8, 12, 16, 20, 28, 32   # Offsets in VARS (BUF 8 B)
VC_DIRTY = 0x20                               # ViewController: Byte +0x20 = alles neu zeichnen
RENDER_HOOK, RENDER_ORIG = 0x40076C88, (6, '447f49a6d517f875d837b9ccbe69eee0914d078600a16cd5cc6d626f3f27285d')   # Laenge + SHA-256 (clr.b d0 ; move.b d0,$20(a2))
K_BIT5, K_SAVE = 0x40072444, 0x40039570       # KeyEvent: langes Halten? ; Projekt speichern (Fall 13, langes Halten)
K_HOOK_A, K_ORIG_A = 0x4001C54C, (8, '5938f6ac8492a4497ca28a80e4fdd6a460c070f0f16a3e4a6e37bea24f79071f')
K_HOOK_L, K_ORIG_L = 0x4001C564, (6, 'c1af6619aaea3604f5c25cd0c68164acc4fec83581f35649e516c7c862ab487c')
K_HOOK_R, K_ORIG_R = 0x4001C5BC, (6, 'b210caad8dca87c456a21e7dbbc4a4450dad3ae26f6e9fe4143fb6c15cc9c202')
K_DONE = 0x4001C2A8                           # Fall erledigt (moveq #1,d2 ; bra Epilog)
OMAGIC = 0x4F564C31                           # 'OVL1'
ACC = 0x4A33C3C0                              # SLOW: +0 Summe, +4 Ziel, +8 Zeit
SLOW_N, SLOW_T = 4, 54067200                  # 4 Rastungen, 0.4 s
BOX = (28, 18, 99, 47)
NE, EQ, PL, MI, CS, LT, GT, BRA, BSR, LS, HI = 0x6, 0x7, 0xA, 0xB, 0x5, 0xD, 0xE, 0x0, 0x1, 0x3, 0x2

# 3x7-Schrift: 7 Zeilen zu 3 Bit, oberste Zeile in den hoechsten Bits, in jeder Zeile Bit 2 = linke Spalte
ROWS = {
    '0': "### #.# #.# #.# #.# #.# ###", '1': ".#. ##. .#. .#. .#. .#. ###", '2': "### ..# ..# ### #.. #.. ###",
    '3': "### ..# ..# ### ..# ..# ###", '4': "#.# #.# #.# ### ..# ..# ..#", '5': "### #.. #.. ### ..# ..# ###",
    '6': "### #.. #.. ### #.# #.# ###", '7': "### ..# ..# .#. .#. .#. .#.", '8': "### #.# #.# ### #.# #.# ###",
    '9': "### #.# #.# ### ..# ..# ###", '-': "... ... ... ### ... ... ...",
    'S': ".## #.. #.. .#. ..# ..# ##.", 'P': "### #.# #.# ### #.. #.. #..", 'E': "### #.. #.. ### #.. #.. ###",
    'D': "##. #.# #.# #.# #.# #.# ##.", 'T': "### .#. .#. .#. .#. .#. .#.", 'R': "##. #.# #.# ##. #.# #.# #.#",
    'U': "#.# #.# #.# #.# #.# #.# ###", 'M': "#.# ### ### #.# #.# #.# #.#",
    'L': "#.. #.. #.. #.. #.. #.. ###", 'O': "### #.# #.# #.# #.# #.# ###", 'A': ".#. #.# #.# ### #.# #.# #.#",
    '/': "..# ..# .#. .#. .#. #.. #..",
    'W': "#.# #.# #.# #.# ### ### #.#", 'I': "### .#. .#. .#. .#. .#. ###", 'N': "##. #.# #.# #.# #.# #.# #.#",
    'G': "### #.. #.. #.# #.# #.# ###", 'H': "#.# #.# #.# ### #.# #.# #.#", 'C': "### #.. #.. #.. #.. #.. ###",
    'V': "#.# #.# #.# #.# #.# #.# .#.",
}
ORDER = "0123456789-SPEDTRUMLOA/WINGHCV"
def glyph(c):
    v = 0
    for row in ROWS[c].split():
        v = (v << 3) | int(row.replace('#', '1').replace('.', '0'), 2)
    return v
FONT = [glyph(c) for c in ORDER]
LABELS = {1: "SPEED", 2: "STRUM", 3: "LOAD", 4: "GROOVE", 5: "HUMAN"}      # Art 3: Text fertig in BUF/BUFN (Lastanzeige, gen_loadmeter_113)
LABEL_X = {1: 54, 2: 54, 3: 56, 4: 52, 5: 54}   # Art 4: Text in BUF (Groove-Name), Art 5: Zahl


def build(org, font_org, np_at):
    """Code nach org, Schrift + Beschriftungen nach font_org (eigene kleine Maske). Gibt (code, font_blob, lab)."""
    a = A(org); w, l = a.w, a.l32
    def fill(x0, y0, x1, y1, col):          # moveq x0,d2 ; y0,d3 ; x1,d4 ; y1,d5 ; col,d6 ; bsr RECT
        w(0x7400 | x0, 0x7600 | y0, 0x7800 | x1, 0x7A00 | y1, 0x7C00 | col); a.bcc(BSR, 'RECT')
    # ---------------- OVS (d0 Art, d1 Wert): merken, ViewController neu zeichnen lassen. C-ABI (d0/d1/a0/a1 frei).
    a.label('OVS')
    w(0x41F9); l(VARS)
    w(0x2140, KIND, 0x2141, VAL)
    w(0x2039); l(TIMER); w(0x0680); l(DUR); w(0x2140, DL)
    w(0x2028, MAGIC, 0x0C80); l(OMAGIC); a.bcc(NE, 'ovr')
    w(0x2028, VC); a.bcc(EQ, 'ovr')
    w(0x2240, 0x7001, 0x1340, VC_DIRTY)     # movea.l d0,a1 ; moveq #1,d0 ; move.b d0,$20(a1)
    a.label('ovr'); w(0x4E75)
    # ---------------- OVT: Ende des Zeichnens aller Views (0x40076c88, statt clr.b d0 ; move.b d0,$20(a2)).
    #   a2 = ViewController, d3 = Bitmap; d2-d7/a2-a6 bleiben; d0 = 0 wie im Original.
    a.label('OVT')
    w(0x41F9); l(VARS)
    w(0x2028, MAGIC, 0x0C80); l(OMAGIC); a.bcc(EQ, 'm1')
    w(0x203C); l(OMAGIC); w(0x2140, MAGIC, 0x42A8, KIND, 0x42A8, PEND)
    a.label('m1')
    w(0x214A, VC)                           # VC = a2
    w(0x7000); a.orig(RENDER_HOOK + 2, 4)   # d0 = 0 ; verschobener Originalbefehl: Neuzeichnen erledigt
    w(0x4AA8, KIND); a.bcc(EQ, 'out')
    w(0x2039); l(TIMER); w(0x90A8, DL); a.bcc(MI, 'live')
    w(0x42A8, KIND); a.bcc(BRA, 'out')      # abgelaufen: dieses Bild ist schon ohne Fenster gezeichnet
    a.label('live')
    w(0x2028, KIND, 0x5780); a.bcc(EQ, 'nk')   # Art 3 (Last): Neuzeichnen kommt von der Messung, nicht jedes Bild
    w(0x7001, 0x1540, VC_DIRTY)             # sichtbar: naechstes Bild wieder ganz zeichnen (Ablauf genau nach 1.5 s)
    a.label('nk')
    w(0x4FEF, 0xFFE0, 0x48D7, 0x0CFC)       # lea -32(sp),sp ; movem.l d2-d7/a2-a3,(sp)
    w(0x2443)                               # movea.l d3,a2   Bitmap
    w(0x47F9); l(VARS)
    w(0x202B, KIND, 0x7203, 0xB081); a.bcc(EQ, 'box')  # Art 3 (LOAD): eigenes Kaestchen
    w(0x4EB9); l(np_at); a.bcc(BRA, 'done')     # sonst: Popup im Stil der Firmware (NPD)
    a.label('box')
    x0, y0, x1, y1 = BOX
    fill(x0, y0, x1, y1, 0)
    fill(x0, y1, x1, y1, 1); fill(x0, y0, x1, y0, 1); fill(x0, y0, x0, y1, 1); fill(x1, y0, x1, y1, 1)
    # Beschriftung aus LTAB[Art-1] = (Zeiger, Laenge, x)
    w(0x202B, KIND, 0x5380, 0x0C80); l(len(LABELS) - 1); a.bcc(HI, 'done')   # Art 1..n, sonst nur Rahmen
    w(0xE788, 0x41F9); l(0); fix_lt = len(a.b) - 4
    w(0xD1C0, 0x7768, 0x0004, 0x7568, 0x0006, 0x2050)   # adda.l d0,a0 ; mvs.w 4(a0),d3 ; mvs.w 6(a0),d2 ; movea.l (a0),a0
    w(0x7E25, 0x7C01)                       # moveq #37,d7 ; moveq #1,d6
    a.bcc(BSR, 'DS')
    # Wert -> Zeichen in BUF
    w(0x41EB, BUF, 0x7600)                  # lea BUF(a3),a0 ; moveq #0,d3
    w(0x202B, KIND, 0x7203, 0xB081); a.bcc(EQ, 'tx')   # Art 3 (LOAD) und 4 (GROOVE): fertiger Text
    w(0x7204, 0xB081); a.bcc(NE, 'cv')
    a.label('tx')
    w(0x262B, BUFN, 0x5383, 0x7207, 0xB283); a.bcc(CS, 'done')   # 1..8 Zeichen, sonst nichts (DS braucht d3 >= 1)
    w(0x5283); a.bcc(BRA, 'u2')
    a.label('cv')
    w(0x282B, VAL); a.bcc(PL, 'pv')         # move.l VAL(a3),d4 ; bpl pv
    w(0x4484, 0x700A, 0x10C0, 0x5283)       # neg.l d4 ; moveq #10,d0 ; move.b d0,(a0)+ ; addq.l #1,d3
    a.label('pv')
    w(0x0C84); l(999); a.bcc(LS, 'pv2'); w(0x7800)   # Schutz: |Wert| > 999 -> 0
    a.label('pv2')
    w(0x7A00, 0x7000, 0x7264)               # moveq #0,d5 ; moveq #0,d0 ; moveq #100,d1
    a.label('h'); w(0xB881); a.bcc(LT, 'hd'); w(0x9881, 0x5280); a.bcc(BRA, 'h')
    a.label('hd'); w(0x4A80); a.bcc(EQ, 't0'); w(0x10C0, 0x5283, 0x7A01)
    a.label('t0'); w(0x7000, 0x720A)
    a.label('t'); w(0xB881); a.bcc(LT, 'td'); w(0x9881, 0x5280); a.bcc(BRA, 't')
    a.label('td'); w(0x4A85); a.bcc(NE, 'pt'); w(0x4A80); a.bcc(EQ, 'u')
    a.label('pt'); w(0x10C0, 0x5283)
    a.label('u'); w(0x10C4, 0x5283)
    a.label('u2')
    w(0x7441, 0x2003, 0xE588, 0x9480)       # moveq #65,d2 ; d2 -= 4*n
    w(0x41EB, BUF, 0x7C02, 0x7E15)          # lea BUF(a3),a0 ; moveq #2,d6 ; moveq #21,d7
    a.bcc(BSR, 'DS')
    a.label('done')
    w(0x4CD7, 0x0CFC, 0x4FEF, 0x0020)       # movem.l (sp),d2-d7/a2-a3 ; lea 32(sp),sp
    a.label('out')
    w(0x7000, 0x4E75)
    # ---------------- DS: a0 Zeichen, d3 Anzahl, d2 x, d7 y unten, d6 Massstab
    a.label('DS')
    w(0x7000, 0x1018, 0x2F08, 0xE588, 0x43F9); l(0); fix_f = len(a.b) - 4
    w(0x2A31, 0x0800)
    a.bcc(BSR, 'GL')
    w(0x205F, 0x2006, 0xE588, 0xD480, 0x5383); a.bcc(NE, 'DS')
    w(0x4E75)
    # ---------------- GL: d5 Zeichen, d2 x, d7 y unten, d6 Massstab
    a.label('GL')
    w(0x2F03, 0x2807, 0x7607)
    a.label('gr')
    w(0x0805, 0x0002); a.bcc(EQ, 'c1'); w(0x2002); a.bcc(BSR, 'BLK')
    a.label('c1')
    w(0x0805, 0x0001); a.bcc(EQ, 'c2'); w(0x2002, 0xD086); a.bcc(BSR, 'BLK')
    a.label('c2')
    w(0x0805, 0x0000); a.bcc(EQ, 'c3'); w(0x2002, 0xD086, 0xD086); a.bcc(BSR, 'BLK')
    a.label('c3')
    w(0xE68D, 0xD886, 0x5383); a.bcc(NE, 'gr')
    w(0x261F, 0x4E75)
    # ---------------- RECT: FILL(bmp, d2, d3, d4, d5, d6)
    a.label('RECT')
    w(0x2F06, 0x2F05, 0x2F04, 0x2F03, 0x2F02, 0x2F0A, 0x4EB9); l(FILL); w(0x4FEF, 0x0018, 0x4E75)
    # ---------------- BLK: d0 x, d4 y, d6 Massstab -> FILL(bmp, x, y, x+s-1, y+s-1, 1)
    a.label('BLK')
    w(0x4878, 0x0001)
    w(0x2204, 0xD286, 0x5381, 0x2F01)
    w(0x2200, 0xD286, 0x5381, 0x2F01)
    w(0x2F04, 0x2F00, 0x2F0A, 0x4EB9); l(FILL); w(0x4FEF, 0x0018, 0x4E75)
    code = bytearray(a.done()); check_cf(bytes(code), org)
    while len(code) % 4: code += b'\0'
    font = bytearray(struct.pack('>%dI' % len(FONT), *FONT)); font_at = font_org
    lt_at = font_org + len(font); font += bytes(8 * len(LABELS))
    for k in sorted(LABELS):
        txt = LABELS[k]; at = font_org + len(font); font += bytes(ORDER.index(c) for c in txt)
        o = lt_at - font_org + 8 * (k - 1); font[o:o + 8] = struct.pack('>Ihh', at, len(txt), LABEL_X[k])
    while len(font) % 4: font += b'\0'
    code[fix_f:fix_f + 4] = struct.pack('>I', font_at)
    code[fix_lt:fix_lt + 4] = struct.pack('>I', lt_at)
    lab = dict(a.lab); lab['FONT'] = font_at; lab['END'] = org + len(code)
    return bytes(code), bytes(font), lab


def build_keys(a, save_cont):
    """SETTINGS (Code 13) im Hauptbildschirm (0x4001c0d2, Fall 13 bei 0x4001c54c), in den Assembler a geschrieben:
    langes Halten speichert das Projekt nicht mehr sofort (sonst speichert jeder, der SETTINGS als Modifier etwas zu
    lange haelt), sondern merkt es (PEND); beim Loslassen ohne Drehung wird dann gespeichert statt das Menue zu oeffnen.
    Neues Druecken und jede SETTINGS-Geste (SP/SP2) loeschen PEND."""
    w, l = a.w, a.l32
    a.label('C13A')                         # statt move.l d3,-(a7) ; jsr BIT5 (0x4001c54c, 8 Bytes: jsr C13A ; nop)
    w(0x2043, 0x2028, 0x0010, 0x7209, 0xC081, 0x5380); a.bcc(NE, 'k1')    # erstes Druecken: (Flags & 9) == 1
    w(0x42B9); l(VARS + PEND)
    a.label('k1')
    w(0x205F); a.orig(K_HOOK_A, 2); w(0x2F08, 0x4EF9); l(K_BIT5)       # verschobener Originalbefehl, dann BIT5(ev)
    a.label('LS')                           # statt jsr SAVE beim langen Halten
    w(0x7001, 0x23C0); l(VARS + PEND); w(0x4E75)
    a.label('C13R')                         # statt pea $9c(a2) ; move.l a6,d2 (Loslassen ohne FUNC -> Menue)
    w(0x4AB9); l(VARS + PEND); a.bcc(EQ, 'kn')
    w(0x42B9); l(VARS + PEND)
    w(0x4878, 0x0020); a.orig(K_HOOK_L, 6); w(0x508F, 0x4EF9); l(save_cont)   # verschobener Aufruf: speichern, kein Menue
    a.label('kn')
    w(0x205F); a.orig(K_HOOK_R, 6); w(0x4ED0)   # verschobene Originalbefehle


FILL_F, FRAME_F, TXT_F = 0x40070DEA, 0x40070F6E, 0x40071A04
F_NAME, F_VAL = 0x40EA14D4, 0x40EA14E4        # Schrift der Parameternamen (0x4014120c) / grosse Ziffern (0x401429ec)
FMT_D, FMT_S = 0x4012A9EA, 0x40124B58
DMODE_B = 0x404E9B5C
NP_STR = {'strum': "Strum", 'groove': "Groove", 'humt': "Hum Time", 'humv': "Hum Vel", 'delay': "Delay", 'vib': "VIBDEL", 'cho': "CHODEL",
          'speed': "Speed", 'track': "Track", 'all': "All"}
GROOVE_NAMES = ["Swing", "Boom Bap", "Disco", "Reggae", "Bongo", "Caixixi", "Highlife", "Kuduro"]


def build_np(org, str_org):
    """NPD: Wert-Popup im Stil von ParameterPageView::draw (0x4001e40a): linke Haelfte gefuellt + Rahmen (0x40070f6e),
    rechte Haelfte geloescht, Name in Parameternamen-Schrift bei (32,47) und 2. Zeile bei (32,34), Wert bei (96,34)
    (Zahl: grosse Ziffern-Schrift; Groove-Name: Namen-Schrift), zuletzt linke Haelfte invertiert. a2 = Bitmap, a3 = VARS.
    Art 1 SPEED (Name nach Delay-Typ), 2 STRUM, 4 GROOVE (Wert = Index), 5 HUM TIME / 6 HUM VEL (Bit 8 = alle Tracks -> 'All').
    Unterprogramme TXN/RCT und die Texte liegen in der zweiten Maske (str_org)."""
    # ---- Unterprogramme in der Text-Maske
    u = A(str_org); w, l = u.w, u.l32
    u.label('TXN')                              # a0 Text, d1 y ; Namen-Schrift, x = 32, mittig
    w(0x2F08, 0x4878, 0x0002, 0x2F01, 0x4878, 32, 0x4879); l(F_NAME); w(0x2F0A, 0x4EB9); l(TXT_F); w(0x4FEF, 0x0018, 0x4E75)
    u.label('RCT')                              # FILL(bmp, d0..d3, d4 als Byte mit Vorzeichen)
    w(0x43F9); l(FILL_F)
    u.label('RCTA')                             # a1 = Funktion
    w(0x49C4, 0x2F04, 0x2F03, 0x2F02, 0x2F01, 0x2F00, 0x2F0A, 0x4E91, 0x4FEF, 0x0018, 0x4E75)
    sub = bytearray(u.done()); check_cf(bytes(sub), str_org); ul = dict(u.lab)
    while len(sub) % 4: sub += b'\0'
    a = A(org); w, l = a.w, a.l32
    fix = {}
    def lea_s(key):
        w(0x41F9); l(0); fix.setdefault(key, []).append(len(a.b) - 4)
    def rect(fn, x0, y0, x1, y1, col):
        w(0x7000 | x0, 0x7200 | y0, 0x7400 | x1, 0x7600 | y1, 0x7800 | (col & 0xFF))
        if fn == FILL_F: w(0x4EB9); l(ul['RCT'])
        else: w(0x43F9); l(fn); w(0x4EB9); l(ul['RCTA'])
    def txn(y): w(0x7200 | y, 0x4EB9); l(ul['TXN'])
    a.label('NPD')
    rect(FILL_F, 0, 0, 63, 63, 1); rect(FRAME_F, 0, 0, 63, 63, 0); rect(FILL_F, 64, 0, 127, 63, 0)
    w(0x2E2B, KIND, 0x2C2B, VAL)                # d7 = Art, d6 = Wert
    lea_s('strum'); w(0x7002, 0xBE80); a.bcc(EQ, 'n1')
    lea_s('groove'); w(0x7004, 0xBE80); a.bcc(EQ, 'n1')
    lea_s('humt'); w(0x7005, 0xBE80); a.bcc(EQ, 'n1')
    lea_s('humv'); w(0x7006, 0xBE80); a.bcc(EQ, 'n1')
    lea_s('delay'); w(0x7000, 0x1039); l(DMODE_B)
    w(0x7203, 0xB081); a.bcc(NE, 'nk'); lea_s('vib'); a.bcc(BRA, 'n1')
    a.label('nk'); w(0x7202, 0xB081); a.bcc(NE, 'n1'); lea_s('cho')
    a.label('n1'); txn(47)
    lea_s('speed'); w(0x7001, 0xBE80); a.bcc(EQ, 'n2')
    w(0x2007, 0x5B80, 0x7201, 0xB081); a.bcc(HI, 'vv')   # d0 = Art-5 ; d0 > 1 (vorzeichenlos): keine 2. Zeile
    lea_s('track'); w(0x0806, 0x0008); a.bcc(EQ, 'n2'); lea_s('all')
    a.label('n2'); txn(34)
    a.label('vv')
    w(0x7004, 0xBE80); a.bcc(NE, 'vn')
    w(0x2006, 0x7207, 0xC081, 0xE588); lea_s('gptr'); w(0x2F30, 0x0800)   # Groove-Name (Index & 7)
    w(0x4879); l(FMT_S); w(0x43F9); l(F_NAME); a.bcc(BRA, 'vt')
    a.label('vn')
    w(0x2006, 0x2207, 0x5B81, 0x7401, 0xB481); a.bcc(CS, 'vs'); w(0x0280); l(0xFF)   # Art 5/6: Wert & 0xFF
    a.label('vs')
    w(0x2F00, 0x4879); l(FMT_D); w(0x43F9); l(F_VAL)
    a.label('vt')
    w(0x4878, 0x0002, 0x4878, 34, 0x4878, 96, 0x2F09, 0x2F0A, 0x4EB9); l(TXT_F); w(0x4FEF, 0x001C)
    rect(FILL_F, 0, 0, 63, 63, -1)
    w(0x4E75)
    code = bytearray(a.done()); check_cf(bytes(code), org)
    while len(code) % 4: code += b'\0'
    sb = bytearray(sub); at = {}
    at['gptr'] = str_org + len(sb); sb += bytes(4 * len(GROOVE_NAMES)); gp = len(sb) - 4 * len(GROOVE_NAMES)
    for k, t in NP_STR.items():
        at[k] = str_org + len(sb); sb += t.encode() + b'\0'
    gaddr = []
    for t in GROOVE_NAMES:
        gaddr.append(str_org + len(sb)); sb += t.encode() + b'\0'
    sb[gp:gp + 4 * len(GROOVE_NAMES)] = struct.pack('>%dI' % len(GROOVE_NAMES), *gaddr)
    while len(sb) % 4: sb += b'\0'
    for k, offs in fix.items():
        for o in offs: code[o:o + 4] = struct.pack('>I', at[k])
    return bytes(code), bytes(sb), dict(a.lab, END=org + len(code))


def build_slow(org):
    a = A(org); w, l = a.w, a.l32
    # ---------------- SLOW (d4 Drehung, d5 Ziel) -> d0 = 1 umschalten / 0 verschlucken
    a.label('SLOW')
    w(0x41F9); l(ACC)
    w(0x2239); l(TIMER); w(0x2001, 0x90A8, 0x0008, 0x2141, 0x0008)
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
    code = bytearray(a.done()); check_cf(bytes(code), org)
    while len(code) % 4: code += b'\0'
    return bytes(code), dict(a.lab, END=org + len(code))


def render_py(kind, value):
    """Python-Gegenstueck: gesetzte Pixel (x, y) des Fensters (fuer den Test)."""
    x0, y0, x1, y1 = BOX
    px = set()
    for x in range(x0, x1 + 1): px.add((x, y0)); px.add((x, y1))
    for y in range(y0, y1 + 1): px.add((x0, y)); px.add((x1, y))
    def text(s, x, yb, sc):
        for c in s:
            g = glyph(c)
            for rr in range(7):
                bits = (g >> (3 * rr)) & 7
                for col in range(3):
                    if bits & (4 >> col):
                        for dx in range(sc):
                            for dy in range(sc): px.add((x + col * sc + dx, yb + rr * sc + dy))
            x += 4 * sc
    text(LABELS[kind], LABEL_X[kind], 37, 1)
    v = str(value); text(v, 65 - 4 * len(v), 21, 2)
    return px


if __name__ == "__main__":
    code, font, lab = build(0x4015C044, 0x4014AB5C, 0x40172608); c2, l2 = build_slow(0x4018DBA8); c3, s3, l3 = build_np(0x40172608, 0x40179730)
    print(len(code), len(font), len(c2), len(c3), len(s3), hex(lab['OVS']), hex(lab['OVT']), hex(l2['SLOW']))
