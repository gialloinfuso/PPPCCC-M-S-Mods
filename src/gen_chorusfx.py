#!/usr/bin/env python3
"""Tweak 'chorus-fx' v3 (Modded Cycles OS 2.0, Model:Samples): Stereo-Chorus als Alternative NUR fuer den Reverb-Platz.
Delay (inkl. Notenwerte) bleibt unveraendert. MODE = Byte 0x404e9b5d im gespeicherten Einstellungsblock (0 = Reverb, sonst Chorus).
Umschalten: Kandidaten-Taste (SETTINGS) halten + Reverb Size drehen (rechts = Chorus, links = Reverb).
Chorus-Ringpuffer im freien BSS-Rest 0x4a338100 (nicht genullt, wird beim ersten Chorus-Block per Magic-Wort geleert).
Haken: H 0x400081b8 (Encoder), R 0x401b7244 (jsr Reverb im Wrapper). Delay-Zeile wird nicht angefasst."""
import json, struct, sys, pathlib, hashlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from gen_solo import A, BASE, matches
import gen_chorus as gc

gc.STATE = 0x4A338100
MAGIC = 0x43484F52
M_CHORUS = gc.MASK                    # 0x40166760  Chorus-DSP (266 B)
M_UI = 0x4016616C                     # R (Reverb-Platz: Namen/Anzeige umstellen, Reverb oder Chorus)
M_DATA = 0x40163FB8                   # Daten (Zeilen, Tasten, Strings) + Anzeigefunktion F0
M_H = 0x401625BC                      # H (Encoder-Haken)
MODE2 = 0x404E9B5E                    # Ping-Pong-Delay: 0 = normal, sonst Ping-Pong
MODE = 0x404E9B5D                     # ungenutztes Byte im gespeicherten Einstellungsblock (COKI, CRC), Standardwert 0
SCRATCH = M_DATA + 0x100
COPY = 0x40044B88                     # Kopieren in den Einstellungsblock (ziel, quelle, laenge) inkl. neuer Pruefsumme
H_HOOK, R_HOOK = 0x400081B8, 0x401B7244
REVERB = 0x400579C4
HELD = 0x4007FAF4
DESC = lambda k: 0x4010DCE0 + 0x38 * k          # Deskriptor k; +0x2c Name, +0x34 Kurzname
OBJ = lambda k: 0x40A71754 + 100 * k            # Parameterobjekt k; Anzeigefunktion (Zeiger) bei +0x20
FN39, FN40 = OBJ(39) + 0x20, OBJ(40) + 0x20
F39_ORIG, F40_ORIG = 0x40045A68, 0x4004E00E     # Reverb Size: 1..127/INF ; Reverb Tone: Wert-64
SPRINTF, FMT_D = 0x40000E6E, 0x4012A9EA         # snprintf, "%d"
KEYS = [3, 6, 7, 9, 10, 11, 12, 13, 14, 15]    # Kandidaten fuer SETTINGS (nicht FUNC 1, TRACK 2, RETRIG 4, MACHINE 5, LFO 8)
STR = [b"Chorus Send\0", b"CHOS\0", b"Cho Speed\0", b"SPD\0", b"Cho Depth\0", b"DEP\0"]
BRA, BSR, HI, NE, EQ, PL, LE = 0x0, 0x1, 0x2, 0x6, 0x7, 0xA, 0xF
PP = True        # Geste auf Encoder 15 (Delay Time) -> MODE2 aktiv
PPMAX = 1        # hoechster Wert von MODE2
PPENC = 15       # Encoder der MODE2-Geste (15 Delay Time, 12 Swing)
PPKEYS = None    # (adresse) eigene Tastentabelle fuer die MODE2-Geste (0-terminiert); None = KEYS
PHASER = None    # (modus, adresse): Reverb-Platz springt in diesem Modus zum Phaser
EXTRA_MODES = []  # [(modus, adresse)]: weitere Reverb-Platz-Modi (1.13-Linie: Razer); leer = Code wie bisher
N_EXTRA = None   # Adresse eines Unterprogramms, das N zusaetzlich aufruft (Delay-Namen)
SWMASK = 3       # Maske fuer den SWTAB-Index
SWTAB = None     # (adresse) 4 x 8 B: Ersatz fuer den String 'Swing' (0x401266ea) je MODE2
G37 = None       # (tabelle, original): Name von Deskriptor 37 waehrend der Geste je MODE2
CMAX = 1         # hoechster Wert des Chorus-Bytes (0 = Reverb)
N_ADDR = None    # Adresse von N (wird in tweak gesetzt)
NAMES3 = False   # NAMETAB-Zeilen mit Send/Speed/Depth-Namen (24 B)
NAMETAB = None   # (adresse) Tabelle je Modus 1..4: [Name27, Kurz27]; None = fester Name

def data_blob(img):
    """Aufbau M_DATA: ROWS (2 x 8 Zeiger = 64 B), KEYS, Strings, F0 (Anzeige 0..127), SCRATCH bei +0x100.
    Zeile = [Name27, Kurz27, Name39, Kurz39, Name40, Kurz40, Fn39, Fn40]; Zeile 0 Original, Zeile 1 Chorus."""
    rd = lambda va: struct.unpack('>I', img[va - BASE:va - BASE + 4])[0]
    orig = [rd(DESC(27) + 0x2C), rd(DESC(27) + 0x34), rd(DESC(39) + 0x2C), rd(DESC(39) + 0x34),
            rd(DESC(40) + 0x2C), rd(DESC(40) + 0x34)]
    # Fn-Zeiger des Originals pruefen (Zielwerte gegen das Image: Deskriptor/Anzeige-Annahmen)
    keys_at = M_DATA + 64
    at = keys_at + len(KEYS) + 1
    adr = []
    for t in STR:
        adr.append(at); at += len(t)
    f0 = (at + 1) & ~1
    code = F0_code(f0)
    rows = struct.pack('>8I', *orig, F39_ORIG, F40_ORIG) + struct.pack('>8I', *adr, f0, f0)
    blob = rows + bytes(KEYS) + b'\0' + b''.join(STR)
    blob += bytes(f0 - M_DATA - len(blob)) + code
    assert len(blob) <= 0x100, len(blob)
    return blob, keys_at, f0

def F0_code(base):
    """Anzeige 'plain 0..127': formatter(ctx 4(a7), wert 8(a7), puffer 12(a7)) -> sprintf(puffer, "%d", wert>>8)"""
    a = A(base)
    a.w(0x202F, 0x0008)                     # move.l 8(a7),d0     Wert (8.8)
    a.w(0xE080)                             # asr.l #8,d0
    a.w(0x222F, 0x000C)                     # move.l 12(a7),d1    Puffer
    a.w(0x2F41, 0x0004)                     # move.l d1,4(a7)
    a.w(0x2F40, 0x000C)                     # move.l d0,12(a7)    Zahl
    a.w(0x203C); a.l32(FMT_D)               # move.l #"%d",d0
    a.w(0x2F40, 0x0008)                     # move.l d0,8(a7)
    a.w(0x4EF9); a.l32(SPRINTF)             # jmp sprintf
    c = a.done(); check_cf(c, base); return c

def check_cf(code, base):
    """ColdFire kennt nur Befehle bis 6 Byte; Unicorn und Capstone akzeptieren mehr -> hier pruefen."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'cap' / 'bindings' / 'python'))
    from capstone import Cs, CS_ARCH_M68K, CS_MODE_BIG_ENDIAN, CS_MODE_M68K_040
    cs = Cs(CS_ARCH_M68K, CS_MODE_BIG_ENDIAN | CS_MODE_M68K_040)
    i = 0
    while i < len(code):
        ins = next(cs.disasm(code[i:i + 12], base + i, 1), None)
        if ins is None: i += 2; continue
        assert ins.size <= 6, (hex(base + i), ins.mnemonic, ins.op_str, ins.size)
        i += ins.size

def build_r():
    """R (per jsr aus dem Wrapper): Namen/Anzeige setzen (Unterprogramm N, auch von H nach dem Umschalten benutzt),
    dann Reverb oder Chorus."""
    a = A(M_UI)
    w, l = a.w, a.l32
    a.label('R')
    a.bcc(BSR, 'N')                         # bsr.w N   Namen + Anzeigefunktionen
    w(0x41F9); l(MODE)                      # lea MODE,a0
    w(0x7390)                               # mvz.b (a0),d1
    w(0x4A81)                               # tst.l d1
    a.bcc(NE, 'Rc')
    w(0x4EF9); l(REVERB)                    # jmp Reverb
    a.label('Rc')
    if PHASER:
        w(0x0C81); l(PHASER[0])             # cmpi.l #Phaser-Modus,d1
        a.bcc(NE, 'rc2')
        w(0x4EF9); l(PHASER[1])             # jmp Phaser
        a.label('rc2')
    for _i, (_m, _ad) in enumerate(EXTRA_MODES):
        w(0x0C81); l(_m)                    # cmpi.l #Modus,d1
        a.bcc(NE, 'rx%d' % _i)
        w(0x4EF9); l(_ad)                   # jmp Effekt
        a.label('rx%d' % _i)
    w(0x41F9); l(gc.STATE + 8)              # lea STATE+8,a0
    w(0x2010)                               # move.l (a0),d0
    w(0x0C80); l(MAGIC)                     # cmpi.l #MAGIC,d0
    a.bcc(EQ, 'go')
    w(0x41F9); l(gc.STATE)                  # lea STATE,a0
    w(0x203C); l(2060)                      # move.l #2060,d0   (Zustand + Ring: 8240 Byte)
    a.label('cl')
    w(0x4298)                               # clr.l (a0)+
    w(0x5380)                               # subq.l #1,d0
    a.bcc(NE, 'cl')
    w(0x203C); l(MAGIC)                     # move.l #MAGIC,d0   (ColdFire: Befehle max. 6 Byte, kein move #imm,abs.l)
    w(0x41F9); l(gc.STATE + 8)              # lea STATE+8,a0
    w(0x2080)                               # move.l d0,(a0)
    a.label('go'); w(0x4EF9); l(gc.MASK)    # jmp Chorus
    # N: Namen + Anzeigefunktionen passend zu MODE (veraendert d0, d1, a0, a1)
    a.label('N')
    w(0x41F9); l(MODE)                      # lea MODE,a0
    w(0x7390)                               # mvz.b (a0),d1
    w(0x7000)                               # moveq #0,d0
    w(0x4A81)                               # tst.l d1
    a.bcc(EQ, 'r0')
    w(0x7020)                               # moveq #32,d0   Zeile 1
    a.label('r0')
    w(0x43F9); l(M_DATA)                    # lea ROWS,a1
    w(0xD3C0)                               # adda.l d0,a1
    w(0x41F9); l(DESC(27) + 0x2C)           # lea Deskriptor27+0x2c,a0
    w(0x2099)                               # move.l (a1)+,(a0)      Name
    w(0x2159, 0x0008)                       # move.l (a1)+,8(a0)     Kurzname
    w(0x41F9); l(DESC(39) + 0x2C)           # lea Deskriptor39+0x2c,a0
    w(0x7001)                               # moveq #1,d0
    a.label('nl')
    w(0x2099)                               # move.l (a1)+,(a0)
    w(0x2159, 0x0008)                       # move.l (a1)+,8(a0)
    w(0x41E8, 0x0038)                       # lea 0x38(a0),a0
    w(0x5380)                               # subq.l #1,d0
    a.bcc(PL, 'nl')
    w(0x23D9); l(FN39)                      # move.l (a1)+,FN39   Anzeigefunktion Size/Speed
    w(0x23D9); l(FN40)                      # move.l (a1)+,FN40   Anzeigefunktion Tone/Depth
    if NAMETAB:
        w(0x4A81)                           # tst.l d1
        a.bcc(EQ, 'nr')
        w(0x2001)                           # move.l d1,d0
        w(0x5380)                           # subq.l #1,d0
        w(0x0280); l(CMAX - 1 if CMAX in (2, 4) else 3)   # andi.l #mask,d0
        w(0xE788)                           # lsl.l #3,d0
        w(0x43F9); l(NAMETAB)               # lea NAMETAB,a1
        w(0xD3C0)                           # adda.l d0,a1
        if NAMES3:                          # Zeile 24 B: Send, Speed, Depth (je Name + Kurzname)
            w(0xD3C0, 0xD3C0)               # adda.l d0,a1 (x2)  -> 24*Index
        w(0x41F9); l(DESC(27) + 0x2C)       # lea Deskriptor27+0x2c,a0
        w(0x2099)                           # move.l (a1)+,(a0)
        w(0x2159, 0x0008)                   # move.l (a1)+,8(a0)
        if NAMES3:
            w(0x41F9); l(DESC(39) + 0x2C)   # lea Deskriptor39+0x2c,a0
            w(0x2099, 0x2159, 0x0008)       # Name, Kurzname
            w(0x41E8, 0x0038)               # lea 0x38(a0),a0    Deskriptor40
            w(0x2099, 0x2159, 0x0008)
        a.label('nr')
    if SWTAB:                               # String 'Swing' je Groove-Art (Popup 'Track / Swing', Swing-Menue)
        w(0x41F9); l(MODE2)                 # lea MODE2,a0
        w(0x7190)                           # mvz.b (a0),d0
        w(0x0280); l(SWMASK)                # andi.l #SWMASK,d0
        w(0xE788)                           # lsl.l #3,d0
        w(0x43F9); l(SWTAB)                 # lea SWTAB,a1
        w(0xD3C0)                           # adda.l d0,a1
        w(0x41F9); l(0x401266EA)            # lea 'Swing',a0
        w(0x20D9, 0x30D9)                   # move.l (a1)+,(a0)+ ; move.w (a1)+,(a0)+   (5 Zeichen + 0)
    if N_EXTRA:
        w(0x4EF9); l(N_EXTRA)               # jmp N_EXTRA (endet mit rts)
    w(0x4E75)                               # rts
    code = a.done()
    assert len(code) <= 280, len(code)
    check_cf(code, M_UI)
    return code, a.lab

def build_h(keys_at):
    a = A(M_H)
    w, l = a.w, a.l32
    # H: Encoder-Haken (per jsr; ersetzt 'mvs.b 8(a2),d1 ; move.l d1,-(a7)')
    a.label('H')
    w(0x4FEF, 0xFFF4)                       # lea -12(a7),a7   (ColdFire: kein movem -(a7))
    w(0x48D7, 0x0038)                       # movem.l d3-d5,(a7)
    w(0x7A00)                               # moveq #0,d5        (kein Ziel)
    w(0x792A, 0x0008)                       # mvs.b 8(a2),d4     Drehrichtung
    w(0x262A, 0x0004)                       # move.l 4(a2),d3    Reglernummer
    w(0x0C83); l(14)                        # cmpi.l #14,d3     Reverb Size -> Chorus-Byte
    a.bcc(NE, 'n1')
    w(0x2A3C); l(MODE)                      # move.l #MODE,d5
    w(0x7600 | CMAX)                        # moveq #CMAX,d3
    w(0x41F9); l(keys_at)                   # lea KEYS,a0
    a.bcc(BRA, 'go')
    a.label('n1')
    if PP:
        w(0x0C83); l(PPENC)                 # cmpi.l #PPENC,d3   -> MODE2-Byte
        a.bcc(NE, 'exit')
        w(0x2A3C); l(MODE2)                 # move.l #MODE2,d5
        w(0x7600 | PPMAX)                   # moveq #PPMAX,d3
        w(0x41F9); l(PPKEYS or keys_at)     # lea Tasten,a0
    else:
        a.bcc(BRA, 'exit')
    a.label('go')
    w(0x4A84)                               # tst.l d4
    a.bcc(EQ, 'exit')
    w(0x2248)                               # movea.l a0,a1      Tastentabelle des Ziels
    a.label('kl')
    w(0x7199)                               # mvz.b (a1)+,d0
    a.bcc(EQ, 'nokey' if G37 else 'exit')   # Tabellenende: keine Taste gehalten
    w(0x2F09)                               # move.l a1,-(a7)
    w(0x2F00)                               # move.l d0,-(a7)
    w(0x4EB9); l(HELD)                      # jsr held
    w(0x588F)                               # addq.l #4,a7
    w(0x225F)                               # movea.l (a7)+,a1
    w(0x4A80)                               # tst.l d0
    a.bcc(EQ, 'kl')
    # Geste aktiv: rechts -> +1, links -> -1, begrenzt auf 0..d3 (nur schreiben, wenn es sich aendert)
    w(0x2045)                               # movea.l d5,a0
    w(0x7190)                               # mvz.b (a0),d0
    w(0xB083)                               # cmp.l d3,d0
    a.bcc(LE, 'v')
    w(0x2003)                               # move.l d3,d0   (ungueltiger Wert -> Maximum)
    a.label('v')
    w(0x2200)                               # move.l d0,d1
    w(0x4A84)                               # tst.l d4
    a.bcc(LE, 'dec')
    w(0x5281)                               # addq.l #1,d1
    a.bcc(BRA, 'cl')
    a.label('dec')
    w(0x5381)                               # subq.l #1,d1
    a.label('cl')
    w(0x4A81)                               # tst.l d1
    a.bcc(PL, 'c1')
    w(0x7200)                               # moveq #0,d1
    a.label('c1')
    w(0xB283)                               # cmp.l d3,d1
    a.bcc(LE, 'c2')
    w(0x2203)                               # move.l d3,d1
    a.label('c2')
    w(0xB081)                               # cmp.l d1,d0
    a.bcc(EQ, 'swallow')
    w(0x13C1); l(SCRATCH)                   # move.b d1,SCRATCH
    w(0x4878, 0x0001)                       # pea 1.w            Laenge
    w(0x4879); l(SCRATCH)                   # pea SCRATCH        Quelle
    w(0x2F05)                               # move.l d5,-(a7)    Ziel (Einstellungsblock, CRC wird erneuert)
    w(0x4EB9); l(COPY)                      # jsr 0x40044b88
    w(0x4FEF, 0x000C)                       # lea 12(a7),a7
    if N_ADDR:
        w(0x4EB9); l(N_ADDR)                # jsr N   Namen sofort umstellen (Popup liest sie gleich danach)
    a.label('swallow')
    if G37:
        w(0x0C85); l(MODE2)                 # cmpi.l #MODE2,d5
        a.bcc(NE, 'sw2')
        w(0x41F9); l(MODE2)                 # lea MODE2,a0
        w(0x7190)                           # mvz.b (a0),d0
        w(0x0280); l(3)                     # andi.l #3,d0
        w(0xE588)                           # lsl.l #2,d0
        w(0x41F9); l(G37[0])                # lea G37TAB,a0
        w(0x2030, 0x0800)                   # move.l 0(a0,d0.l),d0
        w(0x23C0); l(DESC(37) + 0x2C)       # move.l d0,Deskriptor37.Name   (Popup zeigt den Groove)
        a.label('sw2')
    w(0x7800)                               # moveq #0,d4        Drehung verschlucken
    if G37:
        a.bcc(BRA, 'exit')
        a.label('nokey')                    # ohne Taste: Name von Delay Time wiederherstellen
        w(0x0C85); l(MODE2)                 # cmpi.l #MODE2,d5
        a.bcc(NE, 'exit')
        w(0x203C); l(G37[1])                # move.l #Original,d0
        w(0x23C0); l(DESC(37) + 0x2C)       # move.l d0,Deskriptor37.Name
    a.label('exit')
    w(0x2204)                               # move.l d4,d1
    w(0x4CD7, 0x0038)                       # movem.l (a7),d3-d5
    w(0x4FEF, 0x000C)                       # lea 12(a7),a7
    w(0x205F)                               # movea.l (a7)+,a0   Ruecksprung
    w(0x2F01)                               # move.l d1,-(a7)    (Originalbefehl)
    w(0x4ED0)                               # jmp (a0)
    code = a.done()
    assert len(code) <= 280, len(code)
    check_cf(code, M_H)
    return code, a.lab

def tweak(img):
    sw = lambda va, new: {"off": va - BASE, "old": img[va-BASE:va-BASE+len(new)].hex(), "new": new.hex()}
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "Modded-Cycles" / "tools"))
    import sprites
    jsr = lambda t: bytes.fromhex("4eb9") + struct.pack('>I', t)
    chorus = gc.build()
    blob, keys_at, f0 = data_blob(img)
    global N_ADDR
    ui, lab_r = build_r()
    N_ADDR = lab_r['N']
    h, lab_h = build_h(keys_at)
    assert matches(img, H_HOOK, (6, '9bb3f43c614c29728d69125a337d8aa2786eb191967f271dfb2a735504ba1f66'))   # OS 2.0
    assert matches(img, R_HOOK, (6, hashlib.sha256(jsr(REVERB)).hexdigest()))
    w = [sw(gc.MASK, chorus), sprites.redirect_write(gc.MASK),
         sw(M_UI, ui), sprites.redirect_write(M_UI),
         sw(M_H, h), sprites.redirect_write(M_H),
         sw(M_DATA, blob), sprites.redirect_write(M_DATA),
         sw(R_HOOK, jsr(lab_r['R'])), sw(H_HOOK, jsr(lab_h['H']))]
    w.sort(key=lambda x: x["off"])
    t = {"id": "chorus-fx", "order": 66, "name": "Stereo-Chorus als Reverb-Alternative (Prototyp)",
         "description": ["Chorus (Speed/Depth, 0..127, 'Chorus Send') statt Reverb; Taste halten + Reverb Size drehen schaltet um.",
                         "Erzeugt von gen_chorusfx.py."],
         "device": "Model:Cycles", "os": "2.0", "section": 3, "writes": w}
    return t, dict(chorus=chorus, ui=ui, h=h, lab_r=lab_r, lab_h=lab_h, blob=blob, keys_at=keys_at, f0=f0)

if __name__ == "__main__":
    img = open(sys.argv[1], 'rb').read()
    t, parts = tweak(img)
    pathlib.Path(sys.argv[2]).write_text(json.dumps(t, indent=1) + "\n")
    print("Chorus", len(parts['chorus']), "R", len(parts['ui']), "H", len(parts['h']), "Daten", len(parts['blob']),
          "R", hex(parts['lab_r']['R']), "H", hex(parts['lab_h']['H']), "F0", hex(parts['f0']))
    if len(sys.argv) > 3:
        out = bytearray(img)
        for x in t["writes"]:
            o = bytes.fromhex(x["old"]); assert out[x["off"]:x["off"]+len(o)] == o
            out[x["off"]:x["off"]+len(o)] = bytes.fromhex(x["new"])
        pathlib.Path(sys.argv[3]).write_bytes(bytes(out))
